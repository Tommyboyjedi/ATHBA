from core.development.behavior_contract_domain import BehaviorContract
from core.development.behavior_contract_surface import (
    DeclaredProductSurface,
    production_candidate_violations,
    lint_test_candidate_violations,
)
from core.development.specification_domain import SourceRequirementClause
from core.development.behavior_contract_domain import BehaviorContractRequirement


def surface(entries=("ExampleLedger", "put(name, value)", "ExampleLedger.latest")):
    contract = BehaviorContract(
        "surface-contract", "surface-project", "ExampleLedger", "ledger", "ledger behavior",
        [SourceRequirementClause("SRC-1", "ledger behavior", "behavior")],
        [BehaviorContractRequirement("REQ-1", ["SRC-1"], "ledger behavior", "ledger works", "test ledger")],
        [], ["ledger.py"], ["tests/test_ledger.py"], list(entries),
    )
    return DeclaredProductSurface.compile(contract)


def test_surface_compiles_only_explicit_machine_usable_entries():
    value = surface(("ExampleLedger", "put(name, value)", "ExampleLedger.latest", "not API prose"))
    assert value.members == frozenset({"put", "latest"})
    assert value.unsupported_public_api_entries == ("not API prose",)


def test_candidate_lint_tracks_aliases_and_only_product_instances():
    source = '''import pytest
from ledger import ExampleLedger as Ledger

def test_ledger():
    ledger = Ledger()
    copy = ledger
    copy.put("a", " b ")
    assert ledger.latest("a").strip() == "b"
    assert pytest.raises(ValueError)
'''
    assert lint_test_candidate_violations(source, surface(), "ledger.py") == ()


def test_candidate_lint_rejects_undeclared_and_private_product_members():
    source = '''from ledger import ExampleLedger

def test_ledger():
    ledger = ExampleLedger()
    ledger.get("a")
    assert ledger._values["a"] == "b"
'''
    violations = lint_test_candidate_violations(source, surface(), "ledger.py")
    assert [item.member for item in violations] == ["get", "_values"]
    assert "latest" not in " ".join(item.detail for item in violations)


def test_production_lint_permits_incremental_subset_and_private_helpers():
    source = '''class ExampleLedger:
    def put(self, name, value):
        self._values = {name: value}

    def _helper(self):
        return None
'''
    assert production_candidate_violations(source, surface()) == ()


def test_production_lint_rejects_undeclared_public_members_and_attributes():
    source = '''class ExampleLedger:
    visible = True
    def get(self, name):
        self.exposed = name
'''
    assert [item.member for item in production_candidate_violations(source, surface())] == ["visible", "get", "exposed"]


def test_candidate_lint_does_not_track_unrelated_same_named_class():
    source = '''from other import ExampleLedger

def test_other_ledger():
    ledger = ExampleLedger()
    assert ledger.get("a") == "a"
'''
    assert lint_test_candidate_violations(source, surface(), "ledger.py") == ()
