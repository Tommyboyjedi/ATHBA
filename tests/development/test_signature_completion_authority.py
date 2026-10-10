"""Call-shape uncertainty is never a non-functional assurance exemption."""
import pytest

from core.development.assurance_completion import CompletionAuthority, assess_completion
from core.development.feature_signature_evidence import signature_evidence
from core.development.specification_evidence_policy import EvidenceStatus, RevisionFile, SpecificationSnapshot

SOURCE = "Provide a Basket class. Calling add_item(name, price) adds one item."
REVISION = "a" * 40


def evidence(code):
    return signature_evidence(SOURCE,
        SpecificationSnapshot(REVISION, (RevisionFile("basket.py", code),)), "python")


@pytest.mark.parametrize("declaration", [
    "def add_item(self, item, quantity=1, price=1): pass",
    "def add_item(self, item, cost): pass",
])
def test_decorated_call_shape_uncertainty_cannot_complete_behavior(declaration):
    result = evidence("from dataclasses import dataclass\n@dataclass\nclass Basket:\n    " + declaration + "\n")
    assert result["evidence_status"] == EvidenceStatus.UNSUPPORTED.value
    completion = assess_completion(CompletionAuthority(({"answer": "YES"}, result), SOURCE))
    assert not completion.behaviorally_complete
    assert not completion.unproven_assurance


@pytest.mark.parametrize("code", [
    "class Basket:\n    def insert(self, item, cost): pass\n",
    "class Cart:\n    def add_item(self, item, cost): pass\n",
])
def test_source_spelling_resolution_is_explicitly_deferred_only_to_naming(code):
    result = evidence(code)
    assert result["answer"] == "NOT_APPLICABLE"
    assert result["evidence_status"] == EvidenceStatus.NAMING.value
    assert result["findings"] == []
    assert result["deferred_signatures"] == result["required_signatures"]
    completion = assess_completion(CompletionAuthority(({"answer": "YES"}, result), SOURCE))
    assert completion.fully_proven
    assert not completion.unproven_assurance


@pytest.mark.parametrize("code", [
    "class Basket:\n    def add_item(self, a, b, c=1): pass\n",
    "class Basket:\n    def add_item(self, a, b): pass\n    def add_item(self, a, b): pass\n",
    "class Basket:\n    pass\nexec('pass')\n",
])
def test_violated_or_ambiguous_shapes_cannot_be_delegated(code):
    result = evidence(code)
    assert result["answer"] == "NO"
    assert not assess_completion(CompletionAuthority((result,), SOURCE)).behaviorally_complete


@pytest.mark.parametrize("mutation", [
    {"deferred_signatures": []},
    {"deferred_signatures": [{"owner": "Other", "name": "add_item",
       "parameters": ["name", "price"], "source_quote": "add_item(name, price)"}]},
    {"required_signatures": []},
    {"findings": ["call shape unproven"]},
    {"blocked_reason": "unsupported"},
    {"revision": "unavailable"},
])
def test_naming_deferral_requires_exact_source_authority_and_no_shape_findings(mutation):
    result = evidence("class Basket:\n    def insert(self, item, cost): pass\n")
    result.update(mutation)
    assert not assess_completion(CompletionAuthority((result,), SOURCE)).behaviorally_complete


def test_mixed_lexical_deferral_cannot_hide_a_known_shape_violation():
    source = SOURCE + " Calling total() returns the current total."
    snapshot = SpecificationSnapshot(REVISION, (RevisionFile("basket.py",
        "class Basket:\n    def insert(self, item, cost): pass\n    def total(self, extra=1): return 0\n"),))
    result = signature_evidence(source, snapshot, "python")
    assert result["deferred_signatures"]
    assert result["evidence_status"] == EvidenceStatus.FAIL.value
    assert not assess_completion(CompletionAuthority((result,), source)).behaviorally_complete


def test_naming_deferral_is_not_created_from_incomplete_snapshot():
    snapshot = SpecificationSnapshot(REVISION,
        (RevisionFile("basket.py", "class Basket:\n    pass\n"),), complete=False)
    result = signature_evidence(SOURCE, snapshot, "python")
    assert result["answer"] == "NO"
    assert not result["deferred_signatures"]
    assert not assess_completion(CompletionAuthority((result,), SOURCE)).behaviorally_complete


def test_persisted_records_retain_the_behavioral_and_lexical_distinction():
    import json
    for code, complete in (
        ("class Basket:\n    def insert(self, item, cost): pass\n", True),
        ("@unknown\nclass Basket:\n    def add_item(self, item, cost): pass\n", False),
    ):
        result = json.loads(json.dumps(evidence(code)))
        assert assess_completion(CompletionAuthority((result,), SOURCE)).behaviorally_complete == complete
