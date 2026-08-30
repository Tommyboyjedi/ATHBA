import json
from dataclasses import replace

import pytest

from core.development.behavior_contract_coordinator import BehaviorContractCoordinator, SemanticReviewRequest, StepDecisionRequest
from core.development.specification_gatekeeper import (
    SpecificationChecklistPlanner,
    SpecificationGapTddAdapter,
    SpecificationGatekeeper,
)
from core.development.tdd_progression import (
    BehaviorContract,
    BehaviorContractRunState,
    ChecklistEvidence,
    ChecklistItemAssessment,
    ContractCycleRecord,
    GatekeeperAssessmentRecord,
    SemanticReviewResult,
    SourceRequirementClause,
    SpecificationChecklist,
    SpecificationChecklistItem,
    SpecificationGap,
    SpecificationGatekeeperRunState,
    TddPhase,
    TddPhaseState,
    TddSnapshot,
    TddStepDecision,
    TddStepProposal,
    green_work_unit_id,
    red_work_unit_id,
)
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.reasoning_gateway import ReasoningRequest, ReasoningResult
from core.execution.work_unit_gateway import WorkUnitExecutionResult


class FakeReasoningGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, dict):
            return ReasoningResult(text=json.dumps(response), provider="fake", model="fake-model")
        return ReasoningResult(text=response, provider="fake", model="fake-model")


class FakeExecutionGateway:
    def __init__(self, results):
        self.results = dict(results)
        self.calls = []

    async def execute(self, work_unit, repository_binding):
        self.calls.append((work_unit.id, repository_binding.base_sha, work_unit.objective))
        return self.results[work_unit.id]


class MemoryStateRepo:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot
        self.saved = []

    def load(self, project_id: str):
        return self.snapshot

    def save(self, snapshot: TddSnapshot):
        self.snapshot = snapshot
        self.saved.append(snapshot)
        return snapshot


class StaticReviewMaterialProvider:
    def __init__(self, text: str):
        self.text = text

    def render(self, request):
        return self.text


class SequenceStepPlanner:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = []

    async def decide_next_step(self, request: StepDecisionRequest) -> TddStepDecision:
        self.calls.append((request.contract.id, request.run_state.current_pool, list(request.run_state.completed_requirement_refs)))
        return self.decisions.pop(0)


class StubReviewer:
    def __init__(self, review_result: SemanticReviewResult):
        self.review_result = review_result
        self.calls = []

    async def review(self, request: SemanticReviewRequest):
        self.calls.append((request.contract.id, request.cycle.step.step_id, request.candidate_revision, request.review_material))
        return self.review_result


def binding(base_sha="a" * 40, *, registered_root=None):
    return RepositoryBinding(
        repository_id="reservation-book-fixture",
        base_ref="main",
        base_sha=base_sha,
        registered_root=registered_root,
    )


def requirement_text() -> str:
    return (
        "Build a small in-memory ReservationBook for reservable resources. "
        "A resource has a unique id and a positive integer capacity. "
        "Clients can add resources, create uniquely identified reservations for a number of units on a resource, "
        "cancel reservations, and query remaining availability. "
        "Reject duplicate resource ids, duplicate reservation ids, reservations for unknown resources, "
        "cancellation of unknown reservations, zero or negative quantities, and reservations exceeding remaining capacity. "
        "Failed operations must not corrupt existing state. Cancelling a reservation restores that capacity. "
        "The implementation must be in-memory only, dependency-free, small, direct, readable Python 3.14, "
        "suitable for pytest, and free of unnecessary abstractions."
    )


def checklist_payload():
    return {
        "items": [
            {"ref": "SPEC-1", "text": "A resource has a unique id.", "kind": "validation", "evidence_kind": "test"},
            {"ref": "SPEC-2", "text": "Resource capacity must be positive.", "kind": "validation", "evidence_kind": "test"},
            {"ref": "SPEC-3", "text": "The implementation must remain readable and free of unnecessary abstractions.", "kind": "quality", "evidence_kind": "review"},
        ]
    }


