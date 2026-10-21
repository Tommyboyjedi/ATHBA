"""Real-repository, test-backed proofs for bounded production-change reduction."""
from dataclasses import replace
import ast
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import pytest

from core.development.deterministic_regression import (
    DeterministicRegressionRequest, DeterministicRegressionService, REGRESSION_CLEAR,
    SubprocessProjectRuntimeExecutor,
)
from core.development.production_reduction import (
    ProductionChangeReducer, ProductionReductionDependencies,
)
from core.development.production_reduction_domain import ProductionReductionRequest, ReductionPolicy, ReductionCheckpoint
from core.development.production_reduction_journal import ReductionJournal
from core.development.microcycle_domain import RegressionCommandReport
from core.development.production_reduction_syntax import ReductionOpportunity, ReductionPlan
from core.development.python_production_reduction import PythonProductionReductionAdapter

COMMAND = (sys.executable, "-m", "pytest", "-q")
CURRENT = "tests/test_current.py::test_current"
IMPORT_TEST = "from app import Basket\n\ndef test_current():\n    pass\n"
OVERBUILT = (
    '"""seed"""\n\nclass Basket:\n'
    "    def __init__(self):\n        self.items = {}\n\n"
    "    def add(self, name, quantity=1):\n        self.items[name] = quantity\n\n"
    "    def count(self):\n        return len(self.items)\n"
)


def git(root, *args):
    return subprocess.run(("git", *args), cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def commit(root, message):
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def example(tmp_path, candidate=OVERBUILT, baseline='"""seed"""\n',
            test=IMPORT_TEST, prior=None, production_path="app.py"):
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    (root / production_path).write_text(baseline)
    if prior is not None:
        (root / "tests").mkdir()
        (root / "tests/test_prior.py").write_text(prior)
    base = commit(root, "trusted baseline")
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests/test_current.py").write_text(test)
    red = commit(root, "accepted RED authority")
    (root / production_path).write_text(candidate)
    original = commit(root, "original Developer candidate")
    prior_nodes = ("tests/test_prior.py::test_prior",) if prior else ()
    regression = DeterministicRegressionService(SubprocessProjectRuntimeExecutor())
    initial = regression.run(DeterministicRegressionRequest(root, COMMAND, CURRENT, prior_nodes))
    assert initial.status == REGRESSION_CLEAR
    request = ProductionReductionRequest(
        root, "one-scenario", 0, base, red, red, original, (production_path,),
        CURRENT, COMMAND, prior_nodes, True, "python-pytest", initial.state(COMMAND), required_artifacts=(production_path,),
    )
    return root, request, regression


def reduce(tmp_path, request, regression, adapter=None, policy=None):
    dependencies = ProductionReductionDependencies(
        tmp_path / "reduction-evidence", adapter or PythonProductionReductionAdapter(),
        regression, policy or ReductionPolicy(),
    )
    return ProductionChangeReducer(dependencies).reduce(request)


def source(root, revision, path="app.py"):
    return git(root, "show", f"{revision}:{path}")


def test_import_only_excess_is_removed_after_failed_enclosing_declaration_trial(tmp_path):
    root, request, regression = example(tmp_path)

    result = reduce(tmp_path, request, regression)

    assert result.regression.status == REGRESSION_CLEAR
    module = ast.parse(source(root, result.revision))
    basket = next(item for item in module.body if isinstance(item, ast.ClassDef))
    assert basket.name == "Basket"
    assert not any(isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) for item in ast.walk(basket))
    assert result.revision != request.candidate_revision
    assert git(root, "show", f"{request.candidate_revision}:app.py") == OVERBUILT.strip()
    reports = list((tmp_path / "reduction-evidence").rglob("trial-[0-9][0-9][0-9][0-9].json"))
    assert reports, "every retained/rejected reduction must have evidence"
    assert any("failed" in p.read_text() for p in reports), "removing necessary enclosing class must fail"


def test_incidental_later_construction_remains_allowed(tmp_path):
    root, request, regression = example(tmp_path)
    result = reduce(tmp_path, request, regression)

    namespace = {}
    exec(source(root, result.revision), namespace)
    assert isinstance(namespace["Basket"](), namespace["Basket"])
    assert result.regression.status == REGRESSION_CLEAR


