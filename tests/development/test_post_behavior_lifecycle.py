"""Deterministic trust, iteration and process-death proofs for PR30."""
from __future__ import annotations

from dataclasses import replace

import pytest

from core.development.post_behavior_assessment import (
    IdentifierRename, NamingDecision, RefactorDecision, RefactorOpportunity,
)
from core.development.post_behavior_domain import (
    ChangeCandidate, PostBehaviorAssessment, PostBehaviorCall, PostBehaviorEntry,
    PostBehaviorOutcome, PostBehaviorPhase, PostBehaviorPolicy, PostBehaviorReason,
    PostBehaviorState, PostBehaviorStatus, ValidationEvidence,
)
from core.development.post_behavior_lifecycle import PostBehaviorLifecycle
from core.development.post_behavior_ports import PostBehaviorPorts
from core.development.post_behavior_store import PostBehaviorStateCodec, PostBehaviorStateRepository
from core.development.reconciliation_progress import ChecklistItemProgress, PendingReconciliationCall
from core.development.specification_domain import SpecificationChecklistItem

ENTRY = "0" * 39 + "1"
BASE = "0" * 39 + "2"
RENAME = NamingDecision(IdentifierRename("old_name", "required_name"))
NAMING_NO = NamingDecision()
REFACTOR_NO = RefactorDecision()
OBJECTIVE = "Extract duplicated normalization into a private helper."


def refactor(objective=OBJECTIVE):
    return RefactorDecision(RefactorOpportunity(objective, "This removes repeated normalization."))


def entry():
    return PostBehaviorEntry("delivery-1", ENTRY, BASE, ("src/product.py",), "authority-digest",
                             ValidationEvidence(BASE, True, ("final-gatekeeper:accepted",)))


class ProcessDeath(BaseException):
    pass


class ScriptedPorts:
    def __init__(self, naming=None, refactoring=None):
        self.naming = list(naming or [NAMING_NO])
        self.refactoring = list(refactoring or [REFACTOR_NO])
        self.calls = []
        self.revisions = 2
        self.trusted_ref = BASE
        self.reject_tests = None
        self.reject_gatekeeper = None
        self.mutation_success = True
        self.crash_at = None
        self.gatekeeper_checkpoint = False
        self.gatekeeper_inflight = False

    def ports(self):
        return PostBehaviorPorts(self, self, self, self)

    def crash(self, call):
        if self.crash_at == call:
            self.crash_at = None
            raise ProcessDeath(call)

    async def assess_naming(self, state):
        self.calls.append(("naming", state.current_post_behavior_revision))
        self.crash("naming")
        return PostBehaviorAssessment(self.naming.pop(0), f"slice:{state.current_post_behavior_revision}",
                                      ("naming:response",))

    async def assess_refactor(self, state):
        self.calls.append(("refactor", state.current_post_behavior_revision))
        self.crash("refactor")
        return PostBehaviorAssessment(self.refactoring.pop(0), f"slice:{state.current_post_behavior_revision}",
                                      ("refactor:response",))

    async def execute_change(self, state):
        active = state.active_pass
        self.calls.append(("mutation", state.current_post_behavior_revision, active.submission_id))
        self.crash("mutation")
        self.revisions += 1
        return ChangeCandidate(f"{self.revisions:040x}", ("workspace:packet",),
                               self.mutation_success, "bounded workspace result")

    async def test_candidate(self, state):
        active = state.active_pass
        self.calls.append(("tests", active.candidate.revision))
        self.crash("tests")
        return ValidationEvidence(active.candidate.revision, self.reject_tests != active.phase,
                                  ("accepted-suite:result",), "accepted suite result")

    async def reconcile_candidate(self, state, checkpoint):
        active = state.active_pass
        self.calls.append(("gatekeeper", active.candidate.revision))
        if self.gatekeeper_checkpoint:
            checkpoint((ChecklistItemProgress(
                SpecificationChecklistItem("CHECK-1", "Accepted behavior remains satisfied.", "behavior"),
                active.candidate.revision, "accepted-tests-digest", (),
                pending_call=PendingReconciliationCall.TEST if self.gatekeeper_inflight else PendingReconciliationCall.NONE,
            ),))
        self.crash("gatekeeper")
        return ValidationEvidence(active.candidate.revision, self.reject_gatekeeper != active.phase,
                                  ("existing-gatekeeper:result",), "independent reconciliation result")

    async def promote_candidate(self, state):
        active = state.active_pass
        self.calls.append(("promote", active.candidate.revision))
        assert self.trusted_ref in {active.base_revision, active.candidate.revision}
        self.trusted_ref = active.candidate.revision
        self.crash("promote")
        return ("canonical-ref:cas",)


