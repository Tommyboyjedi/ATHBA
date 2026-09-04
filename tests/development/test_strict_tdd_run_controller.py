from __future__ import annotations

from dataclasses import replace
import ast
from pathlib import Path

import pytest

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.microcycle_revision_store import MicrocycleRevisionRepository
from core.development.strict_tdd_feature_domain import StrictTddFeatureResult
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_lifecycle_evidence import StrictTddLifecycleEventKind, StrictTddLifecycleEventRepository, StrictTddLifecycleRunContext
from core.development.strict_tdd_run_controller import StrictTddReceiptDeliveryError, StrictTddRunController, StrictTddRunControllerDependencies
from core.development.strict_tdd_run_domain import StrictTddRunControllerConfig, StrictTddRunMode, StrictTddRunRequest, StrictTddRunState, StrictTddRunStatus
from core.development.strict_tdd_run_reporting import StrictTddEvidenceRepositories, StrictTddRunEvidenceSnapshotCollector, StrictTddRunReportWriter
from core.development.strict_tdd_run_store import StrictTddRunStateRepository
from core.development.strict_tdd_transition_provenance import StrictTddCheckpoint
from core.development.strict_tdd_transitions import FeatureAdvanceResult, FeatureTransitionKind, MicrocycleTransitionKind, ScenarioTransitionKind, StrictTddTransitionPath, TransitionFingerprint


class DummyStates:
    def load(self, project_id):
        return None


class DummyApplication:
    def __init__(self, transitions):
        self.states = DummyStates()
        self.transitions = list(transitions)
        self.calls = 0

    async def advance(self, request):
        self.calls += 1
        result = self.transitions.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FailingLifecycle(StrictTddLifecycleEventRepository):
    def __init__(self, root):
        super().__init__(root)
        self.fail_application_event = True

    def append(self, request):
        if self.fail_application_event and request.event.event_kind == StrictTddLifecycleEventKind.FRONTIER_RED_ACCEPTED:
            self.fail_application_event = False
            raise OSError("event store unavailable")
        return super().append(request)


def request(mode=StrictTddRunMode.START):
    return StrictTddRunRequest("run-one", "project-one", "increment value", "python", "pytest", ("value.py",), ("tests/test_value.py",), "state", "evidence", mode, StrictTddCheckpoint.RED_FRONTIER_ACCEPTED, "athba", "rack", StrictTddRunControllerConfig(3))


def transition(kind=MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED, available=True):
    path = StrictTddTransitionPath(FeatureTransitionKind.SCENARIO_ADVANCED, ScenarioTransitionKind.MICROCYCLE_ADVANCED, kind)
    result = StrictTddFeatureResult("project-one", "", "running", "refs/heads/main", "a" * 40, "refs/heads/work", "b" * 40, "scenario-one", (), None, (), ("evidence://one",))
    return FeatureAdvanceResult(FeatureTransitionKind.SCENARIO_ADVANCED, "running", "running", "project-one", "B-1", "scenario-one", "refs/heads/main", "a" * 40, "refs/heads/work", "b" * 40, ("evidence://one",), False, False, False, available, None, TransitionFingerprint("running", "B-1", "scenario-one", 0, "a" * 40, "b" * 40, (0,), "advance"), result, None, path)


def controller(tmp_path, transitions, lifecycle=None):
    events = lifecycle or StrictTddLifecycleEventRepository(tmp_path / "lifecycle")
    repositories = StrictTddEvidenceRepositories(StrictTddFeatureRepository(tmp_path / "features"), ScenarioDraftStateRepo(tmp_path / "scenarios"), MicrocycleStateRepo(tmp_path / "microcycles"), MicrocycleRevisionRepository(tmp_path / "revisions"), events)
    return StrictTddRunController(StrictTddRunControllerDependencies(DummyApplication(transitions),  # type: ignore[arg-type]
         StrictTddRunStateRepository(tmp_path / "runs"), events, StrictTddRunEvidenceSnapshotCollector(repositories), StrictTddRunReportWriter(tmp_path / "reports")))


