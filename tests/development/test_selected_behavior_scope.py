"""Selected interface form is behavioral; parameter spelling is not."""
from types import SimpleNamespace
from core.development.python_pytest_adapter import PythonCandidateAssessmentFactory
from core.development.scenario_drafting import _authoring_contract
from core.development.microcycle_domain import ScenarioSourceCandidate
from tests.development.test_scenario_drafting import request

def assessed(source):
    base=request("basket")
    candidate=ScenarioSourceCandidate("scenario","REQ1","python","tests/test_app.py",source,"tests/test_app.py::test_one","candidate","memory")
    current=SimpleNamespace(symbol="add_item",interaction="invoke",source_expression="add_item(arg0,arg1)",result=None,
        receiver_owner="Basket",argument_count=2)
    return PythonCandidateAssessmentFactory().assess(SimpleNamespace(candidate=candidate,production_path="app.py",
        contract=_authoring_contract(base),semantic_annotations=(current,)))

def test_current_instance_behavior_cannot_be_replaced_by_module_helper_with_extra_receiver():
    result=assessed("import app as sb\n\ndef test_one():\n    b=sb.Basket()\n    sb.add_item(b,'Item',-1)\n    assert b.total_price()==0\n")
    assert not result.accepted,"Module helper is not the selected instance operation"
    assert any(x.code=="behavior_call_shape" for x in result.issues)

def test_current_instance_behavior_rejects_direct_imported_free_function():
    result=assessed("from app import Basket,add_item\n\ndef test_one():\n    b=Basket()\n    add_item('Item',3)\n    assert b.total_price()==3\n")
    assert not result.accepted,"The argument count alone does not prove the required receiver form"

def test_selected_member_accepts_equivalent_keyword_spelling():
    result=assessed("from app import Basket\n\ndef test_one():\n    b=Basket()\n    b.add_item('Item',cost=3)\n    assert b.total_price()==3\n")
    assert result.accepted,result.repair_feedback()

def test_selected_member_does_not_reject_only_for_alternate_operation_spelling():
    result=assessed("from app import Basket\n\ndef test_one():\n    b=Basket()\n    b.insert('Item',3)\n    assert b.total_price()==3\n")
    assert result.accepted,result.repair_feedback()


def test_current_receiver_metadata_contains_no_future_signature_or_parameter_authority():
    import json
    from core.development.python_pytest_adapter import PythonPytestAdapter
    from core.development.required_public_signature import required_signatures
    from core.development.semantic_api_annotations import SemanticApiAnnotation
    from core.development.strict_tdd_feature_execution_advance import _semantic_annotations
    adapter = PythonPytestAdapter()
    executor = SimpleNamespace(drafting=SimpleNamespace(adapter_catalog=SimpleNamespace(for_language=lambda _: adapter)))
    text = "Provide a Basket class. Calling add_item(name, price) adds an item. Calling future_operation(secret_name) does another thing."
    req = SimpleNamespace(behavior=SimpleNamespace(observable_outcome="add_item('bread', 3) records one item", test_hint="add_item('bread', 3)"),
                          contract=SimpleNamespace(public_api=("add_item(name, price)", "future_operation(secret_name)"),
                                                   required_signatures=required_signatures(text)))
    annotations = _semantic_annotations(executor, req, "python", ())
    selected = next(item for item in annotations if item.symbol == "add_item")
    assert selected.receiver_owner == "Basket"
    assert selected.argument_count == 2
    payload = json.dumps([item.to_dict() for item in annotations])
    assert "future_operation" not in payload and "secret_name" not in payload
    assert "parameters" not in payload
    assert SemanticApiAnnotation.from_dict(selected.to_dict()) == selected


def test_developer_diagnostic_uses_only_current_observation_relative_paths(tmp_path):
    from core.development.strict_microcycle import _workspace_relative_diagnostic
    observed = tmp_path / "current-observation"
    message = f"{observed}/tests/test_app.py:3 failed; {observed}-other/app.py:2"
    result = _workspace_relative_diagnostic(message, observed)
    assert result == f"tests/test_app.py:3 failed; {observed}-other/app.py:2"


import pytest

@pytest.mark.asyncio
async def test_normal_frontier_observation_and_developer_submission_do_not_expose_temporary_root(tmp_path):
    import json
    from tests.development.test_strict_microcycle import (
        MemoryStore, CandidateRepository, Gateway, initial_state, request, regression,
    )
    from core.development.strict_microcycle import StrictMicrocycleService, StrictMicrocycleDependencies
    from core.development.strict_tdd_transitions import MicrocycleTransitionKind
    from core.development.python_pytest_adapter import PythonPytestAdapter
    store = MemoryStore()
    candidates = CandidateRepository(tmp_path, {"base": ""})
    gateway = Gateway(["type"])
    catalog = type("Catalog", (), {"for_language": lambda self, language: PythonPytestAdapter()})()
    service = StrictMicrocycleService(StrictMicrocycleDependencies(store, candidates, gateway, catalog, regression()))
    current = request(tmp_path, initial_state())
    await service.advance(current)
    observed = await service.advance(current)
    assert observed.kind == MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED
    diagnostic = observed.state.boundary_evidence[-1].diagnostic
    assert "widget.py" in diagnostic.message
    assert str(tmp_path / "candidate-0") not in diagnostic.message
    await service.advance(current)
    assert gateway.units
    payload = json.loads(gateway.units[0][0].objective)
    assert str(tmp_path / "candidate-0") not in payload["boundary_diagnostic"]["message"]
    assert "required_signatures" not in payload
