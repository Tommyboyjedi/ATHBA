"""Recorded live provenance through real persistence, routing and evidence adapters."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from core.development.checklist_reconciliation_tree import (
    ChecklistReconciliationTree, ChecklistTreeContext, validate_persisted_tree,
)
from core.development.reconciliation_progress import (
    ChecklistItemProgress, ChecklistSplitProgress, ReconciliationJournal, ReconciliationJournalRequest,
)
from core.development.specification_atomization import ChecklistAtomizationRequest, SpecificationChecklistPlanner
from core.development.specification_domain import (
    SourceRequirementClause, SpecificationChecklist, SpecificationChecklistItem, SpecificationGatekeeperRunState,
)
from core.development.specification_evidence_policy import EvidencePolicyRouter, reconciliation_satisfied
from core.development.specification_evidence_routing import (
    RoutedChecklistReconciler, RoutedChecklistRequest, required_source_subjects,
)
from core.development.specification_reconciliation import (
    AcceptedTestEvidenceCollector, ChecklistItemReconciler, GitAcceptedTestCatalog,
)
from tests.development.test_specification_provenance import COMPOUND, RecordedGateway
from tests.development.test_test_evidence_reconciliation import (
    FakeReasoningGateway, _repository, _run_state, _commit_all,
)

RECORDED = Path(__file__).parent / "fixtures/pr30_routing_omission.json"


def fact(quote="Keep the implementation ... in memory", subject="in memory", modality="required"):
    return SpecificationChecklistItem("memory", "Keep the implementation in memory.",
                                      "constraint", modality, quote, subject)


def routed(root, revision, gateway):
    catalog = GitAcceptedTestCatalog(root, revision)
    return RoutedChecklistReconciler(ChecklistItemReconciler(gateway, catalog), catalog)


@pytest.mark.asyncio
@pytest.mark.parametrize("production,policy,answer", [
    ("class RunningTotal:\n    pass\n", "no_storage", "YES"),
    ('def store():\n    open("total", "w")\n', "no_storage", "NO"),
    ("import requests\n", "dependency_free", "NO"),
])
async def test_recorded_live_response_atomization_disk_reload_and_real_evidence(tmp_path, monkeypatch, production, policy, answer):
    fixture = json.loads(RECORDED.read_text())
    gateway = RecordedGateway([fixture["response"]])
    result = await SpecificationChecklistPlanner(gateway).atomize(
        ChecklistAtomizationRequest(fixture["project_id"], fixture["requirement_text"]))
    assert len(gateway.requests) == len(result.attempts) == 1
    keeper = SpecificationGatekeeperRunState(result.checklist, atomization_attempts=list(result.attempts))
    path = tmp_path / "keeper.json"
    path.write_text(json.dumps(keeper.to_dict()))
    restored = SpecificationGatekeeperRunState.from_dict(json.loads(path.read_text()))
    assert restored.to_dict() == keeper.to_dict()
    assert restored.checklist.items[-1].source_quote == "Keep the implementation ... in memory"
    subjects = required_source_subjects(restored.checklist)
    assert subjects[-2:] == ("dependency-free", "in memory")
    repo = tmp_path / "repository"
    repo.mkdir()
    _repository(repo)
    (repo / "reservation_book.py").write_text(production)
    revision = _commit_all(repo, "deterministic evidence variant")
    accepted = AcceptedTestEvidenceCollector().collect(_run_state(revision))
    evidence_gateway = FakeReasoningGateway([
        {"answer": "YES", "selected_test_names": [accepted[0].test_name], "rationale": "deterministic behavioral judgment"}
        for _ in range(5)
    ])
    import core.development.python_specification_evidence as evidence
    observed = []
    original_storage = evidence.storage_findings
    def storage(trees):
        observed.append(trees)
        return original_storage(trees)
    monkeypatch.setattr(evidence, "storage_findings", storage)
    reconciler = routed(repo, revision, evidence_gateway)
    records = [await reconciler.reconcile(RoutedChecklistRequest(
        "p", item, fixture["requirement_text"], accepted, required_subjects=subjects))
        for item in restored.checklist.items]
    assert len(evidence_gateway.requests) == 5
    assert len(observed) == 1
    assert records[-1]["evidence_policy"] == "no_storage"
    assert records[-1]["adapter"] == {"id": "python-specification", "version": "1", "language": "python"}
    assert records[-1]["inspected_paths"]
    selected = next(record for record in records if record.get("evidence_policy") == policy)
    assert selected["answer"] == answer
    assert reconciliation_satisfied(tuple(records)) is (answer == "YES")
    assert path.read_text() == json.dumps(keeper.to_dict())


INVALID = [
    (COMPOUND, "in memory ... Keep the implementation"),
    (COMPOUND, "Keep the implementation ... on disk"),
    (COMPOUND, "The implementation should store everything in RAM."),
    ("Keep the implementation dependency-free. It stays in memory.", "Keep the implementation ... in memory."),
    ("Keep the implementation dependency-free; keep data in memory.", "Keep the implementation ... in memory."),
    ("Keep the implementation dependency-free and the cache stays in memory.", "Keep the implementation ... in memory."),
    (COMPOUND, "Keep the implementation ... ... in memory."),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("source,quote", INVALID)
async def test_invalid_provenance_rejected_by_reload_collection_and_final_routing(tmp_path, source, quote):
    item = fact(quote)
    checklist = SpecificationChecklist("p", source, [item])
    with pytest.raises(ValueError, match="provenance"):
        SpecificationChecklist.from_dict(checklist.to_dict())
    with pytest.raises(ValueError, match="provenance"):
        required_source_subjects(checklist)
    gateway = FakeReasoningGateway([])
    record = await routed(tmp_path, "a" * 40, gateway).reconcile(RoutedChecklistRequest("p", item, source, []))
    assert record["answer"] == "NO"
    assert record["evidence_status"] == "unsupported_evidence_policy"
    assert "source provenance mismatch" in record["rationale"]
    assert gateway.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("subject", ["dependency-free", "Keep in memory", "", "RAM"])
async def test_omitted_spliced_missing_or_invented_subject_cannot_route(tmp_path, subject):
    item = fact(subject=subject)
    checklist = SpecificationChecklist("p", COMPOUND, [item])
    with pytest.raises(ValueError, match="provenance"):
        SpecificationChecklist.from_dict(checklist.to_dict())
    with pytest.raises(ValueError, match="provenance"):
        required_source_subjects(checklist)
    record = await routed(tmp_path, "a" * 40, FakeReasoningGateway([])).reconcile(
        RoutedChecklistRequest("p", item, COMPOUND, []))
    assert record["answer"] == "NO"


@pytest.mark.asyncio
@pytest.mark.parametrize("source,quote,subject", [
    ("Clients must not persist records in memory.", "Clients ... in memory.", "in memory"),
    ("Caching and persistence are optional.", "Caching ... persistence", "Caching"),
    ("Caching and persistence are not required.", "Caching ... persistence", "Caching"),
    ("Clients must not persist records in memory.", "in memory", "in memory"),
])
async def test_original_qualifier_rejects_strengthened_modality_on_all_downstream_paths(tmp_path, source, quote, subject):
    item = fact(quote, subject)
    checklist = SpecificationChecklist("p", source, [item])
    with pytest.raises(ValueError, match="contradicts"):
        SpecificationChecklist.from_dict(checklist.to_dict())
    with pytest.raises(ValueError, match="contradicts"):
        required_source_subjects(checklist)
    record = await routed(tmp_path, "a" * 40, FakeReasoningGateway([])).reconcile(
        RoutedChecklistRequest("p", item, source, []))
    assert record["answer"] == "NO"
    assert "contradicts" in record["rationale"]


@pytest.mark.asyncio
@pytest.mark.parametrize("source,quote,modality,expected_policy,answer", [
    ("The component must not expose persistence.", "The component must not ... persistence.", "forbidden", "forbidden_public_surface", "NO"),
    ("Persistence is optional and not required.", "Persistence ... not required.", "non_goal", "non_goal_scope", "NOT_APPLICABLE"),
    ("The component must not persist data in memory.", "The component ... persist ... in memory.", "forbidden", "no_storage", "YES"),
])
async def test_verified_original_wording_controls_public_surface_and_optional_scope(tmp_path, source, quote, modality, expected_policy, answer):
    _repository(tmp_path)
    (tmp_path / "reservation_book.py").write_text("def persist():\n    pass\n")
    revision = _commit_all(tmp_path, "public persistence surface")
    subject = "in memory" if expected_policy == "no_storage" else "persistence"
    item = fact(quote, subject, modality)
    keeper = SpecificationChecklist.from_dict(SpecificationChecklist("p", source, [item]).to_dict())
    assert required_source_subjects(keeper) == ()
    record = await routed(tmp_path, revision, FakeReasoningGateway([])).reconcile(
        RoutedChecklistRequest("p", keeper.items[0], source, []))
    assert record["evidence_policy"] == expected_policy
    assert record["answer"] == answer
    assert record["findings"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("quote", [COMPOUND, "in memory.", "Keep ... dependency-free ... in memory."])
async def test_exact_and_multiple_omission_paths_produce_the_same_actual_storage_result(tmp_path, quote):
    revision = _repository(tmp_path)
    item = fact(quote)
    record = await routed(tmp_path, revision, FakeReasoningGateway([])).reconcile(
        RoutedChecklistRequest("p", item, COMPOUND, []))
    assert record["answer"] == "YES"
    assert record["evidence_policy"] == "no_storage"


@pytest.mark.asyncio
@pytest.mark.parametrize("quote,valid", [
    ("Keep ... in memory.", True),
    ("in memory ... Keep", False),
])
async def test_persisted_split_child_with_cached_yes_is_revalidated_before_reuse(tmp_path, quote, valid):
    revision = _repository(tmp_path)
    parent = SpecificationChecklistItem("root", COMPOUND, "behavior", "required", COMPOUND, "implementation")
    child = replace(fact(quote), ref="root-S001")
    second = replace(fact("dependency-free", "dependency-free"), ref="root-S002")
    split = ChecklistSplitProgress("split", "independent obligations", (child, second))
    progress = (
        ChecklistItemProgress(parent, revision, "identity", (),
            result={"answer": "NO", "status": "superseded"}, split=split),
        ChecklistItemProgress(child, revision, "identity", ("root",), result={"answer": "YES", "cached": True}),
    )
    persisted = json.loads(json.dumps([item.to_dict() for item in progress]))
    journal = ReconciliationJournal(ReconciliationJournalRequest(revision, "identity", tuple(persisted), root_refs=("root",)))
    validate_persisted_tree(journal, [parent])
    gateway = FakeReasoningGateway([])
    context = ChecklistTreeContext(routed(tmp_path, revision, gateway), "p", COMPOUND,
                                    [], "python", (), revision, parent)
    records = await ChecklistReconciliationTree(journal, gateway).reconcile(context)
    assert records[1]["answer"] == ("YES" if valid else "NO")
    if valid:
        assert records[1]["cached"]
    else:
        assert "source provenance mismatch" in records[1]["rationale"]
    assert gateway.requests == []


def test_supported_legacy_routing_and_subject_authority_remain_unchanged():
    source = "The component must stay in memory."
    static = SourceRequirementClause("legacy", source, "constraint")
    paraphrase = SourceRequirementClause("behavior", "Remember values.", "behavior")
    checklist = SpecificationChecklist("p", source, [static, paraphrase])
    assert required_source_subjects(checklist) == (source.lower(),)
    assert EvidencePolicyRouter().route_source(static, source) == EvidencePolicyRouter().route(static)
    assert EvidencePolicyRouter().route_source(paraphrase, source) == EvidencePolicyRouter().route(paraphrase)
    with pytest.raises(ValueError, match="provenance"):
        EvidencePolicyRouter().route_source(static, "Only publishing was requested.")