def test_required_operation_cannot_be_removed(tmp_path):
    test = "from app import Basket\n\ndef test_current():\n    assert Basket().value() == 7\n"
    candidate = '"""seed"""\n\nclass Basket:\n    def value(self):\n        return 7\n'
    root, request, regression = example(tmp_path, candidate=candidate, test=test)

    result = reduce(tmp_path, request, regression)

    assert result.regression.status == REGRESSION_CLEAR
    namespace = {}
    exec(source(root, result.revision), namespace)
    assert namespace["Basket"]().value() == 7


def test_prior_accepted_behavior_is_protected_by_same_regression(tmp_path):
    prior = "from app import legacy\n\ndef test_prior():\n    assert legacy() == 5\n"
    baseline = '"""seed"""\n\ndef legacy():\n    return 5\n'
    candidate = baseline + "\nclass Basket:\n    def unnecessary(self):\n        return 99\n"
    root, request, regression = example(tmp_path, candidate, baseline, prior=prior)

    result = reduce(tmp_path, request, regression)

    assert "def legacy():" in source(root, result.revision)
    assert result.regression.status == REGRESSION_CLEAR
    assert request.prior_completed_test_nodes == ("tests/test_prior.py::test_prior",)


def test_unchanged_baseline_material_is_never_opportunistically_trimmed(tmp_path):
    baseline = '"""seed"""\n\ndef untested_existing_capability():\n    return "preserved exactly"\n'
    root, request, regression = example(tmp_path, baseline + "\nclass Basket:\n    pass\n", baseline)

    result = reduce(tmp_path, request, regression)

    assert source(root, result.revision).startswith(baseline.rstrip())
    assert "untested_existing_capability" in source(root, result.revision)


def test_unnecessary_modified_unit_can_be_restored_to_trusted_baseline(tmp_path):
    baseline = '"""seed"""\n\ndef accepted():\n    return 1\n'
    candidate = '"""seed"""\n\ndef accepted():\n    return 999\n\nclass Basket:\n    pass\n'
    root, request, regression = example(tmp_path, candidate, baseline)

    result = reduce(tmp_path, request, regression)

    assert "return 1" in source(root, result.revision)
    assert "return 999" not in source(root, result.revision)


def test_original_candidate_tests_configuration_and_main_checkout_are_immutable(tmp_path):
    root, request, regression = example(tmp_path)
    before = {
        "head": git(root, "rev-parse", "HEAD"),
        "candidate_tree": git(root, "rev-parse", f"{request.candidate_revision}^{{tree}}"),
        "test": (root / "tests/test_current.py").read_bytes(),
        "config": (root / ".gitignore").read_bytes(),
    }

    result = reduce(tmp_path, request, regression)

    assert git(root, "rev-parse", "HEAD") == before["head"]
    assert git(root, "rev-parse", f"{request.candidate_revision}^{{tree}}") == before["candidate_tree"]
    assert (root / "tests/test_current.py").read_bytes() == before["test"]
    assert (root / ".gitignore").read_bytes() == before["config"]
    assert git(root, "show", f"{result.revision}:tests/test_current.py").encode() + b"\n" == before["test"]
    assert git(root, "diff", "--name-only", request.candidate_revision, result.revision) == "app.py"
    assert git(root, "worktree", "list", "--porcelain").count("worktree ") == 1


def test_trial_limit_retains_only_fully_verified_candidate(tmp_path):
    root, request, regression = example(tmp_path)

    result = reduce(tmp_path, request, regression, policy=ReductionPolicy(max_trials=1))

    assert result.regression.status == REGRESSION_CLEAR
    checkpoint = json.loads(next((tmp_path / "reduction-evidence").rglob("checkpoint.json")).read_text())
    assert checkpoint["checkpoint"]["trials"] == 1
    assert checkpoint["checkpoint"]["best_revision"] == result.revision


def test_completed_resume_does_not_repeat_trials_or_need_model_gateway(tmp_path):
    root, request, regression = example(tmp_path)
    first = reduce(tmp_path, request, regression)
    def trial_records():
        records = {}
        for path in (tmp_path / "reduction-evidence").rglob("trial-[0-9][0-9][0-9][0-9].json"):
            record = json.loads(path.read_text())
            record.pop("cleanup_confirmed", None)
            records[str(path)] = record
        return records

    before = trial_records()
    patches = {str(p): p.read_bytes() for p in (tmp_path / "reduction-evidence").rglob("trial-*.patch")}

    class ForbiddenRuntime:
        def execute(self, request):
            raise AssertionError("completed reduction must not repeat test or model work")

    second = reduce(tmp_path, request, DeterministicRegressionService(ForbiddenRuntime()))

    assert second == first
    assert trial_records() == before
    assert {str(p): p.read_bytes() for p in (tmp_path / "reduction-evidence").rglob("trial-*.patch")} == patches