@pytest.mark.asyncio
async def test_start_persists_then_projects_exact_transition_and_checkpoint(tmp_path):
    value = controller(tmp_path, [transition()])
    result = await value.advance(request())
    assert result.status == StrictTddRunStatus.CHECKPOINTED
    assert value.application.calls == 1
    events = value.lifecycle.events(StrictTddLifecycleRunContext("run-one", "project-one", "increment value", "athba", "rack"))
    assert [item.event_kind for item in events] == [StrictTddLifecycleEventKind.RUN_STARTED, StrictTddLifecycleEventKind.FRONTIER_RED_ACCEPTED, StrictTddLifecycleEventKind.CONTROLLED_CHECKPOINT_STOP]
    persisted = value.states.load("run-one")
    assert persisted is not None and persisted.pending_transition_receipt is None


@pytest.mark.asyncio
async def test_failed_event_delivery_replays_receipt_without_application_call(tmp_path):
    lifecycle = FailingLifecycle(tmp_path / "lifecycle")
    value = controller(tmp_path, [transition()], lifecycle)
    with pytest.raises(StrictTddReceiptDeliveryError):
        await value.advance(request())
    state = value.states.load("run-one")
    assert state is not None and state.pending_transition_receipt is not None
    resumed = await value.advance(request(StrictTddRunMode.RESUME))
    assert resumed.status == StrictTddRunStatus.CHECKPOINTED
    assert value.application.calls == 1


@pytest.mark.asyncio
async def test_application_exception_clears_observed_inflight_marker_for_resume(tmp_path):
    value = controller(tmp_path, [OSError("bootstrap unavailable"), transition()])

    with pytest.raises(OSError, match="bootstrap unavailable"):
        await value.advance(request())

    state = value.states.load("run-one")
    assert state is not None
    assert state.transition_in_flight is None
    assert state.pending_transition_receipt is None
    assert state.reason == "application_transition_exception_before_receipt"

    resumed = await value.advance(request(StrictTddRunMode.RESUME))
    assert resumed.status == StrictTddRunStatus.CHECKPOINTED
    assert value.application.calls == 2


@pytest.mark.asyncio
async def test_inflight_without_receipt_fails_closed(tmp_path):
    value = controller(tmp_path, [])
    state = StrictTddRunState("run-one", "project-one", request().immutable_identity_hash, StrictTddRunStatus.RUNNING, transition_in_flight=__import__("core.development.strict_tdd_run_domain", fromlist=["StrictTddTransitionInFlight"]).StrictTddTransitionInFlight(1))
    value.states.save(state)
    result = await value.advance(request(StrictTddRunMode.RESUME))
    assert result.status == StrictTddRunStatus.RECOVERY_REQUIRED
    assert value.application.calls == 0


def test_controller_is_not_a_feature_router_or_live_executor():
    source = Path("core/development/strict_tdd_run_controller.py").read_text()
    tree = ast.parse(source)
    assert tree.body
    assert ".application.run(" not in source
    assert "subprocess" not in source
    assert "pytest" not in source
    assert "git" not in source.lower()

@pytest.mark.asyncio
async def test_durable_nested_progress_with_same_path_does_not_stall(tmp_path):
    first = transition()
    second = replace(first, fingerprint=replace(first.fingerprint, retry_counts=(1,), pending_action="scenario_intent_review"))
    value = controller(tmp_path, [first, second])

    started = await value.advance(replace(request(), requested_checkpoint=None))
    resumed = await value.advance(replace(request(StrictTddRunMode.RESUME), requested_checkpoint=None))

    assert started.status == StrictTddRunStatus.RUNNING
    assert resumed.status == StrictTddRunStatus.RUNNING
    assert resumed.reason is None


@pytest.mark.asyncio
async def test_identical_nested_state_with_same_path_still_stalls(tmp_path):
    first = transition()
    value = controller(tmp_path, [first, first])

    await value.advance(replace(request(), requested_checkpoint=None))
    repeated = await value.advance(replace(request(StrictTddRunMode.RESUME), requested_checkpoint=None))

    assert repeated.status == StrictTddRunStatus.STALLED
    assert repeated.reason == "stable_transition_fingerprint_stalled"
