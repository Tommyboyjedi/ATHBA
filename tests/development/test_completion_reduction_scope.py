"""Completed evidence reduction has explicit scope, never fabricated RED authority."""
import json
from pathlib import Path
import subprocess
import sys

from core.development.deterministic_regression import (
    DeterministicRegressionRequest, DeterministicRegressionService,
    SubprocessProjectRuntimeExecutor, REGRESSION_CLEAR,
)
from core.development.microcycle_domain import (
    TestScenarioDraft as ScenarioDraft, ScenarioParseRequest, FragmentationRequest,
    ScenarioFrontier, FrontierMaterialisationRequest,
)
from core.development.production_reduction import ProductionChangeReducer, ProductionReductionDependencies
from core.development.production_reduction_acceptance import CompletionReductionVerifier
from core.development.production_reduction_domain import (
    ConsolidatedReductionRequest, ContributionScope, ContributionWindow, ReductionFrontierAuthority,
)
from core.development.production_reduction_syntax import ReductionSource, ReductionContributionSource
from core.development.python_production_reduction import PythonProductionReductionAdapter
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.required_public_signature import RequiredPublicSignature

BASE = b'class Basket:\n    pass\n'
FIRST = b'class Basket:\n    def old(self):\n        return 2\n'
OTHER = FIRST + b'\n    def protected(self):\n        return 9\n'
LAST = OTHER + b'\n    def total(self):\n        return 2\n'


def test_interleaved_contribution_protects_outer_class_but_allows_owned_child():
    request = ReductionSource("app.py", b"", LAST, (
        ReductionContributionSource(b"", FIRST, True),
        ReductionContributionSource(FIRST, OTHER, False),
        ReductionContributionSource(OTHER, LAST, True),
    ))
    plan = PythonProductionReductionAdapter().plan(request)
    assert plan.opportunities
    assert all(b"def protected(self)" in item.replacement for item in plan.opportunities)
    assert all(b"class Basket:" in item.replacement for item in plan.opportunities)
    assert any(b"def old(self)" not in item.replacement for item in plan.opportunities)


def test_explicit_required_operation_is_not_retired_even_without_covering_test():
    request = ReductionSource("app.py", BASE, LAST, (
        ReductionContributionSource(BASE, LAST, True),
    ), (RequiredPublicSignature("Basket", "total", (), "total()"),))
    plan = PythonProductionReductionAdapter().plan(request)
    assert plan.opportunities
    assert all(b"def total(self)" in item.replacement for item in plan.opportunities)
    assert any(b"def old(self)" not in item.replacement for item in plan.opportunities)

    # A new owner awaiting Naming cannot silently become an empty protection set.
    unresolved_owner = ReductionSource("app.py", b"", LAST, (
        ReductionContributionSource(b"", LAST, True),
    ), (RequiredPublicSignature("RequiredBasket", "total", (), "total()"),))
    unresolved = PythonProductionReductionAdapter().plan(unresolved_owner)
    assert not unresolved.opportunities
    assert any("required public declaration" in item for item in unresolved.limitations)

    # Unsupported declaration nesting is uncertainty, not permission to retire API.
    conditional = (
        b"class Basket:\n    def old(self):\n        return 2\n"
        b"    if True:\n        def total(self):\n            return 2\n"
    )
    nested = ReductionSource("app.py", b"", conditional, (
        ReductionContributionSource(b"", conditional, True),
    ), (RequiredPublicSignature("Basket", "total", (), "total()"),))
    unsupported = PythonProductionReductionAdapter().plan(nested)
    assert not unsupported.opportunities
    assert any("required public declaration" in item for item in unsupported.limitations)


def _git(root, *args):
    return subprocess.run(("git", *args), cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()


def _commit(root, description):
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", description)
    return _git(root, "rev-parse", "HEAD")


def _authority(test, revision):
    adapter = PythonPytestAdapter()
    draft = ScenarioDraft("completed", "original-1+original-2", "python", test,
                          "tests/test_selected.py::test_selected", "tests/test_selected.py")
    model = adapter.parse_scenario(ScenarioParseRequest(draft))
    fragments = adapter.fragment_scenario(FragmentationRequest(model))
    index = len(fragments) - 1
    frontier = ScenarioFrontier(draft.scenario_id, index, fragments[index].fragment_id,
                                tuple(item.fragment_id for item in fragments))
    artifact = adapter.materialise_frontier(FrontierMaterialisationRequest(model, fragments, frontier, revision))
    assert artifact.complete_source == test
    return ReductionFrontierAuthority(artifact, fragments[index], "green" if index else None,
                                      draft.test_path, "app.py")


def test_completed_approved_test_reduces_without_red_or_developer_history(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.invalid")
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    (root / "app.py").write_bytes(BASE)
    base = _commit(root, "real initial authority")
    (root / "app.py").write_bytes(LAST)
    completed = _commit(root, "real completed requirements")
    (root / "tests").mkdir()
    test = ("from app import Basket\n\ndef test_selected():\n"
            "    assert Basket().total() == 2\n")
    (root / "tests/test_selected.py").write_text(test)
    approved = _commit(root, "approved consolidated observations, production unchanged")
    command = (sys.executable, "-m", "pytest", "-q")
    regression = DeterministicRegressionService(SubprocessProjectRuntimeExecutor())
    initial = regression.run(DeterministicRegressionRequest(
        root, command, "tests/test_selected.py::test_selected", ()))
    assert initial.status == REGRESSION_CLEAR
    request = ConsolidatedReductionRequest(
        root, "checkpoint-one", base, approved, ("app.py",),
        (_authority(test, approved),), command, (), "python-pytest",
        initial.state(command), ("app.py",),
        ContributionScope((ContributionWindow(base, completed, True),)),
    )
    reducer = ProductionChangeReducer(ProductionReductionDependencies(
        tmp_path / "evidence", PythonProductionReductionAdapter(), regression,
        CompletionReductionVerifier(PythonPytestAdapter()),
    ))
    result = reducer.reduce(request)
    assert result.regression.status == REGRESSION_CLEAR
    final = _git(root, "show", f"{result.revision}:app.py")
    assert "def total(self)" in final
    assert "def old(self)" not in final
    assert _git(root, "show", f"{result.revision}:tests/test_selected.py") == test.strip()
    checkpoint = json.loads(Path(result.evidence_ref).read_text())
    authority = checkpoint["authority"]
    assert authority["tests_revision"] == approved
    assert "accepted_red_revision" not in authority
    assert "developer_input_revision" not in authority
    assert "scenario_id" not in authority
    trials = list(Path(result.evidence_ref).parent.glob("trial-[0-9][0-9][0-9][0-9].json"))
    assert any("assessments" in item.read_text() for item in trials)