def setup(tmp_path, scripted=None):
    scripted = scripted or ScriptedPorts()
    repository = PostBehaviorStateRepository(tmp_path)
    lifecycle = PostBehaviorLifecycle(repository, scripted.ports())
    lifecycle.start(entry())
    return lifecycle, repository, scripted


async def until(lifecycle, status):
    state = lifecycle.repository.load("delivery-1")
    while state.status != status and not state.terminal:
        state = await lifecycle.advance("delivery-1")
    assert state.status == status, state
    return state


@pytest.mark.parametrize("passed,revision", [(False, BASE), (True, ENTRY)])
def test_entry_requires_final_gatekeeper_acceptance_of_exact_sha(passed, revision):
    with pytest.raises(ValueError, match="final Gatekeeper"):
        replace(entry(), gatekeeper_evidence=ValidationEvidence(revision, passed, ("evidence",)))


@pytest.mark.asyncio
async def test_unknown_delivery_cannot_bypass_gatekeeper_entry(tmp_path):
    lifecycle = PostBehaviorLifecycle(PostBehaviorStateRepository(tmp_path), ScriptedPorts().ports())
    with pytest.raises(ValueError, match="Gatekeeper-approved"):
        await lifecycle.advance("missing")


@pytest.mark.asyncio
async def test_no_work_preserves_baseline_and_completes_without_execution(tmp_path):
    lifecycle, repository, scripted = setup(tmp_path)
    final = await lifecycle.run("delivery-1")
    assert final.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE
    assert final.current_post_behavior_revision == final.behaviorally_accepted_revision == BASE
    assert final.terminal_reason == PostBehaviorReason.REFACTOR_NO_CHANGE
    assert scripted.calls == [("naming", BASE), ("refactor", BASE)]
    assert [item.stop_reason for item in final.passes] == [
        PostBehaviorReason.NAMING_NO_CHANGE, PostBehaviorReason.REFACTOR_NO_CHANGE]
    assert repository.load("delivery-1") == final


@pytest.mark.asyncio
async def test_revision_chain_refreshes_every_assessment_and_preserves_all_evidence(tmp_path):
    lifecycle, _, scripted = setup(tmp_path, ScriptedPorts([RENAME, NAMING_NO], [refactor(), REFACTOR_NO]))
    final = await lifecycle.run("delivery-1")
    renamed, refactored = f"{3:040x}", f"{4:040x}"
    assert final.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE
    assert final.behaviorally_accepted_revision == BASE
    assert final.current_post_behavior_revision == refactored
    assert final.refactor_promoted_passes == 1
    assert [(item[0], item[1]) for item in scripted.calls] == [
        ("naming", BASE), ("mutation", BASE), ("tests", renamed), ("gatekeeper", renamed), ("promote", renamed),
        ("naming", renamed), ("refactor", renamed), ("mutation", renamed), ("tests", refactored),
        ("gatekeeper", refactored), ("promote", refactored), ("refactor", refactored)]
    promoted = [item for item in final.passes if item.outcome == PostBehaviorOutcome.PROMOTED]
    assert [item.base_revision for item in promoted] == [BASE, renamed]
    for item in promoted:
        assert item.assessment.slice_identity == f"slice:{item.base_revision}"
        assert item.candidate.evidence_refs == ("workspace:packet",)
        assert item.tests.passed and item.gatekeeper.passed and item.promotion_evidence
        assert item.submission_id
    assert promoted[0].submission_id != promoted[1].submission_id


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", [PostBehaviorPhase.NAMING, PostBehaviorPhase.REFACTORING])
@pytest.mark.parametrize("failure", ["tests", "gatekeeper"])
async def test_rejected_validation_retains_previous_trusted_base_and_candidate_evidence(tmp_path, phase, failure):
    scripted = ScriptedPorts([RENAME, NAMING_NO], [refactor(), REFACTOR_NO])
    if failure == "tests":
        scripted.reject_tests = phase
    else:
        scripted.reject_gatekeeper = phase
    lifecycle, repository, _ = setup(tmp_path, scripted)
    final = await lifecycle.run("delivery-1")
    expected = BASE if phase == PostBehaviorPhase.NAMING else f"{3:040x}"
    assert final.status == PostBehaviorStatus.BLOCKED
    assert final.current_post_behavior_revision == scripted.trusted_ref == expected
    assert final.behaviorally_accepted_revision == BASE
    rejected = final.passes[-1]
    assert rejected.outcome == PostBehaviorOutcome.REJECTED
    assert rejected.candidate.revision != expected
    assert rejected.tests.evidence_refs
    if failure == "tests":
        assert rejected.gatekeeper is None
    else:
        assert rejected.gatekeeper.evidence_refs
    assert repository.load("delivery-1") == final