def contract_payload():
    return {
        "id": "contract-reservation-book",
        "project_id": "reservation-book",
        "component_name": "ReservationBook",
        "capability": "Manage in-memory reservations for resources.",
        "requirement_source": requirement_text(),
        "source_clauses": checklist_payload()["items"],
        "observable_requirements": [
            {
                "ref": "BC-1",
                "source_refs": ["SPEC-1", "SPEC-2", "SPEC-3"],
                "summary": "Add a resource with a unique id and readable implementation safeguards.",
                "observable_outcome": "add_resource stores a new resource and rejects invalid capacity.",
                "test_hint": "test_add_resource_unique_and_positive_capacity",
                "error_expectation": "duplicate ids and non-positive capacity raise ValueError",
                "preserves_state_on_failure": True,
            }
        ],
        "invariants": [
            "resource ids are unique",
            "failed operations do not corrupt existing state",
        ],
        "production_paths": ["reservation_book.py"],
        "test_paths": ["tests/test_reservation_book.py"],
        "public_api": ["add_resource(resource_id: str, capacity: int)"],
        "error_semantics": ["invalid operations raise ValueError"],
        "non_goals": ["no persistence"],
        "completion_criteria": ["all relevant obligations are proven by accepted evidence"],
        "status": "approved",
    }


def contract() -> BehaviorContract:
    return BehaviorContract.from_dict(contract_payload())


def single_item_checklist() -> SpecificationChecklist:
    return SpecificationChecklist.from_dict(
        {
            "project_id": "reservation-book",
            "requirement_text": requirement_text(),
            "items": [checklist_payload()["items"][0]],
        }
    )


def approved_cycle(requirement_ref="BC-1", *, step_id="step-1", test_name=None):
    step = TddStepProposal(
        step_id=step_id,
        requirement_refs=[requirement_ref],
        focused_behavior="Adding a resource keeps the identifier unique.",
        test_name=test_name or "tests/test_reservation_book.py::test_add_resource_unique_and_positive_capacity",
        expected_result="Duplicate ids fail and a valid resource can be added.",
        test_path="tests/test_reservation_book.py",
        production_path="reservation_book.py",
        red_objective="Add one failing pytest test for add_resource uniqueness and positive capacity.",
        green_objective="Implement only enough add_resource logic to satisfy the focused test.",
        reason_next_smallest="This proves the first accepted resource behavior.",
    )
    review = SemanticReviewResult(
        verdict="approved",
        rationale="Readable and small.",
        findings=["clean"],
        candidate_revision="c" * 40,
        step_id=step.step_id,
        evidence_refs=["review:1"],
        repair_instructions=[],
    )
    cycle = ContractCycleRecord.from_step(step, base_revision="a" * 40)
    return replace(
        cycle,
        red_phase=TddPhaseState(
            phase=TddPhase.RED.value,
            work_unit_id=red_work_unit_id(step.step_id),
            status="checks_passed",
            accepted_revision="b" * 40,
        ),
        green_phase=TddPhaseState(
            phase=TddPhase.GREEN.value,
            work_unit_id=green_work_unit_id(step.step_id),
            status="checks_passed",
            accepted_revision="c" * 40,
            evidence_location=f"/tmp/{step.step_id}.json",
        ),
        candidate_revision="c" * 40,
        semantic_revision="c" * 40,
        review_result=review,
        review_history=[review],
        pool="approved",
    )


def accepted(work_unit_id: str, revision: str):
    return WorkUnitExecutionResult(
        work_unit_id=work_unit_id,
        accepted=True,
        status="checks_passed",
        accepted_revision=revision,
        change_id=f"change-{work_unit_id}",
        evidence_location=f"/tmp/{work_unit_id}.json",
    )


def run_state(current_pool="approved", completed_requirement_refs=None, cycles=None, gatekeeper_state=None, contract_state=None):
    active_contract = contract_state or contract()
    return BehaviorContractRunState(
        contract=active_contract,
        repository_binding=binding("c" * 40),
        semantic_base_revision="c" * 40,
        current_pool=current_pool,
        completed_requirement_refs=completed_requirement_refs or ["BC-1"],
        cycles=cycles or [],
        gatekeeper_state=gatekeeper_state,
    )


@pytest.mark.asyncio
async def test_valid_component_requirement_can_produce_checklist():
    planner = SpecificationChecklistPlanner(FakeReasoningGateway([checklist_payload()]))

    checklist = await planner.create_checklist(project_id="reservation-book", requirement_text=requirement_text())

    assert checklist.item_refs() == ["SPEC-1", "SPEC-2", "SPEC-3"]
    assert checklist.items[0] == SpecificationChecklistItem(
        ref="SPEC-1",
        text="A resource has a unique id.",
        kind="validation",
    )


