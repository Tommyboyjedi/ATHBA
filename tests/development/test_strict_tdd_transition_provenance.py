from dataclasses import replace
import ast
from pathlib import Path

import pytest

from core.development.strict_tdd_feature_domain import StrictTddFeatureResult
from core.development.strict_tdd_lifecycle_evidence import StrictTddLifecycleEventKind, StrictTddLifecycleRunContext
from core.development.strict_tdd_transition_provenance import (
    StrictTddCheckpoint,
    StrictTddCheckpointPolicy,
    StrictTddCheckpointRequest,
    StrictTddTerminalDisposition,
    StrictTddTerminalPolicy,
    StrictTddTerminalPolicyRequest,
    StrictTddTransitionEventProjector,
    StrictTddTransitionProjectionRequest,
)
from core.development.strict_tdd_transitions import (
    FeatureAdvanceResult,
    FeatureTransitionKind,
    MicrocycleTransitionKind,
    ScenarioTransitionKind,
    StrictTddTransitionPath,
    TransitionFingerprint,
)


def _context():
    return StrictTddLifecycleRunContext(
        "run-provenance", "project", "Feature requirement", "athba", "rack"
    )


def _transition(path, *, available=True, blocker=None, evidence=()):
    result = StrictTddFeatureResult(
        "project", "/project", "running", "refs/heads/main", "a" * 40,
        "refs/heads/work", "b" * 40, "scenario", (), blocker, (), evidence,
    )
    return FeatureAdvanceResult(
        path.feature_kind, "before", "after", "project", "B-1", "scenario",
        "refs/heads/main", "a" * 40, "refs/heads/work", "b" * 40, evidence,
        False, False, False, available, blocker,
        TransitionFingerprint("after", "B-1", "scenario", 2, "a" * 40, "b" * 40, (1,), "advance"),
        result, "c" * 40, path,
    )


@pytest.mark.parametrize(
    "path",
    [
        StrictTddTransitionPath(FeatureTransitionKind.PROJECT_LOADED),
        StrictTddTransitionPath(FeatureTransitionKind.SCENARIO_ADVANCED, ScenarioTransitionKind.DRAFT_CANDIDATE_SUBMITTED),
        StrictTddTransitionPath(FeatureTransitionKind.SCENARIO_ADVANCED, ScenarioTransitionKind.MICROCYCLE_ADVANCED, MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED),
        StrictTddTransitionPath(FeatureTransitionKind.BLOCKED, ScenarioTransitionKind.BLOCKED),
    ],
)
def test_transition_path_accepts_only_explicitly_valid_nesting(path):
    assert path.feature_kind


@pytest.mark.parametrize(
    "feature,scenario,microcycle",
    [
        (FeatureTransitionKind.PROJECT_LOADED, ScenarioTransitionKind.DRAFT_CANDIDATE_SUBMITTED, None),
        (FeatureTransitionKind.BEHAVIOR_RECORDED, ScenarioTransitionKind.SCENARIO_COMPLETED, None),
        (FeatureTransitionKind.SCENARIO_ADVANCED, None, MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED),
        (FeatureTransitionKind.SCENARIO_ADVANCED, ScenarioTransitionKind.MICROCYCLE_ADVANCED, None),
        (FeatureTransitionKind.FEATURE_COMPLETED, ScenarioTransitionKind.SCENARIO_COMPLETED, None),
    ],
)
def test_transition_path_rejects_impossible_nesting(feature, scenario, microcycle):
    with pytest.raises(ValueError):
        StrictTddTransitionPath(feature, scenario, microcycle)


@pytest.mark.parametrize(
    "microcycle,previous,expected",
    [
        (MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED, frozenset(), StrictTddCheckpoint.RED_FRONTIER_ACCEPTED),
        (MicrocycleTransitionKind.CANONICAL_BASE_PROMOTED, frozenset(), StrictTddCheckpoint.FIRST_REGRESSION_CLEAR),
        (MicrocycleTransitionKind.CANONICAL_BASE_PROMOTED, frozenset({StrictTddCheckpoint.FIRST_REGRESSION_CLEAR}), None),
        (MicrocycleTransitionKind.SCENARIO_COMPLETED, frozenset(), StrictTddCheckpoint.SCENARIO_READY_FOR_REVIEW),
        (MicrocycleTransitionKind.GREEN_VERIFIED, frozenset(), None),
    ],
)
def test_checkpoint_policy_uses_typed_microcycle_kinds(microcycle, previous, expected):
    path = StrictTddTransitionPath(FeatureTransitionKind.SCENARIO_ADVANCED, ScenarioTransitionKind.MICROCYCLE_ADVANCED, microcycle)
    assert StrictTddCheckpointPolicy().match(StrictTddCheckpointRequest(path, previous)) == expected


