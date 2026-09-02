from __future__ import annotations

import subprocess

import pytest

from core.development.behavior_contract_coordinator import (
    DynamicTddPlanner,
    GitTesterRepositoryMaterialProvider,
    RepositoryMaterialRequest,
)
from core.development.provisional_semantic_progression import (
    ActionableRequirementSelectionRequest,
    ActionableRequirementSelector,
    ProvisionalReviewRecorder,
    ProvisionalReviewRequest,
    SemanticClosureRequest,
    SemanticClosureService,
)
from core.development.semantic_progression_domain import (
    OpenSemanticObligation,
    ProvisionalRequirementState,
    SemanticObligationDraft,
    SemanticProgressLedger,
)
from core.development.tdd_progression import (
    BehaviorContract,
    BehaviorContractRunState,
    ContractCycleRecord,
    SemanticReviewResult,
    TddStepDecision,
    TddStepProposal,
)
from core.execution.rack_ai_contract import RepositoryBinding


def contract_for(project_id: str, prefix: str, depends_on: dict[str, list[str]] | None = None) -> BehaviorContract:
    depends_on = depends_on or {}
    return BehaviorContract.from_dict(
        {
            "id": f"contract-{project_id}",
            "project_id": project_id,
            "component_name": project_id.title(),
            "capability": "Generic progression coverage",
            "requirement_source": "Generic progression coverage source.",
            "source_clauses": [
                {"ref": f"{prefix}-SRC-1", "text": "First behavior.", "kind": "behavior", "evidence_kind": "test"},
                {"ref": f"{prefix}-SRC-2", "text": "Second behavior.", "kind": "behavior", "evidence_kind": "test"},
                {"ref": f"{prefix}-SRC-3", "text": "Third behavior.", "kind": "behavior", "evidence_kind": "test"},
            ],
            "observable_requirements": [
                {
                    "ref": f"{prefix}-1",
                    "source_refs": [f"{prefix}-SRC-1"],
                    "summary": "first behavior",
                    "observable_outcome": "first outcome",
                    "test_hint": "prove first behavior",
                    "error_expectation": None,
                    "preserves_state_on_failure": True,
                    "depends_on": depends_on.get(f"{prefix}-1", []),
                },
                {
                    "ref": f"{prefix}-2",
                    "source_refs": [f"{prefix}-SRC-2"],
                    "summary": "second behavior",
                    "observable_outcome": "second outcome",
                    "test_hint": "prove second behavior",
                    "error_expectation": None,
                    "preserves_state_on_failure": True,
                    "depends_on": depends_on.get(f"{prefix}-2", []),
                },
                {
                    "ref": f"{prefix}-3",
                    "source_refs": [f"{prefix}-SRC-3"],
                    "summary": "third behavior",
                    "observable_outcome": "third outcome",
                    "test_hint": "prove third behavior",
                    "error_expectation": None,
                    "preserves_state_on_failure": True,
                    "depends_on": depends_on.get(f"{prefix}-3", []),
                },
            ],
            "invariants": [],
            "production_paths": [f"src/{project_id}.py"],
            "test_paths": [f"tests/test_{project_id}.py"],
            "public_api": [project_id],
            "error_semantics": [],
            "non_goals": [],
            "completion_criteria": ["all requirements semantically approved"],
            "status": "tdd_ready",
        }
    )


def binding(base_sha: str, *, root: str | None = None) -> RepositoryBinding:
    return RepositoryBinding(repository_id="repo", base_ref="main", base_sha=base_sha, registered_root=root)


def step(requirement_ref: str, project_id: str, *, step_id: str | None = None) -> TddStepProposal:
    return TddStepProposal(
        step_id=step_id or f"{requirement_ref.lower()}-step",
        requirement_refs=[requirement_ref],
        focused_behavior=f"prove {requirement_ref}",
        test_name=f"tests/test_{project_id}.py::test_{requirement_ref.lower().replace('-', '_')}",
        expected_result=f"{requirement_ref} observable result",
        test_path=f"tests/test_{project_id}.py",
        production_path=f"src/{project_id}.py",
        red_objective="add one failing test",
        green_objective="make the focused test pass",
        reason_next_smallest="smallest useful next behavior",
    )