def test_candidate_with_test_mutation_fails_closed_before_reduction(tmp_path):
    root, request, regression = example(tmp_path)
    (root / "tests/test_current.py").write_text("def test_current():\n    assert True\n")
    altered = commit(root, "unauthorized test change")

    with pytest.raises(ValueError, match="immutable"):
        reduce(tmp_path, replace(request, candidate_revision=altered), regression)


def test_non_python_fake_capability_drives_same_generic_reducer(tmp_path):
    baseline = "CORE\n"
    candidate = "CORE\nEXTRA\n"
    test = 'from pathlib import Path\n\ndef test_current():\n    assert "CORE" in Path("app.toy").read_text()\n'
    root, request, regression = example(tmp_path, candidate, baseline, test, production_path="app.toy")

    class ToyCapability:
        def plan(self, item):
            if item.candidate and b"EXTRA\n" in item.candidate:
                return ReductionPlan((ReductionOpportunity("toy-remove-extra", item.path,
                    item.candidate.replace(b"EXTRA\n", b""), "remove added toy declaration"),))
            return ReductionPlan()

    result = reduce(tmp_path, replace(request, adapter_id="toy"), regression, adapter=ToyCapability())

    assert source(root, result.revision, "app.toy") == "CORE"
    assert result.regression.status == REGRESSION_CLEAR


def test_cancelled_reduction_retains_verified_original_without_trials(tmp_path):
    root, request, regression = example(tmp_path)

    result = reduce(tmp_path, replace(request, cancelled=lambda: True), regression)

    assert result.revision == request.candidate_revision
    assert result.regression.status == REGRESSION_CLEAR


def test_removal_that_only_breaks_prior_accepted_behavior_is_rejected(tmp_path):
    baseline = '"""seed"""\n\ndef legacy():\n    return 5\n'
    candidate = '"""seed"""\n\ndef legacy():\n    return helper()\n\ndef helper():\n    return 5\n\nclass Basket:\n    pass\n'
    prior = "from app import legacy\n\ndef test_prior():\n    assert legacy() == 5\n"
    root, request, regression = example(tmp_path, candidate, baseline, prior=prior)

    class OneHelperRemoval:
        def plan(self, item):
            replacement = item.candidate.replace(b"def helper():\n    return 5\n", b"")
            return ReductionPlan((ReductionOpportunity("helper-removal", item.path,
                replacement, "remove newly added helper declaration"),))

    result = reduce(tmp_path, request, regression, adapter=OneHelperRemoval())

    assert result.revision == request.candidate_revision
    trial = json.loads(next((tmp_path / "reduction-evidence").rglob("trial-[0-9][0-9][0-9][0-9].json")).read_text())
    assert trial["decision"] == "discarded"
    assert trial["regression"]["failing_prior_test_nodes"] == list(request.prior_completed_test_nodes)
    assert any(r["target"] == CURRENT and r["status"] == "passed" for r in trial["regression"]["reports"])


def test_uncertain_trial_cannot_replace_verified_candidate(tmp_path):
    root, request, _regression = example(tmp_path)

    class UncertainRuntime:
        def execute(self, item):
            return RegressionCommandReport(item.target, item.command, None,
                "infrastructure_failure", "executor unavailable")

    with pytest.raises(ValueError, match="infrastructure"):
        reduce(tmp_path, request, DeterministicRegressionService(UncertainRuntime()))

    checkpoint = json.loads(next((tmp_path / "reduction-evidence").rglob("checkpoint.json")).read_text())
    assert checkpoint["checkpoint"]["best_revision"] == request.candidate_revision
    assert git(root, "worktree", "list", "--porcelain").count("worktree ") == 1
    trial = json.loads(next((tmp_path / "reduction-evidence").rglob("trial-[0-9][0-9][0-9][0-9].json")).read_text())
    assert trial["decision"] == "discarded"
    assert trial["revision"] is None


