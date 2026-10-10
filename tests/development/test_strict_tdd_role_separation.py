"""Strict role boundaries and later source-grounded lexical reconciliation."""
import json
from dataclasses import replace
from types import SimpleNamespace
import pytest
from core.development.required_public_signature import required_signatures
from core.development.scenario_drafting import _tester_objective
from tests.development.test_scenario_drafting import request
from core.development.python_public_signature import production_signature_findings
from core.development.post_behavior_assessment import NamingAssessmentInput, NamingMaterial, parse_naming_decision
from core.development.post_behavior_authority import PythonPostBehaviorAuthority, RenameAuthorityRequest
from core.development.post_behavior_slice import PythonProductionSlice, SliceRequest
from core.development.specification_evidence_policy import RevisionFile, SpecificationSnapshot
from core.development.post_behavior_adapters import focused_naming_material

def test_fresh_tester_does_not_receive_global_api_or_completed_tests():
    base = request("catalog")
    base = replace(base, required_signatures=required_signatures("Calling future_api(secret_name) changes another behavior."),
        repository_facts=replace(base.repository_facts, test_excerpt="UNRELATED_COMPLETED_TEST",
            visible_paths=(*base.repository_facts.visible_paths, "unrelated.py")))
    payload = json.loads(_tester_objective(base, None, None))
    assert "required_signatures" not in payload
    assert "UNRELATED_COMPLETED_TEST" not in json.dumps(payload)
    assert "unrelated.py" not in json.dumps(payload)
    assert payload["ticket"]["behavior"] == base.ticket.focused_behavior
    assert base.ticket.production_path in json.dumps(payload)

def test_developer_task_has_no_source_signature_authority_or_revision_essay():
    from core.development.strict_microcycle import DeveloperFrontierRequest, DeveloperFrontierWorkUnitFactory
    from core.development.microcycle_domain import FrontierMaterialisationRequest
    from tests.development.test_strict_microcycle import initial_state
    from core.development.python_pytest_adapter import PythonPytestAdapter
    state = initial_state()
    adapter = PythonPytestAdapter()
    artifact = adapter.materialise_frontier(FrontierMaterialisationRequest(state.model,state.fragments,state.frontier,"red"))
    diagnostic = SimpleNamespace(kind="collection_failure",message="ImportError: absent",facts=())
    packet = DeveloperFrontierRequest("project","widget.py",artifact,SimpleNamespace(diagnostic=diagnostic),
        "red","base",1,required_signatures("Calling future_api(secret_name) changes another behavior."))
    unit = DeveloperFrontierWorkUnitFactory().build(packet)
    payload = json.loads(unit.objective)
    assert "required_signatures" not in payload
    assert "secret_name" not in unit.objective
    assert "development_base_context" not in payload
    assert payload["materialised_active_frontier_test"] == artifact.complete_source
    assert "Do not modify" in payload["task"]
    assert unit.allowed_paths == ["widget.py"]
    assert unit.acceptance.required_artifacts == ["widget.py"]

def test_equivalent_parameter_names_are_not_behavioral_signature_failure():
    sig = required_signatures("Provide a ShoppingBasket class. Calling add_item(name, price) adds an item.")
    code = "class ShoppingBasket:\n    def add_item(self, item_id, cost):\n        return item_id, cost\n"
    assert production_signature_findings(code, sig, complete=True) == ()

@pytest.mark.parametrize("parameters", ["self, item_id, quantity=1, price=0", "self, item_id, cost=0"])
def test_changed_call_domain_remains_a_final_behavioral_shape_failure(parameters):
    sig = required_signatures("Provide a ShoppingBasket class. Calling add_item(name, price) adds an item.")
    assert production_signature_findings("class ShoppingBasket:\n    def add_item("+parameters+"):\n        pass\n",sig,complete=True)

PRODUCTION = "class Basket:\n    def add(self, item_id, cost):\n        self.value = cost\n        return item_id, cost\n"
TEST = "from app import Basket\ndef test_price():\n    b = Basket()\n    assert b.add('bread', cost=3) == ('bread', 3)\n"
def snapshot(rev, source=PRODUCTION, test=TEST):
    return SpecificationSnapshot(rev,(RevisionFile("app.py",source),RevisionFile("tests/test_app.py",test)))