@pytest.mark.asyncio
async def test_execution_failure_reuses_attempt_ledger_and_never_runs_validation(tmp_path):
    scripted = ScriptedPorts([RENAME])
    scripted.mutation_success = False
    lifecycle, _, _ = setup(tmp_path, scripted)
    final = await lifecycle.run("delivery-1")
    assert final.terminal_reason == PostBehaviorReason.CANDIDATE_REJECTED
    assert final.current_post_behavior_revision == BASE
    assert final.attempt_state.tier_one_submissions == 1
    assert final.attempt_state.submissions[0].candidate_revision == f"{3:040x}"
    assert [call[0] for call in scripted.calls] == ["naming", "mutation"]


@pytest.mark.asyncio
async def test_repeated_naming_passes_complete_before_any_refactoring(tmp_path):
    second = NamingDecision(IdentifierRename("another_name", "second_required_name"))
    lifecycle, _, scripted = setup(tmp_path, ScriptedPorts([RENAME, second, NAMING_NO]))
    final = await lifecycle.run("delivery-1")
    assert final.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE
    assert len([call for call in scripted.calls if call[0] == "mutation"]) == 2
    assert scripted.calls[-2:] == [("naming", f"{4:040x}"), ("refactor", f"{4:040x}")]


@pytest.mark.asyncio
async def test_four_promoted_refactors_then_yes_records_limit_and_last_trusted_revision(tmp_path):
    objectives = [
        "Extract duplicated normalization into a private helper.",
        "Replace repeated sorting with a single cached sorted sequence.",
        "Remove an unreachable private fallback branch.",
        "Replace quadratic membership scans with a local lookup set.",
        "Consolidate duplicated error formatting into a private formatter.",
    ]
    lifecycle, _, scripted = setup(tmp_path, ScriptedPorts(refactoring=[refactor(item) for item in objectives]))
    final = await lifecycle.run("delivery-1")
    assert final.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE
    assert final.refactor_promoted_passes == 4
    assert final.current_post_behavior_revision == f"{6:040x}"
    assert final.behaviorally_accepted_revision == BASE
    assert final.terminal_reason == PostBehaviorReason.REFACTOR_LIMIT_REACHED
    assert len([call for call in scripted.calls if call[0] == "mutation"]) == 4
    assert final.passes[-1].assessment.decision.opportunity.objective == objectives[-1]


@pytest.mark.asyncio
@pytest.mark.parametrize("objective", [
    OBJECTIVE, "extract duplicated normalization into a private helper!",
    "Extract duplicated normalization into one private helper.",
])
async def test_substantially_identical_refactor_objectives_stop_without_another_mutation(tmp_path, objective):
    lifecycle, _, scripted = setup(tmp_path, ScriptedPorts(refactoring=[refactor(), refactor(objective)]))
    final = await lifecycle.run("delivery-1")
    assert final.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE
    assert final.terminal_reason == PostBehaviorReason.REPEATED_REFACTOR_OBJECTIVE
    assert final.current_post_behavior_revision == f"{3:040x}"
    assert len([call for call in scripted.calls if call[0] == "mutation"]) == 1


