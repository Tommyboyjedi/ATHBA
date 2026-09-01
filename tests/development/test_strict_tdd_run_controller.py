from pathlib import Path
import pytest
from core.development.strict_tdd_feature_domain import StrictTddFeatureResult
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_lifecycle_evidence import StrictTddLifecycleEventRepository
from core.development.strict_tdd_run_controller import StrictTddCheckpoint,StrictTddRunController,StrictTddRunControllerDependencies,StrictTddRunMode,StrictTddRunRequest,StrictTddRunStatus

class Application:
 def __init__(self,status="completed",evidence=()):self.status=status;self.evidence=evidence;self.calls=0
 async def run(self,request):
  self.calls+=1
  return StrictTddFeatureResult(request.project_id,"/tmp/project",self.status,"refs/heads/main","a"*40,None,None,None,(),None,({"answer":"YES"},) if self.status=="completed" else (),self.evidence)

def request(root,mode=StrictTddRunMode.START,checkpoint=None):
 return StrictTddRunRequest("run-one","project-one","Widget value is one.","python","pytest",("widget.py",),("tests/test_widget.py",),root/"state",root/"evidence",mode,"athba-sha","rack-sha",checkpoint)

def controller(root,application):
 return StrictTddRunController(StrictTddRunControllerDependencies(application,StrictTddFeatureRepository(root/"state/features"),StrictTddLifecycleEventRepository(root/"state/events")))

@pytest.mark.asyncio
async def test_start_writes_events_and_reports(tmp_path):
 app=Application();result=await controller(tmp_path,app).run(request(tmp_path))
 assert result.status is StrictTddRunStatus.COMPLETED
 assert result.structured_report_path.exists() and result.markdown_report_path.exists()
 assert app.calls==1

@pytest.mark.asyncio
async def test_start_rejects_existing_run(tmp_path):
 value=controller(tmp_path,Application());await value.run(request(tmp_path))
 with pytest.raises(ValueError,match="existing"):await value.run(request(tmp_path))

@pytest.mark.asyncio
async def test_checkpoint_requires_persisted_application_marker(tmp_path):
 result=await controller(tmp_path,Application("blocked",("checkpoint:first_regression_clear_frontier",))).run(request(tmp_path,checkpoint=StrictTddCheckpoint.FIRST_REGRESSION_CLEAR_FRONTIER))
 assert result.status is StrictTddRunStatus.CHECKPOINTED
 assert result.checkpoint_reached is StrictTddCheckpoint.FIRST_REGRESSION_CLEAR_FRONTIER