def cycle_for(requirement_ref: str, project_id: str, *, candidate_revision: str = "d" * 40) -> ContractCycleRecord:
    return ContractCycleRecord.from_step(step(requirement_ref, project_id), base_revision="a" * 40).__class__(
        **{
            **ContractCycleRecord.from_step(step(requirement_ref, project_id), base_revision="a" * 40).__dict__,
            "candidate_revision": candidate_revision,
            "pool": "review_ready",
        }
    )


def review_provisional(requirement_ref: str, project_id: str, blocking_refs: list[str], *, revision: str = "d" * 40) -> SemanticReviewResult:
    proposal = step(requirement_ref, project_id)
    return SemanticReviewResult(
        verdict="behavior_correct_with_open_obligations",
        rationale="Behavior is correct but later semantic obligations remain open.",
        findings=["provisional semantic dependency remains open"],
        candidate_revision=revision,
        step_id=proposal.step_id,
        evidence_refs=["review:provisional"],
        open_obligations=[
            SemanticObligationDraft(
                owning_requirement_ref=requirement_ref,
                blocking_requirement_refs=blocking_refs,
                rationale="Later requirement must establish the broader semantic guarantee.",
                evidence_refs=["SRC-2"],
            )
        ],
    )


def run_state(
    contract: BehaviorContract,
    *,
    semantic_base_revision: str = "a" * 40,
    development_base_revision: str | None = None,
    completed_requirement_refs: list[str] | None = None,
    semantic_progress: SemanticProgressLedger | None = None,
    targeted_requirement_ref: str | None = None,
) -> BehaviorContractRunState:
    development_base_revision = development_base_revision or semantic_base_revision
    return BehaviorContractRunState(
        contract=contract,
        repository_binding=binding(development_base_revision),
        semantic_base_revision=semantic_base_revision,
        development_base_revision=development_base_revision,
        completed_requirement_refs=completed_requirement_refs or [],
        semantic_progress=semantic_progress or SemanticProgressLedger(),
        targeted_requirement_ref=targeted_requirement_ref,
    )


