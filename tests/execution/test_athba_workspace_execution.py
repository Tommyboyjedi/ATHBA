from __future__ import annotations

import pytest

from core.development.athba_workspace_routing import AthbaExecutionProfile, AthbaExecutionProfileResolver, AthbaProfileResolutionRequest, AthbaModelWorkKind, AthbaOutboundPriority, AthbaWorkspaceIdentity, GenericModelCapability, WorkspaceComplexity
from core.development.workspace_attempt_policy import WorkspaceAttemptPolicy, WorkspaceAttemptState, WorkspaceAttemptTier, WorkspaceSubmissionRecord
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.fake_workspace_execution_port import DeterministicFakeWorkspacePort, FakeWorkspaceOutcome
from core.execution.profiled_workspace_gateway import ProfiledWorkspaceExecutionGateway, ProfiledWorkspaceGatewayDependencies
from core.execution.rack_ai_request import RepositoryBinding
from core.execution.rack_ai_workspace_connector import RackAiWorkspaceConnector
from core.execution.workspace_execution_port import WorkspaceExecutionRequest, WorkspaceExecutionStatus


def resolver():
    return AthbaExecutionProfileResolver()


def binding():
    return RepositoryBinding("repo", "main", "a" * 40, environment_resources=["python"])


def request(priority=AthbaOutboundPriority.MEDIUM):
    profile = AthbaExecutionProfile(frozenset({GenericModelCapability.CODING}), WorkspaceComplexity.SMALL, False, priority, 300)
    return WorkspaceExecutionRequest(AthbaWorkspaceIdentity("work", "submission", "submission"), profile, binding(), ("src/a.py",), "disabled", (("python", "-m", "pytest"),), ("src/a.py",), "bounded objective")


def unit(kind=AthbaModelWorkKind.FRONTIER_IMPLEMENTATION):
    return DevelopmentWorkUnit("submission", "project", "work", "objective", ["src/a.py"], AcceptanceContract([["python", "-m", "pytest"]]), timeout_seconds=300, model_work_kind=kind, workspace_identity=AthbaWorkspaceIdentity("work", "submission", "submission"), status=WorkUnitStatus.READY)


def test_scenario_profiles_are_reasoning_and_coding_medium_priority_medium():
    for kind in (AthbaModelWorkKind.COMPLETE_SCENARIO_AUTHORING, AthbaModelWorkKind.SCENARIO_REPAIR):
        profile = resolver().resolve(AthbaProfileResolutionRequest(kind, 300))
        assert profile.required_capabilities == {GenericModelCapability.REASONING, GenericModelCapability.CODING}
        assert profile.complexity == WorkspaceComplexity.MEDIUM
        assert profile.priority == AthbaOutboundPriority.MEDIUM


def test_frontier_profiles_are_coding_small_without_historical_worker_identity():
    profile = resolver().resolve(AthbaProfileResolutionRequest(AthbaModelWorkKind.FRONTIER_IMPLEMENTATION, 300))
    assert profile.required_capabilities == {GenericModelCapability.CODING}
    assert profile.complexity == WorkspaceComplexity.SMALL
    assert profile.priority == AthbaOutboundPriority.LOW
    assert "worker" not in str(profile).lower()


def test_stronger_frontier_profile_is_reasoning_coding_medium():
    profile = resolver().resolve(AthbaProfileResolutionRequest(AthbaModelWorkKind.STRONGER_FRONTIER_FALLBACK, 300))
    assert profile.required_capabilities == {GenericModelCapability.REASONING, GenericModelCapability.CODING}
    assert profile.complexity == WorkspaceComplexity.MEDIUM
    assert profile.priority == AthbaOutboundPriority.MEDIUM


def test_deterministic_and_reasoning_only_stages_do_not_produce_workspace_profiles():
    assert resolver().resolve(AthbaProfileResolutionRequest(AthbaModelWorkKind.BEHAVIOR_PLANNING, 300)) is None
    assert resolver().resolve(AthbaProfileResolutionRequest(AthbaModelWorkKind.SCENARIO_INTENT_REVIEW, 300)) is None


