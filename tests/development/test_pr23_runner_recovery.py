"""Executable failure and recovery proof for the PR23 thin runner."""
from __future__ import annotations

import ast
import socket
import json
from dataclasses import replace
from pathlib import Path

import pytest

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.microcycle_revision_store import MicrocycleRevisionRepository
from core.execution.rack_ai_cli_gateway import RackAiCliExecutionGateway
from core.development.strict_tdd_feature_domain import StrictTddFeatureResult
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_lifecycle_evidence import StrictTddLifecycleEventKind, StrictTddLifecycleEventRepository, StrictTddLifecycleRunContext
from core.development.strict_tdd_live_run_composition import StrictTddLiveRunComposition
from core.development.strict_tdd_run_controller import StrictTddRunController, StrictTddRunControllerDependencies
from core.development.strict_tdd_run_domain import StrictTddRunControllerConfig, StrictTddRunMode, StrictTddRunRequest, StrictTddRunState, StrictTddRunStatus, StrictTddTransitionInFlight
from core.development.strict_tdd_run_reporting import StrictTddEvidenceRepositories, StrictTddRunEvidenceSnapshotCollector, StrictTddRunReportWriter
from core.development.strict_tdd_run_store import StrictTddRunStateRepository
from core.development.strict_tdd_transitions import FeatureAdvanceResult, FeatureTransitionKind, StrictTddTransitionPath, TransitionFingerprint
from scripts.run_pr23_strict_tdd_feature import StrictTddRunnerExitCode, main

REQUIREMENT = "A deterministic durable runner transition."
ATHBA_REVISION = "athba-deterministic"
RACK_REVISION = "rack-deterministic"

class States:
    def load(self, project_id): return None

class Application:
    def __init__(self, transitions):
        self.states, self.transitions, self.calls = States(), list(transitions), 0
    async def advance(self, request):
        self.calls += 1
        return self.transitions.pop(0)

class PersistThenFailLifecycle(StrictTddLifecycleEventRepository):
    def __init__(self, root):
        super().__init__(root)
        self.fail = True
    def append(self, request):
        event = super().append(request)
        if self.fail and request.event.event_kind != StrictTddLifecycleEventKind.RUN_STARTED:
            self.fail = False
            raise OSError("simulated lifecycle delivery failure")
        return event

class Factory:
    def __init__(self, transitions, failing=False):
        self.transitions, self.failing, self.applications = transitions, failing, []
    def build(self, request):
        root = request.configuration.state_root
        lifecycle = PersistThenFailLifecycle(root / "lifecycle-events") if self.failing else StrictTddLifecycleEventRepository(root / "lifecycle-events")
        app = Application(self.transitions)
        self.applications.append(app)
        repositories = StrictTddEvidenceRepositories(StrictTddFeatureRepository(root / "features"), ScenarioDraftStateRepo(root / "scenario-drafts"), MicrocycleStateRepo(root / "microcycles"), MicrocycleRevisionRepository(root / "revisions"), lifecycle)
        controller = StrictTddRunController(StrictTddRunControllerDependencies(app, StrictTddRunStateRepository(root / "runs"), lifecycle, StrictTddRunEvidenceSnapshotCollector(repositories), StrictTddRunReportWriter(request.configuration.evidence_root)))
        return StrictTddLiveRunComposition(controller, ATHBA_REVISION, RACK_REVISION)

def transition(completed=False, marker=""):
    kind = FeatureTransitionKind.FEATURE_COMPLETED if completed else FeatureTransitionKind.PROJECT_LOADED
    path = StrictTddTransitionPath(kind, None, None)
    status = ("completed" if completed else "running") + marker
    result = StrictTddFeatureResult("recovery-project", "", status, "refs/heads/main", "a" * 40, None, None, None, (), None, (), ())
    return FeatureAdvanceResult(kind, status, status, "recovery-project", None, None, "refs/heads/main", "a" * 40, None, None, (), False, False, False, not completed, None, TransitionFingerprint(status, None, None, None, "a" * 40, None, (), status), result, None, path)

def args(mode, state, evidence):
    return [mode, "--run-id", "recovery-run", "--project-id", "recovery-project", "--requirement", REQUIREMENT, "--language", "python", "--test-framework", "pytest", "--production-path", "value.py", "--test-path", "tests/test_value.py", "--state-root", str(state), "--evidence-root", str(evidence)]

