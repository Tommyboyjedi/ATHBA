"""Proof reporting cannot manufacture the required live positive chain."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

from core.development.post_behavior_assessment import (
    IdentifierRename, NamingDecision, RefactorDecision, RefactorOpportunity,
)
from core.development.post_behavior_domain import (
    ChangeCandidate, PostBehaviorAssessment, PostBehaviorEntry, PostBehaviorOutcome,
    PostBehaviorPass, PostBehaviorPhase, PostBehaviorReason, PostBehaviorState,
    PostBehaviorStatus, ValidationEvidence,
)
from core.development.post_behavior_evidence import PostBehaviorEvidenceStore
from core.development.microcycle_domain import BoundaryDiagnostic
from core.development.python_pytest_preflight import PythonProbePreflightError
from core.development.strict_tdd_run_controller import StrictTddReceiptDeliveryError
import scripts.run_pr30_post_behavior_proof as proof_runner
from core.development.strict_tdd_run_domain import StrictTddRunMode
from scripts.run_pr30_post_behavior_proof import (
    ProofInput, ProofScope, ProofStatus, observe, predeclare,
)


def git(root, *arguments):
    return subprocess.run(("git", *arguments), cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def commit(root):
    git(root, "add", "product.py", "test_product.py")
    git(root, "commit", "-qm", "deterministic proof-checker fixture")
    return git(root, "rev-parse", "HEAD")


def candidate_pass(phase, number, base, candidate, evidence_root):
    submission = f"submission-{number}"
    artifact = PostBehaviorEvidenceStore(evidence_root).record("workspace_result", {
        "identity": {"submission_id": submission}, "candidate_revision": candidate,
        "execution_provenance": {"invocation_id": f"fixture-{number}", "worker_id": "deterministic-test-only"},
    })
    decision = (NamingDecision(IdentifierRename("old_name", "required_name"))
                if phase == PostBehaviorPhase.NAMING
                else RefactorDecision(RefactorOpportunity("Remove duplicate branches.", "Both compute the same result.")))
    return PostBehaviorPass(
        phase, number, base, PostBehaviorAssessment(decision, "fixture-slice"), submission,
        ChangeCandidate(candidate, (artifact,)), ValidationEvidence(candidate, True, ("tests",)),
        ValidationEvidence(candidate, True, ("gatekeeper",)), outcome=PostBehaviorOutcome.PROMOTED,
        promotion_evidence=("accepted-cas",))


def no_pass(phase, number, revision):
    naming = phase == PostBehaviorPhase.NAMING
    return PostBehaviorPass(
        phase, number, revision, PostBehaviorAssessment(NamingDecision() if naming else RefactorDecision(), "slice"),
        outcome=PostBehaviorOutcome.NO_CHANGE,
        stop_reason=PostBehaviorReason.NAMING_NO_CHANGE if naming else PostBehaviorReason.REFACTOR_NO_CHANGE)


def proof_fixture(tmp_path, *, rename_tests=True, refactor_tests=False):
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "proof-checker@example.test")
    git(root, "config", "user.name", "Deterministic proof checker")
    (root / "product.py").write_text("")
    (root / "test_product.py").write_text("")
    initial = commit(root)
    source = "def old_name(value):\n    if value > 0:\n        return value + 1\n    return value + 1\n"
    tests = "from product import old_name\ndef test_product():\n    assert old_name(2) == 3\n"
    (root / "product.py").write_text(source)
    (root / "test_product.py").write_text(tests)
    baseline = commit(root)
    (root / "product.py").write_text(source.replace("old_name", "required_name"))
    if rename_tests:
        (root / "test_product.py").write_text(tests.replace("old_name", "required_name"))
    renamed = commit(root)
    (root / "product.py").write_text("def required_name(value):\n    return value + 1\n")
    if refactor_tests:
        with (root / "test_product.py").open("a") as handle:
            handle.write("# an unauthorized test-file edit\n")
    refactored = commit(root)
    entry = PostBehaviorEntry("proof-project", initial, baseline, ("product.py",), "original-authority",
                              ValidationEvidence(baseline, True, ("original-final-gatekeeper",)))
    passes = (
        candidate_pass(PostBehaviorPhase.NAMING, 1, baseline, renamed, tmp_path / "evidence"),
        no_pass(PostBehaviorPhase.NAMING, 2, renamed),
        candidate_pass(PostBehaviorPhase.REFACTORING, 3, renamed, refactored, tmp_path / "evidence"),
        no_pass(PostBehaviorPhase.REFACTORING, 4, refactored),
    )
    state = PostBehaviorState(entry, refactored, PostBehaviorStatus.POST_BEHAVIOR_COMPLETE,
        passes=passes, refactor_promoted_passes=1, terminal_reason=PostBehaviorReason.REFACTOR_NO_CHANGE)
    return state, ProofScope(root, ("product.py",), ("test_product.py",))


def test_positive_marker_requires_revision_bound_real_path_evidence(tmp_path):
    state, scope = proof_fixture(tmp_path)
    report = observe(state, scope)
    assert report.status == ProofStatus.PASSED
    assert report.behavioral_baseline == state.behaviorally_accepted_revision
    assert report.final_revision == state.current_post_behavior_revision
    assert report.accepted_rename_revisions == (state.passes[0].candidate.revision,)
    assert report.accepted_refactor_revisions == (state.passes[2].candidate.revision,)


@pytest.mark.parametrize("rename_tests,refactor_tests", [(False, False), (True, True)])
def test_missing_required_write_pattern_does_not_manufacture_proof(tmp_path, rename_tests, refactor_tests):
    state, scope = proof_fixture(tmp_path, rename_tests=rename_tests, refactor_tests=refactor_tests)
    report = observe(state, scope)
    assert report.status == ProofStatus.NOT_OBSERVED
    assert "production/test rename" in report.reason


def test_no_work_completion_reports_positive_chain_not_observed(tmp_path):
    state, scope = proof_fixture(tmp_path)
    baseline = state.behaviorally_accepted_revision
    no_work = PostBehaviorState(state.entry, baseline, PostBehaviorStatus.POST_BEHAVIOR_COMPLETE,
        passes=(no_pass(PostBehaviorPhase.NAMING, 1, baseline), no_pass(PostBehaviorPhase.REFACTORING, 2, baseline)),
        terminal_reason=PostBehaviorReason.REFACTOR_NO_CHANGE)
    report = observe(no_work, scope)
    assert report.status == ProofStatus.NOT_OBSERVED
    assert report.final_revision == baseline


def test_bounded_refactor_stop_is_not_the_required_final_no(tmp_path):
    state, scope = proof_fixture(tmp_path)
    bounded = replace(state.passes[-1], assessment=PostBehaviorAssessment(
        RefactorDecision(RefactorOpportunity("Remove duplicate branches.", "Repeated objective.")), "slice"),
        outcome=PostBehaviorOutcome.BOUNDED_STOP, stop_reason=PostBehaviorReason.REPEATED_REFACTOR_OBJECTIVE)
    stopped = replace(state, passes=(*state.passes[:-1], bounded),
                      terminal_reason=PostBehaviorReason.REPEATED_REFACTOR_OBJECTIVE)
    report = observe(stopped, scope)
    assert report.status == ProofStatus.NOT_OBSERVED
    assert "explicit final refactor NO" in report.reason


@pytest.mark.parametrize("field,value", [
    ("execution_provenance", {}), ("candidate_revision", "0" * 40),
    ("identity", {"submission_id": "different-invocation"}),
])
def test_missing_or_mismatched_provenance_does_not_pass(tmp_path, field, value):
    state, scope = proof_fixture(tmp_path)
    artifact_path = Path(state.passes[0].candidate.evidence_refs[0])
    artifact = json.loads(artifact_path.read_text())
    artifact["payload"][field] = value
    artifact_path.write_text(json.dumps(artifact))
    assert observe(state, scope).status == ProofStatus.NOT_OBSERVED


def test_blocked_lifecycle_reports_exact_diagnostic_without_positive_marker(tmp_path):
    state, scope = proof_fixture(tmp_path)
    blocked = PostBehaviorState(state.entry, state.behaviorally_accepted_revision, PostBehaviorStatus.BLOCKED,
                               terminal_reason=PostBehaviorReason.HUMAN_INTERVENTION,
                               diagnostic="local bounded workspace unavailable")
    report = observe(blocked, scope)
    assert report.status == ProofStatus.BLOCKED
    assert report.reason == "local bounded workspace unavailable"


def proof_input(tmp_path):
    requirement = tmp_path / "requirement.md"
    requirement.write_text("Expose `required_name` with the accepted input/output behavior.\n")
    return ProofInput("frozen-proof", "fresh-project", requirement, tmp_path / "state",
                      tmp_path / "evidence", "operator-configured-local",
                      ("product.py",), ("test_product.py",))


def versions():
    return SimpleNamespace(athba_revision="a" * 40, rack_ai_revision="b" * 40)


def test_predeclaration_records_exact_fixture_and_forbids_second_fresh_start(tmp_path):
    arguments = proof_input(tmp_path)
    requirement = predeclare(arguments, versions())
    plan = json.loads((arguments.proof_root / "predeclared.json").read_text())
    assert plan["requirement_text"] == requirement
    assert plan["athba_revision"] == "a" * 40
    assert plan["rack_ai_revision"] == "b" * 40
    assert plan["manual_target_edits_permitted"] is False
    assert plan["required_chain"][-2:] == ["refactor NO", "POST_BEHAVIOR_COMPLETE"]
    with pytest.raises(ValueError, match="already predeclared"):
        predeclare(arguments, versions())
    assert predeclare(replace(arguments, mode=StrictTddRunMode.RESUME), versions()) == requirement


@pytest.mark.parametrize("change", ["fixture", "model", "paths", "code"])
def test_resume_cannot_retune_fixture_models_paths_or_code_after_observation(tmp_path, change):
    arguments = proof_input(tmp_path)
    predeclare(arguments, versions())
    resumed = replace(arguments, mode=StrictTddRunMode.RESUME)
    revision = versions()
    if change == "fixture":
        arguments.requirement_file.write_text("Different fixture designed after observing failure.")
    elif change == "model":
        resumed = replace(resumed, reasoning_model="different-model")
    elif change == "paths":
        resumed = replace(resumed, production_paths=("other.py",))
    else:
        revision = SimpleNamespace(athba_revision="c" * 40, rack_ai_revision="b" * 40)
    with pytest.raises(ValueError, match="changed after predeclaration"):
        predeclare(resumed, revision)


def test_resume_requires_prior_predeclaration(tmp_path):
    with pytest.raises(ValueError, match="without its immutable predeclaration"):
        predeclare(replace(proof_input(tmp_path), mode=StrictTddRunMode.RESUME), versions())


@pytest.mark.parametrize("error", [
    PythonProbePreflightError(BoundaryDiagnostic("harness_unavailable", "exact pytest preflight blocker")),
    subprocess.SubprocessError("exact subprocess infrastructure blocker"),
    StrictTddReceiptDeliveryError("exact durable receipt delivery blocker"),
])
def test_expected_infrastructure_failure_preserves_exact_durable_proof_blocker(
    tmp_path, monkeypatch, capsys, error,
):
    arguments = proof_input(tmp_path)
    invoked = []

    async def unavailable(request):
        invoked.append(request)
        raise error

    monkeypatch.setattr(proof_runner, "parse", lambda: arguments)
    monkeypatch.setattr(proof_runner, "execute", unavailable)
    assert proof_runner.main() == 2
    assert invoked == [arguments]
    expected = f"{type(error).__name__}: {error}"
    displayed = json.loads(capsys.readouterr().out)
    assert displayed["status"] == "blocked"
    assert displayed["reason"] == expected
    artifacts = [json.loads(path.read_text()) for path in arguments.proof_root.glob("*.json")]
    assert len(artifacts) == 1
    assert artifacts[0]["kind"] == "proof_blocker"
    assert artifacts[0]["payload"]["status"] == "blocked"
    assert artifacts[0]["payload"]["reason"] == expected
    assert not arguments.state_root.exists()
