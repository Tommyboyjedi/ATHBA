"""Crash-boundary regression for an already published, validated synchronization."""
from dataclasses import replace
from pathlib import Path

import pytest

from core.atomic_json_file import read_json_file
from core.delivery_management.branch_environment import BranchEnvironment, BranchEnvironmentBinding
from core.delivery_management.checkpoint import CheckpointBinding, CheckpointDependencies, ManagedCheckpoint
from core.delivery_management.domain import DeliveryPhase, ManagementRequest, MergeStatus
from core.delivery_management.evidence import AcceptedContribution, ContributionKind
from core.delivery_management.store import RecordIdentity
from core.development.feature_management_checkpoint import (
    FeatureCheckpointRequest, management_checkpoint, management_resume_available,
)
from core.development.strict_tdd_feature_application_advance import _result_for
from core.development.strict_tdd_feature_domain import (
    CompletedBehaviorReference, StrictTddFeatureState,
)
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_run_domain import (
    StrictTddRunMode, StrictTddRunState, StrictTddRunStatus, StrictTddTransitionInFlight,
)
from core.development.strict_tdd_transitions import FeatureTransitionKind
from tests.development.test_strict_tdd_run_controller import controller, request
from tests.test_team_merge_management import ControlledObservation, managed


@pytest.mark.asyncio
async def test_controller_replays_published_sync_after_crash_before_feature_save(tmp_path, monkeypatch):
    fixture = managed(tmp_path / "application")
    fixture.delivery(ControlledObservation("first"))
    second = fixture.delivery(ControlledObservation("second"))
    fixture.publish(fixture.prepare("first"))
    key = RecordIdentity("application", second.id)
    token = "controlled-worker"
    fixture.store.save_delivery(replace(second, phase=DeliveryPhase.RUNNING,
        worker_token=token, pending_sync=True,
        pending_sync_revision=fixture.environment.repo.load("application").trusted_base_sha))
    environment = BranchEnvironment(BranchEnvironmentBinding(fixture.environment, fixture.store, key))
    state = StrictTddFeatureState("application", second.behavior.source_sha256, "running",
        canonical_ref=second.branch_ref, canonical_development_base=second.trusted_revision,
        behavioral_entry_revision=second.fork_revision, delivery_identity=second.id,
        completed_behaviors=(CompletedBehaviorReference("REQ001", second.id + "--REQ001",
            second.trusted_revision, ("controlled-accepted-checkpoint",)),))
    states = StrictTddFeatureRepository(Path(second.state_root) / "features")
    states.save(state)
    original = AcceptedContribution.from_dict(read_json_file(Path(second.authority_file)))
    loads = []
    def checkpoint_authority(_request):
        loads.append(_request)
        return replace(original, kind=ContributionKind.CHECKPOINT)
    checkpoint = ManagedCheckpoint(CheckpointDependencies(
        fixture.store, fixture.service, checkpoint_authority),
        CheckpointBinding(key, token, environment))
    published = await checkpoint.synchronize(FeatureCheckpointRequest("application", state))
    assert published is not None
    assert states.load("application") == state  # Process stopped before the feature-save boundary.
    current = fixture.store.delivery(key)
    assert current.trusted_revision == published.revision and not current.pending_sync
    operation_count = len(fixture.store.merges("application"))
    def no_merge_replay(_request):
        raise AssertionError("an accepted synchronization must not merge or validate again")
    monkeypatch.setattr(fixture.service, "synchronize_checkpoint", no_merge_replay)

    class Application:
        def __init__(self):
            self.states = states
            self.calls = 0

        async def advance(self, _request):
            self.calls += 1
            updated = await management_checkpoint(checkpoint, (environment, self.states.load("application")))
            self.states.save(updated)
            return _result_for(FeatureTransitionKind.BEHAVIOR_RECORDED, updated,
                environment.repo.load("application"))

    value = controller(tmp_path / "controller", [])
    value.application = Application()
    value.management_resume = lambda project_id: management_resume_available(checkpoint, states.load(project_id))
    resumed = replace(request(StrictTddRunMode.RESUME), project_id="application",
        source_requirement=second.behavior.source, requested_checkpoint=None)
    value.states.save(StrictTddRunState(resumed.run_id, "application",
        resumed.immutable_identity_hash, StrictTddRunStatus.RUNNING,
        transition_in_flight=StrictTddTransitionInFlight(1)))
    result = await value.advance(resumed)
    assert result.status == StrictTddRunStatus.RUNNING
    assert value.application.calls == 1 and len(loads) == 1
    saved = states.load("application")
    assert saved.canonical_development_base == published.revision
    assert saved.completed_behaviors == state.completed_behaviors
    assert saved.completed_behaviors[0].canonical_revision == second.trusted_revision
    assert len(fixture.store.merges("application")) == operation_count
    assert value.states.load(resumed.run_id).transition_in_flight is None
    # Once rebound, the same receipt cannot authorize replay of an unrelated uncertain call.
    assert not value.management_resume("application")
