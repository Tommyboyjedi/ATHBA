"""Source-mandated call shape cannot be replaced by model-owned defaults."""
import json
from pathlib import Path

import pytest

from core.development.behavior_contract_domain import BehaviorContract
from core.development.required_public_signature import (
    required_signatures,

)

from core.development.python_public_signature import production_signature_findings, scenario_signature_findings

FIXTURE = json.loads((Path(__file__).parent / "fixtures/campaign_shopping_basket.json").read_text())


def test_retained_contract_preserves_signature_even_if_model_omits_public_api():
    payload = dict(FIXTURE["contract"], public_api=[])
    contract = BehaviorContract.from_dict(payload)
    signatures = contract.required_signatures
    add = next(item for item in signatures if item.name == "add_item")
    assert add.parameters == ("name", "price")
    assert add.owner == "ShoppingBasket"
    assert add.source_quote == "add_item(name, price)"
    assert contract.to_dict()["required_signatures"]
    assert BehaviorContract.from_dict(contract.to_dict()).required_signatures == signatures


def test_model_cannot_replace_authoritative_serialized_signature():
    payload = BehaviorContract.from_dict(FIXTURE["contract"]).to_dict()
    payload["required_signatures"][0]["parameters"] = ["item_id", "quantity", "price"]
    with pytest.raises(ValueError, match="source"):
        BehaviorContract.from_dict(payload)


@pytest.mark.parametrize("args", [
    "self, item_id, quantity=1, price=0", "self, name, price=0",
    "self, name, price, quantity=1", "self, name, price, *args",
    "self, name, *, price",
])
def test_wrong_functional_shape_rejected_even_when_empty_basket_test_passes(args):
    source = "class ShoppingBasket:\n    def add_item(" + args + "):\n        pass\n"
    assert production_signature_findings(source, required_signatures(FIXTURE["contract"]["requirement_source"]))


def test_correct_shape_and_not_yet_implemented_operations_allowed():
    signatures = required_signatures(FIXTURE["contract"]["requirement_source"])
    assert production_signature_findings("class ShoppingBasket:\n    def add_item(self, name, price):\n        pass\n", signatures) == ()
    assert production_signature_findings("class ShoppingBasket:\n    pass\n", signatures) == ()


@pytest.mark.parametrize("call", [
    'b.add_item("bread", 1, 3)', 'b.add_item("bread")',
    'b.add_item("bread", quantity=1, price=3)', 'b.add_item(*values)',
])
def test_tester_cannot_adopt_drifted_api(call):
    source = 'from shopping_basket import ShoppingBasket\ndef test_basket():\n    b = ShoppingBasket()\n    ' + call + '\n'
    assert scenario_signature_findings(source, required_signatures(FIXTURE["contract"]["requirement_source"]))


def test_correct_two_argument_and_keyword_calls():
    source = 'from shopping_basket import ShoppingBasket\ndef test_basket():\n    b = ShoppingBasket()\n    b.add_item("bread", 3)\n    b.add_item(name="milk", price=2)\n'
    assert scenario_signature_findings(source, required_signatures(FIXTURE["contract"]["requirement_source"])) == ()


def test_generic_explicit_notation_without_example_argument_inference():
    values = required_signatures("Provide a Counter class. Calling increment(delta) changes state. increment(3) is an example.")
    assert [(item.owner, item.name, item.parameters) for item in values] == [("Counter", "increment", ("delta",))]
    assert required_signatures("A cart can hold a name and a price.") == ()

def test_public_candidate_accepted_by_executor_is_rejected_before_promotion(tmp_path):
    import subprocess
    from core.development.signature_candidate_validation import SignatureCandidateContext, validate_signature_candidate
    from core.execution.work_unit_gateway import WorkUnitExecutionResult
    root = tmp_path / "repository"
    root.mkdir()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
    git("init", "-q")
    (root / "shopping_basket.py").write_text(FIXTURE["production_source"])
    git("add", ".")
    git("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-qm", "wrong signature")
    revision = git("rev-parse", "HEAD")
    result = WorkUnitExecutionResult("work", True, "checks_passed", accepted_revision=revision,
                                     evidence_location="public-work-evidence")
    rejected = validate_signature_candidate(SignatureCandidateContext(root, "shopping_basket.py",
        required_signatures(FIXTURE["contract"]["requirement_source"]), "python"), result)
    assert not rejected.accepted and rejected.accepted_revision is None
    assert revision in rejected.error
    assert rejected.evidence_location == result.evidence_location
    assert git("rev-parse", "HEAD") == revision


def test_legacy_signature_authority_roundtrips_without_entering_semantic_review():
    from dataclasses import replace
    from tests.development.test_strict_microcycle import initial_state
    from core.development.microcycle_domain import TestScenarioDraft
    from core.development.behavior_completion import BehaviorCompletionCommand, BehaviorCompletionService
    from core.development.provider_behavior_reviewer import _request
    signatures = required_signatures(FIXTURE["contract"]["requirement_source"])
    state = initial_state()
    state = replace(state, scenario_draft=replace(state.scenario_draft, required_signatures=signatures))
    restored = TestScenarioDraft.from_dict(state.scenario_draft.to_dict())
    assert restored.required_signatures == signatures
    packet = BehaviorCompletionService._request(BehaviorCompletionCommand(state))
    assert packet.required_signatures == signatures
    assert "required_signatures" not in json.loads(_request(packet).prompt)

