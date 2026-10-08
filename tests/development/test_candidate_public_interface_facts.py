"""Source interface facts are harness-only; a candidate cannot redefine a query."""
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from core.development.python_pytest_adapter import PythonCandidateAssessmentFactory
from core.development.scenario_drafting import (
    ScenarioDraftWorkUnitFactory, ScenarioDraftWorkUnitRequest, _authoring_contract,
)
from core.development.semantic_api_annotations import SemanticApiAnnotation
from core.development.microcycle_domain import ScenarioSourceCandidate
from tests.development.test_scenario_drafting import (
    accepted, approval, binding, components, request,
)

FACTS = (
    SemanticApiAnnotation("add", "invoke", "add(arg0)", None, "Catalog", 1),
    SemanticApiAnnotation("item_count", "invoke", "item_count()", None, "Catalog", 0),
    SemanticApiAnnotation("future_operation", "invoke", "future_operation(arg0)", None, "Catalog", 1),
)


def assess(source):
    candidate = ScenarioSourceCandidate("scenario", "REQ1", "python", "tests/test_catalog.py",
        source, "tests/test_catalog.py::test_one", "candidate", "memory")
    return PythonCandidateAssessmentFactory().assess(SimpleNamespace(
        candidate=candidate, production_path="catalog.py", contract=_authoring_contract(request("catalog")),
        semantic_annotations=(), candidate_interface_facts=FACTS))


def test_retained_property_query_cannot_replace_a_source_operation():
    result = assess("from catalog import Catalog\n\ndef test_one():\n    c=Catalog()\n    assert c.item_count==0\n")
    assert not result.accepted
    assert any(i.code == "behavior_call_shape" for i in result.issues)


def test_setup_calls_are_checked_even_if_the_current_behavior_is_a_query():
    result = assess("from catalog import Catalog\n\ndef test_one():\n    c=Catalog()\n    c.add('a',2,10)\n    assert c.item_count()==1\n")
    assert not result.accepted


def test_invoked_public_query_and_current_setup_pass():
    result = assess("from catalog import Catalog\n\ndef test_one():\n    c=Catalog()\n    c.add('a')\n    assert c.item_count()==1\n")
    assert result.accepted, result.repair_feedback()


def test_unrelated_owner_or_equivalent_identifier_is_not_lexically_rejected():
    result = assess("from catalog import Catalog, Other\n\ndef test_one():\n    c=Catalog()\n    other=Other()\n    assert other.item_count==0\n    assert c.count_items()==0\n")
    assert result.accepted, result.repair_feedback()


def test_private_interface_facts_never_enter_fresh_tester_semantic_context():
    base = replace(request("catalog"), candidate_interface_facts=FACTS)
    task = ScenarioDraftWorkUnitFactory().build(ScenarioDraftWorkUnitRequest(base, 1, None)).objective
    assert "candidate_interface_facts" not in task
    assert "future_operation" not in task
    assert "arg0" not in task
    assert "required_signatures" not in task


@pytest.mark.asyncio
async def test_property_repair_uses_precise_feedback_and_keeps_attempt_authority_on_resume():
    base = replace(request("catalog"), candidate_interface_facts=FACTS)
    bad = "from catalog import Catalog\n\ndef test_one():\n    c=Catalog()\n    assert c.item_count==0\n"
    good = bad.replace("c.item_count==0", "c.item_count()==0")
    service, gateway, reasoning, _ = components(
        [accepted("d1", "b"*40, "d1"), accepted("d2", "c"*40, "d2")],
        [approval("SRC-CATALOG")], {"b"*40: bad, "c"*40: good})
    first = await service.draft(base, binding())
    assert first.state.attempts[0].status == "candidate_invalid"
    assert reasoning.requests == []
    state_type = type(first.state)
    assert state_type.from_dict(first.state.to_dict()) == first.state
    changed = replace(base, candidate_interface_facts=FACTS[:1])
    with pytest.raises(ValueError, match="stale scenario"):
        await service.draft(changed, binding())
    await service.submit_candidate(base, binding())
    completed = await service.draft(base, binding())
    assert completed.approved
    assert len(completed.state.attempts) == 2
    repair = json.loads(gateway.calls[1][0].objective)
    assert repair["previous_candidate"]["source"] == bad
    assert "invok" in repair["repair_feedback"].lower()
    assert "future_operation" not in gateway.calls[1][0].objective



def test_known_source_operation_cannot_be_annotated_as_a_property_read():
    from core.development.required_public_signature import required_signatures
    from core.development.strict_tdd_feature_execution_advance import _semantic_annotations
    class Adapter:
        def extract_api_expressions(self, text):
            return ("c.item_count",)
        def describe_api_expression(self, request):
            return SemanticApiAnnotation("item_count", "read", request.source_expression)
    adapter = Adapter()
    executor = SimpleNamespace(drafting=SimpleNamespace(
        adapter_catalog=SimpleNamespace(for_language=lambda _: adapter)))
    req = SimpleNamespace(
        behavior=SimpleNamespace(observable_outcome="c.item_count == 0", test_hint="c.item_count"),
        contract=SimpleNamespace(public_api=(), required_signatures=required_signatures(
            "Provide a Catalog class. Calling item_count() returns the count.")))
    annotations = _semantic_annotations(executor, req, "language", ())
    assert len(annotations) == 1
    assert annotations[0].interaction == "invoke"
    assert annotations[0].source_expression == "item_count()"


def test_public_free_function_argument_count_is_not_skipped():
    candidate = ScenarioSourceCandidate("scenario", "REQ1", "python", "tests/test_catalog.py",
        "from catalog import lookup\n\ndef test_one():\n    assert lookup('a',2)==2\n",
        "tests/test_catalog.py::test_one", "candidate", "memory")
    result = PythonCandidateAssessmentFactory().assess(SimpleNamespace(
        candidate=candidate, production_path="catalog.py", contract=_authoring_contract(request("catalog")),
        semantic_annotations=(), candidate_interface_facts=(
            SemanticApiAnnotation("lookup", "invoke", "lookup(arg0)", None, None, 1),)))
    assert any(i.code == "behavior_call_shape" for i in result.issues)
