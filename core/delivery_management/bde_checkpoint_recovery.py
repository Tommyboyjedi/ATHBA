"""Resume only a branch revision already accepted by the existing durable BDE."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.development.deterministic_regression import REGRESSION_CLEAR
from core.development.microcycle_revision_state import RevisionTransitionKind
from core.development.microcycle_revision_store import MicrocycleRevisionRepository
from core.development.post_behavior_domain import PostBehaviorCall
from core.development.project_environment import DevelopmentProject
from core.development.post_behavior_store import PostBehaviorStateRepository
from core.development.project_revision_synchronization import TrustedProjectRevisionSynchronizer
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.delivery_management.git_workspaces import GitCommand, git
from core.delivery_management.publication import checkout_matches

if TYPE_CHECKING:
    from core.delivery_management.branch_environment import BranchEnvironment
    from core.delivery_management.domain import TeamDelivery
    from core.development.strict_tdd_feature_domain import StrictTddFeatureState


def recover_accepted_checkpoint(environment: BranchEnvironment) -> DevelopmentProject:
    binding = environment.binding
    record = binding.records.delivery(binding.identity)
    project = environment.repo.load(binding.identity.project_id)
    if record is None or project is None:
        raise ValueError("unknown delivery cannot recover accepted BDE authority")
    actual = git(GitCommand(Path(record.worktree), ("rev-parse", record.branch_ref)))
    if actual == record.trusted_revision:
        return project
    if record.revision_intent is not None:
        return environment.recover_trusted_revision()
    feature = StrictTddFeatureRepository(Path(record.state_root) / "features").load(record.project_id)
    if (feature is None or feature.delivery_identity != record.id
            or feature.source_requirement_hash != record.behavior.source_sha256
            or feature.canonical_ref != record.branch_ref):
        raise ValueError("branch advance lacks exact durable delivery/source authority")
    accepted = _microcycle_revision(record, feature) or _post_revision(record, feature)
    if accepted != actual:
        raise ValueError("branch advance has no exact durable accepted BDE checkpoint")
    root = Path(record.worktree)
    if not any(checkout_matches(root, revision) for revision in (record.trusted_revision, actual)):
        raise ValueError("BDE checkpoint recovery refuses unowned checkout changes")
    return TrustedProjectRevisionSynchronizer(environment).synchronize(record.project_id, actual)


def _microcycle_revision(record: TeamDelivery, feature: StrictTddFeatureState) -> str | None:
    scenario = feature.current_scenario_id
    if scenario is None or not scenario.startswith(record.id + "--"):
        return None
    root = Path(record.state_root)
    lifecycle = MicrocycleRevisionRepository(root / "revisions").load(scenario)
    microcycle = MicrocycleStateRepo(root / "microcycles").load(scenario)
    if (lifecycle is None or microcycle is None or lifecycle.canonical_ref != record.branch_ref
            or lifecycle.last_transition not in {RevisionTransitionKind.REGRESSION_CLEAR.value,
                                                RevisionTransitionKind.BEHAVIOR_COMPLETED.value}):
        return None
    revision = lifecycle.canonical_development_base
    regression = microcycle.regression
    if (microcycle.scenario_draft.scenario_id != scenario
            or microcycle.development_base_revision != revision
            or regression.status != REGRESSION_CLEAR or not regression.reports
            or any(report.status != "passed" for report in regression.reports)):
        return None
    return revision


def _post_revision(record: TeamDelivery, feature: StrictTddFeatureState) -> str | None:
    post = PostBehaviorStateRepository(Path(record.state_root) / "post-behavior").load(record.project_id)
    if (post is None or post.entry.delivery_id != record.project_id or post.active_pass is None
            or post.pending_call != PostBehaviorCall.PROMOTION
            or post.entry.behaviorally_accepted_revision != feature.canonical_development_base
            or post.entry.trusted_entry_revision != feature.behavioral_entry_revision):
        return None
    change = post.active_pass
    if change.candidate is None or not change.candidate.success or change.candidate.revision is None:
        return None
    revision = change.candidate.revision
    if any(evidence is None or not evidence.passed or evidence.revision != revision
           for evidence in (change.tests, change.gatekeeper)):
        return None
    return revision