@pytest.mark.asyncio
async def test_malformed_or_invalid_checklist_output_fails_closed():
    planner = SpecificationChecklistPlanner(FakeReasoningGateway(["not json"]))
    with pytest.raises(ValueError, match="specification checklist response was not valid JSON"):
        await planner.create_checklist(project_id="reservation-book", requirement_text=requirement_text())

    bad_kind = SpecificationChecklistPlanner(FakeReasoningGateway([{"items": [{"ref": "SPEC-1", "text": "x", "kind": "string"}]}]))
    with pytest.raises(ValueError, match="unsupported checklist item kind"):
        await bad_kind.create_checklist(project_id="reservation-book", requirement_text=requirement_text())


def test_checklist_round_trip_defaults_and_duplicates_are_validated():
    checklist = SpecificationChecklist(
        project_id="reservation-book",
        requirement_text=requirement_text(),
        items=[SourceRequirementClause.from_dict(item) for item in checklist_payload()["items"]],
    )
    restored = SpecificationChecklist.from_dict(checklist.to_dict())
    assert restored.item_refs() == ["SPEC-1", "SPEC-2", "SPEC-3"]

    legacy = SourceRequirementClause.from_dict({"ref": "SPEC-9", "text": "Readable code.", "kind": "quality"})
    assert legacy.evidence_kind == "review"

    with pytest.raises(ValueError, match="specification checklist items must not be empty"):
        SpecificationChecklist(project_id="reservation-book", requirement_text=requirement_text(), items=[])

    with pytest.raises(ValueError, match="duplicate checklist item refs"):
        SpecificationChecklist(
            project_id="reservation-book",
            requirement_text=requirement_text(),
            items=[
                SourceRequirementClause(ref="SPEC-1", text="a", kind="behavior"),
                SourceRequirementClause(ref="SPEC-1", text="b", kind="validation"),
            ],
        )


def test_quality_evidence_kind_alias_normalizes_to_review():
    clause = SourceRequirementClause.from_dict(
        {"ref": "SPEC-10", "text": "Readable code.", "kind": "quality", "evidence_kind": "quality"}
    )

    assert clause.evidence_kind == "review"


@pytest.mark.asyncio
async def test_semantically_unapproved_green_cannot_close_checklist_item():
    active_contract = contract()
    step = TddStepProposal(
        step_id="step-unapproved",
        requirement_refs=["BC-1"],
        focused_behavior="Adding a resource keeps the identifier unique.",
        test_name="tests/test_reservation_book.py::test_add_resource_unique_and_positive_capacity",
        expected_result="Duplicate ids fail and a valid resource can be added.",
        test_path="tests/test_reservation_book.py",
        production_path="reservation_book.py",
        red_objective="Add one failing pytest test for add_resource uniqueness and positive capacity.",
        green_objective="Implement only enough add_resource logic to satisfy the focused test.",
        reason_next_smallest="This proves the first accepted resource behavior.",
    )
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="a" * 40),
        red_phase=TddPhaseState(
            phase=TddPhase.RED.value,
            work_unit_id=red_work_unit_id(step.step_id),
            status="checks_passed",
            accepted_revision="b" * 40,
        ),
        green_phase=TddPhaseState(
            phase=TddPhase.GREEN.value,
            work_unit_id=green_work_unit_id(step.step_id),
            status="checks_passed",
            accepted_revision="c" * 40,
            evidence_location="/tmp/step-unapproved.json",
        ),
        candidate_revision="c" * 40,
        pool="review_ready",
    )
    checklist = single_item_checklist()
    gatekeeper = SpecificationGatekeeper(FakeReasoningGateway([]))

    state = await gatekeeper.assess(
        active_contract,
        run_state(cycles=[cycle], gatekeeper_state=SpecificationGatekeeperRunState(checklist=checklist), contract_state=active_contract),
        SpecificationGatekeeperRunState(checklist=checklist),
    )

    assert state.latest_assessment is not None
    assert state.latest_assessment.item_assessments[0].status == "missing_test_evidence"


