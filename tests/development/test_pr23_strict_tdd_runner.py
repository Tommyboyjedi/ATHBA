"""Deterministic executable proof for the thin PR23 CLI runner."""
from __future__ import annotations

from dataclasses import replace
import json
import socket
import pytest
from pathlib import Path
import shutil
import subprocess
import tempfile

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.microcycle_revision_store import MicrocycleRevisionRepository
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_lifecycle_evidence import StrictTddLifecycleEventKind, StrictTddLifecycleEventRepository, StrictTddLifecycleRunContext
from core.development.strict_tdd_live_run_composition import StrictTddLiveRunCompositionFactory
from core.development.strict_tdd_run_reporting import StrictTddEvidenceRepositories, StrictTddRunEvidenceSnapshotCollector, StrictTddRunReportWriter
from core.development.strict_tdd_run_store import StrictTddRunStateRepository
from core.execution.reasoning_gateway import ReasoningResult
from core.execution.work_unit_gateway import ExecutionPolicyEvidence, WorkUnitExecutionResult
from scripts.run_pr23_strict_tdd_feature import main, parse

from core.execution.rack_ai_cli_gateway import RackAiCliExecutionGateway
REQUIREMENT = "Build a small in-memory ToggleSwitch. It can be instantiated, begins in the off state, and calling toggle changes it to the on state."

class Reasoning:
    def __init__(self, log): self.log, self.call_count = log, 0
    async def reason(self, request):
        self.call_count += 1; self.log.append(request)

        values = {
            "athba_source_requirement_clauses": {"clauses":[{"ref":"SRC-1","text":"Instantiate ToggleSwitch.","kind":"behavior"},{"ref":"SRC-2","text":"New switch is off.","kind":"behavior"},{"ref":"SRC-3","text":"toggle makes switch on.","kind":"behavior"}]},
            "athba_behavior_contract": contract(),
            "athba_specification_checklist": {"items":[{"ref":"CHK-1","text":"A ToggleSwitch is created off and toggled on.","kind":"behavior"}]},
            "athba_scenario_intent_review": {"disposition":"approved","feedback":"scenario observes every behavior","evidence_refs":["SRC-1","SRC-2","SRC-3"]},
            "athba_senior_behavior_review": {"verdict":"approved","rationale":"canonical scenario is green","findings":[],"evidence_refs":["SRC-1","SRC-2","SRC-3"]},
            "athba_checklist_test_reconciliation": {"answer":"YES","selected_test_names":["tests/test_toggle_switch.py::test_B_1"],"rationale":"accepted final test proves it"}}
        if request.purpose not in values: raise AssertionError(request.purpose)
        return ReasoningResult(json.dumps(values[request.purpose]), provider="deterministic", model="fake")

