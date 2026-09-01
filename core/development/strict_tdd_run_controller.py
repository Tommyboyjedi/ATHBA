from __future__ import annotations
from dataclasses import asdict,dataclass,replace
from enum import Enum
from hashlib import sha256
from pathlib import Path
import re
from core.atomic_json_file import read_json_file,write_json_atomically
from core.development.strict_tdd_feature_application import StrictTddFeatureApplicationService
from core.development.strict_tdd_feature_domain import StrictTddFeatureRequest,StrictTddFeatureResult
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_lifecycle_evidence import LifecycleEventDraft,PersistingLifecycleEventSinkDependencies,PersistingStrictTddLifecycleEventSink,StrictTddLifecycleEvent,StrictTddLifecycleEventKind,StrictTddLifecycleEventRepository,StrictTddLifecycleRunContext,StrictTddLifecycleStatus,StrictTddProofReportBuilder,StrictTddProofReportInput
_SAFE=re.compile(r"[A-Za-z0-9_-]{1,128}\Z");MAX_PROCESS_TRANSITIONS=8
class StrictTddRunMode(str,Enum): START="start";RESUME="resume"
class StrictTddRunStatus(str,Enum): RUNNING="running";CHECKPOINTED="checkpointed";BLOCKED="blocked";COMPLETED="completed";STALLED="stalled";TRANSITION_LIMIT="transition_limit"
class StrictTddCheckpoint(str,Enum): FRONTIER_RED_ACCEPTED="frontier_red_accepted";FIRST_REGRESSION_CLEAR_FRONTIER="first_regression_clear_frontier";SCENARIO_COMPLETED_BEFORE_REVIEW="scenario_completed_before_review"
@dataclass(frozen=True)
class StrictTddRunRequest:
 run_id:str;project_id:str;source_requirement:str;language_id:str;test_framework:str;production_paths:tuple[str,...];test_paths:tuple[str,...];state_root:Path;evidence_root:Path;mode:StrictTddRunMode;athba_revision:str;rack_ai_revision:str;stop_after_checkpoint:StrictTddCheckpoint|None=None
 def __post_init__(self):
  if not _SAFE.fullmatch(self.run_id) or not _SAFE.fullmatch(self.project_id):raise ValueError("run and project ids must be safe")
  if not all(isinstance(x,str) and x.strip() for x in (self.source_requirement,self.language_id,self.test_framework,self.athba_revision,self.rack_ai_revision,*self.production_paths,*self.test_paths)):raise ValueError("run fields must be non-empty")
@dataclass(frozen=True)
class StrictTddRunState:
 run_id:str;project_id:str;source_hash:str;status:StrictTddRunStatus;transition_count:int=0;checkpoint:StrictTddCheckpoint|None=None;blocked_reason:str|None=None;last_result:dict[str,object]|None=None
 def to_dict(self):
  v=asdict(self);v["status"]=self.status.value;v["checkpoint"]=None if self.checkpoint is None else self.checkpoint.value;return v
 @classmethod
 def from_dict(cls,v):
  p=v.get("checkpoint");return cls(str(v["run_id"]),str(v["project_id"]),str(v["source_hash"]),StrictTddRunStatus(str(v["status"])),int(v["transition_count"]),None if p is None else StrictTddCheckpoint(str(p)),v.get("blocked_reason"),v.get("last_result"))
class StrictTddRunRepository:
 def __init__(self,root):self.root=Path(root).resolve()
 def load(self,run):
  p=self._path(run);return None if not p.exists() else StrictTddRunState.from_dict(read_json_file(p))
 def save(self,state):write_json_atomically(self._path(state.run_id),state.to_dict())
 def _path(self,run):return self.root/"strict-tdd-runs"/f"{sha256(run.encode()).hexdigest()}.json"
@dataclass(frozen=True)
class StrictTddRunResult:
 run_id:str;project_id:str;status:StrictTddRunStatus;application_result:StrictTddFeatureResult|None;canonical_ref:str|None;canonical_revision:str|None;working_ref:str|None;working_revision:str|None;last_lifecycle_event:StrictTddLifecycleEvent|None;checkpoint_reached:StrictTddCheckpoint|None;blocked_reason:str|None;structured_report_path:Path;markdown_report_path:Path;final_reconciliation:tuple[dict[str,object],...]=()
@dataclass(frozen=True)
class StrictTddRunControllerDependencies:
 application:StrictTddFeatureApplicationService;feature_states:StrictTddFeatureRepository;lifecycle_events:StrictTddLifecycleEventRepository;reports:StrictTddProofReportBuilder=StrictTddProofReportBuilder()
@dataclass(frozen=True)
class StrictTddRunFinalization:
 request:StrictTddRunRequest;repository:StrictTddRunRepository;state:StrictTddRunState;application_result:StrictTddFeatureResult|None;event_kind:StrictTddLifecycleEventKind