@pytest.mark.asyncio
async def test_completed_checklist_item_does_not_reopen_without_changed_evidence():
    active_contract = contract()
    cycle = approved_cycle()
    checklist = single_item_checklist()
    gateway = FakeReasoningGateway(
        [
            {
                "status": "proven",
                "rationale": "The accepted add_resource test proves unique resource ids.",
                "selected_test_names": [cycle.step.test_name],
            },
            {
                "status": "proven",
                "rationale": "The accepted add_resource test proves unique resource ids.",
                "selected_test_names": [cycle.step.test_name],
            },
        ]
    )
    gatekeeper = SpecificationGatekeeper(gateway)
    initial = await gatekeeper.assess(
        active_contract,
        run_state(cycles=[cycle], gatekeeper_state=SpecificationGatekeeperRunState(checklist=checklist), contract_state=active_contract),
        SpecificationGatekeeperRunState(checklist=checklist),
    )
    repeated = await gatekeeper.assess(
        active_contract,
        run_state(cycles=[cycle], gatekeeper_state=initial, contract_state=active_contract),
        initial,
    )

    assert initial.latest_assessment is not None
    assert repeated.latest_assessment is not None
    assert initial.latest_assessment.item_assessments[0].status == "proven"
    assert repeated.latest_assessment.item_assessments[0].status == "proven"


@pytest.mark.asyncio
async def test_gatekeeper_preserves_multiple_independent_obligation_classes():
    checklist = await SpecificationChecklistPlanner(FakeReasoningGateway([checklist_payload()])).create_checklist(
        project_id="reservation-book",
        requirement_text=requirement_text(),
    )

    assert {item.kind for item in checklist.items} == {"validation", "quality"}
    assert all("evidence_kind" not in item.to_dict() for item in checklist.items)


@pytest.mark.asyncio
async def test_accepted_tdd_and_review_evidence_can_prove_independent_items():
    active_contract = contract()
    cycle = approved_cycle()
    checklist = SpecificationChecklist.from_dict(
        {
            "project_id": "reservation-book",
            "requirement_text": requirement_text(),
            "items": [checklist_payload()["items"][0], checklist_payload()["items"][2]],
        }
    )
    gatekeeper = SpecificationGatekeeper(
        FakeReasoningGateway(
            [
                {
                    "status": "proven",
                    "rationale": "The accepted add_resource test proves unique resource ids.",
                    "selected_test_names": [cycle.step.test_name],
                }
            ]
        )
    )

    state = await gatekeeper.assess(
        active_contract,
        run_state(cycles=[cycle], gatekeeper_state=SpecificationGatekeeperRunState(checklist=checklist), contract_state=active_contract),
        SpecificationGatekeeperRunState(checklist=checklist),
    )

    assert state.latest_assessment is not None
    assessments = {item.checklist_ref: item for item in state.latest_assessment.item_assessments}
    assert assessments["SPEC-1"].status == "proven"
    assert assessments["SPEC-1"].evidence[0].test_name == cycle.step.test_name
    assert assessments["SPEC-3"].status == "proven"
    assert assessments["SPEC-3"].evidence[0].evidence_kind == "review"
    assert state.latest_assessment.status == "complete"


@pytest.mark.asyncio
async def test_invented_evidence_is_downgraded_and_state_round_trips():
    active_contract = contract()
    cycle = approved_cycle()
    checklist = single_item_checklist()
    gatekeeper = SpecificationGatekeeper(
        FakeReasoningGateway(
            [
                {
                    "status": "proven",
                    "rationale": "This test proves it.",
                    "selected_test_names": ["tests/test_reservation_book.py::test_invented"],
                }
            ]
        )
    )

    assessed = await gatekeeper.assess(
        active_contract,
        run_state(cycles=[cycle], gatekeeper_state=SpecificationGatekeeperRunState(checklist=checklist), contract_state=active_contract),
        SpecificationGatekeeperRunState(checklist=checklist),
    )

    restored = BehaviorContractRunState.from_dict(
        run_state(cycles=[cycle], gatekeeper_state=assessed, contract_state=active_contract).to_dict()
    )

    assert assessed.latest_assessment is not None
    assert assessed.latest_assessment.status == "incomplete"
    assert assessed.latest_assessment.item_assessments[0].status == "uncertain"
    assert restored.gatekeeper_state is not None
    assert restored.gatekeeper_state.latest_assessment is not None
    assert restored.gatekeeper_state.latest_assessment.item_assessments[0].status == "uncertain"


