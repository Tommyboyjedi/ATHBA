"""Fake-only qualification of modality and canonical deterministic evidence."""
import json
from dataclasses import replace

import pytest

from core.development.specification_atomization import ChecklistAtomizationRequest, SpecificationChecklistPlanner
from core.development.specification_domain import SpecificationChecklistItem
from core.development.specification_evidence_policy import (
    EvidencePolicyRouter, EvidenceStatus, RevisionFile, SpecificationSnapshot, reconciliation_satisfied,
)
from core.development.specification_evidence_routing import RoutedChecklistReconciler, RoutedChecklistRequest
from core.development.specification_obligations import EvidencePolicy
from core.development.python_specification_evidence import PythonSpecificationEvidenceAdapter
from core.development.specification_reconciliation import (
    AcceptedTestEvidenceCollector, ChecklistItemReconciler, GitAcceptedTestCatalog,
)
from core.development.specification_revision_snapshot import GitSpecificationSnapshot
from tests.development.test_test_evidence_reconciliation import (
    FakeReasoningGateway, _repository, _run_state, _commit_all,
)

REGRESSION = (
    "No persistence, deletion, subscriptions, validation rules, or concurrency are required. "
    "Keep the component small, direct and dependency-free."
)


def item(text, *, modality="required", subject="", kind="constraint"):
    return SpecificationChecklistItem("SPEC-1", text, kind, modality, text, subject or text)


def snapshot(source="class Component:\n    pass\n", metadata=()):
    return SpecificationSnapshot("a" * 40, (RevisionFile("component.py", source), *metadata))


def verify(obligation, repository=None):
    return PythonSpecificationEvidenceAdapter().verify(EvidencePolicyRouter().route(obligation), repository or snapshot())


@pytest.mark.parametrize("wording,modality", [
    ("Deletion is not required.", "non_goal"),
    ("Deletion is optional.", "non_goal"),
    ("Deletion is out of scope.", "non_goal"),
    ("Do not implement deletion.", "forbidden"),
    ("Deletion must not exist.", "forbidden"),
])
@pytest.mark.asyncio
async def test_atomizer_requires_explicit_modality_and_retains_source(wording, modality):
    payload = item(wording, modality=modality, subject="Deletion").to_dict()
    gateway = FakeReasoningGateway([{"items": [payload]}])
    checklist = await SpecificationChecklistPlanner(gateway).create_checklist(ChecklistAtomizationRequest("p", wording))
    restored = type(checklist).from_dict(checklist.to_dict())
    assert restored.items[0].modality == modality
    assert restored.items[0].source_quote == wording
    prompt = json.loads(gateway.requests[0].prompt)
    assert prompt["requirement_text"] == wording
    assert "modality" in prompt["required_output_schema"]["items"][0]
    assert "production" not in prompt and "observable_requirements" not in prompt


@pytest.mark.asyncio
async def test_signalboard_original_wording_is_not_strengthened():
    first, second = REGRESSION.split(". ")
    first += "."
    facts = [item(first, modality="non_goal", subject=subject).to_dict()
             for subject in ("persistence", "deletion", "subscriptions", "validation rules", "concurrency")]
    facts += [item(second, subject=subject, kind="quality").to_dict() for subject in ("small", "direct", "dependency-free")]
    for index, fact in enumerate(facts):
        fact["ref"] = f"SPEC-{index}"
    checklist = await SpecificationChecklistPlanner(FakeReasoningGateway([{"items": facts}])).create_checklist(ChecklistAtomizationRequest("p", REGRESSION))
    assert [entry.modality for entry in checklist.items] == ["non_goal"] * 5 + ["required"] * 3
    assert [EvidencePolicyRouter().route(entry).policy for entry in checklist.items] == [EvidencePolicy.NON_GOAL] * 5 + [EvidencePolicy.QUALITY] * 2 + [EvidencePolicy.DEPENDENCY]


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["missing", "strengthened", "quote_dropped_operator", "invented_quote"])
async def test_atomizer_rejects_missing_modality_or_source_drift(mutation):
    source = "Deletion is not required."
    fact = item(source, modality="non_goal", subject="Deletion").to_dict()
    if mutation == "missing":
        fact.pop("modality")
    elif mutation == "strengthened":
        fact["modality"] = "forbidden"
    elif mutation == "quote_dropped_operator":
        fact.update(modality="required", source_quote="Deletion")
    else:
        fact["source_quote"] = "Deletion is optional."
    with pytest.raises(ValueError):
        await SpecificationChecklistPlanner(FakeReasoningGateway([{"items": [fact]}])).create_checklist(ChecklistAtomizationRequest("p", source))


