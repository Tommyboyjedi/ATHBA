import json
import subprocess

import pytest

from core.development.test_evidence_reconciliation import GitAcceptedTestCatalog, TestEvidenceReconciler
from core.development.tdd_progression import (
    BehaviorContract,
    BehaviorContractRequirement,
    BehaviorContractRunState,
    ContractCycleRecord,
    SourceRequirementClause,
    SpecificationChecklist,
    SpecificationChecklistItem,
    TddPhaseState,
    TddStepProposal,
)
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.reasoning_gateway import ReasoningRequest, ReasoningResult


class FakeReasoningGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.requests.append(request)
        return ReasoningResult(text=json.dumps(self.responses.pop(0)), provider="fake", model="fake")


def _contract() -> BehaviorContract:
    clause = SourceRequirementClause(ref="SRC-1", text="Clients can add resources.", kind="behavior")
    requirement = BehaviorContractRequirement(
        ref="BR-1",
        source_refs=["SRC-1"],
        summary="Add resource",
        observable_outcome="A resource can be added.",
        test_hint="add resource",
    )
    return BehaviorContract(
        id="contract-1",
        project_id="project-1",
        component_name="ReservationBook",
        capability="resource reservations",
        requirement_source="Clients can add resources.",
        source_clauses=[clause],
        observable_requirements=[requirement],
        invariants=["resources remain addressable"],
        production_paths=["reservation_book.py"],
        test_paths=["tests/test_reservation_book.py"],
    )


def _run_state(revision: str) -> BehaviorContractRunState:
    step = TddStepProposal(
        step_id="STEP-1",
        requirement_refs=["BR-1"],
        focused_behavior="add a resource",
        test_name="tests/test_reservation_book.py::test_add_resource",
        expected_result="resource is available",
        test_path="tests/test_reservation_book.py",
        production_path="reservation_book.py",
        red_objective="test fails before implementation",
        green_objective="test passes after implementation",
        reason_next_smallest="first behavior",
    )
    cycle = ContractCycleRecord(
        step=step,
        pool="approved",
        base_revision="a" * 40,
        red_phase=TddPhaseState(phase="red", work_unit_id="STEP-1--red", accepted_revision="b" * 40),
        green_phase=TddPhaseState(phase="green", work_unit_id="STEP-1--green", accepted_revision=revision),
        candidate_revision=revision,
        semantic_revision=revision,
    )
    return BehaviorContractRunState(
        contract=_contract(),
        repository_binding=RepositoryBinding(repository_id="fixture", base_ref="main", base_sha=revision),
        semantic_base_revision=revision,
        current_pool="completed",
        completed_requirement_refs=["BR-1"],
        cycles=[cycle],
    )


def _head_revision(root):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, text=True, capture_output=True).stdout.strip()


def _commit_all(root, message):
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "-qm", message],
        cwd=root,
        check=True,
    )
    return _head_revision(root)