def test_gatekeeper_records_explicit_evidence_and_assessment_round_trip():
    evidence = ChecklistEvidence(
        checklist_ref="SPEC-1",
        evidence_kind="test",
        test_name="tests/test_reservation_book.py::test_add_resource_unique_and_positive_capacity",
        test_path="tests/test_reservation_book.py",
        step_id="step-1",
        requirement_ref="BC-1",
        accepted_revision="b" * 40,
        semantic_revision="c" * 40,
        evidence_location="/tmp/step-1.json",
        rationale="The accepted test proves duplicate ids are rejected.",
    )
    assessment = GatekeeperAssessmentRecord(
        status="complete",
        item_assessments=[
            ChecklistItemAssessment.from_dict(
                {
                    "checklist_ref": "SPEC-1",
                    "status": "proven",
                    "rationale": "covered",
                    "evidence": [evidence.to_dict()],
                }
            )
        ],
    )
    restored = GatekeeperAssessmentRecord.from_dict(assessment.to_dict())

    assert restored.status == "complete"
    assert restored.item_assessments[0].evidence[0].test_name == evidence.test_name

@pytest.mark.asyncio
async def test_gatekeeper_matches_equivalent_checklist_text_when_refs_drift():
    payload = contract_payload()
    payload["source_clauses"] = [
        {"ref": "REQ-010", "text": "Reject duplicate reservation ids.", "kind": "validation", "evidence_kind": "test"}
    ]
    payload["observable_requirements"] = [
        {
            "ref": "BC-10",
            "source_refs": ["REQ-010"],
            "summary": "Reject duplicate reservation ids.",
            "observable_outcome": "Duplicate reservation ids raise ValueError.",
            "test_hint": "test_duplicate_reservation_ids_are_rejected",
            "error_expectation": "duplicate reservation ids raise ValueError",
            "preserves_state_on_failure": True,
        }
    ]
    active_contract = BehaviorContract.from_dict(payload)
    step = TddStepProposal(
        step_id="step-drift",
        requirement_refs=["BC-10"],
        focused_behavior="Duplicate reservation ids are rejected.",
        test_name="tests/test_reservation_book.py::test_duplicate_reservation_ids_are_rejected",
        expected_result="A second reservation with the same id raises ValueError.",
        test_path="tests/test_reservation_book.py",
        production_path="reservation_book.py",
        red_objective="Add one failing pytest test for duplicate reservation ids.",
        green_objective="Implement only enough logic to reject duplicate reservation ids.",
        reason_next_smallest="This is a single observable validation rule.",
    )
    review = SemanticReviewResult(
        verdict="approved",
        rationale="Readable and small.",
        findings=["clean"],
        candidate_revision="d" * 40,
        step_id=step.step_id,
        evidence_refs=["review:drift"],
        repair_instructions=[],
    )
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="a" * 40),
        red_phase=TddPhaseState(
            phase=TddPhase.RED.value,
            work_unit_id=red_work_unit_id(step.step_id),
            status="checks_passed",
            accepted_revision="b" * 40,
        ),
        green_phase=TddPhaseState(
            phase=TddPhase.GREEN.value,
            work_unit_id=green_work_unit_id(step.step_id),
            status="checks_passed",
            accepted_revision="d" * 40,
            evidence_location="/tmp/step-drift.json",
        ),
        candidate_revision="d" * 40,
        semantic_revision="d" * 40,
        review_result=review,
        review_history=[review],
        pool="approved",
    )
    checklist = SpecificationChecklist.from_dict(
        {
            "project_id": "reservation-book",
            "requirement_text": requirement_text(),
            "items": [{"ref": "REQ-08", "text": "Reject duplicate reservation ids.", "kind": "validation", "evidence_kind": "test"}],
        }
    )
    gatekeeper = SpecificationGatekeeper(
        FakeReasoningGateway(
            [
                {
                    "status": "proven",
                    "rationale": "The accepted duplicate-reservation test proves the obligation.",
                    "selected_test_names": [step.test_name],
                }
            ]
        )
    )

    state = await gatekeeper.assess(
        active_contract,
        run_state(cycles=[cycle], gatekeeper_state=SpecificationGatekeeperRunState(checklist=checklist), contract_state=active_contract, completed_requirement_refs=["BC-10"]),
        SpecificationGatekeeperRunState(checklist=checklist),
    )

    assert state.latest_assessment is not None
    assert state.latest_assessment.item_assessments[0].status == "proven"