def test_acceptance_mutating_immutable_test_cannot_be_retained(tmp_path):
    root, request, _regression = example(tmp_path)
    original_test = (root / "tests/test_current.py").read_bytes()

    class MutatingRuntime:
        def execute(self, item):
            (item.project_root / "tests/test_current.py").write_text("def test_current():\n    pass\n")
            return RegressionCommandReport(item.target, item.command, 0, "passed", "claimed pass")

    with pytest.raises(ValueError, match="mutated"):
        reduce(tmp_path, request, DeterministicRegressionService(MutatingRuntime()))

    checkpoint = json.loads(next((tmp_path / "reduction-evidence").rglob("checkpoint.json")).read_text())
    assert checkpoint["checkpoint"]["best_revision"] == request.candidate_revision
    assert (root / "tests/test_current.py").read_bytes() == original_test
    assert git(root, "worktree", "list", "--porcelain").count("worktree ") == 1


def test_tiny_deadline_keeps_verified_original_without_partial_acceptance(tmp_path):
    _root, request, regression = example(tmp_path)

    result = reduce(tmp_path, request, regression, policy=ReductionPolicy(max_seconds=0.001))

    assert result.revision == request.candidate_revision
    assert result.regression.status == REGRESSION_CLEAR
    checkpoint = json.loads(Path(result.evidence_ref).read_text())
    assert checkpoint["checkpoint"]["termination"] == "deadline_reached"
    assert checkpoint["checkpoint"]["accepted"] == 0


def test_pending_trial_resume_discards_workspace_and_preserves_attempt_budget(tmp_path):
    root, request, regression = example(tmp_path)
    policy = ReductionPolicy(max_trials=1)
    journal = ReductionJournal(tmp_path / "reduction-evidence", request)
    checkpoint = ReductionCheckpoint(
        journal.identity, request.candidate_revision, request.initial_regression,
        time.time() + 120.0, trials=1, tried_ids=("interrupted-op",), tried_states=("interrupted-state",),
    )
    journal.save((checkpoint, policy))
    parent = Path(tempfile.mkdtemp(prefix="athba-reduction-"))
    workspace = parent / "candidate"
    git(root, "worktree", "add", "--detach", str(workspace), request.candidate_revision)
    (workspace / "app.py").write_text("unverified interrupted source")
    journal.record(("trial-0001.json", {
        "decision": "pending", "workspace": str(workspace),
        "source_revision": request.candidate_revision, "transformation_id": "interrupted-op",
    }))
    try:
        result = reduce(tmp_path, request, regression, policy=policy)
        saved = json.loads(Path(result.evidence_ref).read_text())["checkpoint"]
        assert result.revision == request.candidate_revision
        assert saved["trials"] == 1
        assert saved["accepted"] == 0
        assert saved["termination"] == "trial_budget_reached"
        assert not workspace.exists()
        assert json.loads((journal.root / "trial-0001.json").read_text())["decision"] == "discarded_interrupted"
        assert git(root, "worktree", "list", "--porcelain").count("worktree ") == 1
    finally:
        if workspace.exists():
            git(root, "worktree", "remove", "--force", str(workspace))
        parent.rmdir()


def test_expired_pending_resume_still_cleans_interrupted_trial(tmp_path):
    root, request, regression = example(tmp_path)
    policy = ReductionPolicy(max_trials=1)
    journal = ReductionJournal(tmp_path / "reduction-evidence", request)
    journal.save((ReductionCheckpoint(
        journal.identity, request.candidate_revision, request.initial_regression,
        time.time() - 1.0, trials=1,
    ), policy))
    parent = Path(tempfile.mkdtemp(prefix="athba-reduction-"))
    workspace = parent / "candidate"
    git(root, "worktree", "add", "--detach", str(workspace), request.candidate_revision)
    journal.record(("trial-0001.json", {"decision": "pending", "workspace": str(workspace),
        "source_revision": request.candidate_revision, "transformation_id": "interrupted-op"}))
    try:
        result = reduce(tmp_path, request, regression, policy=policy)
        assert result.revision == request.candidate_revision
        assert not workspace.exists()
        assert json.loads((journal.root / "trial-0001.json").read_text())["decision"] == "discarded_interrupted"
        assert json.loads(Path(result.evidence_ref).read_text())["checkpoint"]["termination"] == "deadline_reached"
    finally:
        if workspace.exists():
            git(root, "worktree", "remove", "--force", str(workspace))
        parent.rmdir()