@pytest.mark.asyncio
async def test_restart_at_every_persisted_transition_does_not_replay_work(tmp_path):
    lifecycle, repository, scripted = setup(tmp_path, ScriptedPorts([RENAME, NAMING_NO], [refactor(), REFACTOR_NO]))
    seen = set()
    state = repository.load("delivery-1")
    while not state.terminal:
        seen.add(state.status)
        lifecycle = PostBehaviorLifecycle(PostBehaviorStateRepository(tmp_path), scripted.ports())
        lifecycle.start(entry())
        state = await lifecycle.advance("delivery-1")
    assert {item for item in PostBehaviorStatus if item not in {
        PostBehaviorStatus.POST_BEHAVIOR_COMPLETE, PostBehaviorStatus.BLOCKED}} <= seen
    assert [item[0] for item in scripted.calls].count("mutation") == 2
    assert [item[0] for item in scripted.calls].count("naming") == 2
    assert [item[0] for item in scripted.calls].count("refactor") == 2
    snapshot = list(scripted.calls)
    assert await lifecycle.run("delivery-1") == state
    assert scripted.calls == snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("call,status", [
    ("naming", PostBehaviorStatus.NAMING_ASSESSMENT_PENDING),
    ("mutation", PostBehaviorStatus.NAMING_RENAME_PENDING),
    ("gatekeeper", PostBehaviorStatus.NAMING_VALIDATION_PENDING),
    ("refactor", PostBehaviorStatus.REFACTOR_ASSESSMENT_PENDING),
])
async def test_unknown_inflight_model_work_blocks_without_resubmission(tmp_path, call, status):
    scripted = ScriptedPorts([RENAME, NAMING_NO], [refactor(), REFACTOR_NO])
    lifecycle, repository, _ = setup(tmp_path, scripted)
    await until(lifecycle, status)
    if call == "gatekeeper":
        await lifecycle.advance("delivery-1")
    scripted.crash_at = call
    with pytest.raises(ProcessDeath):
        await lifecycle.advance("delivery-1")
    before = list(scripted.calls)
    persisted = repository.load("delivery-1")
    assert persisted.pending_call != PostBehaviorCall.NONE
    final = await PostBehaviorLifecycle(repository, scripted.ports()).run("delivery-1")
    assert final.status == PostBehaviorStatus.BLOCKED
    assert final.terminal_reason == PostBehaviorReason.INTERRUPTED_CALL
    assert final.current_post_behavior_revision == persisted.current_post_behavior_revision
    assert scripted.calls == before


@pytest.mark.asyncio
@pytest.mark.parametrize("call", ["tests", "promote"])
async def test_restart_repeats_only_safe_tests_or_idempotent_promotion(tmp_path, call):
    lifecycle, repository, scripted = setup(tmp_path, ScriptedPorts([RENAME, NAMING_NO]))
    await until(lifecycle, PostBehaviorStatus.NAMING_VALIDATION_PENDING)
    if call == "promote":
        await lifecycle.advance("delivery-1")
        await lifecycle.advance("delivery-1")
    scripted.crash_at = call
    with pytest.raises(ProcessDeath):
        await lifecycle.advance("delivery-1")
    persisted = repository.load("delivery-1")
    assert persisted.current_post_behavior_revision == BASE
    if call == "promote":
        assert scripted.trusted_ref == f"{3:040x}"
    final = await PostBehaviorLifecycle(repository, scripted.ports()).run("delivery-1")
    assert final.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE
    assert final.current_post_behavior_revision == f"{3:040x}"
    assert [item[0] for item in scripted.calls].count("mutation") == 1
    assert [item[0] for item in scripted.calls].count(call) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown", [False, True])
async def test_gatekeeper_restart_obeys_durable_per_call_journal(tmp_path, unknown):
    lifecycle, repository, scripted = setup(tmp_path, ScriptedPorts([RENAME, NAMING_NO]))
    await until(lifecycle, PostBehaviorStatus.NAMING_VALIDATION_PENDING)
    await lifecycle.advance("delivery-1")
    scripted.gatekeeper_checkpoint = True
    scripted.gatekeeper_inflight = unknown
    scripted.crash_at = "gatekeeper"
    with pytest.raises(ProcessDeath):
        await lifecycle.advance("delivery-1")
    persisted = repository.load("delivery-1")
    assert len(persisted.active_pass.reconciliation_progress) == 1
    final = await PostBehaviorLifecycle(repository, scripted.ports()).run("delivery-1")
    assert final.status == (PostBehaviorStatus.BLOCKED if unknown else PostBehaviorStatus.POST_BEHAVIOR_COMPLETE)
    assert [item[0] for item in scripted.calls].count("gatekeeper") == (1 if unknown else 2)


@pytest.mark.asyncio
async def test_durable_assessor_decision_is_used_without_reassessment(tmp_path):
    lifecycle, repository, scripted = setup(tmp_path, ScriptedPorts([RENAME, NAMING_NO]))
    pending = await until(lifecycle, PostBehaviorStatus.NAMING_RENAME_PENDING)
    # Process death between persisted assessor result and its pure routing transition.
    restored = replace(pending, status=PostBehaviorStatus.NAMING_ASSESSMENT_PENDING, generation=pending.generation + 1)
    repository.save(restored)
    final = await PostBehaviorLifecycle(repository, scripted.ports()).run("delivery-1")
    assert final.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE
    assert [call[0] for call in scripted.calls].count("naming") == 2
    assert [call[0] for call in scripted.calls].count("mutation") == 1