def test_non_goal_absence_never_demands_test_proof():
    obligation = item("Deletion is not required.", modality="non_goal", subject="Deletion")
    result = verify(obligation)
    assert result.status == EvidenceStatus.NOT_REQUIRED
    record = result.to_record(obligation)
    assert record["answer"] == "NOT_APPLICABLE"
    assert record["accepted_test_names"] == []
    assert reconciliation_satisfied((record,))


def test_non_goal_present_is_separate_scope_expansion():
    obligation = item("Deletion is not required.", modality="non_goal", subject="Deletion")
    result = verify(obligation, snapshot("class Component:\n    def delete_signal(self):\n        pass\n"))
    assert result.status == EvidenceStatus.NOT_REQUIRED
    assert result.findings == ("unrequested_surface_detected:delete_signal",)
    assert "not explicitly prohibited" in result.details[0]
    assert not reconciliation_satisfied((result.to_record(obligation),))


@pytest.mark.parametrize("method,present", [("delete_signal", True), ("removeEntry", True), ("publish", False)])
def test_explicit_prohibition_uses_declared_api(method, present):
    obligation = item("The component must not expose deletion.", modality="forbidden", subject="deletion")
    result = verify(obligation, snapshot(f"class Component:\n    def {method}(self):\n        pass\n"))
    assert result.status == (EvidenceStatus.FAIL if present else EvidenceStatus.PASS)
    assert result.policy == EvidencePolicy.PUBLIC_SURFACE


@pytest.mark.parametrize("source,metadata,status", [
    ("import collections\nimport local_helper\n", (RevisionFile("local_helper.py", "VALUE = 1\n"),), EvidenceStatus.PASS),
    ("import requests\n", (), EvidenceStatus.FAIL),
    ("from requests import Session\n", (), EvidenceStatus.FAIL),
    ("import requests\n", (RevisionFile("helpers/requests.py", "VALUE = 1\n"),), EvidenceStatus.FAIL),
    ("VALUE = 1\n", (RevisionFile("pyproject.toml", '[project]\ndependencies = ["requests"]\n'),), EvidenceStatus.FAIL),
    ("VALUE = 1\n", (RevisionFile("requirements.txt", 'requests>=2\n'),), EvidenceStatus.FAIL),
    ("VALUE = 1\n", (RevisionFile("setup.cfg", '[options]\ninstall_requires = requests\n'),), EvidenceStatus.FAIL),
    ("VALUE = 1\n", (RevisionFile("pyproject.toml", '[project]\ndynamic = ["dependencies"]\n'),), EvidenceStatus.UNSUPPORTED),
    ('__import__("requests")\n', (), EvidenceStatus.UNSUPPORTED),
    ("VALUE = 1\n", (RevisionFile("setup.py", 'from setuptools import setup\nsetup()\n'),), EvidenceStatus.UNSUPPORTED),
])
def test_dependency_verifier_inspects_imports_and_metadata(source, metadata, status):
    result = verify(item("Component must be dependency-free.", subject="dependency-free", kind="quality"), snapshot(source, metadata))
    assert result.policy == EvidencePolicy.DEPENDENCY
    assert result.status == status


@pytest.mark.parametrize("source,status", [
    ("class Component:\n    def __init__(self):\n        self.values = {}\n", EvidenceStatus.PASS),
    ('def store():\n    open("file", "w")\n', EvidenceStatus.FAIL),
    ('import sqlite3\n', EvidenceStatus.FAIL),
    ('def store(callback):\n    callback()\n', EvidenceStatus.UNSUPPORTED),
])
def test_storage_uses_static_verifier_and_fails_closed_for_opaque_effects(source, status):
    result = verify(item("The component must not persist.", modality="forbidden", subject="persist"), snapshot(source))
    assert result.policy == EvidencePolicy.STORAGE
    assert result.status == status


