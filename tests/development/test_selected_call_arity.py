"""Selected source call shape remains behavioral, without lexical name authority."""
import json
from dataclasses import replace

import pytest

from core.development.semantic_api_annotations import SemanticApiAnnotation
from tests.development.test_selected_behavior_scope import assessed
from tests.development.test_scenario_drafting import (
    accepted, approval, binding, components, request,
)


@pytest.mark.parametrize("arguments", ["'item1', 1, 10.0", "'bread', 3, 1.0", "'x'"])
def test_selected_owned_call_cannot_change_source_argument_count(arguments):
    result = assessed(
        f"from app import Basket\n\ndef test_one():\n"
        f"    b=Basket()\n    b.add_item({arguments})\n"
        "    assert b.total_price()==5\n"
    )
    assert not result.accepted
    assert any(item.code == "behavior_call_shape" for item in result.issues)
    assert "2" in result.repair_feedback()


@pytest.mark.parametrize("source", [
    "from app import Basket as B\n\ndef test_one():\n    b=B()\n    b.add_item('x',1,2)\n    assert b.total_price()==2\n",
    "import app as sb\n\ndef test_one():\n    b=sb.Basket()\n    b.add_item('x',1,2)\n    assert b.total_price()==2\n",
    "from app import Basket\n\ndef test_one():\n    assert Basket().add_item('x',1,2)==2\n",
])
def test_import_alias_or_inline_constructor_preserves_selected_receiver(source):
    assert not assessed(source).accepted


@pytest.mark.parametrize("arguments", ["'x', cost=3", "item_id='x', cost=3", "'x', 3"])
def test_lexical_parameter_spelling_is_not_arity_authority(arguments):
    result = assessed(
        f"from app import Basket\n\ndef test_one():\n"
        f"    b=Basket()\n    b.add_item({arguments})\n"
        "    assert b.total_price()==3\n"
    )
    assert result.accepted, result.repair_feedback()


def test_unrelated_receiver_is_not_treated_as_the_selected_source_owner():
    source = (
        "from app import Basket, Other\n\ndef test_one():\n"
        "    b=Basket()\n    other=Other()\n    other.add_item('x',1,2)\n"
        "    b.add_item('x',3)\n    assert b.total_price()==3\n"
    )
    assert assessed(source).accepted


def test_rebound_receiver_is_not_inferred_from_an_earlier_constructor():
    source = (
        "from app import Basket, Other\n\ndef test_one():\n"
        "    b=Basket()\n    b=Other()\n    b.add_item('x',1,2)\n"
        "    assert b.total_price()==2\n"
    )
    assert not any(item.code == "behavior_call_shape" for item in assessed(source).issues)


def test_dynamic_argument_expansion_cannot_claim_selected_arity():
    source = (
        "from app import Basket\n\ndef test_one():\n"
        "    b=Basket()\n    b.add_item(*('x',1,2))\n"
        "    assert b.total_price()==2\n"
    )
    assert any(item.code == "behavior_call_shape" for item in assessed(source).issues)


@pytest.mark.asyncio
async def test_selected_arity_rejection_enters_existing_candidate_repair_before_intent_review():
    base = replace(request("catalog"), semantic_annotations=(
        SemanticApiAnnotation("add", "invoke", "add(value)", None, "Catalog", 1),
    ))
    invalid = (
        "from catalog import Catalog\n\ndef test_catalog():\n"
        "    c=Catalog()\n    c.add('a',1,10)\n    assert c.item_id('a')=='a'\n"
    )
    repaired = invalid.replace("c.add('a',1,10)", "c.add('a')")
    service, gateway, reasoning, _ = components(
        [accepted("catalog-ticket--scenario-draft-1", "b"*40, "draft-1"), accepted("catalog-ticket--scenario-draft-2", "c"*40, "draft-2")],
        [approval("SRC-CATALOG")], {"b"*40: invalid, "c"*40: repaired},
    )
    first = await service.draft(base, binding())
    assert first.state.attempts[0].status == "candidate_invalid"
    assert reasoning.requests == []
    second = await service.submit_candidate(base, binding())
    assert second.state.attempts[-1].status == "candidate_submitted"
    completed = await service.draft(base, binding())
    assert completed.approved
    assert len(second.state.attempts) == 2
    assert len(reasoning.requests) == 1
    repair = json.loads(gateway.calls[1][0].objective)
    assert repair["previous_candidate"]["source"] == invalid
    assert "requires 1 explicit arguments" in repair["repair_feedback"]
    assert "required_signatures" not in repair
    assert "naming_authority" not in repair


@pytest.mark.parametrize("body", [
    "b=Other()\n    b.add_item('x',1,2)",
    "B=Other\n    b=B()\n    b.add_item('x',1,2)",
    "if condition:\n        b=Other()\n    b.add_item('x',1,2)",
])
def test_shadowed_or_conditional_ownership_does_not_establish_a_call_shape(body):
    source = (
        "from app import Basket as B, Other\n\ndef test_one():\n"
        "    b=B()\n    " + body + "\n    assert b.total_price()==2\n"
    )
    assert not any(item.code == "behavior_call_shape" for item in assessed(source).issues)


def test_simple_owned_receiver_alias_still_rejects_extra_argument():
    source = (
        "from app import Basket\n\ndef test_one():\n"
        "    b=Basket()\n    current=b\n    current.add_item('x',1,2)\n"
        "    assert current.total_price()==2\n"
    )
    assert any(item.code == "behavior_call_shape" for item in assessed(source).issues)