@pytest.mark.parametrize(
    "transition,requested,expected",
    [
        (_transition(StrictTddTransitionPath(FeatureTransitionKind.BLOCKED), blocker="stop"), None, StrictTddTerminalDisposition.BLOCKED),
        (_transition(StrictTddTransitionPath(FeatureTransitionKind.FEATURE_COMPLETED), available=False), None, StrictTddTerminalDisposition.COMPLETED),
        (_transition(StrictTddTransitionPath(FeatureTransitionKind.SCENARIO_ADVANCED, ScenarioTransitionKind.MICROCYCLE_ADVANCED, MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED)), StrictTddCheckpoint.RED_FRONTIER_ACCEPTED, StrictTddTerminalDisposition.CHECKPOINT),
        (_transition(StrictTddTransitionPath(FeatureTransitionKind.SCENARIO_ADVANCED), available=True), None, StrictTddTerminalDisposition.CONTINUE),
        (_transition(StrictTddTransitionPath(FeatureTransitionKind.SCENARIO_ADVANCED), available=False), None, StrictTddTerminalDisposition.BLOCKED),
    ],
)
def test_terminal_policy_uses_typed_availability_and_checkpoints(transition, requested, expected):
    decision = StrictTddTerminalPolicy().decide(StrictTddTerminalPolicyRequest(transition, requested, frozenset()))
    assert decision.disposition == expected


@pytest.mark.parametrize(
    "microcycle,expected",
    [
        (MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED, StrictTddLifecycleEventKind.FRONTIER_RED_ACCEPTED),
        (MicrocycleTransitionKind.DEVELOPER_CANDIDATE_ACCEPTED, StrictTddLifecycleEventKind.DEVELOPER_COMPLETED),
        (MicrocycleTransitionKind.REGRESSION_CLEAR, StrictTddLifecycleEventKind.REGRESSION_COMPLETED),
        (MicrocycleTransitionKind.CANONICAL_BASE_PROMOTED, StrictTddLifecycleEventKind.CANONICAL_BASE_PROMOTED),
        (MicrocycleTransitionKind.FRONTIER_ADVANCED, StrictTddLifecycleEventKind.FRONTIER_ADVANCED),
        (MicrocycleTransitionKind.SCENARIO_COMPLETED, StrictTddLifecycleEventKind.SCENARIO_COMPLETED),
        (MicrocycleTransitionKind.BEHAVIOR_REVIEW_APPROVED, StrictTddLifecycleEventKind.BEHAVIOR_REVIEW_COMPLETED),
        (MicrocycleTransitionKind.BEHAVIOR_REPAIR_VERIFIED, StrictTddLifecycleEventKind.BEHAVIOR_REPAIR_COMPLETED),
        (MicrocycleTransitionKind.BEHAVIOR_COMPLETED, StrictTddLifecycleEventKind.BEHAVIOR_COMPLETED),
        (MicrocycleTransitionKind.BLOCKED, StrictTddLifecycleEventKind.TRANSITION_BLOCKED),
    ],
)
def test_projector_maps_exact_microcycle_kind(microcycle, expected):
    path = StrictTddTransitionPath(FeatureTransitionKind.SCENARIO_ADVANCED, ScenarioTransitionKind.MICROCYCLE_ADVANCED, microcycle)
    draft = StrictTddTransitionEventProjector().project(StrictTddTransitionProjectionRequest(_context(), _transition(path), 4))[0]
    assert draft.event_kind == expected
    assert draft.candidate_revision == "c" * 40


def test_projector_identity_is_deterministic_and_uses_fallback_evidence():
    path = StrictTddTransitionPath(FeatureTransitionKind.SCENARIO_ADVANCED, ScenarioTransitionKind.MICROCYCLE_ADVANCED, MicrocycleTransitionKind.GREEN_VERIFIED)
    request = StrictTddTransitionProjectionRequest(_context(), _transition(path), 9)
    projector = StrictTddTransitionEventProjector()
    first, second = projector.project(request)[0], projector.project(request)[0]
    assert first == second
    assert first.evidence_refs[0].startswith("transition:scenario_advanced:")


def test_projector_has_no_persistence_or_external_effect_dependencies():
    source = Path("core/development/strict_tdd_transition_provenance.py").read_text()
    tree = ast.parse(source)
    assert tree.body
    assert "StrictTddLifecycleEventRepository" not in source
    assert "StrictTddLifecycleEventSink" not in source
    assert ".record(" not in source
