import copy
import json

import pytest

from core.development.behavior_contract_coordinator import _contract_prompt
from core.development.tdd_progression import (
    BehaviorContract,
    BehaviorContractRunState,
    SourceRequirementClause,
)
from core.execution.rack_ai_contract import RepositoryBinding


def payload() -> dict:
    return {
        "id": "contract-ledger",
        "project_id": "ledger-project",
        "component_name": "Ledger",
        "capability": "Store one payload.",
        "requirement_source": (
            "Build Ledger. Ledger.publish stores a payload. "
            "Ledger.latest reports the payload."
        ),
        "source_clauses": [
            {"ref": "SRC-1", "text": "Ledger.publish stores a payload.", "kind": "behavior"},
            {"ref": "SRC-2", "text": "Ledger.latest reports the payload.", "kind": "behavior"},
        ],
        "observable_requirements": [
            {
                "ref": "REQ-1",
                "source_refs": ["SRC-1", "SRC-2"],
                "summary": "Store and report a payload.",
                "observable_outcome": "A published payload is reported.",
                "test_hint": "test_publish_then_latest",
                "error_expectation": None,
                "preserves_state_on_failure": True,
                "depends_on": [],
                "technical_bindings": [
                    {"technical_ref": "TECH-1", "role": "subject"},
                    {"technical_ref": "TECH-2", "role": "action"},
                    {"technical_ref": "TECH-3", "role": "observation"},
                ],
            }
        ],
        "invariants": [],
        "production_paths": ["ledger.py"],
        "test_paths": ["tests/test_ledger.py"],
        "public_api": ["Ledger()", "publish(payload)", "latest"],
        "error_semantics": [],
        "non_goals": [],
        "completion_criteria": ["accepted proof"],
        "status": "tdd_ready",
        "technical_decisions": [
            {
                "ref": "TECH-1",
                "kind": "class",
                "qualified_identifier": "Ledger",
                "origin": "source_requirement",
                "source_clause_refs": ["SRC-1"],
                "evidence_refs": [],
                "source_excerpt": "Ledger",
            },
            {
                "ref": "TECH-2",
                "kind": "method",
                "qualified_identifier": "Ledger.publish",
                "origin": "source_requirement",
                "source_clause_refs": ["SRC-1"],
                "evidence_refs": [],
                "source_excerpt": "Ledger.publish",
            },
            {
                "ref": "TECH-3",
                "kind": "property",
                "qualified_identifier": "Ledger.latest",
                "origin": "behavior_planner",
                "source_clause_refs": ["SRC-2"],
                "evidence_refs": [],
                "source_excerpt": None,
            },
        ],
    }


def test_legacy_contract_without_technical_fields_loads_and_retains_public_api():
    legacy = payload()
    legacy.pop("technical_decisions")
    legacy["observable_requirements"][0].pop("technical_bindings")

    restored = BehaviorContract.from_dict(legacy)

    assert restored.technical_decisions == []
    assert restored.observable_requirements[0].technical_bindings == []
    assert restored.public_api == ["Ledger()", "publish(payload)", "latest"]


def test_technical_decisions_and_bindings_round_trip_through_contract_and_run_state():
    contract = BehaviorContract.from_dict(payload())
    persisted_contract = contract.to_dict()
    assert BehaviorContract.from_dict(persisted_contract).to_dict() == persisted_contract

    state = BehaviorContractRunState(
        contract=contract,
        repository_binding=RepositoryBinding("ledger-fixture", "main", "a" * 40),
        semantic_base_revision=None,
    )
    restored = BehaviorContractRunState.from_dict(state.to_dict())
    assert restored.contract.to_dict() == persisted_contract


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: value["technical_decisions"].append(
                copy.deepcopy(value["technical_decisions"][0])
            ),
            "duplicate technical decision refs",
        ),
        (
            lambda value: value["observable_requirements"][0]["technical_bindings"].append(
                {"technical_ref": "MISSING", "role": "other"}
            ),
            "technical binding ref must exist",
        ),
        (
            lambda value: value["observable_requirements"][0]["technical_bindings"].append(
                {"technical_ref": "TECH-1", "role": "subject"}
            ),
            "duplicate requirement technical bindings",
        ),
        (
            lambda value: value["technical_decisions"][2].__setitem__(
                "source_excerpt", "Ledger.latest"
            ),
            "only source_requirement technical decisions may carry a source excerpt",
        ),
        (lambda value: value["technical_decisions"][0].__setitem__("kind", "package"), "unsupported technical decision kind"),
        (lambda value: value["technical_decisions"][0].__setitem__("origin", "architect"), "unsupported technical decision origin"),
        (lambda value: value["observable_requirements"][0]["technical_bindings"][0].__setitem__("role", "implementation"), "unsupported technical binding role"),
        (lambda value: value["technical_decisions"][0].__setitem__("source_excerpt", "InventedLedger"), "exact substring"),
        (lambda value: value["technical_decisions"][0].__setitem__("source_clause_refs", ["SRC-404"]), "must exist in source clauses"),
        (
            lambda value: value["technical_decisions"][2].update(
                {"origin": "upstream_design", "evidence_refs": []}
            ),
            "require provenance evidence refs",
        ),
        (
            lambda value: value["technical_decisions"].append(
                {
                    "ref": "TECH-4",
                    "kind": "field",
                    "qualified_identifier": "Ledger._payload",
                    "origin": "upstream_design",
                    "source_clause_refs": [],
                    "evidence_refs": ["architecture:ledger-v1"],
                    "source_excerpt": None,
                }
            ),
            "must be bound to observable requirements",
        ),
        (lambda value: value.__setitem__("technical_decisions", {"TECH-1": {}}), "technical_decisions must be a list"),
    ],
)
def test_invalid_technical_decision_structures_fail_closed(mutate, message):
    value = payload()
    mutate(value)

    with pytest.raises(ValueError, match=message):
        BehaviorContract.from_dict(value)


def test_source_requirement_requires_identifier_in_exact_source_excerpt():
    value = payload()
    value["technical_decisions"][0]["source_excerpt"] = "Ledger.publish"
    assert BehaviorContract.from_dict(value).technical_decision_refs() == ["TECH-1", "TECH-2", "TECH-3"]


def test_behavior_planner_decision_can_name_identifier_absent_from_source():
    value = payload()
    value["technical_decisions"][2]["qualified_identifier"] = "PayloadProjection.read"

    contract = BehaviorContract.from_dict(value)
    assert contract.technical_decisions[2].qualified_identifier == "PayloadProjection.read"


def test_prose_mentions_do_not_create_technical_decisions_automatically():
    value = payload()
    value.pop("technical_decisions")
    value["observable_requirements"][0].pop("technical_bindings")
    value["observable_requirements"][0]["summary"] = "SomeClass.some_method stores a payload."
    value["non_goals"] = ["SomeClass.some_method remains ordinary prose."]

    assert BehaviorContract.from_dict(value).technical_decisions == []


def test_model_serializer_and_behavior_planner_prompt_remain_unchanged_by_phase_one():
    contract = BehaviorContract.from_dict(payload())
    model_payload = json.dumps(contract.to_model_dict(), sort_keys=True)
    prompt = _contract_prompt(
        project_id=contract.project_id,
        requirement_text=contract.requirement_source,
        source_clauses=[SourceRequirementClause.from_dict(item) for item in payload()["source_clauses"]],
        production_paths=contract.production_paths,
        test_paths=contract.test_paths,
    )

    assert "technical_decisions" not in model_payload
    assert "technical_bindings" not in model_payload
    assert "technical_decisions" not in prompt
    assert "technical_bindings" not in prompt