def test_gap_adapter_uses_contract_source_ref_when_checklist_ref_drifts():
    payload = contract_payload()
    payload["source_clauses"] = [
        {"ref": "REQ-010", "text": "Reject duplicate reservation ids.", "kind": "validation", "evidence_kind": "test"}
    ]
    payload["observable_requirements"] = [
        {
            "ref": "BC-10",
            "source_refs": ["REQ-010"],
            "summary": "Reject duplicate reservation ids.",
            "observable_outcome": "Duplicate reservation ids raise ValueError.",
            "test_hint": "test_duplicate_reservation_ids_are_rejected",
            "error_expectation": "duplicate reservation ids raise ValueError",
            "preserves_state_on_failure": True,
        }
    ]
    active_contract = BehaviorContract.from_dict(payload)
    gap = SpecificationGap(
        checklist_ref="REQ-08",
        obligation_text="Reject duplicate reservation ids.",
        item_kind="validation",
        reason="No accepted executable proof yet.",
        desired_proof="Add accepted executable proof for duplicate reservation ids.",
        related_test_names=[],
    )

    updated = SpecificationGapTddAdapter().extend_contract_for_gap(active_contract, gap)
    supplemental = next(item for item in updated.observable_requirements if item.ref.startswith("GK-REQ-08-"))

    assert supplemental.source_refs == ["REQ-010"]




def test_gap_adapter_adds_supplemental_requirement_without_suppressing_existing_source_ref():
    adapter = SpecificationGapTddAdapter()
    gap = SpecificationGap(
        checklist_ref="SPEC-2",
        obligation_text="Resource capacity must be positive.",
        item_kind="validation",
        reason="No accepted executable proof yet.",
        desired_proof="Add accepted executable proof for positive capacity rejection.",
        related_test_names=[],
    )

    updated = adapter.extend_contract_for_gap(contract(), gap)
    repeated = adapter.extend_contract_for_gap(updated, gap)

    gap_requirements = [item for item in updated.observable_requirements if item.ref.startswith("GK-SPEC-2-")]
    assert len(gap_requirements) == 1
    assert gap_requirements[0].source_refs == ["SPEC-2"]
    assert gap_requirements[0].error_expectation == "Add executable proof for the missing validation outcome."
    assert len(repeated.observable_requirements) == len(updated.observable_requirements)


@pytest.mark.asyncio
async def test_coordinator_blocks_completion_until_checklist_is_proven():
    planner = SequenceStepPlanner(
        [TddStepDecision(status="complete", rationale="The contract appears finished.", completed_requirement_refs=["BC-1"])]
    )
    gateway = FakeReasoningGateway([checklist_payload()])
    state_repo = MemoryStateRepo()
    coordinator = BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({}),
        reasoning_gateway=gateway,
        repository_binding=binding("a" * 40),
        state_repo=state_repo,
        step_planner=planner,
        reviewer=StubReviewer(
            SemanticReviewResult(
                verdict="approved",
                rationale="ok",
                findings=[],
                candidate_revision="c" * 40,
                step_id="unused",
            )
        ),
        review_material_provider=StaticReviewMaterialProvider("review"),
        gatekeeper=SpecificationGatekeeper(gateway),
    )

    result = await coordinator.run_contract(contract())

    saved_run = state_repo.snapshot.contract_runs["contract-reservation-book"]
    assert result.current_pool == "approved"
    assert result.blocked_reason == "specification checklist incomplete"
    assert saved_run.gatekeeper_state is not None
    assert saved_run.gatekeeper_state.latest_assessment is not None
    assert saved_run.gatekeeper_state.latest_assessment.status == "incomplete"
    assert saved_run.gatekeeper_state.latest_assessment.gaps[0].checklist_ref == "SPEC-1"