@pytest.mark.parametrize("text", ["small", "direct", "readable", "beautiful"])
def test_unsupported_quality_never_uses_unit_tests(text):
    result = verify(item(f"Keep it {text}.", subject=text, kind="quality"))
    assert result.status == EvidenceStatus.UNSUPPORTED
    assert result.to_record(item(text))["answer"] == "NO"


def test_existing_static_quality_limits_are_reused():
    obligation = item("Keep within existing coding-principles limits.", subject="existing coding-principles limits", kind="quality")
    assert verify(obligation).status == EvidenceStatus.PASS
    assert verify(obligation, snapshot("class Component:\n    def work(self, a, b, c):\n        pass\n")).status == EvidenceStatus.FAIL


def test_dynamic_surface_cannot_prove_an_explicit_absence():
    obligation = item("The component must not expose deletion.", modality="forbidden", subject="deletion")
    assert verify(obligation, snapshot("class Component(Base):\n    pass\n")).status == EvidenceStatus.UNSUPPORTED
    assert verify(obligation, snapshot("def __getattr__(name):\n    return name\n")).status == EvidenceStatus.UNSUPPORTED


@pytest.mark.asyncio
async def test_router_calls_no_llm_for_deterministic_item_and_reads_only_canonical_revision(tmp_path):
    revision = _repository(tmp_path)
    gateway = FakeReasoningGateway([])
    catalog = GitAcceptedTestCatalog(tmp_path, revision)
    routed = RoutedChecklistReconciler(ChecklistItemReconciler(gateway, catalog), catalog)
    obligation = item("Component must be dependency-free.", subject="dependency-free", kind="quality")
    (tmp_path / "reservation_book.py").write_text("import requests\n")
    record = await routed.reconcile(RoutedChecklistRequest("p", obligation, obligation.text, []))
    assert record["answer"] == "YES" and record["revision"] == revision
    assert not gateway.requests
    final = _commit_all(tmp_path, "add dependency")
    catalog = GitAcceptedTestCatalog(tmp_path, final)
    record = await RoutedChecklistReconciler(ChecklistItemReconciler(gateway, catalog), catalog).reconcile(RoutedChecklistRequest("p", obligation, obligation.text, []))
    assert record["answer"] == "NO" and not gateway.requests


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ["YES", "NO"])
async def test_behavioral_reconciliation_semantics_and_accepted_test_bodies_unchanged(tmp_path, answer):
    revision = _repository(tmp_path)
    state = _run_state(revision)
    before = state.to_dict()
    accepted = AcceptedTestEvidenceCollector().collect(state)
    names = [accepted[0].test_name] if answer == "YES" else []
    response = {"answer": answer, "selected_test_names": names, "rationale": "semantic judgment unchanged"}
    original_gateway = FakeReasoningGateway([response])
    routed_gateway = FakeReasoningGateway([response])
    catalog = GitAcceptedTestCatalog(tmp_path, revision)
    text = "Publishing under an existing signal name replaces the current value."
    obligation = item(text, kind="behavior")
    routed = RoutedChecklistReconciler(ChecklistItemReconciler(routed_gateway, catalog), catalog)
    record = await routed.reconcile(RoutedChecklistRequest("p", obligation, text, accepted))
    from core.development.specification_reconciliation import ChecklistReconciliationRequest
    original = await ChecklistItemReconciler(original_gateway, catalog).reconcile(ChecklistReconciliationRequest("p", obligation.ref, text, accepted))
    assert record == original.to_dict()
    assert routed_gateway.requests == original_gateway.requests
    assert "def test_add_resource" in routed_gateway.requests[0].prompt
    assert "class ReservationBook" not in routed_gateway.requests[0].prompt
    assert state.to_dict() == before


