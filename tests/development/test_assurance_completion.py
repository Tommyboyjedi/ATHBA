"""Language-neutral assurance confidence never becomes invented proof."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from core.development.assurance_completion import CompletionAuthority, assess_completion, AssuranceGap
from core.development.specification_domain import SpecificationChecklistItem
from core.development.specification_evidence_policy import EvidenceResult, EvidencePolicyRouter, EvidenceStatus
from core.development.specification_obligations import EvidencePolicy
from core.development.feature_signature_evidence import signature_evidence
from core.development.specification_evidence_policy import SpecificationSnapshot, RevisionFile

REVISION = "a" * 40
SOURCE = "Keep all state in memory."
ITEM = SpecificationChecklistItem("M", SOURCE, "constraint", source_quote=SOURCE, subject="in memory")


def record(status=EvidenceStatus.UNSUPPORTED):
    return EvidenceResult(status, EvidencePolicy.STORAGE, REVISION, ("No bounded effect proof.",)).to_record(ITEM)


def test_unproven_assurance_preserves_no_and_permits_only_qualified_completion():
    entry = record()
    result = assess_completion(CompletionAuthority(({"answer": "YES"}, entry), SOURCE))
    assert result.behaviorally_complete and not result.fully_proven
    assert result.unproven_assurance[0].checklist_ref == "M"
    assert entry["answer"] == "NO"
    assert entry["evidence_status"] == EvidenceStatus.UNSUPPORTED.value


@pytest.mark.parametrize("status,complete,proven", [
    (EvidenceStatus.PASS, True, True), (EvidenceStatus.FAIL, False, False),
    (EvidenceStatus.UNSUPPORTED, True, False)])
def test_assurance_outcomes_are_distinct(status, complete, proven):
    result = assess_completion(CompletionAuthority((record(status),), SOURCE))
    assert result.behaviorally_complete == complete
    assert result.fully_proven == proven


@pytest.mark.parametrize("mutation", [
    {"evidence_policy": EvidencePolicy.UNSUPPORTED.value},
    {"status": "split_correction_exhausted"}, {"blocked_reason": "provider_failure"},
    {"evidence_status": "fail"}, {"source_item": None},
])
def test_unknown_must_not_hide_invalidity_exhaustion_or_violation(mutation):
    result = assess_completion(CompletionAuthority(({**record(), **mutation},), SOURCE))
    assert not result.behaviorally_complete


def test_unknown_provenance_cannot_permit_qualified_completion():
    assert not assess_completion(CompletionAuthority((record(),), "Store data in a database.")).behaviorally_complete


def test_missing_behavior_remains_blocking_even_with_unproven_assurance():
    assert not assess_completion(CompletionAuthority(({"answer": "NO"}, record()), SOURCE)).behaviorally_complete


def test_compound_assurance_is_not_partially_approved():
    source = "Keep it dependency-free and in memory."
    item = SpecificationChecklistItem("C", source, "constraint", source_quote=source, subject="dependency-free and in memory")
    entry = EvidenceResult(EvidenceStatus.UNSUPPORTED, EvidencePolicy.UNSUPPORTED, REVISION, ("Compound.",)).to_record(item)
    assert not assess_completion(CompletionAuthority((entry,), source)).behaviorally_complete


def test_dependency_and_nonpersistence_are_independent_source_grounded_children():
    source = "Keep it dependency-free and in memory."
    children = [SpecificationChecklistItem(str(i), subject, "constraint", source_quote=source, subject=subject)
                for i, subject in enumerate(("dependency-free", "in memory"))]
    assert [EvidencePolicyRouter().route_source(x, source).policy for x in children] == [
        EvidencePolicy.DEPENDENCY, EvidencePolicy.STORAGE]
    assert {x.obligation_type for x in children} == {"mechanical_assurance", "non_persistence_assurance"}


def test_positive_persistence_has_behavioral_policy_not_absence_assurance():
    source = "Persist records across sessions."
    item = SpecificationChecklistItem("P", source, "constraint", source_quote=source, subject=source)
    assert EvidencePolicyRouter().route_source(item, source).policy == EvidencePolicy.BEHAVIORAL
    entry = EvidenceResult(EvidenceStatus.UNSUPPORTED, EvidencePolicy.STORAGE, REVISION, ("Unknown.",)).to_record(item)
    assert not assess_completion(CompletionAuthority((entry,), source)).behaviorally_complete


def test_domain_does_not_require_rejection_or_runtime_validation():
    source = "Values are supported identifiers."
    item = SpecificationChecklistItem("D", source, "validation", source_quote=source, subject="supported identifiers")
    assert EvidencePolicyRouter().route_source(item, source).policy == EvidencePolicy.DOMAIN
    entry = EvidenceResult(EvidenceStatus.DOMAIN, EvidencePolicy.DOMAIN, REVISION, ("Caller domain.",)).to_record(item)
    result = assess_completion(CompletionAuthority((entry, {"answer": "YES"}), source))
    assert result.fully_proven
    assert entry["answer"] == "NOT_APPLICABLE"


def test_explicit_error_behavior_is_not_a_precondition():
    source = "Reject unsupported identifiers with DomainError."
    item = SpecificationChecklistItem("E", source, "validation", source_quote=source, subject="unsupported identifiers")
    assert EvidencePolicyRouter().route_source(item, source).policy == EvidencePolicy.BEHAVIORAL


def test_signature_lexical_difference_passes_and_shape_difference_violates():
    source = "Calling add(amount) adds a value."
    def snapshot(code):
        return SpecificationSnapshot(REVISION, (RevisionFile("component.py", code),))
    good = signature_evidence(source, snapshot("def add(value): return value"), "python")
    bad = signature_evidence(source, snapshot("def add(value, other=0): return value"), "python")
    assert good["answer"] == "YES"
    assert bad["answer"] == "NO" and bad["evidence_status"] == "fail"
    assert not assess_completion(CompletionAuthority((bad,), source)).behaviorally_complete


def test_unsupported_declaration_is_not_a_proven_signature_violation():
    source = "Provide a Counter class. Calling add(amount) adds a value."
    snapshot = SpecificationSnapshot(REVISION, (RevisionFile("counter.py",
        "from dataclasses import dataclass\\n@dataclass\\nclass Counter:\\n    def add(self, value): return value\\n"),))
    entry = signature_evidence(source, snapshot, "python")
    assert entry["answer"] == "NO" and entry["evidence_status"] == "unsupported_evidence_policy"
    assert assess_completion(CompletionAuthority((entry,), source)).unproven_assurance


def test_unproven_assurance_is_language_neutral_and_does_not_expand_container_analysis():
    result = assess_completion(CompletionAuthority((record(),), SOURCE))
    assert result.behaviorally_complete
    assert "list" not in result.unproven_assurance[0].diagnostic

@pytest.mark.asyncio
async def test_qualified_delivery_reaches_naming_refactor_and_round_trips(tmp_path):
    from tests.development.test_post_behavior_lifecycle import entry, ScriptedPorts
    from core.development.post_behavior_domain import PostBehaviorStatus
    from core.development.post_behavior_lifecycle import PostBehaviorLifecycle
    from core.development.post_behavior_store import PostBehaviorStateRepository, PostBehaviorStateCodec
    original = entry()
    gap = AssuranceGap("M", "no_storage", original.behaviorally_accepted_revision, "Unknown effects.")
    qualified = replace(original, gatekeeper_evidence=replace(original.gatekeeper_evidence,
        unproven_assurance=(gap,)))
    repo = PostBehaviorStateRepository(tmp_path)
    ports = ScriptedPorts()
    lifecycle = PostBehaviorLifecycle(repo, ports.ports())
    lifecycle.start(qualified)
    result = await lifecycle.run(original.delivery_id)
    assert result.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE_WITH_UNPROVEN_ASSURANCE
    assert result.terminal and result.unproven_assurance == (gap,)
    assert [item[0] for item in ports.calls] == ["naming", "refactor"]
    assert PostBehaviorStateCodec.decode(PostBehaviorStateCodec.encode(result)) == result
    with pytest.raises(ValueError, match="qualified completion"):
        replace(result, status=PostBehaviorStatus.POST_BEHAVIOR_COMPLETE)


def test_actual_delivery_loader_accepts_only_source_grounded_qualified_state(tmp_path):
    from tests.development.test_post_behavior_integration import seeded_delivery, PROJECT
    from core.development.post_behavior_entry import AcceptedBehavioralDeliveryLoader
    from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
    state_root, root, entry_revision, baseline = seeded_delivery(tmp_path)
    repo = StrictTddFeatureRepository(state_root / "features")
    feature = repo.load(PROJECT)
    data = dict(feature.contract_payload)
    data["requirement_source"] += " " + SOURCE
    keeper = json.loads(json.dumps(feature.gatekeeper_payload))
    keeper["checklist"]["requirement_text"] = data["requirement_source"]
    keeper["checklist"]["items"].append(ITEM.to_dict())
    entry = {**record(), "revision": feature.canonical_development_base}
    feature = replace(feature, status="completed_with_unproven_assurance", contract_payload=data,
        gatekeeper_payload=keeper, final_reconciliation=(*feature.final_reconciliation, entry))
    repo.save(feature)
    accepted = AcceptedBehavioralDeliveryLoader(state_root).load(PROJECT)
    assert accepted.entry.gatekeeper_evidence.unproven_assurance[0].checklist_ref == "M"
    assert accepted.contract.requirement_source == data["requirement_source"]
    repo.save(replace(feature, final_reconciliation=(*feature.final_reconciliation[:-1],
        {**entry, "evidence_status": "fail"})))
    with pytest.raises(ValueError, match="Gatekeeper"):
        AcceptedBehavioralDeliveryLoader(state_root).load(PROJECT)

def test_positive_persistence_cannot_be_deduced_as_static_absence():
    from core.development.source_obligation_semantics import validate_planned_clauses
    from core.development.specification_domain import SourceRequirementClause
    source = "Persist records across sessions."
    clause = SourceRequirementClause("P", source, "constraint", "mechanical", source, source)
    with pytest.raises(ValueError, match="behavioral evidence channel"):
        validate_planned_clauses([clause], source)

def test_mechanical_assurance_cannot_be_a_fresh_behavioral_red():
    from core.development.source_obligation_semantics import validate_planned_clauses
    from core.development.specification_domain import SourceRequirementClause
    source = "Use no external dependencies."
    clause = SourceRequirementClause("M", source, "constraint", "test", source, source)
    with pytest.raises(ValueError, match="cannot require a behavioral RED"):
        validate_planned_clauses([clause], source)

def test_unknown_evidence_requires_exact_revision():
    assert not assess_completion(CompletionAuthority(({**record(), "revision": "unavailable"},), SOURCE)).behaviorally_complete


def test_validation_cannot_carry_confidence_from_another_revision():
    from core.development.post_behavior_domain import ValidationEvidence
    with pytest.raises(ValueError, match="exact validation revision"):
        ValidationEvidence(REVISION, True, ("evidence",),
            unproven_assurance=(AssuranceGap("M", "no_storage", "b" * 40, "Unknown."),))