@pytest.mark.asyncio
async def test_serialization_roundtrip_and_tampering_fail_closed(tmp_path):
    lifecycle, repository, _ = setup(tmp_path, ScriptedPorts([RENAME, NAMING_NO]))
    final = await lifecycle.run("delivery-1")
    payload = PostBehaviorStateCodec.encode(final)
    assert PostBehaviorStateCodec.decode(payload) == final
    payload["current_post_behavior_revision"] = f"{99:040x}"
    with pytest.raises(ValueError, match="trusted revision"):
        PostBehaviorStateCodec.decode(payload)
    with pytest.raises(ValueError, match="baseline"):
        lifecycle.start(replace(entry(), behavioral_authority_digest="changed"))
    with pytest.raises(ValueError, match="baseline"):
        repository.save(replace(final, entry=replace(entry(), behavioral_authority_digest="changed"),
                                generation=final.generation + 1))


@pytest.mark.parametrize("status", [
    PostBehaviorStatus.REFACTOR_ASSESSMENT_PENDING, PostBehaviorStatus.REFACTOR_CHANGE_PENDING,
    PostBehaviorStatus.REFACTOR_COMPLETE, PostBehaviorStatus.POST_BEHAVIOR_COMPLETE,
])
def test_persisted_state_cannot_skip_naming_no(status):
    with pytest.raises(ValueError, match="naming"):
        PostBehaviorState(entry(), BASE, status=status)


def test_policy_cannot_exceed_pr30_four_pass_ceiling():
    with pytest.raises(ValueError, match="four"):
        PostBehaviorPolicy(5)


@pytest.mark.asyncio
async def test_promoted_record_cannot_be_forged_from_rejected_validation(tmp_path):
    scripted = ScriptedPorts([RENAME])
    scripted.reject_gatekeeper = PostBehaviorPhase.NAMING
    lifecycle, _, _ = setup(tmp_path, scripted)
    final = await lifecycle.run("delivery-1")
    rejected = final.passes[-1]
    with pytest.raises(ValueError, match="promotion requires"):
        replace(rejected, outcome=PostBehaviorOutcome.PROMOTED, promotion_evidence=("forged",))


@pytest.mark.asyncio
async def test_storage_error_after_canonical_cas_preserves_recoverable_promotion_marker(tmp_path, monkeypatch):
    lifecycle, repository, scripted = setup(tmp_path, ScriptedPorts([RENAME, NAMING_NO]))
    await until(lifecycle, PostBehaviorStatus.NAMING_VALIDATION_PENDING)
    await lifecycle.advance("delivery-1")
    await lifecycle.advance("delivery-1")
    original_save = repository.save
    fail_once = True

    def save_with_one_storage_failure(state):
        nonlocal fail_once
        if fail_once and any(item.outcome == PostBehaviorOutcome.PROMOTED for item in state.passes):
            fail_once = False
            raise OSError("simulated checkpoint storage unavailable after canonical CAS")
        original_save(state)

    monkeypatch.setattr(repository, "save", save_with_one_storage_failure)
    with pytest.raises(OSError, match="after canonical CAS"):
        await lifecycle.advance("delivery-1")
    persisted = repository.load("delivery-1")
    assert persisted.pending_call == PostBehaviorCall.PROMOTION
    assert persisted.status == PostBehaviorStatus.NAMING_VALIDATION_PENDING
    assert persisted.current_post_behavior_revision == BASE
    assert scripted.trusted_ref == f"{3:040x}"
    final = await PostBehaviorLifecycle(repository, scripted.ports()).run("delivery-1")
    assert final.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE
    assert final.current_post_behavior_revision == f"{3:040x}"
    assert [item[0] for item in scripted.calls].count("mutation") == 1
    assert [item[0] for item in scripted.calls].count("promote") == 2


@pytest.mark.asyncio
async def test_repeated_rename_across_promoted_revisions_stops_without_endless_cycle(tmp_path):
    lifecycle, _, scripted = setup(tmp_path, ScriptedPorts([RENAME, RENAME]))
    final = await lifecycle.run("delivery-1")
    assert final.status == PostBehaviorStatus.BLOCKED
    assert final.terminal_reason == PostBehaviorReason.REPEATED_RENAME
    assert final.behaviorally_accepted_revision == BASE
    assert final.current_post_behavior_revision == f"{3:040x}"
    assert [item[0] for item in scripted.calls].count("mutation") == 1
    assert final.passes[-1].assessment.decision == RENAME