def test_deadline_after_trial_execution_never_promotes_partial_trial(tmp_path):
    root, request, _regression = example(tmp_path)

    class OverrunningRuntime:
        def execute(self, item):
            time.sleep(item.timeout_seconds + 0.02)
            return RegressionCommandReport(item.target, item.command, 0, "passed", "late pass")

    result = reduce(tmp_path, request, DeterministicRegressionService(OverrunningRuntime()),
                    policy=ReductionPolicy(max_seconds=6.0))

    assert result.revision == request.candidate_revision
    assert result.regression.status == REGRESSION_CLEAR
    saved = json.loads(Path(result.evidence_ref).read_text())["checkpoint"]
    assert saved["accepted"] == 0
    assert saved["termination"] == "deadline_reached"
    assert git(root, "worktree", "list", "--porcelain").count("worktree ") == 1


def test_required_artifact_deletion_is_discarded_even_if_test_passes(tmp_path):
    _root, request, regression = example(tmp_path, test="def test_current():\n    pass\n")

    class RemoveFile:
        def plan(self, item):
            return ReductionPlan((ReductionOpportunity("remove-file", item.path, None,
                "remove newly added optional source file"),))

    result = reduce(tmp_path, request, regression, adapter=RemoveFile())

    assert result.revision == request.candidate_revision
    assert result.regression.status == REGRESSION_CLEAR
    trial = json.loads(next((tmp_path / "reduction-evidence").rglob("trial-[0-9][0-9][0-9][0-9].json")).read_text())
    assert trial["decision"] == "discarded"
    assert "artifact" in json.dumps(trial).lower()


def test_unpromoted_retry_edits_remain_reducible_relative_to_trusted_baseline(tmp_path):
    root, request, regression = example(tmp_path)
    first_candidate = request.candidate_revision
    (root / "app.py").write_text(OVERBUILT + "\ndef retry_extra():\n    return 123\n")
    retry_candidate = commit(root, "second Developer candidate carrying unpromoted edits")
    initial = regression.run(DeterministicRegressionRequest(root, COMMAND, CURRENT))
    assert initial.status == REGRESSION_CLEAR
    retry = replace(request, developer_input_revision=first_candidate, candidate_revision=retry_candidate,
                    initial_regression=initial.state(COMMAND))

    result = reduce(tmp_path, retry, regression)

    parsed = ast.parse(source(root, result.revision))
    assert any(isinstance(node, ast.ClassDef) and node.name == "Basket" for node in parsed.body)
    assert not any(isinstance(node, ast.FunctionDef) for node in ast.walk(parsed))
    assert result.regression.status == REGRESSION_CLEAR
    assert source(root, first_candidate) == OVERBUILT.strip()


def test_cleanup_interruption_resume_does_not_promote_uncheckpointed_trial(tmp_path):
    root, request, regression = example(tmp_path)
    policy = ReductionPolicy(max_trials=1)
    journal = ReductionJournal(tmp_path / "reduction-evidence", request)
    journal.save((ReductionCheckpoint(
        journal.identity, request.candidate_revision, request.initial_regression,
        time.time() + 120.0, trials=1,
    ), policy))
    parent = Path(tempfile.mkdtemp(prefix="athba-reduction-"))
    workspace = parent / "candidate"
    git(root, "worktree", "add", "--detach", str(workspace), request.candidate_revision)
    (workspace / "app.py").write_text('"""seed"""\n\nclass Basket:\n    pass\n')
    uncheckpointed = commit(workspace, "trial committed before cleanup interruption")
    journal.record(("trial-0001.json", {
        "decision": "retained", "workspace": str(workspace),
        "source_revision": request.candidate_revision, "revision": uncheckpointed,
        "transformation_id": "completed-before-cleanup",
    }))
    try:
        result = reduce(tmp_path, request, regression, policy=policy)
        assert result.revision == request.candidate_revision
        assert result.revision != uncheckpointed
        assert not workspace.exists()
        saved = json.loads(Path(result.evidence_ref).read_text())["checkpoint"]
        assert saved["trials"] == 1
        assert saved["accepted"] == 0
    finally:
        if workspace.exists():
            git(root, "worktree", "remove", "--force", str(workspace))
        parent.rmdir()