def test_source_parameter_authority_reaches_naming_only():
    contract = SimpleNamespace(public_api=[],source_clauses=[],requirement_source="Provide a Basket class. Calling add(name, price) adds an item.")
    material = focused_naming_material(SimpleNamespace(contract=contract))
    assert "price" in material.required_identifiers
    assert material.required_signatures[0].parameters == ("name","price")

def test_parameter_rename_is_exact_and_preserves_positional_and_keyword_behavior():
    base = snapshot("accepted")
    focused = PythonProductionSlice().derive(SliceRequest(snapshot("entry",""),base))
    after = snapshot("candidate",PRODUCTION.replace("cost","price"),TEST.replace("cost=","price="))
    authority = PythonPostBehaviorAuthority().rename(RenameAuthorityRequest(base,after,focused,
        __import__("core.development.post_behavior_assessment",fromlist=["IdentifierRename"]).IdentifierRename("cost","price")))
    assert authority.passed,authority.reason
    scope={};exec(after.files[0].source,scope)
    assert scope["Basket"]().add("bread",3)==("bread",3)
    assert scope["Basket"]().add("bread",price=3)==("bread",3)
    bad=snapshot("bad",after.files[0].source.replace("self.value = price","self.value = 0"),after.files[1].source)
    assert not PythonPostBehaviorAuthority().rename(RenameAuthorityRequest(base,bad,focused,
        __import__("core.development.post_behavior_assessment",fromlist=["IdentifierRename"]).IdentifierRename("cost","price"))).passed

@pytest.mark.parametrize("source",[
    "def add(cost):\n    price = 1\n    return cost + price\n",
    "def add(cost):\n    return lambda: cost\n",
    "def add(cost):\n    return locals()['cost']\n",
])
def test_unsafe_parameter_rename_fails_closed(source):
    base=snapshot("accepted",source)
    focused=PythonProductionSlice().derive(SliceRequest(snapshot("entry",""),base))
    after=snapshot("candidate",source.replace("cost","price"))
    result=PythonPostBehaviorAuthority().rename(RenameAuthorityRequest(base,after,focused,
        __import__("core.development.post_behavior_assessment",fromlist=["IdentifierRename"]).IdentifierRename("cost","price")))
    assert not result.passed

def test_naming_no_cannot_hide_explicit_parameter_mismatch():
    material=NamingMaterial("Calling add(name, price)",("Basket","add","name","price"),
        required_signatures("Provide a Basket class. Calling add(name, price) adds an item."))
    base=snapshot("accepted")
    focused=PythonProductionSlice().derive(SliceRequest(snapshot("entry",""),base))
    with pytest.raises(ValueError,match="parameter"):
        parse_naming_decision("NO",NamingAssessmentInput(material,focused))
    assert parse_naming_decision("cost -> price",NamingAssessmentInput(material,focused)).rename.required_name=="price"

def test_named_call_and_value_semantics_expose_quantity_drift_without_name_comparison():
    fixture=json.loads((__import__("pathlib").Path(__file__).parent/"fixtures/campaign_shopping_basket.json").read_text())
    namespace={};exec(fixture["production_source"],namespace)
    basket=namespace["ShoppingBasket"]()
    basket.add_item("bread",3);basket.add_item("milk",2)
    assert basket.item_count()==2
    assert basket.total_price()!=5  # Observable failure, unrelated to spelling.
    correct={}
    exec("class Basket:\n    def add_item(self, item_id, cost):\n        return item_id,cost\n",correct)
    assert correct["Basket"]().add_item("bread",3)==("bread",3)

def test_missing_original_operation_can_only_be_closed_in_naming():
    from core.development.feature_signature_evidence import signature_evidence
    source="Provide a Basket class. Calling add(name, price) adds an item."
    code="class Basket:\n    def insert(self,item_id,cost):\n        return item_id,cost\n"
    snap=snapshot("a"*40,code)
    evidence=signature_evidence(source,snap,"python")
    assert evidence["answer"]=="NOT_APPLICABLE" and evidence["evidence_status"]=="deferred_to_naming"
    from core.development.assurance_completion import CompletionAuthority, assess_completion
    assert assess_completion(CompletionAuthority(({"answer":"YES"},evidence),source)).behaviorally_complete
    material=NamingMaterial(source,("Basket","add","name","price"),required_signatures(source))
    focused=PythonProductionSlice().derive(SliceRequest(snapshot("entry",""),snap))
    with pytest.raises(ValueError,match="operation"):
        parse_naming_decision("NO",NamingAssessmentInput(material,focused))
    assert parse_naming_decision("insert -> add",NamingAssessmentInput(material,focused)).rename

