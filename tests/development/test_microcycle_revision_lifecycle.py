import subprocess
from pathlib import Path

import pytest

from core.development.microcycle_revision_git import MicrocycleGitClient, RevisionResolveRequest
from core.development.microcycle_revision_lifecycle import (
    CanonicalDevelopmentBasePromoter,
    RackAiRevisionBindingFactory,
    RevisionCompletionService,
    RevisionRecoveryService,
    RevisionStateInitialiser,
    WorkingRevisionAdvancer,
)
from core.development.microcycle_revision_state import (
    RevisionBindingRequest,
    RevisionCompletionRequest,
    RevisionInitialisationRequest,
    RevisionRecoveryRequest,
    RevisionTransitionKind,
    RevisionTransitionRequest,
)
from core.development.microcycle_revision_store import MicrocycleRevisionRepository, managed_working_ref


def run(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def commit(root: Path, branch: str, name: str) -> str:
    run(root, "switch", "-c", branch)
    (root / f"{name}.txt").write_text(name, encoding="utf-8")
    run(root, "add", f"{name}.txt")
    run(root, "commit", "-qm", name)
    sha = run(root, "rev-parse", "HEAD")
    run(root, "switch", "main")
    return sha


def setup_lifecycle(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    run(root, "init", "-q", "-b", "main")
    run(root, "config", "user.name", "ATHBA")
    run(root, "config", "user.email", "athba@example.test")
    (root / "seed").write_text("seed", encoding="utf-8")
    run(root, "add", "seed")
    run(root, "commit", "-qm", "seed")
    base = run(root, "rev-parse", "main")
    repo = MicrocycleRevisionRepository(tmp_path / "state")
    git = MicrocycleGitClient(root)
    state = RevisionStateInitialiser(repo, git).initialise(
        RevisionInitialisationRequest("widget-growth", "refs/heads/main", base, ("approved",))
    )
    return root, repo, git, state


def transition(state, candidate, kind):
    return RevisionTransitionRequest(state, candidate, kind, ("evidence",))


def test_initialisation_draft_and_resume_preserve_canonical_and_working_refs(tmp_path):
    root, repo, git, state = setup_lifecycle(tmp_path)
    before = run(root, "rev-parse", "main"), git.resolve(RevisionResolveRequest(state.working_ref))

    assert state.working_ref.startswith("refs/heads/athba/microcycles/")
    assert before == (state.canonical_development_base, state.canonical_development_base)
    assert "planning material"  # Drafting has no lifecycle invocation and changes neither ref.
    resumed = RevisionStateInitialiser(repo, git).initialise(
        RevisionInitialisationRequest(state.scenario_id, state.canonical_ref, state.canonical_development_base)
    )
    assert resumed == state
    assert (run(root, "rev-parse", "main"), git.resolve(RevisionResolveRequest(state.working_ref))) == before


def test_frontier_and_developer_candidates_advance_only_working_ref(tmp_path):
    root, repo, git, state = setup_lifecycle(tmp_path)
    red = commit(root, "red", "red")
    red_state = WorkingRevisionAdvancer(repo, git).advance(
        transition(state, red, RevisionTransitionKind.FRONTIER_ACCEPTED.value)
    ).resulting_state
    run(root, "update-ref", "refs/heads/main", red)
    green = commit(root, "green", "green")
    run(root, "update-ref", "refs/heads/main", state.canonical_development_base)
    green_state = WorkingRevisionAdvancer(repo, git).advance(
        transition(red_state, green, RevisionTransitionKind.DEVELOPER_CANDIDATE_ACCEPTED.value)
    ).resulting_state

    assert red_state.working_revision == red
    assert green_state.working_revision == green
    assert green_state.canonical_development_base == state.canonical_development_base
    assert run(root, "rev-parse", "main") == state.canonical_development_base


def test_invalid_rejected_and_non_fast_forward_candidates_advance_neither_ref(tmp_path):
    root, repo, git, state = setup_lifecycle(tmp_path)
    before = run(root, "rev-parse", "main"), git.resolve(RevisionResolveRequest(state.working_ref))
    with pytest.raises(ValueError, match="unavailable"):
        WorkingRevisionAdvancer(repo, git).advance(
            transition(state, "a" * 40, RevisionTransitionKind.FRONTIER_ACCEPTED.value)
        )
    first = commit(root, "first", "first")
    advanced = WorkingRevisionAdvancer(repo, git).advance(
        transition(state, first, RevisionTransitionKind.FRONTIER_ACCEPTED.value)
    ).resulting_state
    unrelated = commit(root, "unrelated", "unrelated")
    with pytest.raises(ValueError, match="fast-forward"):
        WorkingRevisionAdvancer(repo, git).advance(
            transition(advanced, unrelated, RevisionTransitionKind.DEVELOPER_CANDIDATE_ACCEPTED.value)
        )

    assert before[0] == run(root, "rev-parse", "main")
    assert git.resolve(RevisionResolveRequest(advanced.working_ref)) == first


def test_binding_resolves_the_persisted_working_ref_to_its_matching_sha(tmp_path):
    root, repo, git, state = setup_lifecycle(tmp_path)
    red = commit(root, "red", "red")
    updated = WorkingRevisionAdvancer(repo, git).advance(
        transition(state, red, RevisionTransitionKind.FRONTIER_ACCEPTED.value)
    ).resulting_state
    factory = RackAiRevisionBindingFactory(RevisionRecoveryService(repo, git), git)

    binding = factory.build(RevisionBindingRequest(updated.scenario_id, "project", str(root), ("/srv/venv",)))

    assert binding.base_ref == updated.working_ref
    assert binding.base_sha == updated.working_revision
    assert git.resolve(RevisionResolveRequest(binding.base_ref)) == binding.base_sha


def test_ref_sha_mismatch_fails_before_gateway_invocation(tmp_path):
    root, repo, git, state = setup_lifecycle(tmp_path)
    other = commit(root, "other", "other")
    run(root, "update-ref", state.working_ref, other)
    gateway_calls = []

    with pytest.raises(ValueError, match="diverged"):
        RackAiRevisionBindingFactory(RevisionRecoveryService(repo, git), git).build(
            RevisionBindingRequest(state.scenario_id, "project", str(root))
        )

    assert gateway_calls == []


def test_regression_clear_promotes_only_exact_working_revision(tmp_path):
    root, repo, git, state = setup_lifecycle(tmp_path)
    candidate = commit(root, "green", "green")
    working = WorkingRevisionAdvancer(repo, git).advance(
        transition(state, candidate, RevisionTransitionKind.DEVELOPER_CANDIDATE_ACCEPTED.value)
    ).resulting_state
    promoted = CanonicalDevelopmentBasePromoter(repo, git).promote(
        transition(working, candidate, RevisionTransitionKind.REGRESSION_CLEAR.value)
    ).resulting_state

    assert promoted.canonical_development_base == candidate
    assert promoted.working_revision == candidate
    assert run(root, "rev-parse", "main") == candidate


def test_accumulated_regression_repair_and_rejection_leave_canonical_base_unchanged(tmp_path):
    root, repo, git, state = setup_lifecycle(tmp_path)
    repair = commit(root, "repair", "repair")
    updated = WorkingRevisionAdvancer(repo, git).advance(
        transition(state, repair, RevisionTransitionKind.REGRESSION_REPAIR_ACCEPTED.value)
    ).resulting_state

    assert updated.working_revision == repair
    assert updated.canonical_development_base == state.canonical_development_base
    assert run(root, "rev-parse", "main") == state.canonical_development_base


def test_non_fast_forward_canonical_promotion_and_concurrent_cas_fail_closed(tmp_path, monkeypatch):
    root, repo, git, state = setup_lifecycle(tmp_path)
    candidate = commit(root, "candidate", "candidate")
    working = WorkingRevisionAdvancer(repo, git).advance(
        transition(state, candidate, RevisionTransitionKind.DEVELOPER_CANDIDATE_ACCEPTED.value)
    ).resulting_state
    other = commit(root, "other", "other")
    run(root, "update-ref", "refs/heads/main", other)
    with pytest.raises(ValueError, match="diverged"):
        CanonicalDevelopmentBasePromoter(repo, git).promote(
            transition(working, candidate, RevisionTransitionKind.REGRESSION_CLEAR.value)
        )

    root, repo, git, state = setup_lifecycle(tmp_path / "cas")
    candidate = commit(root, "candidate", "candidate")
    other = commit(root, "other", "other")
    original = git.update

    def concurrent(request):
        run(root, "update-ref", state.working_ref, other)
        return original(request)

    monkeypatch.setattr(git, "update", concurrent)
    with pytest.raises(subprocess.CalledProcessError):
        WorkingRevisionAdvancer(repo, git).advance(
            transition(state, candidate, RevisionTransitionKind.FRONTIER_ACCEPTED.value)
        )
    assert repo.load(state.scenario_id) == state


def test_persistence_failure_rolls_back_ref_and_metadata(tmp_path, monkeypatch):
    root, repo, git, state = setup_lifecycle(tmp_path)
    candidate = commit(root, "candidate", "candidate")
    monkeypatch.setattr(repo, "save", lambda value: (_ for _ in ()).throw(OSError("disk unavailable")))

    with pytest.raises(OSError, match="disk unavailable"):
        WorkingRevisionAdvancer(repo, git).advance(
            transition(state, candidate, RevisionTransitionKind.FRONTIER_ACCEPTED.value)
        )

    assert git.resolve(RevisionResolveRequest(state.working_ref)) == state.working_revision


def test_recovery_recreates_only_missing_safe_ref_and_rejects_divergence(tmp_path):
    root, repo, git, state = setup_lifecycle(tmp_path)
    run(root, "update-ref", "-d", state.working_ref, state.working_revision)
    recovery = RevisionRecoveryService(repo, git)

    assert recovery.recover(RevisionRecoveryRequest(state.scenario_id)) == state
    assert git.resolve(RevisionResolveRequest(state.working_ref)) == state.working_revision
    other = commit(root, "other", "other")
    run(root, "update-ref", state.working_ref, other)
    with pytest.raises(ValueError, match="working ref diverged"):
        recovery.recover(RevisionRecoveryRequest(state.scenario_id))
    run(root, "update-ref", state.working_ref, state.working_revision)
    run(root, "update-ref", "refs/heads/main", other)
    with pytest.raises(ValueError, match="canonical development base diverged"):
        recovery.recover(RevisionRecoveryRequest(state.scenario_id))


def test_behavior_completion_removes_working_ref_and_prevents_recreation(tmp_path):
    root, repo, git, state = setup_lifecycle(tmp_path)
    green = commit(root, "green", "green")
    working = WorkingRevisionAdvancer(repo, git).advance(
        transition(state, green, RevisionTransitionKind.DEVELOPER_CANDIDATE_ACCEPTED.value)
    ).resulting_state
    promoted = CanonicalDevelopmentBasePromoter(repo, git).promote(
        transition(working, green, RevisionTransitionKind.REGRESSION_CLEAR.value)
    ).resulting_state
    completed = RevisionCompletionService(repo, git).complete(RevisionCompletionRequest(promoted, ("approved",)))

    assert completed.status == "behavior_complete"
    assert git.resolve(RevisionResolveRequest(completed.working_ref)) is None
    assert RevisionRecoveryService(repo, git).recover(RevisionRecoveryRequest(completed.scenario_id)) == completed
    with pytest.raises(ValueError, match="completed"):
        RevisionStateInitialiser(repo, git).initialise(
            RevisionInitialisationRequest(completed.scenario_id, completed.canonical_ref, completed.canonical_development_base)
        )


@pytest.mark.parametrize("scenario_id", ("../escape", "a/b", "a..b", "refs/heads/main", "space id"))
def test_unsafe_scenario_id_cannot_escape_managed_namespace(scenario_id):
    with pytest.raises(ValueError, match="unsafe"):
        managed_working_ref(scenario_id)