def test_final_api_shape_checks_wrong_defaults_without_lexical_rejection():
    from core.development.feature_signature_evidence import signature_evidence
    from core.development.specification_evidence_policy import RevisionFile, SpecificationSnapshot
    source = FIXTURE["contract"]["requirement_source"]
    for implementation in [FIXTURE["production_source"]]:
        evidence = signature_evidence(source, SpecificationSnapshot("revision", (RevisionFile("shopping_basket.py", implementation),)), "python")
        assert evidence["answer"] == "NO"
    correct = "class ShoppingBasket:\n    def add_item(self, name, price):\n        pass\n    def item_count(self):\n        return 0\n    def total_price(self):\n        return 0\n"
    assert signature_evidence(source, SpecificationSnapshot("revision", (RevisionFile("shopping_basket.py", correct),)), "python")["answer"] == "YES"


@pytest.mark.asyncio
async def test_source_deduction_omission_uses_existing_single_repair():
    from core.development.behavior_contract_coordinator import RequirementClausePlanner
    from core.execution.reasoning_gateway import ReasoningResult
    requests = []
    class Gateway:
        async def reason(self, request):
            requests.append(request)
            text = "Add one item." if len(requests) == 1 else "Calling add_item(name, price) adds one item."
            return ReasoningResult(json.dumps({"clauses": [{"ref": "source", "text": text, "kind": "behavior", "evidence_kind": "test"}]}))
    result = await RequirementClausePlanner(Gateway()).plan_clauses(
        project_id="project", requirement_text="Provide a Basket class. Calling add_item(name, price) adds an item.")
    assert len(requests) == 2
    assert result.attempts[0].validation_error
    assert "add_item(name, price)" in result.clauses[0].text


def test_generic_signature_validation_fails_closed_for_unregistered_language():
    from core.development.public_signature_validation import production_signature_findings
    from core.development.required_public_signature import SignatureInspection
    signatures = required_signatures("Calling add_item(name, price) adds an item.")
    assert production_signature_findings(SignatureInspection("anything", signatures), "unsupported")


def test_generic_contract_module_has_no_target_language_parser():
    import ast
    import core.development.required_public_signature as contract
    imports = [item for item in ast.walk(ast.parse(Path(contract.__file__).read_text())) if isinstance(item, ast.Import)]
    assert not any(alias.name == "ast" for item in imports for alias in item.names)


@pytest.mark.parametrize("source", [
    "class ShoppingBasket(Base):\n    def add_item(self, name, price):\n        pass\n",
    "class ShoppingBasket:\n    def add_item(self, name, price):\n        pass\nShoppingBasket.add_item = replacement\n",
    "class ShoppingBasket:\n    def add_item(self, name, price):\n        pass\nsetattr(ShoppingBasket, 'add_item', replacement)\n",
])
def test_dynamic_api_replacement_cannot_bypass_declared_signature(source):
    signatures = required_signatures(FIXTURE["contract"]["requirement_source"])
    assert production_signature_findings(source, signatures)


@pytest.mark.parametrize("source", [
    "Optional operation preview(value).",
    "The operation preview(value) is not required.",
    "Do not implement operation delete(name).",
    "The function delete(name) must not be implemented.",
    "Calling preview(value) is out of scope.",
    "Optional API: Calling preview(value).",
    "Calling Widget.preview(value) is not required.",
])
def test_non_required_source_declaration_cannot_invent_required_operation(source):
    assert required_signatures(source) == ()


def test_repeated_declaration_uses_its_own_source_modality():
    signatures = required_signatures("Calling preview(value, scale) is optional. Calling preview(value) must return the supplied value.")
    assert len(signatures) == 1
    assert signatures[0].parameters == ("value",)


def test_old_frozen_signature_metadata_does_not_expand_narrow_resume_task():
    from dataclasses import replace
    from core.development.scenario_drafting import _validate_resume
    from core.development.scenario_drafting_domain import ScenarioDraftRunState
    from tests.development.test_scenario_drafting import request
    from tests.development.test_strict_microcycle import initial_state
    requested = replace(request("catalog"), required_signatures=required_signatures("Provide a Widget class. Calling grow() changes the count."))
    approved = initial_state()
    state = ScenarioDraftRunState(requested.scenario_id, requested.ticket.step_id,
        requested.source_requirement_refs, requested.language_id, requested.test_framework,
        requested.allowed_test_path, requested.development_base_revision,
        approved_microcycle=approved, status="approved", semantic_annotations=requested.semantic_annotations)
    restored = ScenarioDraftRunState.from_dict(state.to_dict())
    _validate_resume(restored, requested)
    assert "required_signatures" not in __import__("core.development.scenario_drafting",fromlist=["_tester_objective"])._tester_objective(requested,None,None)
    authoritative = replace(approved, scenario_draft=replace(approved.scenario_draft, required_signatures=requested.required_signatures))
    _validate_resume(replace(restored, approved_microcycle=authoritative), requested)
    assert restored.attempts == state.attempts