class GitGateway:
    def __init__(self, root, log): self.root, self.log, self.call_count = root, log, 0
    async def execute(self, unit, binding):
        self.call_count += 1
        objective, role = json.loads(unit.objective), json.loads(unit.objective)["role"]
        self.log.append((role, unit.id, tuple(unit.allowed_paths), binding.base_ref, binding.base_sha, objective))
        assert binding.base_sha and binding.base_ref
        assert unit.allowed_paths == (["tests/test_toggle_switch.py"] if role == "Tester" else ["toggle_switch.py"])
        worktree = Path(tempfile.mkdtemp(prefix="athba-runner-")); worktree.rmdir()
        git(self.root, "worktree", "add", "--detach", str(worktree), binding.base_sha)
        try:
            if role == "Tester":
                target = worktree / "tests/test_toggle_switch.py"; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(scenario(), encoding="utf-8")
            else:
                (worktree / "toggle_switch.py").write_text(implementation(objective["materialised_active_frontier_test"]), encoding="utf-8")
            git(worktree, "add", "--", *unit.allowed_paths)
            changed = tuple(git(worktree, "diff", "--cached", "--name-only").splitlines())
            assert changed and all(path in unit.allowed_paths for path in changed)
            git(worktree, "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "--no-verify", "-m", unit.id)
            return WorkUnitExecutionResult(unit.id, True, "checks_passed", accepted_revision=git(worktree, "rev-parse", "HEAD"), evidence_location=f"fake/{unit.id}", policy_evidence=ExecutionPolicyEvidence(unit.allowed_paths, unit.allowed_paths))
        finally:
            subprocess.run(["git","worktree","remove","--force",str(worktree)], cwd=self.root, capture_output=True, text=True, check=False); shutil.rmtree(worktree, ignore_errors=True)

class ObservedApplication:
    def __init__(self, app, reasoning, counts): self.app, self.reasoning, self.counts, self.transitions = app, reasoning, counts, []
    def __getattr__(self, name): return getattr(self.app, name)
    async def advance(self, request):
        before = self.reasoning.call_count; result = await self.app.advance(request); self.transitions.append(result); after = self.reasoning.call_count
        if getattr(result, "deterministic_regression_invoked", False): self.counts.append((before, after))
        return result

class Factory:
    def __init__(self, log, counts): self.log, self.counts, self.reasoners, self.gateways, self.applications = log, counts, [], [], []
    def build(self, request):
        config = request.configuration
        reasoning = Reasoning(self.log); gateway = GitGateway(config.state_root / "projects" / config.workload_id / "repository", self.gateways)
        self.reasoners.append(reasoning); self.gateways.append(gateway)
        composition = StrictTddLiveRunCompositionFactory().build(replace(request, configuration=replace(config, athba_revision="athba-deterministic", rack_ai_revision="rack-deterministic"), reasoning_gateway=reasoning, execution_gateway=gateway))
        application = ObservedApplication(composition.controller.application, reasoning, self.counts)
        composition.controller.application = application
        self.applications.append(application)
        return composition

def test_parser_accepts_start_and_resume():
    for mode in ("start", "resume"):
        assert parse(args(mode, Path("/tmp/state"), Path("/tmp/evidence"))).mode.value == mode

def test_cli_happy_path_checkpoints_restarts_completes_and_replays(tmp_path, capsys):
    state, evidence, log, counts = tmp_path/"state", tmp_path/"evidence", [], []
    first = Factory(log, counts)
    assert main(args("start", state, evidence), first) == 0
    assert json.loads(capsys.readouterr().out)["checkpoint_reached"] == "first_regression_clear"
    assert StrictTddRunStateRepository(state/"runs").load("toggle-run").reached_checkpoints
    repository = state/"projects/toggle-project/repository"
    scenario_id = next(item.scenario_id for item in first.applications[0].transitions if item.scenario_id)
    microcycles = MicrocycleStateRepo(state / "microcycles")
    checkpoint_state = microcycles.load(scenario_id)
    assert checkpoint_state is not None
    checkpoint_frontier_index = checkpoint_state.frontier.index
    checkpoint_developer_attempts = tuple(
        item for item in checkpoint_state.developer_attempts
        if item.frontier_index == checkpoint_frontier_index
    )
    checkpoint_frontier_counts = tuple(
        item for item in checkpoint_state.frontier_attempt_counts
        if item.frontier_index == checkpoint_frontier_index
    )
    assert checkpoint_developer_attempts and checkpoint_frontier_counts
    checkpoint_work_units = tuple(item for item in log if isinstance(item, tuple))
    context = StrictTddLifecycleRunContext("toggle-run","toggle-project",REQUIREMENT,"athba-deterministic","rack-deterministic")
    checkpoint_events = StrictTddLifecycleEventRepository(state/"lifecycle-events").events(context)
    checkpoint_event_facts = {
        (item.event_kind, item.candidate_revision)
        for item in checkpoint_events
        if item.event_kind in {
            StrictTddLifecycleEventKind.DEVELOPER_COMPLETED,
            StrictTddLifecycleEventKind.REGRESSION_COMPLETED,
            StrictTddLifecycleEventKind.CANONICAL_BASE_PROMOTED,
        }
    }
    assert "toggle_switch.py" in git(repository, "show", "--name-only", "--format=", git(repository, "rev-parse", "refs/heads/main"))
    del first
    resumed = Factory(log, counts)
    assert main(args("resume", state, evidence), resumed) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "completed"
    assert subprocess.run(["/srv/ATHBA/.venv/bin/python","-m","pytest","-q"], cwd=repository, capture_output=True, text=True, timeout=15).returncode == 0
    resumed_state = microcycles.load(scenario_id)
    assert resumed_state is not None
    assert tuple(
        item for item in resumed_state.developer_attempts
        if item.frontier_index == checkpoint_frontier_index
    ) == checkpoint_developer_attempts
    assert tuple(
        item for item in resumed_state.frontier_attempt_counts
        if item.frontier_index == checkpoint_frontier_index
    ) == checkpoint_frontier_counts
    resumed_work_units = tuple(item for item in log if isinstance(item, tuple))[len(checkpoint_work_units):]
    assert not ({item[1] for item in checkpoint_work_units} & {item[1] for item in resumed_work_units})
    resumed_events = StrictTddLifecycleEventRepository(state/"lifecycle-events").events(context)[len(checkpoint_events):]
    overlap = (
        checkpoint_event_facts
        & {(item.event_kind, item.candidate_revision) for item in resumed_events}
    )
    assert not overlap, overlap
    planner = next(x for x in log if getattr(x, "purpose", None) == "athba_behavior_contract")
    gatekeeper = next(x for x in log if getattr(x, "purpose", None) == "athba_specification_checklist")
    assert REQUIREMENT in planner.prompt and '"items"' not in planner.prompt and REQUIREMENT in gatekeeper.prompt
    assert counts and all(before == after for before, after in counts)
    context = StrictTddLifecycleRunContext("toggle-run","toggle-project",REQUIREMENT,"athba-deterministic","rack-deterministic")
    kinds = [x.event_kind for x in StrictTddLifecycleEventRepository(state/"lifecycle-events").events(context)]
    assert kinds.index(StrictTddLifecycleEventKind.RUN_STARTED) < kinds.index(StrictTddLifecycleEventKind.CONTROLLED_CHECKPOINT_STOP)
    assert kinds.index(StrictTddLifecycleEventKind.RUN_RESUMED) < kinds.index(StrictTddLifecycleEventKind.RUN_COMPLETED)
    assert kinds.count(StrictTddLifecycleEventKind.RUN_COMPLETED) == 1
    report = json.loads(Path(regenerate(state, evidence).structured).read_text(encoding="utf-8"))
    sections = report["sections"]
    replay = Factory([], [])
    assert main(args("resume", state, evidence), replay) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "completed"
    assert replay.reasoners[0].call_count == replay.gateways[0].call_count == 0

def args(mode, state, evidence):
    return [mode,"--run-id","toggle-run","--project-id","toggle-project","--requirement",REQUIREMENT,"--language","python","--test-framework","pytest","--production-path","toggle_switch.py","--test-path","tests/test_toggle_switch.py","--state-root",str(state),"--evidence-root",str(evidence),"--stop-after","first_regression_clear"]

def contract():
    return {"id":"contract-toggle-switch","project_id":"toggle-project","component_name":"ToggleSwitch","capability":"Toggle in-memory state.","requirement_source":REQUIREMENT,"source_clauses":[{"ref":"SRC-1","text":"Instantiate ToggleSwitch.","kind":"behavior"},{"ref":"SRC-2","text":"New switch is off.","kind":"behavior"},{"ref":"SRC-3","text":"toggle makes switch on.","kind":"behavior"}],"observable_requirements":[{"ref":"B-1","source_refs":["SRC-1","SRC-2","SRC-3"],"summary":"Create an off ToggleSwitch and toggle it on.","observable_outcome":"A new switch is off and is on after toggle.","test_hint":"test_toggle_switch","error_expectation":"none","preserves_state_on_failure":False}],"invariants":[],"production_paths":["toggle_switch.py"],"test_paths":["tests/test_toggle_switch.py"],"public_api":["ToggleSwitch()","toggle()","is_on"],"error_semantics":[],"non_goals":["no persistence"],"completion_criteria":["accepted executable proof"],"status":"tdd_ready"}

def scenario():
    return """# ATHBA-SCENARIO-RATIONALE: observable in-memory state transition
# ATHBA-SOURCE-REFS: SRC-1, SRC-2, SRC-3
from toggle_switch import ToggleSwitch

def test_B_1():
    switch = ToggleSwitch()
    assert switch.is_on is False
    switch.toggle()
    assert switch.is_on is True
"""

def implementation(source):
    if "switch.toggle()" in source: return "class ToggleSwitch:\n    def __init__(self):\n        self.is_on = False\n\n    def toggle(self):\n        self.is_on = True\n"
    if "assert switch.is_on is False" in source: return "class ToggleSwitch:\n    def __init__(self):\n        self.is_on = False\n"
    if "switch = ToggleSwitch()" in source: return "class ToggleSwitch:\n    def __init__(self):\n        self.is_on = True\n"
    return "class ToggleSwitch:\n    def __init__(self):\n        self.is_on = True\n"

def regenerate(state, evidence):
    run = StrictTddRunStateRepository(state/"runs").load("toggle-run"); assert run is not None
    lifecycle = StrictTddLifecycleEventRepository(state/"lifecycle-events")
    repositories = StrictTddEvidenceRepositories(StrictTddFeatureRepository(state/"features"),ScenarioDraftStateRepo(state/"scenario-drafts"),MicrocycleStateRepo(state/"microcycles"),MicrocycleRevisionRepository(state/"revisions"),lifecycle)
    context = StrictTddLifecycleRunContext("toggle-run","toggle-project",REQUIREMENT,"athba-deterministic","rack-deterministic")
    return StrictTddRunReportWriter(evidence).write("toggle-run", StrictTddRunEvidenceSnapshotCollector(repositories).collect(context, run))

def git(root, *arguments):
    value = subprocess.run(["git",*arguments],cwd=root,capture_output=True,text=True,check=False)
    if value.returncode: raise AssertionError(value.stderr or value.stdout)
    return value.stdout.strip()


@pytest.fixture(autouse=True)
def prevent_live_boundaries(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("deterministic runner proof must not contact a live boundary")

    async def forbidden_execution(*_args, **_kwargs):
        raise AssertionError("deterministic runner proof must not invoke Rack AI")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(RackAiCliExecutionGateway, "execute", forbidden_execution)