@pytest.mark.asyncio
async def test_canonical_snapshot_failure_and_ungrounded_static_claim_fail_closed(tmp_path):
    assert not GitSpecificationSnapshot(tmp_path).read("invalid").complete
    revision = _repository(tmp_path)
    catalog = GitAcceptedTestCatalog(tmp_path, revision)
    gateway = FakeReasoningGateway([])
    routed = RoutedChecklistReconciler(ChecklistItemReconciler(gateway, catalog), catalog)
    obligation = item("Component must be dependency-free.", subject="dependency-free", kind="quality")
    record = await routed.reconcile(RoutedChecklistRequest("p", obligation, "Only publishing was requested.", []))
    assert record["evidence_status"] == "unsupported_evidence_policy"
    assert record["answer"] == "NO" and not gateway.requests


def test_compound_constraints_and_reversed_dependency_modality_fail_closed():
    assert verify(item("Keep it small, direct and dependency-free.", kind="quality")).status == EvidenceStatus.UNSUPPORTED
    assert verify(item("It must not be dependency-free.", modality="forbidden", subject="dependency-free")).status == EvidenceStatus.UNSUPPORTED


def test_storage_configuration_is_not_silently_ignored():
    obligation = item("The component must not persist.", modality="forbidden", subject="persist")
    result = verify(obligation, snapshot(metadata=(RevisionFile("storage.json", '{"backend":"sqlite"}'),)))
    assert result.status == EvidenceStatus.UNSUPPORTED


def test_negative_behavioral_invariant_stays_on_behavioral_path():
    obligation = item("Failed operations must not corrupt existing state.", modality="forbidden", subject="existing state", kind="invariant")
    assert EvidencePolicyRouter().route(obligation).policy == EvidencePolicy.BEHAVIORAL


def test_private_helpers_are_not_unrequested_public_capabilities():
    obligation = item("Deletion is not required.", modality="non_goal", subject="Deletion")
    result = verify(obligation, snapshot("class _Private:\n    def delete_signal(self):\n        self.deletion = True\n\nclass Component:\n    pass\n"))
    assert result.findings == ()


def test_optional_capability_is_permitted_but_not_a_mandatory_acceptance_obligation():
    obligation = item("Deletion is optional.", modality="non_goal", subject="Deletion")
    result = verify(obligation, snapshot("class Component:\n    def delete_signal(self):\n        pass\n"))
    assert result.status == EvidenceStatus.NOT_REQUIRED
    assert result.findings == ()


def test_dynamic_public_extension_does_not_establish_explicit_absence():
    obligation = item("The component must not expose deletion.", modality="forbidden", subject="deletion")
    assert verify(obligation, snapshot("from third_party import *\n")).status == EvidenceStatus.UNSUPPORTED


def test_capability_explicitly_required_elsewhere_is_not_unrequested():
    obligation = item("Deletion is not required.", modality="non_goal", subject="Deletion")
    decision = replace(EvidencePolicyRouter().route(obligation), required_subjects=("deletion",))
    result = PythonSpecificationEvidenceAdapter().verify(decision, snapshot("def delete_signal():\n    pass\n"))
    assert result.findings == ()


@pytest.mark.parametrize("source", [
    "def save():\n    pass\nsave()\n",
    "def work(stream):\n    stream.write('data')\n",
    "def open():\n    pass\nopen()\n",
])
def test_storage_does_not_infer_effects_from_arbitrary_internal_names(source):
    obligation = item("The component must not persist.", modality="forbidden", subject="persist")
    result = verify(obligation, snapshot(source))
    assert result.status == EvidenceStatus.UNSUPPORTED
    assert not any("storage API reference" in detail for detail in result.details)


@pytest.mark.parametrize("source", [
    "def store(target):\n    target.data = 1\n",
    "def store(target):\n    target[0] = 1\n",
    "def store(target):\n    return str(target)\n",
])
def test_storage_opaque_protocol_effects_are_unsupported(source):
    obligation = item("The component must not persist.", modality="forbidden", subject="persist")
    assert verify(obligation, snapshot(source)).status == EvidenceStatus.UNSUPPORTED