@pytest.mark.parametrize("test",[
    "from app import Basket\ndef test_one():\n    b=Basket()\n    alias=b.add\n    assert alias('x',cost=3)\n",
    "from app import Basket\ndef test_one():\n    b=Basket()\n    assert b.add('x',**{'cost':3})\n",
    "def test_one():\n    assert unknown.add('x',cost=3)\n",
])
def test_unresolved_keyword_parameter_references_fail_closed(test):
    from core.development.post_behavior_assessment import IdentifierRename
    base=snapshot("accepted",test=test)
    focused=PythonProductionSlice().derive(SliceRequest(snapshot("entry",""),base))
    after=snapshot("candidate",PRODUCTION.replace("cost","price"),test.replace("cost=","price="))
    assert not PythonPostBehaviorAuthority().rename(RenameAuthorityRequest(
        base,after,focused,IdentifierRename("cost","price"))).passed

def test_parameter_and_field_same_spelling_are_ambiguous_and_fail_closed():
    from core.development.post_behavior_assessment import IdentifierRename
    code="class Basket:\n    def add(self,item_id,cost):\n        self.cost=cost\n        return 'cost',cost\n"
    renamed=code.replace("item_id,cost","item_id,price").replace("self.cost=cost","self.cost=price").replace("'cost',cost","'cost',price")
    base=snapshot("accepted",code)
    focused=PythonProductionSlice().derive(SliceRequest(snapshot("entry",""),base))
    after=snapshot("candidate",renamed,TEST.replace("cost=","price="))
    assert not PythonPostBehaviorAuthority().rename(RenameAuthorityRequest(base,after,focused,IdentifierRename("cost","price"))).passed

def test_parameter_rename_preserves_literal_text():
    from core.development.post_behavior_assessment import IdentifierRename
    code = PRODUCTION.replace("return item_id, cost", "return 'cost', cost")
    renamed = code.replace("item_id, cost):","item_id, price):").replace("self.value = cost","self.value = price").replace("'cost', cost","'cost', price")
    base = snapshot("accepted",code)
    focused = PythonProductionSlice().derive(SliceRequest(snapshot("entry",""),base))
    assert PythonPostBehaviorAuthority().rename(RenameAuthorityRequest(
        base,snapshot("candidate",renamed,TEST.replace("cost=","price=")),focused,IdentifierRename("cost","price"))).passed

def test_interaction_bindings_are_scoped_to_selected_behavior():
    from core.development.python_pytest_adapter import PythonPytestAdapter
    from core.development.strict_tdd_feature_execution_advance import _semantic_expression_sources
    request=SimpleNamespace(behavior=SimpleNamespace(observable_outcome="RunningTotal.total() starts zero",test_hint="total() returns zero"),
        contract=SimpleNamespace(public_api=("RunningTotal.total()","RunningTotal.add(amount)")))
    sources=_semantic_expression_sources(PythonPytestAdapter(),request,())
    assert any("total" in item for item in sources)
    assert not any("add" in item or "amount" in item for item in sources)

def test_parameter_lexical_mismatch_does_not_fail_pre_naming_gatekeeper_shape():
    from core.development.feature_signature_evidence import signature_evidence
    source="Provide a Basket class. Calling add(name, price) adds an item."
    assert signature_evidence(source,snapshot("accepted"),"python")["answer"]=="YES"

def test_signature_gatekeeper_evidence_is_stable_across_durable_json_roundtrip():
    from core.development.feature_signature_evidence import signature_evidence
    source="Provide a Basket class. Calling add(name, price) adds an item."
    evidence=signature_evidence(source,snapshot("accepted"),"python")
    assert evidence == json.loads(json.dumps(evidence))