def test_receipt_replay_uses_existing_event_id_and_sequence_before_new_application_advance(tmp_path, capsys):
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    first = Factory([transition()], failing=True)
    assert main(args("start", state, evidence), first) == StrictTddRunnerExitCode.RECEIPT_DELIVERY_FAILED
    assert json.loads(capsys.readouterr().out)["status"] == "receipt_delivery_failed"
    saved = StrictTddRunStateRepository(state / "runs").load("recovery-run")
    assert saved is not None and saved.pending_transition_receipt is not None
    context = StrictTddLifecycleRunContext("recovery-run", "recovery-project", REQUIREMENT, ATHBA_REVISION, RACK_REVISION)
    before = StrictTddLifecycleEventRepository(state / "lifecycle-events").events(context)
    application_event = next(event for event in before if event.event_kind != StrictTddLifecycleEventKind.RUN_STARTED)
    assert (evidence / "recovery-run" / "proof-report.json").exists()
    resumed = Factory([transition(completed=True)])
    assert main(args("resume", state, evidence), resumed) == 0
    capsys.readouterr()
    after = StrictTddLifecycleEventRepository(state / "lifecycle-events").events(context)
    replayed = [event for event in after if event.event_id == application_event.event_id]
    assert len(replayed) == 1 and replayed[0].sequence_number == application_event.sequence_number
    assert resumed.applications[0].calls == 1

def test_inflight_without_receipt_is_recovery_required_without_application_advance(tmp_path, capsys):
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    request = StrictTddRunRequest("recovery-run", "recovery-project", REQUIREMENT, "python", "pytest", ("value.py",), ("tests/test_value.py",), state.name, evidence.name, StrictTddRunMode.RESUME, None, ATHBA_REVISION, RACK_REVISION, StrictTddRunControllerConfig(100))
    StrictTddRunStateRepository(state / "runs").save(StrictTddRunState(request.run_id, request.project_id, request.immutable_identity_hash, StrictTddRunStatus.RUNNING, transition_in_flight=StrictTddTransitionInFlight(1)))
    factory = Factory([])
    assert main(args("resume", state, evidence), factory) == StrictTddRunnerExitCode.RECOVERY_REQUIRED
    assert json.loads(capsys.readouterr().out)["status"] == "recovery_required"
    assert factory.applications[0].calls == 0
    assert Path(StrictTddRunStateRepository(state / "runs").load("recovery-run").structured_report_path).exists()

@pytest.fixture(autouse=True)
def prevent_live_boundaries(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("deterministic runner proof must not contact a live boundary")

    async def forbidden_execution(*_args, **_kwargs):
        raise AssertionError("deterministic runner proof must not invoke Rack AI")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(RackAiCliExecutionGateway, "execute", forbidden_execution)


def test_runner_script_has_only_typed_composition_dependencies():
    script = Path(__file__).parents[2] / "scripts" / "run_pr23_strict_tdd_feature.py"
    text = script.read_text(encoding="utf-8")
    tree = ast.parse(text)
    forbidden = {
        "subprocess", "StrictMicrocycleService", "ScenarioDraftingService",
        "DeterministicRegressionService", "BehaviorRepairService",
        "RackAiCliExecutionGateway", "WorkUnit",
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert not (forbidden & names)
    assert "subprocess" not in imports
    assert "git" not in text.lower()

@pytest.mark.parametrize("extra", [["--requirement-file", "missing"], ["--run-id", "../unsafe"], ["--project-id", "../unsafe"], ["--production-path", ""], ["--test-path", ""], ["--language", "ruby"], ["--stop-after", "invalid"]])
def test_invalid_cli_input_does_not_create_run_state(tmp_path, extra):
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    values = args("start", state, evidence) + extra
    assert main(values, Factory([])) == StrictTddRunnerExitCode.INVALID_INPUT
    assert not (state / "runs").exists()



@pytest.mark.parametrize(
    "values",
    [
        lambda state, evidence: [item for item in args("start", state, evidence) if item not in {"--requirement", REQUIREMENT}],
        lambda state, evidence: args("resume", state, evidence)[:2] + ["unknown-run"] + args("resume", state, evidence)[3:],
    ],
)
def test_missing_requirement_or_unknown_resume_does_not_create_run_state(tmp_path, values):
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    assert main(values(state, evidence), Factory([])) == StrictTddRunnerExitCode.INVALID_INPUT
    assert not (state / "runs").exists()


def test_blocked_and_transition_limit_results_write_reports(tmp_path, capsys):
    state, evidence = tmp_path / "blocked-state", tmp_path / "blocked-evidence"
    initial = transition()
    blocked = replace(
        initial,
        kind=FeatureTransitionKind.BLOCKED,
        resulting_status="blocked",
        transition_path=StrictTddTransitionPath(FeatureTransitionKind.BLOCKED, None, None),
    )
    assert main(args("start", state, evidence), Factory([blocked])) == StrictTddRunnerExitCode.BLOCKED
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"
    assert Path(StrictTddRunStateRepository(state / "runs").load("recovery-run").structured_report_path).exists()

    state, evidence = tmp_path / "limited-state", tmp_path / "limited-evidence"
    factory = Factory([transition(marker=f"-{item}") for item in range(100)])
    assert main(args("start", state, evidence), factory) == StrictTddRunnerExitCode.TRANSITION_LIMIT_REACHED
    assert json.loads(capsys.readouterr().out)["status"] == "transition_limit_reached"
    assert Path(StrictTddRunStateRepository(state / "runs").load("recovery-run").structured_report_path).exists()