@pytest.mark.asyncio
async def test_coordinator_can_reenter_tdd_lane_for_targeted_gap():
    planner = SequenceStepPlanner(
        [
            TddStepDecision(status="complete", rationale="The original requirement set appears finished.", completed_requirement_refs=["BC-1"]),
            TddStepDecision(
                status="propose",
                rationale="A targeted proof is still needed for SPEC-1.",
                proposal=TddStepProposal(
                    step_id="gap-step-1",
                    requirement_refs=["GK-SPEC-1-1"],
                    focused_behavior="Add accepted executable proof for unique resource ids.",
                    test_name="tests/test_reservation_book.py::test_add_resource_unique_and_positive_capacity",
                    expected_result="Duplicate resource ids raise ValueError.",
                    test_path="tests/test_reservation_book.py",
                    production_path="reservation_book.py",
                    red_objective="Add one failing pytest test for duplicate resource ids.",
                    green_objective="Implement only enough add_resource logic to satisfy the targeted gap proof.",
                    reason_next_smallest="This is the missing executable proof for SPEC-1.",
                ),
            ),
            TddStepDecision(status="complete", rationale="The targeted gap is now covered.", completed_requirement_refs=["BC-1", "GK-SPEC-1-1"]),
        ]
    )
    gateway = FakeReasoningGateway(
        [
            {
                "items": [
                    {"ref": "SPEC-1", "text": "A resource has a unique id.", "kind": "validation", "evidence_kind": "test"}
                ]
            },
            {
                "status": "proven",
                "rationale": "The accepted targeted pytest proves SPEC-1.",
                "selected_test_names": ["tests/test_reservation_book.py::test_add_resource_unique_and_positive_capacity"],
            },
        ]
    )
    reviewer = StubReviewer(
        SemanticReviewResult(
            verdict="approved",
            rationale="Readable and small.",
            findings=["clean"],
            candidate_revision="d" * 40,
            step_id="gap-step-1",
            evidence_refs=["review:gap"],
            repair_instructions=[],
        )
    )
    execution_gateway = FakeExecutionGateway(
        {
            red_work_unit_id("gap-step-1"): accepted(red_work_unit_id("gap-step-1"), "b" * 40),
            green_work_unit_id("gap-step-1"): accepted(green_work_unit_id("gap-step-1"), "d" * 40),
        }
    )
    state_repo = MemoryStateRepo()
    coordinator = BehaviorContractCoordinator(
        execution_gateway=execution_gateway,
        reasoning_gateway=gateway,
        repository_binding=binding("a" * 40),
        state_repo=state_repo,
        step_planner=planner,
        reviewer=reviewer,
        review_material_provider=StaticReviewMaterialProvider("review"),
        gatekeeper=SpecificationGatekeeper(gateway),
        gap_adapter=SpecificationGapTddAdapter(),
    )

    result = await coordinator.run_contract(contract())

    saved_run = state_repo.snapshot.contract_runs["contract-reservation-book"]
    assert result.current_pool == "completed"
    assert saved_run.current_pool == "completed"
    assert saved_run.gatekeeper_state is not None
    assert saved_run.gatekeeper_state.is_complete()
    assert any(item.ref == "GK-SPEC-1-1" for item in saved_run.contract.observable_requirements)
    assert any(call[0] == red_work_unit_id("gap-step-1") for call in execution_gateway.calls)
    assert any(call[0] == green_work_unit_id("gap-step-1") for call in execution_gateway.calls)


@pytest.mark.asyncio
async def test_untraceable_executable_gap_blocks_before_ordinary_tdd():
    gateway = FakeReasoningGateway([
        {
            "items": [
                {
                    "ref": "SPEC-UNTRACEABLE",
                    "text": "An invented broad obligation.",
                    "kind": "validation",
                    "evidence_kind": "test",
                }
            ]
        }
    ])
    execution_gateway = FakeExecutionGateway({})
    coordinator = BehaviorContractCoordinator(
        execution_gateway=execution_gateway,
        reasoning_gateway=gateway,
        repository_binding=binding("a" * 40),
        state_repo=MemoryStateRepo(),
        step_planner=SequenceStepPlanner([]),
        reviewer=StubReviewer(
            SemanticReviewResult(
                verdict="approved",
                rationale="unused",
                findings=[],
                candidate_revision="a" * 40,
                step_id="unused",
            )
        ),
        review_material_provider=StaticReviewMaterialProvider("unused"),
        gatekeeper=SpecificationGatekeeper(gateway),
        gap_adapter=SpecificationGapTddAdapter(),
    )

    result = await coordinator.run_contract(contract())

    assert result.current_pool == "replan_ready"
    assert result.blocked_reason == "specification checklist has no traceable executable gap"
    assert execution_gateway.calls == []