def test_athba_priority_has_only_low_and_medium():
    assert {item.value for item in AthbaOutboundPriority} == {"low", "medium"}
    with pytest.raises(ValueError):
        AthbaOutboundPriority("high")
    with pytest.raises(ValueError):
        AthbaOutboundPriority("paramount")


def test_request_wire_has_no_athba_stage_or_concrete_resource_identity():
    wire = request().to_wire()
    assert "work_kind" not in wire
    assert not {"worker_id", "model_id", "gpu_id", "jcode_profile"} & set(wire)
    assert wire["capabilities"] == ["coding"]


def test_fake_replays_same_submission_idempotently():
    port = DeterministicFakeWorkspacePort([FakeWorkspaceOutcome(WorkspaceExecutionStatus.ACCEPTED, "b" * 40)])
    first = port.submit_workspace_change(request())
    second = port.submit_workspace_change(request())
    assert first == second
    assert len(port.submitted) == 1


def test_fake_exposes_external_blockers_without_model_attempt_semantics():
    port = DeterministicFakeWorkspacePort([FakeWorkspaceOutcome(WorkspaceExecutionStatus.CAPABILITY_UNAVAILABLE)])
    result = port.submit_workspace_change(request())
    assert result.is_external_blocker()
    assert not result.is_model_originated()


@pytest.mark.asyncio
async def test_profiled_gateway_migrates_frontier_work_to_generic_port():
    port = DeterministicFakeWorkspacePort([FakeWorkspaceOutcome(WorkspaceExecutionStatus.ACCEPTED, "c" * 40, evidence_refs=("evidence",))])
    gateway = ProfiledWorkspaceExecutionGateway(ProfiledWorkspaceGatewayDependencies(port, resolver()))
    result = await gateway.execute(unit(), binding())
    assert result.accepted
    assert port.submitted[0].profile.required_capabilities == {GenericModelCapability.CODING}
    assert port.submitted[0].identity.work_id == "work"
    assert port.submitted[0].identity.submission_id == "submission"


def test_tier_policy_escalates_once_then_blocks_after_four_more_failures():
    policy = WorkspaceAttemptPolicy()
    state = WorkspaceAttemptState("work", base_ref="main", base_sha="a" * 40, allowed_paths=("src/a.py",), active_frontier="frontier")
    for number in range(1, 5):
        state = policy.record_model_failure(state, WorkspaceSubmissionRecord(f"tier1-{number}", True))
    assert state.tier == WorkspaceAttemptTier.TIER_TWO
    assert state.tier_one_submissions == 4
    assert state.global_submission_sequence == 4
    for number in range(1, 5):
        state = policy.record_model_failure(state, WorkspaceSubmissionRecord(f"tier2-{number}", True))
    assert state.tier == WorkspaceAttemptTier.CAPABILITY_BLOCKED
    assert state.tier_two_submissions == 4
    assert not policy.can_submit(state)


def test_tier_policy_does_not_consume_attempt_for_external_blocker_or_duplicate():
    policy = WorkspaceAttemptPolicy()
    state = WorkspaceAttemptState("work")
    unchanged = policy.record_external_blocker(state)
    once = policy.record_model_failure(unchanged, WorkspaceSubmissionRecord("one", True, "candidate"))
    duplicate = policy.record_model_failure(once, WorkspaceSubmissionRecord("one", True, "candidate"))
    assert unchanged == state
    assert once.tier_one_submissions == 1
    assert duplicate == once


def test_connector_fails_closed_on_selection_execution_mismatch():
    class Transport:
        def submit(self, payload):
            return {"submission_id": payload["submission_id"], "status": "accepted", "selected_worker_id": "selected", "executed_worker_id": "other"}
    result = RackAiWorkspaceConnector(Transport()).submit_workspace_change(request())
    assert result.status == WorkspaceExecutionStatus.SELECTION_EXECUTION_MISMATCH