def _repository(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "reservation_book.py").write_text("class ReservationBook:\n    pass\n", encoding="utf-8")
    (tmp_path / "tests" / "test_reservation_book.py").write_text("def test_add_resource():\n    assert True\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return _commit_all(tmp_path, "seed")


def _checklist() -> SpecificationChecklist:
    return SpecificationChecklist(
        project_id="project-1",
        requirement_text="Clients can add resources.",
        items=[
            SpecificationChecklistItem(ref="CHECK-1", text="Clients can add resources.", kind="behavior"),
            SpecificationChecklistItem(ref="CHECK-2", text="The code is readable.", kind="quality"),
        ],
    )


@pytest.mark.asyncio
async def test_reconciler_returns_yes_only_for_accepted_final_test(tmp_path):
    revision = _repository(tmp_path)
    gateway = FakeReasoningGateway([
        {"answer": "YES", "selected_test_names": ["tests/test_reservation_book.py::test_add_resource"], "rationale": "direct"},
        {"answer": "NO", "selected_test_names": [], "rationale": "no unit test proves readability"},
    ])

    results = await TestEvidenceReconciler(gateway, GitAcceptedTestCatalog(tmp_path, revision)).reconcile(_checklist(), _run_state(revision))

    assert [item.answer for item in results] == ["YES", "NO"]
    assert results[0].accepted_test_names == ["tests/test_reservation_book.py::test_add_resource"]
    assert results[1].accepted_test_names == []
    assert len(gateway.requests) == 2


@pytest.mark.asyncio
async def test_reconciler_rejects_an_invented_test_identifier(tmp_path):
    revision = _repository(tmp_path)
    gateway = FakeReasoningGateway([
        {"answer": "YES", "selected_test_names": ["tests/test_reservation_book.py::test_invented"], "rationale": "invented"},
        {"answer": "NO", "selected_test_names": [], "rationale": "no"},
    ])

    results = await TestEvidenceReconciler(gateway, GitAcceptedTestCatalog(tmp_path, revision)).reconcile(_checklist(), _run_state(revision))

    assert results[0].answer == "NO"
    assert results[0].accepted_test_names == []
    assert "not present" in results[0].rationale


@pytest.mark.asyncio
async def test_reconciliation_is_pure_and_covers_every_checklist_item_once(tmp_path):
    revision = _repository(tmp_path)
    state = _run_state(revision)
    before = state.to_dict()
    gateway = FakeReasoningGateway([
        {"answer": "NO", "selected_test_names": [], "rationale": "not direct"},
        {"answer": "NO", "selected_test_names": [], "rationale": "not a unit test"},
    ])

    results = await TestEvidenceReconciler(gateway, GitAcceptedTestCatalog(tmp_path, revision)).reconcile(_checklist(), state)

    assert [item.checklist_ref for item in results] == ["CHECK-1", "CHECK-2"]
    assert state.to_dict() == before


@pytest.mark.asyncio
async def test_reconciler_rejects_accepted_test_missing_from_final_trusted_revision(tmp_path):
    initial_revision = _repository(tmp_path)
    (tmp_path / "tests" / "test_reservation_book.py").write_text("def test_other_behavior():\n    assert True\n", encoding="utf-8")
    final_revision = _commit_all(tmp_path, "remove accepted test")
    gateway = FakeReasoningGateway([
        {"answer": "YES", "selected_test_names": ["tests/test_reservation_book.py::test_add_resource"], "rationale": "older accepted test"},
        {"answer": "NO", "selected_test_names": [], "rationale": "no unit test proves readability"},
    ])

    results = await TestEvidenceReconciler(gateway, GitAcceptedTestCatalog(tmp_path, final_revision)).reconcile(_checklist(), _run_state(initial_revision))

    assert results[0].answer == "NO"
    assert results[0].accepted_test_names == []
    assert "preserved" in results[0].rationale


@pytest.mark.asyncio
async def test_reconciler_rejects_changed_test_body_at_final_trusted_revision(tmp_path):
    accepted_revision = _repository(tmp_path)
    (tmp_path / "tests" / "test_reservation_book.py").write_text(
        "def test_add_resource():\n    value = False\n    assert value\n",
        encoding="utf-8",
    )
    final_revision = _commit_all(tmp_path, "change accepted test body")
    gateway = FakeReasoningGateway([
        {"answer": "YES", "selected_test_names": ["tests/test_reservation_book.py::test_add_resource"], "rationale": "same node id"},
        {"answer": "NO", "selected_test_names": [], "rationale": "no unit test proves readability"},
    ])

    results = await TestEvidenceReconciler(gateway, GitAcceptedTestCatalog(tmp_path, final_revision)).reconcile(_checklist(), _run_state(accepted_revision))

    assert results[0].answer == "NO"
    assert results[0].accepted_test_names == []
    assert "preserved" in results[0].rationale