def git(repo, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def test_sequential_semantic_progression_keeps_development_and_semantic_aligned():
    contract = contract_for("order_book", "OB", {"OB-2": ["OB-1"]})
    selected = ActionableRequirementSelector().select(ActionableRequirementSelectionRequest(contract, run_state(contract)))

    assert selected == ["OB-1", "OB-3"]


def test_provisional_green_records_open_obligation_and_development_revision():
    contract = contract_for("order_book", "OB", {"OB-2": ["OB-1"]})
    state = run_state(contract)
    cycle = cycle_for("OB-1", "order_book")
    review = review_provisional("OB-1", "order_book", ["OB-2"])

    recorded = ProvisionalReviewRecorder().record(ProvisionalReviewRequest(state, cycle, review))

    assert recorded.development_base_revision == "d" * 40
    assert recorded.ledger.provisional_requirement_refs() == {"OB-1"}
    assert recorded.ledger.open_requirement_refs() == {"OB-1"}


def test_continue_from_provisional_revision_selects_other_actionable_requirement():
    contract = contract_for("order_book", "OB", {"OB-2": ["OB-1"]})
    ledger = SemanticProgressLedger(
        provisional_requirements=[
            ProvisionalRequirementState(
                requirement_ref="OB-1",
                development_revision="d" * 40,
                originating_step_id="ob-1-step",
                accepted_test_names=["tests/test_order_book.py::test_ob_1"],
                open_obligation_ids=["ob-1::obligation::1"],
            )
        ],
        open_obligations=[
            OpenSemanticObligation(
                obligation_id="ob-1::obligation::1",
                owning_requirement_ref="OB-1",
                blocking_requirement_refs=["OB-2"],
                rationale="OB-2 must finish the semantic story.",
                evidence_refs=["OB-SRC-2"],
                originating_step_id="ob-1-step",
                introduced_revision="d" * 40,
            )
        ],
    )
    selected = ActionableRequirementSelector().select(
        ActionableRequirementSelectionRequest(
            contract,
            run_state(contract, semantic_base_revision="a" * 40, development_base_revision="d" * 40, semantic_progress=ledger),
        )
    )

    assert selected == ["OB-2", "OB-3"]


def test_obligation_closure_promotes_prior_provisional_requirement_without_rerunning_green():
    contract = contract_for("order_book", "OB", {"OB-2": ["OB-1"]})
    ledger = SemanticProgressLedger(
        provisional_requirements=[
            ProvisionalRequirementState(
                requirement_ref="OB-1",
                development_revision="d" * 40,
                originating_step_id="ob-1-step",
                accepted_test_names=["tests/test_order_book.py::test_ob_1"],
                open_obligation_ids=["ob-1::obligation::1"],
            )
        ],
        open_obligations=[
            OpenSemanticObligation(
                obligation_id="ob-1::obligation::1",
                owning_requirement_ref="OB-1",
                blocking_requirement_refs=["OB-2"],
                rationale="OB-2 must finish the semantic story.",
                evidence_refs=["OB-SRC-2"],
                originating_step_id="ob-1-step",
                introduced_revision="d" * 40,
            )
        ],
    )
    closed = SemanticClosureService().close(
        SemanticClosureRequest(
            run_state(
                contract,
                semantic_base_revision="e" * 40,
                development_base_revision="f" * 40,
                completed_requirement_refs=["OB-2"],
                semantic_progress=ledger,
            )
        )
    )

    assert closed.promoted_requirement_refs == ["OB-1"]
    assert set(closed.completed_requirement_refs) == {"OB-1", "OB-2"}
    assert not closed.ledger.provisional_requirements
    assert closed.ledger.resolution_history[0].resolution_revision == "e" * 40


def test_dependency_cycle_is_bounded_at_contract_validation():
    with pytest.raises(ValueError, match="acyclic"):
        contract_for("cache_rules", "FC", {"FC-1": ["FC-2"], "FC-2": ["FC-1"], "FC-3": ["FC-2"]})


def test_repeated_blocked_selection_is_prevented_for_open_obligation_owner():
    contract = contract_for("cache_rules", "FC", {"FC-2": ["FC-1"]})
    ledger = SemanticProgressLedger(
        provisional_requirements=[
            ProvisionalRequirementState(
                requirement_ref="FC-1",
                development_revision="d" * 40,
                originating_step_id="fc-1-step",
                accepted_test_names=["tests/test_cache_rules.py::test_fc_1"],
                open_obligation_ids=["fc-1::obligation::1"],
            )
        ],
        open_obligations=[
            OpenSemanticObligation(
                obligation_id="fc-1::obligation::1",
                owning_requirement_ref="FC-1",
                blocking_requirement_refs=["FC-2"],
                rationale="FC-2 must add the broader semantic rule.",
                evidence_refs=["FC-SRC-2"],
                originating_step_id="fc-1-step",
                introduced_revision="d" * 40,
            )
        ],
    )

    selected = ActionableRequirementSelector().select(
        ActionableRequirementSelectionRequest(contract, run_state(contract, semantic_progress=ledger))
    )

    assert "FC-1" not in selected
    assert selected[0] == "FC-2"


def test_regression_shape_avoids_rerunning_blocked_prerequisite_cycle():
    contract = contract_for("cache_rules", "FC", {"FC-2": ["FC-1"]})
    planner = DynamicTddPlanner(None)
    blocked = TddStepDecision(status="propose", rationale="wrong next step", proposal=step("FC-2", "cache_rules"))

    with pytest.raises(ValueError, match="currently actionable"):
        planner._validate_decision(type("Req", (), {"contract": contract, "run_state": run_state(contract), "decision": blocked})())

    ledger = SemanticProgressLedger(
        provisional_requirements=[
            ProvisionalRequirementState(
                requirement_ref="FC-1",
                development_revision="d" * 40,
                originating_step_id="fc-1-step",
                accepted_test_names=["tests/test_cache_rules.py::test_fc_1"],
                open_obligation_ids=["fc-1::obligation::1"],
            )
        ],
        open_obligations=[
            OpenSemanticObligation(
                obligation_id="fc-1::obligation::1",
                owning_requirement_ref="FC-1",
                blocking_requirement_refs=["FC-2"],
                rationale="FC-2 must close the semantic obligation.",
                evidence_refs=["FC-SRC-2"],
                originating_step_id="fc-1-step",
                introduced_revision="d" * 40,
            )
        ],
    )
    allowed = ActionableRequirementSelector().select(
        ActionableRequirementSelectionRequest(contract, run_state(contract, development_base_revision="d" * 40, semantic_progress=ledger))
    )

    assert allowed == ["FC-2", "FC-3"]


def test_resume_uses_development_base_revision_for_repository_material(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "Test User")
    src = repo / "src"
    tests_dir = repo / "tests"
    src.mkdir()
    tests_dir.mkdir()
    (src / "order_book.py").write_text("VALUE = 'semantic'\n")
    (tests_dir / "test_order_book.py").write_text("def test_ob_1():\n    assert True\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "semantic")
    semantic_rev = git(repo, "rev-parse", "HEAD")
    (src / "order_book.py").write_text("VALUE = 'development'\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "development")
    development_rev = git(repo, "rev-parse", "HEAD")

    contract = contract_for("order_book", "OB")
    state = BehaviorContractRunState(
        contract=contract,
        repository_binding=binding(semantic_rev, root=str(repo)),
        semantic_base_revision=semantic_rev,
        development_base_revision=development_rev,
    )
    material = GitTesterRepositoryMaterialProvider(repo).render(RepositoryMaterialRequest(contract, state))

    assert material["trusted_revision"] == development_rev
    assert "development" in material["production_files"][0]["content"]


def test_completion_is_blocked_while_unresolved_obligations_remain():
    contract = contract_for("cache_rules", "FC")
    ledger = SemanticProgressLedger(
        provisional_requirements=[
            ProvisionalRequirementState(
                requirement_ref="FC-1",
                development_revision="d" * 40,
                originating_step_id="fc-1-step",
                accepted_test_names=["tests/test_cache_rules.py::test_fc_1"],
                open_obligation_ids=["fc-1::obligation::1"],
            )
        ],
        open_obligations=[
            OpenSemanticObligation(
                obligation_id="fc-1::obligation::1",
                owning_requirement_ref="FC-1",
                blocking_requirement_refs=["FC-2"],
                rationale="FC-2 must close the semantic obligation.",
                evidence_refs=["FC-SRC-2"],
                originating_step_id="fc-1-step",
                introduced_revision="d" * 40,
            )
        ],
    )
    state = run_state(
        contract,
        completed_requirement_refs=["FC-1", "FC-2", "FC-3"],
        semantic_progress=ledger,
    )
    decision = TddStepDecision(status="complete", rationale="done")

    with pytest.raises(ValueError, match="open semantic obligations"):
        DynamicTddPlanner(None)._validate_decision(
            type("Req", (), {"contract": contract, "run_state": state, "decision": decision})()
        )


def test_targeted_requirement_is_priority_signal_not_exclusive_selector():
    contract = contract_for("order_book", "OB")
    selected = ActionableRequirementSelector().select(
        ActionableRequirementSelectionRequest(contract, run_state(contract, targeted_requirement_ref="OB-2"))
    )

    assert selected[0] == "OB-2"
    assert set(selected) == {"OB-1", "OB-2", "OB-3"}