class StrictTddRunController:
 def __init__(self,d):self.application=d.application;self.features=d.feature_states;self.events=d.lifecycle_events;self.reports=d.reports
 async def run(self,r):
  repo=StrictTddRunRepository(r.state_root);old=repo.load(r.run_id);self._validate(r,old);state=old or StrictTddRunState(r.run_id,r.project_id,_hash(r),StrictTddRunStatus.RUNNING)
  if state.transition_count>=MAX_PROCESS_TRANSITIONS:return self._finish(StrictTddRunFinalization(r,repo,replace(state,status=StrictTddRunStatus.TRANSITION_LIMIT,blocked_reason="process transition safety guard reached"),None,StrictTddLifecycleEventKind.RUN_BLOCKED))
  sink=_sink(r,self.events);_event(sink,StrictTddLifecycleEventKind.RUN_RESUMED if old else StrictTddLifecycleEventKind.RUN_STARTED,StrictTddLifecycleStatus.STARTED,"durable run state");repo.save(state);out=await self.application.run(_feature(r));_application_events(sink,out)
  checkpoint=_checkpoint(r,out)
  if checkpoint:return self._finish(StrictTddRunFinalization(r,repo,replace(state,status=StrictTddRunStatus.CHECKPOINTED,transition_count=state.transition_count+1,checkpoint=checkpoint,last_result=asdict(out)),out,StrictTddLifecycleEventKind.CONTROLLED_CHECKPOINT_STOP))
  if out.current_status=="completed":return self._finish(StrictTddRunFinalization(r,repo,replace(state,status=StrictTddRunStatus.COMPLETED,transition_count=state.transition_count+1,last_result=asdict(out)),out,StrictTddLifecycleEventKind.RUN_COMPLETED))
  value=asdict(out);same=state.last_result==value;return self._finish(StrictTddRunFinalization(r,repo,replace(state,status=StrictTddRunStatus.STALLED if same else StrictTddRunStatus.BLOCKED,transition_count=state.transition_count+1,blocked_reason="identical persisted application result" if same else out.blocked_reason or out.current_status,last_result=value),out,StrictTddLifecycleEventKind.RUN_BLOCKED))
 def _validate(self,r,state):
  feature=self.features.load(r.project_id)
  if r.mode is StrictTddRunMode.START:
   if state or feature:raise ValueError("start rejects existing run or feature state")
  else:
   if state is None:raise ValueError("resume requires persisted run state")
   if (state.project_id,state.source_hash)!=(r.project_id,_hash(r)):raise ValueError("resume identity differs from persisted run")
   if feature is None or feature.source_requirement_hash!=_feature(r).source_requirement_hash:raise ValueError("resume requires matching feature state")
 def _finish(self,value):
  r,repo,state,out,kind=value.request,value.repository,value.state,value.application_result,value.event_kind;repo.save(state);sink=_sink(r,self.events);status=StrictTddLifecycleStatus.CHECKPOINTED if kind is StrictTddLifecycleEventKind.CONTROLLED_CHECKPOINT_STOP else StrictTddLifecycleStatus.COMPLETED if kind is StrictTddLifecycleEventKind.RUN_COMPLETED else StrictTddLifecycleStatus.BLOCKED;event=_event(sink,kind,status,state.blocked_reason or state.status.value);structured,markdown=_report(r,self.events,self.features,self.reports);return StrictTddRunResult(r.run_id,r.project_id,state.status,out,None if out is None else out.canonical_ref,None if out is None else out.canonical_development_base,None if out is None else out.working_ref,None if out is None else out.working_revision,event,state.checkpoint,state.blocked_reason,structured,markdown,() if out is None else out.final_reconciliation)
def _hash(r):return sha256(r.source_requirement.encode()).hexdigest()
def _context(r):return StrictTddLifecycleRunContext(r.run_id,r.project_id,r.source_requirement,r.athba_revision,r.rack_ai_revision)
def _sink(r,e):return PersistingStrictTddLifecycleEventSink(PersistingLifecycleEventSinkDependencies(e,_context(r)))
def _feature(r):return StrictTddFeatureRequest(r.project_id,r.source_requirement,r.language_id,r.test_framework,r.production_paths,r.test_paths,"run-controller","resume",None,str(r.evidence_root))
def _event(sink,k,status,message):return sink.record(LifecycleEventDraft(f"{k.value}-{sink.repository.next_sequence(sink.context)}",k,status,(f"controller:{k.value}",),message=message))
def _application_events(s,o):
 for k in (StrictTddLifecycleEventKind.PROJECT_LOADED,StrictTddLifecycleEventKind.BEHAVIOR_CONTRACT_COMPLETED,StrictTddLifecycleEventKind.GATEKEEPER_COMPLETED):_event(s,k,StrictTddLifecycleStatus.COMPLETED,"durable application state")
 if o.current_status=="completed":_event(s,StrictTddLifecycleEventKind.RECONCILIATION_COMPLETED,StrictTddLifecycleStatus.COMPLETED,"durable final reconciliation")
def _checkpoint(r,o):
 m=None if r.stop_after_checkpoint is None else f"checkpoint:{r.stop_after_checkpoint.value}";return r.stop_after_checkpoint if m and m in o.evidence_refs else None
def _report(r,events,features,builder):
 context=_context(r);report=builder.build(StrictTddProofReportInput(context,features.load(r.project_id),(),(),events.events(context)));root=r.evidence_root/r.run_id;root.mkdir(parents=True,exist_ok=True);a,b=root/"report.json",root/"report.md";write_json_atomically(a,report.structured);b.write_text(report.markdown,encoding="utf-8");return a,b
