import json
import subprocess
from types import SimpleNamespace
from dataclasses import replace
from pathlib import Path

import pytest

from core.development.behavior_contract_coordinator import (
    BehaviorContractCoordinator,
    BehaviorContractPlanner,
    ContractDeveloperWorkUnitFactory,
    ContractRepairWorkUnitFactory,
    ContractTesterWorkUnitFactory,
    DependencyDecisionRequest,
    DependencyPrerequisitePlanner,
    DynamicTddPlanner,
    GitReviewMaterialProvider,
    GitTesterRepositoryMaterialProvider,
    RepairWorkUnitBuildRequest,
    RepositoryMaterialRequest,
    RequirementClausePlanner,
    ReviewMaterialRequest,
    SemanticReviewRequest,
    SeniorReviewer,
    WorkUnitBuildRequest,
    _first_executable_gap,
)
from core.development.failure_progression import (
    FAILURE_ACTIONS,
    FAILURE_PRIORITY,
    DependencyDisposition,
    FailureClassification,
    FailureDecision,
    FailureObservation,
    FailureProgressState,
    FailureRouteState,
    PacketKind,
    ProgressionAction,
    RepairPacket,
    RetryRoute,
    SplitChildStep,
    WorkPacketSplit,
)
from core.development.tdd_progression import (
    BehaviorContract,
    BehaviorContractLoadOptions,
    BehaviorContractRequirement,
    BehaviorContractRunState,
    ContractCycleRecord,
    SemanticReviewResult,
    SourceRequirementClause,
    TddPhase,
    TddPhaseState,
    TddSnapshot,
    TddStepProposal,
)
from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.execution.rack_ai_contract import RepositoryBinding, find_forbidden_resource_selection_keys, to_rack_ai_request
from core.execution.reasoning_gateway import ReasoningRequest, ReasoningResult
from core.execution.work_unit_gateway import ExecutionPolicyEvidence, WorkUnitExecutionResult
from core.llm.contracts.provider import NormalizedResult, Provider, ProviderRequest


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
        self.calls.append((work_unit.id, repository_binding.base_sha, work_unit.objective, work_unit.change_key))
        result = self.results[work_unit.id]
        if isinstance(result, list):
            if not result:
                raise AssertionError(f"no more results configured for {work_unit.id}")
            return result.pop(0)
        return result


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


class FakeEnvironmentRecovery:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def recover_and_verify(self, project_id: str) -> bool:
        self.calls.append(project_id)
        return self.outcomes.pop(0)


class StubProvider(Provider):
    def __init__(self):
        self.calls = []

    def invoke(self, request: ProviderRequest):
        self.calls.append({
            "prompt": request.prompt,
            "model": request.model,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "response_schema": request.response_schema,
        })
        return NormalizedResult(
            text="{\"ok\": true}",
            usage={"input_tokens": 1, "output_tokens": 1},
            raw={"provider": "stub", "model": request.model},
        )


def binding(base_sha="a" * 40, *, registered_root=None):
    return RepositoryBinding(
        repository_id="reservation-book-fixture",
        base_ref="main",
        base_sha=base_sha,
        registered_root=None if registered_root is None else str(registered_root),
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


def source_clause_payload():
    return {
        "clauses": [
            {"ref": "SRC-1", "text": "A resource can be added with a unique id.", "kind": "behavior"},
            {"ref": "SRC-2", "text": "A resource capacity must be a positive integer.", "kind": "validation"},
            {"ref": "SRC-3", "text": "A reservation can be created for a known resource.", "kind": "behavior"},
            {"ref": "SRC-4", "text": "A reservation quantity must not exceed remaining capacity.", "kind": "validation"},
        ]
    }


def contract_payload():
    return {
        "id": "contract-reservation-book",
        "project_id": "reservation-book",
        "component_name": "ReservationBook",
        "capability": "Manage in-memory reservations for resources.",
        "requirement_source": requirement_text(),
        "source_clauses": source_clause_payload()["clauses"],
        "observable_requirements": [
            {
                "ref": "RB-1",
                "source_refs": ["SRC-1", "SRC-2"],
                "summary": "Add a resource with a unique id and positive capacity.",
                "observable_outcome": "add_resource stores a new resource and availability reflects full capacity.",
                "test_hint": "test_add_resource_sets_availability",
                "error_expectation": "duplicate resource ids and non-positive capacity raise ValueError",
                "preserves_state_on_failure": True,
            },
            {
                "ref": "RB-2",
                "source_refs": ["SRC-3", "SRC-4"],
                "summary": "Create a reservation on a known resource within remaining capacity.",
                "observable_outcome": "reserve stores the reservation and decreases availability.",
                "test_hint": "test_reserve_reduces_capacity",
                "error_expectation": "unknown resources and over-capacity reservations raise ValueError",
                "preserves_state_on_failure": True,
            },
        ],
        "invariants": [
            "resource ids are unique",
            "reservation ids are unique",
            "failed operations do not corrupt state",
        ],
        "production_paths": ["reservation_book.py"],
        "test_paths": ["tests/test_reservation_book.py"],
        "public_api": [
            "add_resource(resource_id: str, capacity: int)",
            "reserve(reservation_id: str, resource_id: str, quantity: int)",
            "cancel(reservation_id: str)",
            "available(resource_id: str)",
        ],
        "error_semantics": ["invalid operations raise ValueError"],
        "non_goals": ["no persistence", "no concurrency", "no external dependencies"],
        "completion_criteria": ["all source clauses are covered by observable requirements and accepted tests"],
        "status": "tdd_ready",
    }


def contract() -> BehaviorContract:
    return BehaviorContract.from_dict(contract_payload())


def test_contract_rejects_unknown_or_cyclic_requirement_dependencies():
    payload = contract_payload()
    payload["observable_requirements"][0]["depends_on"] = ["RB-404"]
    with pytest.raises(ValueError, match="must reference"):
        BehaviorContract.from_dict(payload)

    payload = contract_payload()
    payload["observable_requirements"][0]["depends_on"] = ["RB-2"]
    payload["observable_requirements"][1]["depends_on"] = ["RB-1"]
    with pytest.raises(ValueError, match="acyclic"):
        BehaviorContract.from_dict(payload)


@pytest.mark.asyncio
async def test_tdd_planner_rejects_a_requirement_before_its_prerequisite_is_approved():
    payload = contract_payload()
    payload["observable_requirements"][1]["depends_on"] = ["RB-1"]
    dependency_contract = BehaviorContract.from_dict(payload)
    step = proposal("RB-2")
    gateway = FakeReasoningGateway([{
        "status": "propose",
        "rationale": "Try the reservation behavior.",
        "proposal": step.to_dict(),
        "completed_requirement_refs": [],
    }])

    with pytest.raises(ValueError, match="prerequisites"):
        await DynamicTddPlanner(gateway).decide_next_step(dependency_contract, run_state())


def single_requirement_contract() -> BehaviorContract:
    payload = contract_payload()
    payload["source_clauses"] = payload["source_clauses"][:2]
    payload["observable_requirements"] = [payload["observable_requirements"][0]]
    return BehaviorContract.from_dict(payload)


def multi_production_contract() -> BehaviorContract:
    payload = contract_payload()
    payload["source_clauses"] = payload["source_clauses"][:2]
    payload["observable_requirements"] = [payload["observable_requirements"][0]]
    payload["production_paths"] = ["reservation_book.py", "reservation_index.py"]
    return BehaviorContract.from_dict(payload)


def proposal(requirement_ref="RB-1", *, step_id="step-1"):
    return TddStepProposal(
        step_id=step_id,
        requirement_refs=[requirement_ref],
        focused_behavior="Adding a new resource reports the full remaining capacity.",
        test_name="tests/test_reservation_book.py::test_add_resource_sets_availability",
        expected_result="available('room-a') returns 5 after adding room-a with capacity 5.",
        test_path="tests/test_reservation_book.py",
        production_path="reservation_book.py",
        red_objective="Add one failing pytest test proving add_resource stores capacity and exposes availability.",
        green_objective="Implement only enough ReservationBook code to store a resource and report availability.",
        reason_next_smallest="This establishes the base state every later reservation behavior depends on.",
    )


def split_child(step_id: str, *, depends_on: list[str] | None = None) -> SplitChildStep:
    return SplitChildStep(
        step_id=step_id,
        requirement_refs=["RB-1"],
        focused_behavior=f"{step_id} isolates one smaller observable slice of add_resource.",
        test_name=f"tests/test_reservation_book.py::test_{step_id.replace('-', '_')}",
        expected_result=f"{step_id} proves one accepted observable slice of add_resource.",
        test_path="tests/test_reservation_book.py",
        production_path="reservation_book.py",
        red_objective=f"Add a failing test for {step_id}.",
        green_objective=f"Implement only enough code for {step_id}.",
        reason_next_smallest=f"{step_id} is the next smallest bounded semantic slice.",
        depends_on=list(depends_on or []),
    )


def split_decision(*children: SplitChildStep) -> dict[str, object]:
    return {
        "status": "split",
        "rationale": "The packet exceeded the resource budget and must be decomposed into smaller semantic work.",
        "child_steps": [child.to_dict() for child in children],
    }


def cannot_split_decision(rationale: str) -> dict[str, object]:
    return {"status": "cannot_split", "rationale": rationale, "child_steps": []}


def accepted(work_unit_id: str, revision: str):
    return WorkUnitExecutionResult(
        work_unit_id=work_unit_id,
        accepted=True,
        status="checks_passed",
        accepted_revision=revision,
        change_id=f"change-{work_unit_id}",
        evidence_location=f"/tmp/{work_unit_id}.json",
    )


def rejected(
    work_unit_id: str,
    *,
    error="acceptance failed",
    status="checks_failed",
    allowed_paths: list[str] | None = None,
    changed_paths: list[str] | None = None,
):
    policy_evidence = None
    if allowed_paths is not None or changed_paths is not None:
        policy_evidence = ExecutionPolicyEvidence(
            allowed_paths=list(allowed_paths or []),
            changed_paths=list(changed_paths or []),
        )
    return WorkUnitExecutionResult(
        work_unit_id=work_unit_id,
        accepted=False,
        status=status,
        change_id=f"change-{work_unit_id}",
        evidence_location=f"/tmp/{work_unit_id}.json",
        error=error,
        policy_evidence=policy_evidence,
    )


def run_state(
    current_pool="tdd_ready",
    completed_requirement_refs=None,
    cycles=None,
    semantic_base_revision="a" * 40,
    contract_state=None,
    registered_root=None,
    failure_progress=None,
    blocked_reason=None,
):
    active_contract = contract_state or contract()
    return BehaviorContractRunState(
        contract=active_contract,
        repository_binding=binding(semantic_base_revision, registered_root=registered_root),
        semantic_base_revision=semantic_base_revision,
        current_pool=current_pool,
        completed_requirement_refs=completed_requirement_refs or [],
        cycles=cycles or [],
        failure_progress=failure_progress or FailureProgressState(),
        blocked_reason=blocked_reason,
    )


def failure_decision(classification: FailureClassification, action: ProgressionAction | None = None) -> FailureDecision:
    observation = FailureObservation(
        source="pytest",
        message=classification.value,
        plausible=[classification],
        evidence_refs=["packet.json"],
    )
    return FailureDecision(
        observations=[observation],
        plausible=[classification],
        dominant=classification,
        priority=FAILURE_PRIORITY[classification],
        action=action or FAILURE_ACTIONS[classification],
    )


def repair_progress(classification: FailureClassification, route: RetryRoute, role: str) -> FailureProgressState:
    return FailureProgressState(
        state=FailureRouteState.AWAITING_REPAIR,
        history=[failure_decision(classification)],
        retry_counts={route.value: 1},
        repair_packets=[
            RepairPacket(
                kind=PacketKind.REPAIR,
                role=role,
                work_unit_id="repair-packet",
                trusted_revision="a" * 40,
                original_objective="repair objective",
                allowed_paths=["reservation_book.py" if role == "Developer" else "tests/test_reservation_book.py"],
                classification=classification,
                evidence=[classification.value],
            )
        ],
    )


def run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def write_repo_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def create_review_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo_root = tmp_path / "reservation-book-fixture"
    repo_root.mkdir()
    run_git(repo_root, "init", "-b", "main")
    run_git(repo_root, "config", "user.name", "ATHBA Test")
    run_git(repo_root, "config", "user.email", "athba@example.com")

    write_repo_file(
        repo_root / "reservation_book.py",
        "class ReservationBook:\n    def available(self, resource_id: str) -> int:\n        return 0\n",
    )
    write_repo_file(
        repo_root / "tests/test_reservation_book.py",
        "def test_add_resource_sets_availability():\n    assert False\n",
    )
    run_git(repo_root, "add", ".")
    run_git(repo_root, "commit", "-m", "base")
    base_revision = run_git(repo_root, "rev-parse", "HEAD")

    write_repo_file(
        repo_root / "reservation_book.py",
        "class ReservationBook:\n    def __init__(self) -> None:\n        self._resources: dict[str, int] = {}\n\n    def add_resource(self, resource_id: str, capacity: int) -> None:\n        self._resources[resource_id] = capacity\n\n    def available(self, resource_id: str) -> int:\n        return self._resources[resource_id]\n",
    )
    write_repo_file(
        repo_root / "tests/test_reservation_book.py",
        "from reservation_book import ReservationBook\n\n\ndef test_add_resource_sets_availability():\n    book = ReservationBook()\n\n    book.add_resource('room-a', 5)\n\n    assert book.available('room-a') == 5\n",
    )
    run_git(repo_root, "add", ".")
    run_git(repo_root, "commit", "-m", "candidate")
    candidate_revision = run_git(repo_root, "rev-parse", "HEAD")
    return repo_root, base_revision, candidate_revision


@pytest.mark.asyncio
async def test_valid_component_requirement_becomes_valid_behavior_contract():
    gateway = FakeReasoningGateway([source_clause_payload(), contract_payload()])
    planner = BehaviorContractPlanner(gateway)

    result = await planner.create_contract(
        project_id="reservation-book",
        requirement_text=requirement_text(),
        production_paths=["reservation_book.py"],
        test_paths=["tests/test_reservation_book.py"],
    )

    assert result.component_name == "ReservationBook"
    assert result.source_clause_refs() == ["SRC-1", "SRC-2", "SRC-3", "SRC-4"]
    assert result.requirement_refs() == ["RB-1", "RB-2"]
    assert result.observable_requirements[0].source_refs == ["SRC-1", "SRC-2"]
    assert result.production_paths == ["reservation_book.py"]
    assert result.test_paths == ["tests/test_reservation_book.py"]
    assert find_forbidden_resource_selection_keys(result.to_dict()) == []


@pytest.mark.asyncio
async def test_valid_source_requirement_clause_extraction_parses():
    planner = RequirementClausePlanner(FakeReasoningGateway([source_clause_payload()]))

    clauses = await planner.create_clauses(project_id="reservation-book", requirement_text=requirement_text())

    assert [clause.ref for clause in clauses] == ["SRC-1", "SRC-2", "SRC-3", "SRC-4"]
    assert clauses[0] == SourceRequirementClause(ref="SRC-1", text="A resource can be added with a unique id.", kind="behavior")


@pytest.mark.asyncio
async def test_malformed_source_requirement_clause_input_fails_closed():
    planner = RequirementClausePlanner(FakeReasoningGateway(["not json"]))

    with pytest.raises(ValueError, match="source requirement clauses response was not valid JSON"):
        await planner.create_clauses(project_id="reservation-book", requirement_text=requirement_text())


@pytest.mark.asyncio
async def test_empty_source_clauses_are_rejected():
    planner = RequirementClausePlanner(FakeReasoningGateway([{"clauses": []}]))

    with pytest.raises(ValueError, match="source requirement clauses must not be empty"):
        await planner.create_clauses(project_id="reservation-book", requirement_text=requirement_text())


@pytest.mark.asyncio
async def test_duplicate_source_clause_refs_are_rejected():
    planner = RequirementClausePlanner(
        FakeReasoningGateway([
            {
                "clauses": [
                    {"ref": "SRC-1", "text": "Add a resource.", "kind": "behavior"},
                    {"ref": "SRC-1", "text": "Reject duplicate ids.", "kind": "validation"},
                ]
            }
        ])
    )

    with pytest.raises(ValueError, match="duplicate source clause refs"):
        await planner.create_clauses(project_id="reservation-book", requirement_text=requirement_text())


@pytest.mark.asyncio
async def test_malformed_contract_input_fails_closed():
    gateway = FakeReasoningGateway([source_clause_payload(), "not json"])
    planner = BehaviorContractPlanner(gateway)

    with pytest.raises(ValueError, match="behavior contract response was not valid JSON"):
        await planner.create_contract(project_id="reservation-book", requirement_text="broken")

@pytest.mark.asyncio
async def test_contract_planner_repairs_uncovered_source_clauses_once():
    invalid_payload = contract_payload()
    invalid_payload["observable_requirements"] = [invalid_payload["observable_requirements"][0]]
    gateway = FakeReasoningGateway([source_clause_payload(), invalid_payload, contract_payload()])
    planner = BehaviorContractPlanner(gateway)

    restored = await planner.create_contract(
        project_id="reservation-book",
        requirement_text=requirement_text(),
        production_paths=["reservation_book.py"],
        test_paths=["tests/test_reservation_book.py"],
    )

    assert restored.requirement_refs() == ["RB-1", "RB-2"]
    assert len(gateway.requests) == 3
    assert gateway.requests[1].purpose == "athba_behavior_contract"
    assert gateway.requests[2].purpose == "athba_behavior_contract_repair"
    assert "source clauses must be covered by observable requirements" in gateway.requests[2].prompt


@pytest.mark.asyncio
async def test_contract_planner_repairs_requirement_source_back_to_exact_original_text():
    truncated_payload = contract_payload()
    truncated_payload["requirement_source"] = "Build a small in-memory ReservationBook for reservable resources."
    gateway = FakeReasoningGateway([source_clause_payload(), truncated_payload, contract_payload()])
    planner = BehaviorContractPlanner(gateway)

    restored = await planner.create_contract(
        project_id="reservation-book",
        requirement_text=requirement_text(),
        production_paths=["reservation_book.py"],
        test_paths=["tests/test_reservation_book.py"],
    )

    assert restored.requirement_source == requirement_text()
    assert len(gateway.requests) == 3
    assert gateway.requests[1].purpose == "athba_behavior_contract"
    assert gateway.requests[2].purpose == "athba_behavior_contract_repair"
    assert "requirement_source must exactly equal the supplied requirement_text" in gateway.requests[1].prompt
    assert "requirement_source must preserve the original requirement text exactly" in gateway.requests[2].prompt
    assert "requirement_source must exactly equal the supplied requirement_text" in gateway.requests[2].prompt


@pytest.mark.asyncio
async def test_fenced_json_contract_output_fails_closed():
    gateway = FakeReasoningGateway([source_clause_payload(), "```json\n{}\n```"])
    planner = BehaviorContractPlanner(gateway)

    with pytest.raises(ValueError, match="behavior contract response was not valid JSON"):
        await planner.create_contract(project_id="reservation-book", requirement_text="broken")


@pytest.mark.asyncio
async def test_prose_before_json_contract_output_fails_closed():
    payload = json.dumps(contract_payload())
    gateway = FakeReasoningGateway([source_clause_payload(), f"Here is the JSON you asked for:\n{payload}"])
    planner = BehaviorContractPlanner(gateway)

    with pytest.raises(ValueError, match="behavior contract response was not valid JSON"):
        await planner.create_contract(project_id="reservation-book", requirement_text="broken")


def test_contract_requirement_refs_are_retained_through_round_trip():
    restored = BehaviorContract.from_dict(
        contract().to_dict(),
        BehaviorContractLoadOptions(
            allowed_production_paths=["reservation_book.py"],
            allowed_test_paths=["tests/test_reservation_book.py"],
        ),
    )

    assert restored.requirement_refs() == ["RB-1", "RB-2"]
    assert restored.source_clause_refs() == ["SRC-1", "SRC-2", "SRC-3", "SRC-4"]
    assert restored.observable_requirements[0].source_refs == ["SRC-1", "SRC-2"]


def test_contract_rejects_wrong_field_types_invalid_status_and_invalid_paths():
    base = contract_payload()

    wrong_public_api = dict(base)
    wrong_public_api["public_api"] = {"add_resource": "callable"}
    with pytest.raises(ValueError, match="public api must be a list"):
        BehaviorContract.from_dict(wrong_public_api)

    wrong_error_semantics = dict(base)
    wrong_error_semantics["error_semantics"] = "raise ValueError"
    with pytest.raises(ValueError, match="error semantics must be a list"):
        BehaviorContract.from_dict(wrong_error_semantics)

    invalid_status = dict(base)
    invalid_status["status"] = "READY"
    with pytest.raises(ValueError, match="unsupported contract status"):
        BehaviorContract.from_dict(invalid_status)

    absolute_path = dict(base)
    absolute_path["production_paths"] = ["/srv/reservation_book.py"]
    with pytest.raises(ValueError, match="repository-relative"):
        BehaviorContract.from_dict(absolute_path)

    conceptual_path = dict(base)
    conceptual_path["production_paths"] = ["AddResource"]
    with pytest.raises(ValueError, match="file paths"):
        BehaviorContract.from_dict(conceptual_path)

    parent_escape = dict(base)
    parent_escape["test_paths"] = ["../tests/test_reservation_book.py"]
    with pytest.raises(ValueError, match="repository-relative"):
        BehaviorContract.from_dict(parent_escape)


def test_contract_rejects_traceability_gaps_and_unknown_refs():
    base = contract_payload()

    empty_source_refs = dict(base)
    empty_source_refs["observable_requirements"] = [dict(base["observable_requirements"][0]), dict(base["observable_requirements"][1])]
    empty_source_refs["observable_requirements"][0]["source_refs"] = []
    with pytest.raises(ValueError, match="requirement source refs must not be empty"):
        BehaviorContract.from_dict(empty_source_refs)

    unknown_source_ref = dict(base)
    unknown_source_ref["observable_requirements"] = [dict(base["observable_requirements"][0]), dict(base["observable_requirements"][1])]
    unknown_source_ref["observable_requirements"][0]["source_refs"] = ["SRC-999"]
    with pytest.raises(ValueError, match="must exist in source clauses"):
        BehaviorContract.from_dict(unknown_source_ref)

    uncovered_clause = dict(base)
    uncovered_clause["observable_requirements"] = [dict(base["observable_requirements"][0]), dict(base["observable_requirements"][1])]
    uncovered_clause["observable_requirements"][1]["source_refs"] = ["SRC-3"]
    with pytest.raises(ValueError, match="source clauses must be covered"):
        BehaviorContract.from_dict(uncovered_clause)

    duplicate_clause_refs = dict(base)
    duplicate_clause_refs["source_clauses"] = list(base["source_clauses"]) + [dict(base["source_clauses"][0])]
    with pytest.raises(ValueError, match="duplicate source clause refs"):
        BehaviorContract.from_dict(duplicate_clause_refs)

    duplicate_requirement_refs = dict(base)
    duplicate_requirement_refs["observable_requirements"] = [dict(base["observable_requirements"][0]), dict(base["observable_requirements"][0])]
    with pytest.raises(ValueError, match="duplicate requirement refs"):
        BehaviorContract.from_dict(duplicate_requirement_refs)


def test_source_clause_only_in_completion_criteria_still_fails_coverage():
    payload = contract_payload()
    payload["completion_criteria"] = payload["completion_criteria"] + ["SRC-4 capacity enforcement remains required"]
    payload["observable_requirements"] = [dict(payload["observable_requirements"][0]), dict(payload["observable_requirements"][1])]
    payload["observable_requirements"][1]["source_refs"] = ["SRC-3"]

    with pytest.raises(ValueError, match="source clauses must be covered"):
        BehaviorContract.from_dict(payload)


def test_one_source_clause_can_map_to_multiple_observable_requirements():
    payload = contract_payload()
    payload["source_clauses"] = [
        {"ref": "SRC-1", "text": "Reservation quantity must be positive.", "kind": "validation"},
    ]
    payload["observable_requirements"] = [
        {
            "ref": "RB-1",
            "source_refs": ["SRC-1"],
            "summary": "Reject zero reservation quantity.",
            "observable_outcome": "reserve rejects quantity 0 without changing state.",
            "test_hint": "test_reject_zero_quantity",
            "error_expectation": "ValueError",
            "preserves_state_on_failure": True,
        },
        {
            "ref": "RB-2",
            "source_refs": ["SRC-1"],
            "summary": "Reject negative reservation quantity.",
            "observable_outcome": "reserve rejects negative quantity without changing state.",
            "test_hint": "test_reject_negative_quantity",
            "error_expectation": "ValueError",
            "preserves_state_on_failure": True,
        },
    ]

    contract_state = BehaviorContract.from_dict(payload)

    assert contract_state.uncovered_source_clause_refs() == []


def test_multiple_source_clauses_can_map_to_one_requirement_when_behavior_is_coherent():
    payload = contract_payload()

    contract_state = BehaviorContract.from_dict(payload)

    assert contract_state.observable_requirements[0].source_refs == ["SRC-1", "SRC-2"]


@pytest.mark.asyncio
async def test_contract_output_paths_must_match_allowed_path_sets():
    payload = contract_payload()
    payload["production_paths"] = ["other.py"]
    payload["test_paths"] = ["tests/other_test.py"]
    planner = BehaviorContractPlanner(FakeReasoningGateway([source_clause_payload(), payload]))

    with pytest.raises(ValueError, match="allowed path set"):
        await planner.create_contract(
            project_id="reservation-book",
            requirement_text=requirement_text(),
            production_paths=["reservation_book.py"],
            test_paths=["tests/test_reservation_book.py"],
        )


def test_no_worker_model_or_gpu_fields_leak_into_contract_or_tdd_requests():
    step = proposal()
    red_request = to_rack_ai_request("reservation-book", binding(), ContractTesterWorkUnitFactory().build(WorkUnitBuildRequest(contract(), step)))
    green_request = to_rack_ai_request("reservation-book", binding(), ContractDeveloperWorkUnitFactory().build(WorkUnitBuildRequest(contract(), step)))

    assert find_forbidden_resource_selection_keys(contract().to_dict()) == []
    assert find_forbidden_resource_selection_keys(red_request) == []
    assert find_forbidden_resource_selection_keys(green_request) == []


def test_dynamic_tdd_step_retains_traceability_back_to_source_clauses():
    step = proposal("RB-1")
    contract_state = contract()
    requirement = next(item for item in contract_state.observable_requirements if item.ref == step.requirement_refs[0])

    assert requirement.source_refs == ["SRC-1", "SRC-2"]
    assert [clause.text for clause in contract_state.source_clauses if clause.ref in requirement.source_refs] == [
        "A resource can be added with a unique id.",
        "A resource capacity must be a positive integer.",
    ]


@pytest.mark.asyncio
async def test_contract_prompt_explicitly_constrains_raw_json_types_paths_atomicity_and_traceability():
    gateway = FakeReasoningGateway([source_clause_payload(), contract_payload()])
    planner = BehaviorContractPlanner(gateway)

    await planner.create_contract(
        project_id="reservation-book",
        requirement_text=requirement_text(),
        production_paths=["reservation_book.py"],
        test_paths=["tests/test_reservation_book.py"],
    )

    clause_prompt = gateway.requests[0].prompt
    assert "Produce ATHBA PR16 source requirement clauses as raw JSON only." in clause_prompt
    assert "one source obligation per clause" in clause_prompt
    assert "preserve happy-path, failure, query, and state-preservation obligations" in clause_prompt
    assert "do not invent requirements beyond reasonable decomposition of the supplied text" in clause_prompt

    prompt = gateway.requests[1].prompt
    assert "return raw JSON only" in prompt
    assert "do not use code fences" in prompt
    assert "do not add commentary before or after the JSON" in prompt
    assert "\"status\": \"tdd_ready\"" in prompt
    assert "\"public_api\": [" in prompt
    assert "\"error_semantics\": [" in prompt
    assert "\"source_refs\": [" in prompt
    assert "\"source_clauses\": [" in prompt
    assert "copy source clause refs exactly into source_refs" in prompt
    assert "every supplied source clause must be covered" in prompt
    assert "allowed_production_paths" in prompt
    assert "reservation_book.py" in prompt
    assert "allowed_test_paths" in prompt
    assert "tests/test_reservation_book.py" in prompt
    assert "one requirement ref must be completable by one focused semantic TDD slice" in prompt
    assert "do not bundle unrelated failure modes under one requirement ref" in prompt
    assert "do not include worker ids, model ids, GPU ids, endpoints, ports, or backend selection" in prompt


@pytest.mark.asyncio
async def test_tester_can_propose_one_next_focused_tdd_step_from_contract():
    step = proposal()
    gateway = FakeReasoningGateway([
        {
            "status": "propose",
            "rationale": "RB-1 is the smallest useful missing behavior.",
            "proposal": step.to_dict(),
            "completed_requirement_refs": [],
        },
        {
            "disposition": "reject_dependency",
            "parent_requirement_ref": "RB-1",
            "prerequisite_refs": [],
            "rationale": "The requested resource behavior is independently testable.",
        },
    ])
    planner = DynamicTddPlanner(gateway)

    decision = await planner.decide_next_step(contract(), run_state())

    assert decision.status == "propose"
    assert decision.proposal == step
    assert "Tester planner" in gateway.requests[0].prompt
    assert '"allowed_requirement_refs": [' in gateway.requests[0].prompt


@pytest.mark.asyncio
async def test_tester_planner_receives_bounded_external_repository_material(tmp_path: Path):
    repo_root, base_revision, _ = create_review_repo(tmp_path)
    step = proposal()
    gateway = FakeReasoningGateway([
        {
            "status": "propose",
            "rationale": "RB-1 is the smallest useful missing behavior.",
            "proposal": step.to_dict(),
            "completed_requirement_refs": [],
        }
    ])

    decision = await DynamicTddPlanner(gateway).decide_next_step(
        contract(),
        run_state(semantic_base_revision=base_revision, registered_root=repo_root),
    )

    assert decision.proposal == step
    prompt = json.loads(gateway.requests[0].prompt)
    material = prompt["repository_material"]
    assert material["repository_kind"] == "external_registered_repository"
    assert material["trusted_revision"] == base_revision
    assert material["production_files"][0]["path"] == "reservation_book.py"
    assert material["production_files"][0]["module_name"] == "reservation_book"
    assert "class ReservationBook" in material["production_files"][0]["content"]
    assert material["known_pytest_nodes"] == ["tests/test_reservation_book.py::test_add_resource_sets_availability"]
    assert "do not invent ATHBA imports or paths" in gateway.requests[0].prompt


def test_tester_work_unit_receives_external_repository_context_without_athba_assumptions(tmp_path: Path):
    repo_root, base_revision, _ = create_review_repo(tmp_path)
    state = run_state(semantic_base_revision=base_revision, registered_root=repo_root)
    material = GitTesterRepositoryMaterialProvider(repo_root).render(RepositoryMaterialRequest(contract(), state))

    work_unit = ContractTesterWorkUnitFactory().build(WorkUnitBuildRequest(contract(), proposal(), material))

    assert "standalone external repository, not ATHBA" in work_unit.objective
    assert "Do not import ATHBA internals" in work_unit.objective
    assert '"module_name": "reservation_book"' in work_unit.objective
    assert "collection-safe" in work_unit.objective


def test_repository_material_allows_the_first_test_file_to_be_absent(tmp_path: Path):
    repo_root = tmp_path / "clean-target"
    repo_root.mkdir()
    (repo_root / "reservation_book.py").write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo_root, check=True)
    subprocess.run(["git", "add", "reservation_book.py"], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "-qm", "seed"],
        cwd=repo_root,
        check=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root, check=True, text=True, capture_output=True
    ).stdout.strip()

    material = GitTesterRepositoryMaterialProvider(repo_root).render(
        RepositoryMaterialRequest(contract(), run_state(semantic_base_revision=revision, registered_root=repo_root))
    )

    assert material["test_files"] == [{
        "path": "tests/test_reservation_book.py",
        "module_name": "tests.test_reservation_book",
        "content": "",
        "truncated": False,
        "pytest_nodes": [],
    }]
    assert material["all_contract_files_empty"] is True


def test_empty_external_source_uses_collection_safe_module_access_in_red_objective():
    material = {
        "all_contract_files_empty": True,
        "production_files": [{"module_name": "reservation_book", "content": ""}],
    }

    work_unit = ContractTesterWorkUnitFactory().build(WorkUnitBuildRequest(contract(), proposal(), material))

    assert "import reservation_book" in work_unit.objective
    assert "getattr(reservation_book, 'ReservationBook')" in work_unit.objective
    assert "Do not use `from reservation_book import ReservationBook`" in work_unit.objective


@pytest.mark.asyncio
async def test_step_planner_repairs_non_pytest_function_name():
    invalid_step = proposal().to_dict()
    invalid_step["test_name"] = "tests/test_reservation_book.py::resource_is_added"
    repaired_step = proposal().to_dict()
    gateway = FakeReasoningGateway([
        {"status": "propose", "rationale": "bad node", "proposal": invalid_step, "completed_requirement_refs": []},
        {"status": "propose", "rationale": "fixed node", "proposal": repaired_step, "completed_requirement_refs": []},
    ])

    decision = await DynamicTddPlanner(gateway).decide_next_step(contract(), run_state())

    assert decision.proposal == proposal()
    assert gateway.requests[1].purpose == "athba_tdd_step_selection_repair"
    assert "pytest node id" in gateway.requests[1].prompt


@pytest.mark.asyncio
async def test_step_planner_repairs_athba_internal_leakage_for_external_repository(tmp_path: Path):
    repo_root, base_revision, _ = create_review_repo(tmp_path)
    invalid_step = proposal().to_dict()
    invalid_step["red_objective"] = "Import ReservationBook from athba.models."
    gateway = FakeReasoningGateway([
        {"status": "propose", "rationale": "bad import", "proposal": invalid_step, "completed_requirement_refs": []},
        {"status": "propose", "rationale": "fixed import", "proposal": proposal().to_dict(), "completed_requirement_refs": []},
    ])

    decision = await DynamicTddPlanner(gateway).decide_next_step(
        contract(),
        run_state(semantic_base_revision=base_revision, registered_root=repo_root),
    )

    assert decision.proposal == proposal()
    assert gateway.requests[1].purpose == "athba_tdd_step_selection_repair"
    assert "ATHBA-internal" in gateway.requests[1].prompt

@pytest.mark.asyncio
async def test_step_planner_repairs_fenced_json_and_short_test_name():
    invalid_step = {
        "status": "propose",
        "rationale": "Start with resource creation.",
        "proposal": {
            "step_id": "TEST-001",
            "requirement_refs": ["RB-1"],
            "focused_behavior": "Add a resource.",
            "test_name": "test_add_resource_unique_and_duplicate",
            "expected_result": "A duplicate id raises ValueError.",
            "test_path": "tests/test_reservation_book.py",
            "production_path": "reservation_book.py",
            "red_objective": "Write a failing test.",
            "green_objective": "Implement only enough production code.",
            "reason_next_smallest": "This is the base capability.",
            "exception_type": "ValueError",
            "exception_message": "duplicate id",
        },
        "completed_requirement_refs": [],
    }
    repaired_step = {
        "status": "propose",
        "rationale": "Start with resource creation.",
        "proposal": {
            **invalid_step["proposal"],
            "test_name": "tests/test_reservation_book.py::test_add_resource_unique_and_duplicate",
        },
        "completed_requirement_refs": [],
    }
    gateway = FakeReasoningGateway([f"```json\n{json.dumps(invalid_step)}\n```", repaired_step])

    decision = await DynamicTddPlanner(gateway).decide_next_step(contract(), run_state())

    assert decision.proposal is not None
    assert decision.proposal.test_name == "tests/test_reservation_book.py::test_add_resource_unique_and_duplicate"
    assert gateway.requests[1].purpose == "athba_tdd_step_selection_repair"
    assert "step decision response was not valid JSON" in gateway.requests[1].prompt



@pytest.mark.asyncio
async def test_step_planner_repairs_requirement_ref_drift():
    invalid_step = {
        "status": "propose",
        "rationale": "Start with resource creation.",
        "proposal": {
            "step_id": "TEST-002",
            "requirement_refs": ["RB-999"],
            "focused_behavior": "Add a resource.",
            "test_name": "tests/test_reservation_book.py::test_add_resource_unique_and_duplicate",
            "expected_result": "A duplicate id raises ValueError.",
            "test_path": "tests/test_reservation_book.py",
            "production_path": "reservation_book.py",
            "red_objective": "Write a failing test.",
            "green_objective": "Implement only enough production code.",
            "reason_next_smallest": "This is the base capability.",
            "exception_type": "ValueError",
            "exception_message": "duplicate id",
        },
        "completed_requirement_refs": [],
    }
    repaired_step = {
        "status": "propose",
        "rationale": "Start with resource creation.",
        "proposal": {
            **invalid_step["proposal"],
            "requirement_refs": ["RB-1"],
        },
        "completed_requirement_refs": [],
    }
    gateway = FakeReasoningGateway([invalid_step, repaired_step])

    decision = await DynamicTddPlanner(gateway).decide_next_step(contract(), run_state())

    assert decision.proposal is not None
    assert decision.proposal.requirement_refs == ["RB-1"]
    assert gateway.requests[1].purpose == "athba_tdd_step_selection_repair"
    assert "step proposal referenced a requirement outside the contract" in gateway.requests[1].prompt




@pytest.mark.asyncio
async def test_step_proposal_cannot_include_multiple_unrelated_behaviors():
    multi = proposal()
    multi = replace(multi, requirement_refs=["RB-1", "RB-2"])
    gateway = FakeReasoningGateway([
        {
            "status": "propose",
            "rationale": "Do two things at once.",
            "proposal": multi.to_dict(),
            "completed_requirement_refs": [],
        }
    ])

    with pytest.raises(ValueError, match="exactly one requirement ref"):
        await DynamicTddPlanner(gateway).decide_next_step(contract(), run_state())


@pytest.mark.asyncio
async def test_already_covered_requirements_are_not_selected_again():
    repeated = proposal("RB-1")
    gateway = FakeReasoningGateway([
        {
            "status": "propose",
            "rationale": "Repeat RB-1.",
            "proposal": repeated.to_dict(),
            "completed_requirement_refs": [],
        }
    ])

    with pytest.raises(ValueError, match="already semantically covered"):
        await DynamicTddPlanner(gateway).decide_next_step(contract(), run_state(completed_requirement_refs=["RB-1"]))


@pytest.mark.asyncio
async def test_tester_can_recognize_contract_completion_without_hard_coded_step_count():
    gateway = FakeReasoningGateway([
        {
            "status": "complete",
            "rationale": "All contract requirements are already semantically covered.",
            "proposal": None,
            "completed_requirement_refs": [],
        }
    ])

    decision = await DynamicTddPlanner(gateway).decide_next_step(
        contract(),
        run_state(completed_requirement_refs=["RB-1", "RB-2"]),
    )

    assert decision.status == "complete"
    assert decision.completed_requirement_refs == ["RB-1", "RB-2"]


@pytest.mark.asyncio
async def test_completion_requires_all_semantically_approved_requirements():
    gateway = FakeReasoningGateway([
        {
            "status": "complete",
            "rationale": "I think this is done.",
            "proposal": None,
            "completed_requirement_refs": ["RB-1", "RB-2"],
        }
    ])

    with pytest.raises(ValueError, match="semantically approved"):
        await DynamicTddPlanner(gateway).decide_next_step(contract(), run_state())


@pytest.mark.asyncio
async def test_completion_rejects_partial_semantically_approved_requirements():
    gateway = FakeReasoningGateway([
        {
            "status": "complete",
            "rationale": "Close enough.",
            "proposal": None,
            "completed_requirement_refs": ["RB-1", "RB-2"],
        }
    ])

    with pytest.raises(ValueError, match="semantically approved"):
        await DynamicTddPlanner(gateway).decide_next_step(
            contract(),
            run_state(completed_requirement_refs=["RB-1"]),
        )


@pytest.mark.asyncio
async def test_completion_rejects_unknown_requirement_refs_in_model_claim():
    gateway = FakeReasoningGateway([
        {
            "status": "complete",
            "rationale": "Done.",
            "proposal": None,
            "completed_requirement_refs": ["RB-1", "RB-2", "RB-999"],
        }
    ])

    with pytest.raises(ValueError, match="outside the contract"):
        await DynamicTddPlanner(gateway).decide_next_step(
            contract(),
            run_state(completed_requirement_refs=["RB-1", "RB-2"]),
        )


@pytest.mark.asyncio
async def test_green_cannot_begin_before_accepted_red_and_tester_failures_use_bounded_retries():
    step = proposal()
    reasoner = FakeReasoningGateway([
        {
            "status": "propose",
            "rationale": "Start with RB-1.",
            "proposal": step.to_dict(),
            "completed_requirement_refs": [],
        }
    ])
    gateway = FakeExecutionGateway({step.step_id + "--red": rejected(step.step_id + "--red")})
    repo = MemoryStateRepo()

    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(contract())

    assert [call[0] for call in gateway.calls] == [step.step_id + "--red"] * 3
    assert result.current_pool == "replan_ready"
    assert result.blocked_reason is not None
    assert "tester_candidate_defect" in result.blocked_reason


@pytest.mark.asyncio
async def test_mechanically_accepted_green_is_persisted_as_review_ready_before_review_progresses():
    contract_state = single_requirement_contract()
    step = proposal()
    reasoner = FakeReasoningGateway([
        {
            "status": "propose",
            "rationale": "Start with RB-1.",
            "proposal": step.to_dict(),
            "completed_requirement_refs": [],
        },
        {
            "verdict": "approved",
            "rationale": "Looks good.",
            "findings": ["minimal implementation"],
            "candidate_revision": "c" * 40,
            "step_id": step.step_id,
            "evidence_refs": ["review:1"],
            "repair_instructions": [],
        },
        {
            "status": "complete",
            "rationale": "Proof finished.",
            "proposal": None,
            "completed_requirement_refs": [],
        },
    ])
    gateway = FakeExecutionGateway(
        {
            step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
            step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
        }
    )
    repo = MemoryStateRepo()

    await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    pools = [snap.contract_runs[contract_state.id].current_pool for snap in repo.saved if contract_state.id in snap.contract_runs]
    assert "review_ready" in pools


@pytest.mark.asyncio
async def test_next_tdd_cycle_cannot_start_before_semantic_approval():
    contract_state = single_requirement_contract()
    step = proposal()
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="b" * 40),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=step.step_id + "--red", status="checks_passed", accepted_revision="b" * 40),
        green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id=step.step_id + "--green", status="checks_passed", accepted_revision="c" * 40),
        candidate_revision="c" * 40,
        pool="review_ready",
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("b" * 40),
        current_trusted_revision="b" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="review_ready",
                cycles=[cycle],
                semantic_base_revision="b" * 40,
                contract_state=contract_state,
            )
        },
    )
    reasoner = FakeReasoningGateway([
        {
            "verdict": "approved",
            "rationale": "Looks good.",
            "findings": ["minimal implementation"],
            "candidate_revision": "c" * 40,
            "step_id": step.step_id,
            "evidence_refs": ["review:1"],
            "repair_instructions": [],
        },
        {
            "status": "complete",
            "rationale": "Done.",
            "proposal": None,
            "completed_requirement_refs": [],
        },
    ])
    gateway = FakeExecutionGateway({})

    await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert gateway.calls == []
    assert reasoner.requests[0].purpose == "athba_senior_review"


@pytest.mark.asyncio
async def test_approved_review_promotes_candidate_revision_to_semantic_base():
    contract_state = single_requirement_contract()
    step = proposal()
    reasoner = FakeReasoningGateway([
        {"status": "propose", "rationale": "Start.", "proposal": step.to_dict(), "completed_requirement_refs": []},
        {
            "verdict": "approved",
            "rationale": "Looks good.",
            "findings": ["minimal implementation"],
            "candidate_revision": "c" * 40,
            "step_id": step.step_id,
            "evidence_refs": ["review:1"],
            "repair_instructions": [],
        },
        {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
    ])
    gateway = FakeExecutionGateway({
        step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
        step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
    })

    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=MemoryStateRepo(),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert result.semantic_revision == "c" * 40


@pytest.mark.asyncio
async def test_senior_reviewer_repairs_fenced_json_response():
    step = proposal()
    reviewer = SeniorReviewer(
        FakeReasoningGateway([
            '```json\n' + json.dumps(review_repair(step.step_id, "c" * 40), indent=2) + '\n```',
            review_repair(step.step_id, "c" * 40),
        ])
    )
    review = await reviewer.review(
        SemanticReviewRequest(
            contract=single_requirement_contract(),
            run_state=run_state(current_pool="review_ready", semantic_base_revision="b" * 40, contract_state=single_requirement_contract()),
            cycle=replace(
                ContractCycleRecord.from_step(step, base_revision="b" * 40),
                red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=step.step_id + "--red", status="checks_passed", accepted_revision="b" * 40),
                green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id=step.step_id + "--green", status="checks_passed", accepted_revision="c" * 40),
                candidate_revision="c" * 40,
                pool="review_ready",
            ),
            candidate_revision="c" * 40,
            review_material="candidate source",
        )
    )

    assert review.verdict == "repair_required"
    assert review.candidate_revision == "c" * 40
    assert review.step_id == step.step_id
    assert reviewer.gateway.requests[1].purpose == "athba_senior_review_repair"


@pytest.mark.asyncio
async def test_repair_required_moves_to_repair_ready():
    step = proposal()
    reasoner = FakeReasoningGateway([
        {"status": "propose", "rationale": "Start.", "proposal": step.to_dict(), "completed_requirement_refs": []},
        {
            "verdict": "repair_required",
            "rationale": "Remove a noisy comment.",
            "findings": ["comment is noisy"],
            "candidate_revision": "c" * 40,
            "step_id": step.step_id,
            "evidence_refs": ["review:1"],
            "repair_instructions": ["Remove the noisy comment and keep behavior unchanged."],
        },
    ])
    gateway = FakeExecutionGateway({
        step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
        step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
    })
    repo = MemoryStateRepo()

    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract())

    assert result.current_pool in {"repair_ready", "replan_ready"}
    assert "repair_ready" in [snap.contract_runs[contract().id].current_pool for snap in repo.saved if contract().id in snap.contract_runs]


@pytest.mark.asyncio
async def test_repair_result_returns_to_review_ready_before_final_approval():
    contract_state = single_requirement_contract()
    step = proposal()
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="b" * 40),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=step.step_id + "--red", status="checks_passed", accepted_revision="b" * 40),
        green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id=step.step_id + "--green", status="checks_passed", accepted_revision="c" * 40),
        candidate_revision="c" * 40,
        pool="repair_ready",
        review_result=SemanticReviewResult(
            verdict="repair_required",
            rationale="Remove a noisy comment.",
            findings=["comment is noisy"],
            candidate_revision="c" * 40,
            step_id=step.step_id,
            evidence_refs=["review:1"],
            repair_instructions=["Remove the noisy comment and keep behavior unchanged."],
        ),
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("b" * 40),
        current_trusted_revision="b" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="repair_ready",
                cycles=[cycle],
                semantic_base_revision="b" * 40,
                contract_state=contract_state,
            )
        },
    )
    reasoner = FakeReasoningGateway([
        {
            "verdict": "approved",
            "rationale": "Repair is clean.",
            "findings": ["comment removed"],
            "candidate_revision": "d" * 40,
            "step_id": step.step_id,
            "evidence_refs": ["review:2"],
            "repair_instructions": [],
        },
        {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
    ])
    gateway = FakeExecutionGateway({step.step_id + "--repair-1": accepted(step.step_id + "--repair-1", "d" * 40)})
    repo = MemoryStateRepo(snapshot)

    await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    pools = [snap.contract_runs[contract_state.id].current_pool for snap in repo.saved if contract_state.id in snap.contract_runs]
    assert "review_ready" in pools
    assert gateway.calls[0][0] == step.step_id + "--repair-1"


@pytest.mark.asyncio
async def test_repair_attempts_are_bounded():
    step = proposal()
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="b" * 40),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=step.step_id + "--red", status="checks_passed", accepted_revision="b" * 40),
        green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id=step.step_id + "--green", status="checks_passed", accepted_revision="c" * 40),
        candidate_revision="c" * 40,
        pool="review_ready",
        repair_attempts=2,
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("b" * 40),
        current_trusted_revision="b" * 40,
        contract_runs={contract().id: run_state(current_pool="review_ready", cycles=[cycle], semantic_base_revision="b" * 40)},
    )
    reasoner = FakeReasoningGateway([
        {
            "verdict": "repair_required",
            "rationale": "Still noisy.",
            "findings": ["comment remains"],
            "candidate_revision": "c" * 40,
            "step_id": step.step_id,
            "evidence_refs": ["review:3"],
            "repair_instructions": ["Remove the comment."],
        }
    ])

    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({}),
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract())

    assert result.current_pool == "replan_ready"
    assert result.blocked_reason == "semantic repair budget exhausted"


@pytest.mark.asyncio
async def test_replan_required_moves_to_replan_ready_and_stops_lane():
    step = proposal()
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="b" * 40),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=step.step_id + "--red", status="checks_passed", accepted_revision="b" * 40),
        green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id=step.step_id + "--green", status="checks_passed", accepted_revision="c" * 40),
        candidate_revision="c" * 40,
        pool="review_ready",
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("b" * 40),
        current_trusted_revision="b" * 40,
        contract_runs={contract().id: run_state(current_pool="review_ready", cycles=[cycle], semantic_base_revision="b" * 40)},
    )
    reasoner = FakeReasoningGateway([
        {
            "verdict": "replan_required",
            "rationale": "The contract missed a state invariant.",
            "findings": ["state invariant missing"],
            "candidate_revision": "c" * 40,
            "step_id": step.step_id,
            "evidence_refs": ["review:4"],
            "repair_instructions": [],
        }
    ])

    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({}),
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract())

    assert result.current_pool == "replan_ready"
    assert result.blocked_reason == "The contract missed a state invariant."


@pytest.mark.asyncio
async def test_semantically_rejected_candidate_never_becomes_next_cycle_base():
    step = proposal()
    reasoner = FakeReasoningGateway([
        {"status": "propose", "rationale": "Start.", "proposal": step.to_dict(), "completed_requirement_refs": []},
        {
            "verdict": "repair_required",
            "rationale": "Need cleanup.",
            "findings": ["cleanup"],
            "candidate_revision": "c" * 40,
            "step_id": step.step_id,
            "evidence_refs": ["review:1"],
            "repair_instructions": ["Clean up comments."],
        },
    ])
    gateway = FakeExecutionGateway({
        step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
        step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
    })

    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=MemoryStateRepo(),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract())

    assert result.semantic_revision == "a" * 40


def test_pool_state_transitions_persist_in_snapshot_round_trip():
    cycle = replace(
        ContractCycleRecord.from_step(proposal(), base_revision="a" * 40),
        pool="review_ready",
        candidate_revision="c" * 40,
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("a" * 40),
        current_trusted_revision="a" * 40,
        contract_runs={
            contract().id: run_state(current_pool="review_ready", cycles=[cycle]),
        },
    )

    restored = TddSnapshot.from_dict(snapshot.to_dict())

    assert restored.contract_runs[contract().id].current_pool == "review_ready"
    assert restored.contract_runs[contract().id].cycles[0].candidate_revision == "c" * 40


@pytest.mark.asyncio
async def test_resume_can_continue_from_review_ready_without_rerunning_green():
    contract_state = single_requirement_contract()
    step = proposal()
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="b" * 40),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=step.step_id + "--red", status="checks_passed", accepted_revision="b" * 40),
        green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id=step.step_id + "--green", status="checks_passed", accepted_revision="c" * 40),
        candidate_revision="c" * 40,
        pool="review_ready",
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("b" * 40),
        current_trusted_revision="b" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="review_ready",
                cycles=[cycle],
                semantic_base_revision="b" * 40,
                contract_state=contract_state,
            )
        },
    )
    gateway = FakeExecutionGateway({})
    reasoner = FakeReasoningGateway([
        {
            "verdict": "approved",
            "rationale": "Looks good.",
            "findings": ["minimal implementation"],
            "candidate_revision": "c" * 40,
            "step_id": step.step_id,
            "evidence_refs": ["review:1"],
            "repair_instructions": [],
        },
        {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
    ])

    await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert gateway.calls == []


@pytest.mark.asyncio
async def test_resume_can_continue_from_repair_ready():
    contract_state = single_requirement_contract()
    step = proposal()
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="b" * 40),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=step.step_id + "--red", status="checks_passed", accepted_revision="b" * 40),
        green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id=step.step_id + "--green", status="checks_passed", accepted_revision="c" * 40),
        candidate_revision="c" * 40,
        pool="repair_ready",
        review_result=SemanticReviewResult(
            verdict="repair_required",
            rationale="Cleanup.",
            findings=["cleanup"],
            candidate_revision="c" * 40,
            step_id=step.step_id,
            evidence_refs=["review:1"],
            repair_instructions=["Remove comment noise."],
        ),
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("b" * 40),
        current_trusted_revision="b" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="repair_ready",
                cycles=[cycle],
                semantic_base_revision="b" * 40,
                contract_state=contract_state,
            )
        },
    )
    gateway = FakeExecutionGateway({step.step_id + "--repair-1": accepted(step.step_id + "--repair-1", "d" * 40)})
    reasoner = FakeReasoningGateway([
        {
            "verdict": "approved",
            "rationale": "Clean now.",
            "findings": ["clean"],
            "candidate_revision": "d" * 40,
            "step_id": step.step_id,
            "evidence_refs": ["review:2"],
            "repair_instructions": [],
        },
        {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
    ])

    await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert gateway.calls[0][0] == step.step_id + "--repair-1"


@pytest.mark.asyncio
async def test_coordinator_completion_keeps_persisted_approved_requirement_refs():
    contract_state = single_requirement_contract()
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("d" * 40),
        current_trusted_revision="d" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="approved",
                completed_requirement_refs=["RB-1"],
                semantic_base_revision="d" * 40,
                contract_state=contract_state,
            )
        },
    )
    reasoner = FakeReasoningGateway([
        {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
    ])

    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({}),
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert result.current_pool == "completed"
    assert result.completed_requirement_refs == ["RB-1"]


@pytest.mark.asyncio
async def test_completed_contract_is_not_rerun():
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("d" * 40),
        current_trusted_revision="d" * 40,
        contract_runs={
            contract().id: run_state(
                current_pool="completed",
                completed_requirement_refs=["RB-1", "RB-2"],
                semantic_base_revision="d" * 40,
            )
        },
    )
    gateway = FakeExecutionGateway({})
    reasoner = FakeReasoningGateway([])

    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
    ).run_contract(contract())

    assert result.current_pool == "completed"
    assert gateway.calls == []
    assert reasoner.requests == []


def test_tester_and_developer_prompts_remain_specific_and_path_bounded():
    step = proposal()
    red = ContractTesterWorkUnitFactory().build(WorkUnitBuildRequest(contract(), step))
    green = ContractDeveloperWorkUnitFactory().build(WorkUnitBuildRequest(contract(), step))
    repair = ContractRepairWorkUnitFactory().build(
        RepairWorkUnitBuildRequest(
            contract(),
            ContractCycleRecord.from_step(step, base_revision="a" * 40),
            SemanticReviewResult(
                verdict="repair_required",
                rationale="cleanup",
                findings=["cleanup"],
                candidate_revision="c" * 40,
                step_id=step.step_id,
                evidence_refs=["review:1"],
                repair_instructions=["Remove the noisy comment."],
            ),
        )
    )

    assert red.allowed_paths == ["tests/test_reservation_book.py"]
    assert green.allowed_paths == ["reservation_book.py"]
    assert repair.allowed_paths == ["reservation_book.py"]
    assert red.acceptance.commands == [["python3", "-B", "scripts/assert_test_fails.py", step.test_name]]
    expected_pytest = ["python3", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    assert green.acceptance.commands == [expected_pytest + [step.test_name], expected_pytest + [step.test_path]]
    assert repair.acceptance.commands == [expected_pytest + [step.test_name], expected_pytest + [step.test_path]]
    assert "Act in ATHBA's Tester role during RED" in red.objective
    assert "Do not edit tests" in green.objective
    assert "Reviewer instructions" in repair.objective


def test_git_review_material_provider_includes_real_diff_source_and_evidence(tmp_path: Path):
    repo_root, base_revision, candidate_revision = create_review_repo(tmp_path)
    cycle = replace(
        ContractCycleRecord.from_step(proposal(), base_revision=base_revision),
        candidate_revision=candidate_revision,
        green_phase=TddPhaseState(
            phase=TddPhase.GREEN.value,
            work_unit_id="step-1--green",
            status="checks_passed",
            accepted_revision=candidate_revision,
            evidence_location="/tmp/step-1.json",
            change_id="change-step-1",
        ),
        pool="review_ready",
    )

    material = GitReviewMaterialProvider(repo_root).render(
        ReviewMaterialRequest(
            contract(),
            run_state(semantic_base_revision=base_revision, contract_state=contract(), registered_root=repo_root),
            cycle,
        )
    )
    payload = json.loads(material)

    assert payload["candidate_revision"] == candidate_revision
    assert payload["prior_semantic_revision"] == base_revision
    assert "add_resource" in payload["production_diff"]
    assert "class ReservationBook" in payload["production_source"]["content"]
    assert "test_add_resource_sets_availability" in payload["test_source"]["content"]
    assert payload["rack_ai_evidence"]["change_id"] == "change-step-1"
    assert find_forbidden_resource_selection_keys(payload) == []


def test_git_review_material_provider_is_read_only(tmp_path: Path):
    repo_root, base_revision, candidate_revision = create_review_repo(tmp_path)
    cycle = replace(
        ContractCycleRecord.from_step(proposal(), base_revision=base_revision),
        candidate_revision=candidate_revision,
        green_phase=TddPhaseState(
            phase=TddPhase.GREEN.value,
            work_unit_id="step-1--green",
            status="checks_passed",
            accepted_revision=candidate_revision,
        ),
        pool="review_ready",
    )
    provider = GitReviewMaterialProvider(repo_root)
    before_status = run_git(repo_root, "status", "--short")
    before_head = run_git(repo_root, "rev-parse", "HEAD")

    provider.render(
        ReviewMaterialRequest(
            contract(),
            run_state(semantic_base_revision=base_revision, contract_state=contract(), registered_root=repo_root),
            cycle,
        )
    )

    assert run_git(repo_root, "status", "--short") == before_status == ""
    assert run_git(repo_root, "rev-parse", "HEAD") == before_head == candidate_revision


def test_git_review_material_provider_fails_closed_on_missing_candidate_revision(tmp_path: Path):
    repo_root, base_revision, _ = create_review_repo(tmp_path)
    cycle = replace(
        ContractCycleRecord.from_step(proposal(), base_revision=base_revision),
        candidate_revision="f" * 40,
        pool="review_ready",
    )

    with pytest.raises(ValueError, match="rev-parse"):
        GitReviewMaterialProvider(repo_root).render(
            ReviewMaterialRequest(
                contract(),
                run_state(semantic_base_revision=base_revision, contract_state=contract(), registered_root=repo_root),
                cycle,
            )
        )


def test_git_review_material_provider_fails_closed_on_missing_candidate_file(tmp_path: Path):
    repo_root, base_revision, candidate_revision = create_review_repo(tmp_path)
    cycle = replace(
        ContractCycleRecord.from_step(replace(proposal(), production_path="missing.py"), base_revision=base_revision),
        candidate_revision=candidate_revision,
        pool="review_ready",
    )

    with pytest.raises(ValueError, match="git show"):
        GitReviewMaterialProvider(repo_root).render(
            ReviewMaterialRequest(
                contract(),
                run_state(semantic_base_revision=base_revision, contract_state=contract(), registered_root=repo_root),
                cycle,
            )
        )


@pytest.mark.asyncio
async def test_senior_reviewer_prompt_receives_git_review_material(tmp_path: Path):
    repo_root, base_revision, candidate_revision = create_review_repo(tmp_path)
    cycle = replace(
        ContractCycleRecord.from_step(proposal(), base_revision=base_revision),
        candidate_revision=candidate_revision,
        green_phase=TddPhaseState(
            phase=TddPhase.GREEN.value,
            work_unit_id="step-1--green",
            status="checks_passed",
            accepted_revision=candidate_revision,
            evidence_location="/tmp/step-1.json",
            change_id="change-step-1",
        ),
        pool="review_ready",
    )
    review_material = GitReviewMaterialProvider(repo_root).render(
        ReviewMaterialRequest(
            contract(),
            run_state(semantic_base_revision=base_revision, contract_state=contract(), registered_root=repo_root),
            cycle,
        )
    )
    gateway = FakeReasoningGateway([
        {
            "verdict": "approved",
            "rationale": "Looks good.",
            "findings": ["clean implementation"],
            "candidate_revision": candidate_revision,
            "step_id": cycle.step.step_id,
            "evidence_refs": ["review:1"],
            "repair_instructions": [],
        }
    ])

    await SeniorReviewer(gateway).review(
        contract=contract(),
        run_state=run_state(semantic_base_revision=base_revision, contract_state=contract(), registered_root=repo_root),
        cycle=cycle,
        candidate_revision=candidate_revision,
        review_material=review_material,
    )

    assert "production_diff" in gateway.requests[0].prompt
    assert "test_source" in gateway.requests[0].prompt
    assert candidate_revision in gateway.requests[0].prompt
    assert "allowed_source_refs" in gateway.requests[0].prompt
    assert "do not fail this candidate solely because other future contract requirements remain unimplemented" in gateway.requests[0].prompt


@pytest.mark.asyncio
async def test_senior_reviewer_repairs_out_of_scope_review_findings():
    cycle = ContractCycleRecord.from_step(proposal(), base_revision="b" * 40)
    request_state = run_state(current_pool="review_ready", semantic_base_revision="b" * 40, contract_state=contract())
    gateway = FakeReasoningGateway([
        {
            "verdict": "repair_required",
            "rationale": "Missing future reservation API.",
            "findings": ["Future reservation behavior is not implemented."],
            "candidate_revision": "c" * 40,
            "step_id": cycle.step.step_id,
            "evidence_refs": ["SRC-3"],
            "repair_instructions": ["Implement reservation support."],
        },
        {
            "verdict": "approved",
            "rationale": "The candidate satisfies the active add-resource step.",
            "findings": ["The active step is implemented cleanly."],
            "candidate_revision": "c" * 40,
            "step_id": cycle.step.step_id,
            "evidence_refs": ["SRC-1", "SRC-2"],
            "repair_instructions": [],
        },
    ])

    review = await SeniorReviewer(gateway).review(
        contract=contract(),
        run_state=request_state,
        cycle=replace(cycle, candidate_revision="c" * 40),
        candidate_revision="c" * 40,
        review_material="candidate source",
    )

    assert review.verdict == "approved"
    assert gateway.requests[1].purpose == "athba_senior_review_repair"
    assert "active review scope" in gateway.requests[1].prompt
    assert '"allowed_source_refs": [' in gateway.requests[1].prompt


@pytest.mark.asyncio
async def test_coordinator_uses_default_git_review_material_provider_when_repository_root_registered(tmp_path: Path):
    repo_root, base_revision, candidate_revision = create_review_repo(tmp_path)
    contract_state = single_requirement_contract()
    step = proposal()
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision=base_revision),
        red_phase=TddPhaseState(
            phase=TddPhase.RED.value,
            work_unit_id=step.step_id + "--red",
            status="checks_passed",
            accepted_revision=base_revision,
        ),
        green_phase=TddPhaseState(
            phase=TddPhase.GREEN.value,
            work_unit_id=step.step_id + "--green",
            status="checks_passed",
            accepted_revision=candidate_revision,
            evidence_location="/tmp/step-1.json",
            change_id="change-step-1",
        ),
        candidate_revision=candidate_revision,
        pool="review_ready",
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding(base_revision, registered_root=repo_root),
        current_trusted_revision=base_revision,
        contract_runs={
            contract_state.id: run_state(
                current_pool="review_ready",
                cycles=[cycle],
                semantic_base_revision=base_revision,
                contract_state=contract_state,
                registered_root=repo_root,
            )
        },
    )
    reasoner = FakeReasoningGateway([
        {
            "verdict": "approved",
            "rationale": "Looks good.",
            "findings": ["clean implementation"],
            "candidate_revision": candidate_revision,
            "step_id": step.step_id,
            "evidence_refs": ["review:1"],
            "repair_instructions": [],
        },
        {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
    ])

    await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({}),
        reasoning_gateway=reasoner,
        repository_binding=binding(base_revision, registered_root=repo_root),
        state_repo=MemoryStateRepo(snapshot),
    ).run_contract(contract_state)

    assert "production_diff" in reasoner.requests[0].prompt
    assert "test_source" in reasoner.requests[0].prompt
    assert candidate_revision in reasoner.requests[0].prompt


@pytest.mark.asyncio
async def test_provider_reasoning_gateway_uses_provider_neutral_adapter():
    provider = StubProvider()
    gateway = ProviderReasoningGateway(provider=provider, model="local-reasoner", max_tokens=123)

    result = await gateway.reason(ReasoningRequest(purpose="athba_test", prompt="hello", project_id="p1"))

    assert result.text == '{"ok": true}'
    assert result.provider == "stub"
    assert result.model == "local-reasoner"
    assert provider.calls[0]["model"] == "local-reasoner"
    assert provider.calls[0]["max_tokens"] == 123


@pytest.mark.asyncio
async def test_rejected_red_is_persisted_and_cannot_become_green_base():
    step = proposal()
    reasoner = FakeReasoningGateway([
        {
            "status": "propose",
            "rationale": "Start with RB-1.",
            "proposal": step.to_dict(),
            "completed_requirement_refs": [],
        },
        {
            "disposition": "reject_dependency",
            "parent_requirement_ref": "RB-1",
            "prerequisite_refs": [],
            "rationale": "No prerequisite is required for this focused behavior.",
        },
    ])
    red_result = WorkUnitExecutionResult(
        work_unit_id=step.step_id + "--red",
        accepted=False,
        status="checks_failed",
        change_id="red-collection-failure",
        evidence_location="/srv/rack-ai/state/changes/red-collection-failure/review-packet.json",
        error="expected failure was not trustworthy: ERROR collecting test module",
    )
    execution = FakeExecutionGateway({step.step_id + "--red": red_result})
    state_repo = MemoryStateRepo()

    result = await BehaviorContractCoordinator(
        execution_gateway=execution,
        reasoning_gateway=reasoner,
        repository_binding=binding(),
        state_repo=state_repo,
        max_tester_repairs=0,
    ).run_contract(contract())

    saved_cycle = state_repo.snapshot.contract_runs[contract().id].cycles[0]
    assert result.current_pool == "replan_ready"
    assert [call[0] for call in execution.calls] == [step.step_id + "--red"]
    assert all("green" not in call[0] for call in execution.calls)
    assert saved_cycle.red_phase is not None
    assert saved_cycle.red_phase.status == "checks_failed"
    assert saved_cycle.red_phase.change_id == "red-collection-failure"
    assert saved_cycle.red_phase.evidence_location.endswith("review-packet.json")
    assert saved_cycle.green_phase is not None
    assert saved_cycle.green_phase.accepted_revision is None
    assert saved_cycle.green_phase.base_sha is None


@pytest.mark.asyncio
async def test_targeted_requirement_limits_planner_and_persists_across_resume():
    target_state = replace(
        run_state(),
        targeted_requirement_ref="RB-2",
        targeted_checklist_ref="SPEC-2",
    )
    invalid = proposal("RB-1").to_dict()
    repaired = proposal("RB-2").to_dict()
    gateway = FakeReasoningGateway([
        {"status": "propose", "rationale": "wrong target", "proposal": invalid, "completed_requirement_refs": []},
        {"status": "propose", "rationale": "targeted repair", "proposal": repaired, "completed_requirement_refs": []},
    ])

    decision = await DynamicTddPlanner(gateway).decide_next_step(contract(), target_state)
    restored = BehaviorContractRunState.from_dict(target_state.to_dict())

    assert decision.proposal == proposal("RB-2")
    assert json.loads(gateway.requests[0].prompt)["allowed_requirement_refs"] == ["RB-2"]
    assert gateway.requests[1].purpose == "athba_tdd_step_selection_repair"
    assert restored.targeted_requirement_ref == "RB-2"
    assert restored.targeted_checklist_ref == "SPEC-2"
    assert restored.active_requirement_refs() == ["RB-2"]


def test_targeted_gap_selection_skips_untraceable_checklist_item():
    untraceable = SimpleNamespace(checklist_ref="SPEC-UNTRACEABLE", obligation_text="Broad invented item")
    traceable = SimpleNamespace(checklist_ref="SRC-2", obligation_text="A resource capacity must be a positive integer.")
    gatekeeper_state = SimpleNamespace(
        checklist=SimpleNamespace(
            items=[
                SimpleNamespace(ref="SPEC-UNTRACEABLE", kind="validation"),
                SimpleNamespace(ref="SRC-2", kind="validation"),
            ]
        ),
        latest_assessment=SimpleNamespace(gaps=[untraceable, traceable]),
    )

    assert _first_executable_gap(contract(), gatekeeper_state) is traceable


def test_targeted_gap_selection_accepts_paraphrased_traceable_gap():
    paraphrased = SimpleNamespace(
        checklist_ref="create_reservation",
        obligation_text="Clients can create uniquely identified reservations for a number of units on a resource.",
    )
    gatekeeper_state = SimpleNamespace(
        checklist=SimpleNamespace(items=[SimpleNamespace(ref="create_reservation", kind="behavior")]),
        latest_assessment=SimpleNamespace(gaps=[paraphrased]),
    )

    assert _first_executable_gap(contract(), gatekeeper_state) is paraphrased


@pytest.mark.asyncio
async def test_dependency_prerequisite_planner_sends_reasoning_request_boundary():
    payload = contract_payload()
    payload["observable_requirements"][1]["depends_on"] = ["RB-1"]
    gateway = FakeReasoningGateway([
        {
            "disposition": "already_planned",
            "parent_requirement_ref": "RB-2",
            "prerequisite_refs": ["RB-1"],
            "rationale": "The blocked behavior depends on the already planned setup requirement.",
            "prerequisite_observable": None,
        }
    ])
    evidence = FailureObservation(
        source="pytest",
        message="ImportError while collecting the blocked reservation test.",
        evidence_refs=["tests/test_reservation_book.py::test_reserve_reduces_capacity"],
        plausible=[FailureClassification.TEST_COLLECTION_OR_BOOTSTRAP_FAILURE],
        stderr="ImportError: missing reservation dependency",
        status="checks_failed",
    )

    decision = await DependencyPrerequisitePlanner(gateway).decide(
        DependencyDecisionRequest(
            contract=BehaviorContract.from_dict(payload),
            step=proposal("RB-2"),
            evidence=evidence,
            trusted_revision="f" * 40,
        )
    )

    sent = gateway.requests[0]
    prompt = json.loads(sent.prompt)
    assert isinstance(sent, ReasoningRequest)
    assert sent.purpose == "athba_dependency_prerequisite_decision"
    assert sent.project_id == "reservation-book"
    assert prompt["blocked_requirement_ref"] == "RB-2"
    assert "ImportError while collecting the blocked reservation test." in sent.prompt
    assert "test_reserve_reduces_capacity" in sent.prompt
    assert decision.disposition is DependencyDisposition.ALREADY_PLANNED
    assert decision.prerequisite_refs == ["RB-1"]


@pytest.mark.asyncio
async def test_dependency_prerequisite_planner_repairs_fenced_json_response():
    payload = contract().to_dict()
    payload["observable_requirements"][1]["depends_on"] = ["RB-1"]
    dependency = {
        "disposition": "add_prerequisite",
        "parent_requirement_ref": "RB-2",
        "prerequisite_refs": ["RB-0"],
        "rationale": "A smaller observable prerequisite must be proven first.",
        "prerequisite_observable": "A new resource can be stored before reservation validation.",
    }
    gateway = FakeReasoningGateway([
        f"```json\n{json.dumps(dependency)}\n```",
        dependency,
    ])
    evidence = FailureObservation(
        source="pytest",
        message="ImportError while collecting the blocked reservation test.",
        evidence_refs=["tests/test_reservation_book.py::test_reserve_reduces_capacity"],
        plausible=[FailureClassification.TEST_COLLECTION_OR_BOOTSTRAP_FAILURE],
        stderr="ImportError: missing reservation dependency",
        status="checks_failed",
    )

    decision = await DependencyPrerequisitePlanner(gateway).decide(
        DependencyDecisionRequest(
            contract=BehaviorContract.from_dict(payload),
            step=proposal("RB-2"),
            evidence=evidence,
            trusted_revision="f" * 40,
        )
    )

    assert decision.disposition is DependencyDisposition.ADD_PREREQUISITE
    assert decision.prerequisite_refs == ["RB-0"]
    assert gateway.requests[1].purpose == "athba_dependency_prerequisite_decision_repair"
    assert "dependency decision response was not valid JSON" in gateway.requests[1].prompt


def test_behavior_contract_run_state_round_trip_preserves_binding_resources():
    restored = BehaviorContractRunState.from_dict(
        BehaviorContractRunState(
            contract=contract(),
            repository_binding=RepositoryBinding(
                repository_id="reservation-book-fixture",
                base_ref="main",
                base_sha="a" * 40,
                environment_resources=["/srv/env/python-314", "/srv/env/pytest"],
            ),
            semantic_base_revision="a" * 40,
            current_pool="tdd_ready",
            completed_requirement_refs=[],
            cycles=[],
        ).to_dict()
    )

    assert restored.repository_binding.environment_resources == ["/srv/env/python-314", "/srv/env/pytest"]


def review_approved(step_id: str, revision: str) -> dict[str, object]:
    return {
        "verdict": "approved",
        "rationale": "Looks good.",
        "findings": ["approved"],
        "candidate_revision": revision,
        "step_id": step_id,
        "evidence_refs": ["review:approved"],
        "repair_instructions": [],
    }


def review_repair(step_id: str, revision: str) -> dict[str, object]:
    return {
        "verdict": "repair_required",
        "rationale": "Remove the noisy comment.",
        "findings": ["comment is noisy"],
        "candidate_revision": revision,
        "step_id": step_id,
        "evidence_refs": ["review:repair"],
        "repair_instructions": ["Remove the noisy comment and keep behavior unchanged."],
    }


def review_replan(step_id: str, revision: str) -> dict[str, object]:
    return {
        "verdict": "replan_required",
        "rationale": "The change does not integrate with the contract.",
        "findings": ["integration mismatch"],
        "candidate_revision": revision,
        "step_id": step_id,
        "evidence_refs": ["review:replan"],
        "repair_instructions": [],
    }


def saved_runs(repo: MemoryStateRepo, contract_id: str) -> list[BehaviorContractRunState]:
    return [snapshot.contract_runs[contract_id] for snapshot in repo.saved if contract_id in snapshot.contract_runs]


@pytest.mark.asyncio
async def test_resource_limit_failure_splits_into_persisted_children_and_updates_trusted_revision():
    contract_state = single_requirement_contract()
    parent = proposal(step_id="parent-step")
    child_a = split_child("child-a")
    child_b = split_child("child-b", depends_on=["child-a"])
    repo = MemoryStateRepo()
    gateway = FakeReasoningGateway([
        {"status": "propose", "rationale": "Start with RB-1.", "proposal": parent.to_dict(), "completed_requirement_refs": []},
        split_decision(child_a, child_b),
        review_approved("child-a", "d" * 40),
        review_approved("child-b", "f" * 40),
        {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
    ])
    execution = FakeExecutionGateway({
        "parent-step--red": accepted("parent-step--red", "b" * 40),
        "parent-step--green": rejected("parent-step--green", error="resource exhausted while implementing the packet"),
        "child-a--red": accepted("child-a--red", "c" * 40),
        "child-a--green": accepted("child-a--green", "d" * 40),
        "child-b--red": accepted("child-b--red", "e" * 40),
        "child-b--green": accepted("child-b--green", "f" * 40),
    })

    result = await BehaviorContractCoordinator(
        execution_gateway=execution,
        reasoning_gateway=gateway,
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    split_states = [item for item in saved_runs(repo, contract_state.id) if item.failure_progress.splits]
    assert result.current_pool == "completed"
    assert [call[:2] for call in execution.calls] == [
        ("parent-step--red", "a" * 40),
        ("parent-step--green", "b" * 40),
        ("child-a--red", "b" * 40),
        ("child-a--green", "c" * 40),
        ("child-b--red", "d" * 40),
        ("child-b--green", "e" * 40),
    ]
    assert [request.purpose for request in gateway.requests].count("athba_resource_limit_split") == 1
    assert split_states[-1].failure_progress.splits[-1] == WorkPacketSplit(
        parent_work_unit_id="parent-step--green",
        parent_step_id="parent-step",
        parent_requirement_ref="RB-1",
        child_work_unit_ids=["child-a", "child-b"],
        preserved_objective=parent.green_objective,
        rationale="The packet exceeded the resource budget and must be decomposed into smaller semantic work.",
        trusted_revision="b" * 40,
        split_depth=1,
        child_steps=[child_a, child_b],
        completed_child_ids=["child-a", "child-b"],
    )


@pytest.mark.asyncio
async def test_resume_split_uses_persisted_children_without_replanning():
    contract_state = single_requirement_contract()
    parent = proposal(step_id="parent-step")
    child_a = split_child("child-a")
    child_b = split_child("child-b", depends_on=["child-a"])
    split = WorkPacketSplit(
        parent_work_unit_id="parent-step--green",
        parent_step_id="parent-step",
        parent_requirement_ref="RB-1",
        child_work_unit_ids=["child-a", "child-b"],
        preserved_objective=parent.green_objective,
        rationale="The packet exceeded the resource budget and must be decomposed into smaller semantic work.",
        trusted_revision="b" * 40,
        split_depth=1,
        child_steps=[child_a, child_b],
    )
    parent_cycle = replace(
        ContractCycleRecord.from_step(parent, base_revision="a" * 40),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id="parent-step--red", status="checks_passed", accepted_revision="b" * 40),
        green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id="parent-step--green", status="checks_failed", error="resource exhausted while implementing the packet"),
        pool="tdd_ready",
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("a" * 40),
        current_trusted_revision="a" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="tdd_ready",
                cycles=[parent_cycle],
                contract_state=contract_state,
                failure_progress=FailureProgressState(splits=[split]),
                blocked_reason="resource_limit_failure: split into child-a, child-b",
            )
        },
    )
    execution = FakeExecutionGateway({
        "child-a--red": accepted("child-a--red", "c" * 40),
        "child-a--green": accepted("child-a--green", "d" * 40),
        "child-b--red": accepted("child-b--red", "e" * 40),
        "child-b--green": accepted("child-b--green", "f" * 40),
    })
    gateway = FakeReasoningGateway([
        review_approved("child-a", "d" * 40),
        review_approved("child-b", "f" * 40),
        {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
    ])

    result = await BehaviorContractCoordinator(
        execution_gateway=execution,
        reasoning_gateway=gateway,
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert result.current_pool == "completed"
    assert [call[:2] for call in execution.calls] == [
        ("child-a--red", "b" * 40),
        ("child-a--green", "c" * 40),
        ("child-b--red", "d" * 40),
        ("child-b--green", "e" * 40),
    ]
    assert [request.purpose for request in gateway.requests].count("athba_resource_limit_split") == 0


@pytest.mark.asyncio
async def test_cannot_split_resource_limit_failure_replans_without_child_work():
    contract_state = single_requirement_contract()
    parent = proposal(step_id="parent-step")
    execution = FakeExecutionGateway({
        "parent-step--red": accepted("parent-step--red", "b" * 40),
        "parent-step--green": rejected("parent-step--green", error="resource exhausted while implementing the packet"),
    })
    gateway = FakeReasoningGateway([
        {"status": "propose", "rationale": "Start with RB-1.", "proposal": parent.to_dict(), "completed_requirement_refs": []},
        cannot_split_decision("The packet is already the smallest coherent semantic slice."),
    ])

    result = await BehaviorContractCoordinator(
        execution_gateway=execution,
        reasoning_gateway=gateway,
        repository_binding=binding(),
        state_repo=MemoryStateRepo(),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert result.current_pool == "replan_ready"
    assert "smallest coherent semantic slice" in (result.blocked_reason or "")
    assert [call[0] for call in execution.calls] == ["parent-step--red", "parent-step--green"]


@pytest.mark.asyncio
async def test_cannot_split_resource_limit_failure_accepts_fenced_json_response():
    contract_state = single_requirement_contract()
    parent = proposal(step_id="parent-step")
    execution = FakeExecutionGateway({
        "parent-step--red": accepted("parent-step--red", "b" * 40),
        "parent-step--green": rejected("parent-step--green", error="jcode wall-clock timeout exceeded for worker local-coder after 900 seconds"),
    })
    fenced_decision = "```json\n" + json.dumps(
        cannot_split_decision("The packet is already the smallest coherent semantic slice."),
        indent=2,
    ) + "\n```"
    gateway = FakeReasoningGateway([
        {"status": "propose", "rationale": "Start with RB-1.", "proposal": parent.to_dict(), "completed_requirement_refs": []},
        fenced_decision,
    ])

    result = await BehaviorContractCoordinator(
        execution_gateway=execution,
        reasoning_gateway=gateway,
        repository_binding=binding(),
        state_repo=MemoryStateRepo(),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert result.current_pool == "replan_ready"
    assert "smallest coherent semantic slice" in (result.blocked_reason or "")
    assert [request.purpose for request in gateway.requests].count("athba_resource_limit_split") == 1


@pytest.mark.asyncio
async def test_split_depth_exhaustion_replans_without_calling_split_planner():
    contract_state = single_requirement_contract()
    grandchild = split_child("grandchild-a")
    nested_split = WorkPacketSplit(
        parent_work_unit_id="child-a--green",
        parent_step_id="child-a",
        parent_requirement_ref="RB-1",
        child_work_unit_ids=["grandchild-a", "grandchild-b"],
        preserved_objective="Implement only enough code for child-a.",
        rationale="The first split child also exceeded the resource budget.",
        trusted_revision="d" * 40,
        split_depth=2,
        child_steps=[grandchild, split_child("grandchild-b", depends_on=["grandchild-a"])],
    )
    cycle = replace(
        ContractCycleRecord.from_step(proposal(step_id="grandchild-a"), base_revision="d" * 40),
        step=TddStepProposal(
            step_id=grandchild.step_id,
            requirement_refs=list(grandchild.requirement_refs),
            focused_behavior=grandchild.focused_behavior,
            test_name=grandchild.test_name,
            expected_result=grandchild.expected_result,
            test_path=grandchild.test_path,
            production_path=grandchild.production_path,
            red_objective=grandchild.red_objective,
            green_objective=grandchild.green_objective,
            reason_next_smallest=grandchild.reason_next_smallest,
        ),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id="grandchild-a--red", status="checks_passed", accepted_revision="e" * 40),
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("d" * 40),
        current_trusted_revision="d" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="cycle_active",
                cycles=[cycle],
                contract_state=contract_state,
                semantic_base_revision="d" * 40,
                failure_progress=FailureProgressState(splits=[nested_split]),
            )
        },
    )

    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({
            "grandchild-a--green": rejected("grandchild-a--green", error="resource exhausted again"),
        }),
        reasoning_gateway=FakeReasoningGateway([]),
        repository_binding=binding("d" * 40),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert result.current_pool == "replan_ready"
    assert "split depth exhausted" in (result.blocked_reason or "")


@pytest.mark.asyncio
async def test_red_security_violation_routes_to_tester_repair():
    step = proposal()
    repo = MemoryStateRepo()
    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({step.step_id + "--red": rejected(step.step_id + "--red", error="unauthorized path_policy violation")}),
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []}
        ]),
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(single_requirement_contract())

    retry_snapshot = next(item for item in saved_runs(repo, single_requirement_contract().id) if item.failure_progress.state is FailureRouteState.AWAITING_REPAIR)
    assert retry_snapshot.failure_progress.history[-1].dominant is FailureClassification.SECURITY_OR_EXECUTION_POLICY_VIOLATION
    assert retry_snapshot.failure_progress.history[-1].action is ProgressionAction.REPAIR_CANDIDATE
    assert retry_snapshot.failure_progress.repair_packets[-1].role == "Tester"
    assert result.current_pool == "replan_ready"


@pytest.mark.asyncio
async def test_green_security_violation_routes_to_developer_repair():
    step = proposal()
    repo = MemoryStateRepo()
    gateway = FakeExecutionGateway({
        step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
        step.step_id + "--green": rejected(step.step_id + "--green", error="unauthorized path_policy violation"),
    })
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []}
        ]),
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(single_requirement_contract())

    retry_snapshot = next(item for item in saved_runs(repo, single_requirement_contract().id) if item.failure_progress.state is FailureRouteState.AWAITING_REPAIR)
    assert retry_snapshot.failure_progress.history[-1].dominant is FailureClassification.SECURITY_OR_EXECUTION_POLICY_VIOLATION
    assert retry_snapshot.failure_progress.history[-1].action is ProgressionAction.REPAIR_CANDIDATE
    assert retry_snapshot.failure_progress.repair_packets[-1].role == "Developer"
    assert result.current_pool == "replan_ready"
    assert gateway.calls[1][1] == "b" * 40


@pytest.mark.asyncio
async def test_red_change_scope_violation_routes_to_tester_repair():
    step = proposal()
    repo = MemoryStateRepo()
    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({step.step_id + "--red": rejected(step.step_id + "--red", error="changed_paths out-of-scope edit")}),
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []}
        ]),
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(single_requirement_contract())

    retry_snapshot = next(item for item in saved_runs(repo, single_requirement_contract().id) if item.failure_progress.state is FailureRouteState.AWAITING_REPAIR)
    assert retry_snapshot.failure_progress.history[-1].dominant is FailureClassification.CHANGE_SCOPE_VIOLATION
    assert retry_snapshot.failure_progress.history[-1].action is ProgressionAction.REPAIR_CANDIDATE
    assert retry_snapshot.failure_progress.repair_packets[-1].role == "Tester"
    assert result.current_pool == "replan_ready"


@pytest.mark.asyncio
async def test_green_change_scope_violation_routes_to_developer_repair():
    step = proposal()
    repo = MemoryStateRepo()
    gateway = FakeExecutionGateway({
        step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
        step.step_id + "--green": rejected(step.step_id + "--green", error="changed_paths out-of-scope edit"),
    })
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []}
        ]),
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(single_requirement_contract())

    retry_snapshot = next(item for item in saved_runs(repo, single_requirement_contract().id) if item.failure_progress.state is FailureRouteState.AWAITING_REPAIR)
    assert retry_snapshot.failure_progress.history[-1].dominant is FailureClassification.CHANGE_SCOPE_VIOLATION
    assert retry_snapshot.failure_progress.history[-1].action is ProgressionAction.REPAIR_CANDIDATE
    assert retry_snapshot.failure_progress.repair_packets[-1].role == "Developer"
    assert result.current_pool == "replan_ready"
    assert gateway.calls[1][1] == "b" * 40


@pytest.mark.asyncio
async def test_green_security_violation_preserves_developer_retry_budget_and_failed_revision():
    step = proposal()
    repo = MemoryStateRepo()
    gateway = FakeExecutionGateway({
        step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
        step.step_id + "--green": rejected(
            step.step_id + "--green",
            error="unauthorized path_policy violation",
            allowed_paths=["reservation_book.py"],
            changed_paths=["docs/out_of_scope.md"],
        ),
    })
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []}
        ]),
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(contract())

    saved = repo.snapshot.contract_runs[contract().id]
    retry_snapshot = next(item for item in saved_runs(repo, contract().id) if item.failure_progress.state is FailureRouteState.AWAITING_REPAIR)
    packet = retry_snapshot.failure_progress.repair_packets[-1]
    assert result.current_pool == "replan_ready"
    assert saved.semantic_base_revision == "a" * 40
    assert retry_snapshot.failure_progress.retry_counts == {RetryRoute.DEVELOPER_REPAIR.value: 1}
    assert saved.failure_progress.retry_counts == {RetryRoute.DEVELOPER_REPAIR.value: 2}
    assert retry_snapshot.failure_progress.history[-1].observations[0].phase == TddPhase.GREEN.value
    assert retry_snapshot.failure_progress.history[-1].observations[0].work_unit_id == step.step_id + "--green"
    assert packet.role == "Developer"
    assert packet.originating_phase == TddPhase.GREEN.value
    assert packet.allowed_paths == ["reservation_book.py"]
    assert packet.changed_paths == ["docs/out_of_scope.md"]
    assert packet.trusted_revision == "b" * 40
    assert gateway.calls[1][:2] == (step.step_id + "--green", "b" * 40)
    assert gateway.calls[2][:2] == (step.step_id + "--green", "b" * 40)


@pytest.mark.asyncio
async def test_red_change_scope_violation_preserves_tester_retry_budget_and_failed_revision():
    step = proposal()
    repo = MemoryStateRepo()
    gateway = FakeExecutionGateway({
        step.step_id + "--red": rejected(
            step.step_id + "--red",
            error="changed_paths out-of-scope edit",
            allowed_paths=["tests/test_reservation_book.py"],
            changed_paths=["docs/out_of_scope.md"],
        )
    })
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []}
        ]),
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(contract())

    saved = repo.snapshot.contract_runs[contract().id]
    retry_snapshot = next(item for item in saved_runs(repo, contract().id) if item.failure_progress.state is FailureRouteState.AWAITING_REPAIR)
    packet = retry_snapshot.failure_progress.repair_packets[-1]
    assert result.current_pool == "replan_ready"
    assert saved.semantic_base_revision == "a" * 40
    assert retry_snapshot.failure_progress.retry_counts == {RetryRoute.TESTER_REPAIR.value: 1}
    assert saved.failure_progress.retry_counts == {RetryRoute.TESTER_REPAIR.value: 2}
    assert retry_snapshot.failure_progress.history[-1].observations[0].phase == TddPhase.RED.value
    assert retry_snapshot.failure_progress.history[-1].observations[0].work_unit_id == step.step_id + "--red"
    assert packet.role == "Tester"
    assert packet.originating_phase == TddPhase.RED.value
    assert packet.allowed_paths == ["tests/test_reservation_book.py"]
    assert packet.changed_paths == ["docs/out_of_scope.md"]
    assert packet.trusted_revision == "a" * 40
    assert gateway.calls[0][:2] == (step.step_id + "--red", "a" * 40)
    assert gateway.calls[1][:2] == (step.step_id + "--red", "a" * 40)


@pytest.mark.asyncio
async def test_athba_request_defect_policy_violation_fails_closed_without_role_blame():
    contract_state = single_requirement_contract()
    step = proposal()
    repo = MemoryStateRepo()

    class WrongAllowedPathDeveloperFactory:
        def build(self, request):
            unit = ContractDeveloperWorkUnitFactory().build(request)
            return replace(unit, allowed_paths=["tests/test_reservation_book.py"])

    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({
            step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
            step.step_id + "--green": rejected(
                step.step_id + "--green",
                error="unauthorized path_policy violation",
                allowed_paths=["tests/test_reservation_book.py"],
                changed_paths=["reservation_book.py"],
            ),
        }),
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []}
        ]),
        repository_binding=binding(),
        state_repo=repo,
        developer_factory=WrongAllowedPathDeveloperFactory(),
    ).run_contract(contract_state)

    saved = repo.snapshot.contract_runs[contract_state.id]
    observation = saved.failure_progress.history[-1].observations[0]
    assert result.current_pool == "replan_ready"
    assert saved.semantic_base_revision == "a" * 40
    assert saved.failure_progress.retry_counts == {}
    assert saved.failure_progress.repair_packets == []
    assert observation.phase == TddPhase.GREEN.value
    assert observation.work_unit_id == step.step_id + "--green"
    assert observation.allowed_paths == ["tests/test_reservation_book.py"]
    assert observation.changed_paths == ["reservation_book.py"]
    assert "athba_request_defect" in (saved.blocked_reason or "")


@pytest.mark.asyncio
async def test_change_scope_within_contract_phase_scope_replans_without_role_blame():
    contract_state = multi_production_contract()
    step = proposal()
    repo = MemoryStateRepo()
    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({
            step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
            step.step_id + "--green": rejected(
                step.step_id + "--green",
                error="changed_paths out-of-scope edit",
                allowed_paths=["reservation_book.py"],
                changed_paths=["reservation_index.py"],
            ),
        }),
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []}
        ]),
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(contract_state)

    saved = repo.snapshot.contract_runs[contract_state.id]
    assert result.current_pool == "replan_ready"
    assert saved.semantic_base_revision == "a" * 40
    assert saved.failure_progress.retry_counts == {}
    assert saved.failure_progress.repair_packets == []
    assert "plan_scope_change" in (saved.blocked_reason or "")


@pytest.mark.asyncio
async def test_resume_green_security_violation_retry_preserves_developer_route_and_red_base():
    contract_state = single_requirement_contract()
    step = proposal()
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="a" * 40),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=step.step_id + "--red", status="checks_passed", accepted_revision="b" * 40),
        green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id=step.step_id + "--green", status="checks_failed", error="unauthorized path_policy violation"),
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("a" * 40),
        current_trusted_revision="a" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="cycle_active",
                cycles=[cycle],
                contract_state=contract_state,
                semantic_base_revision="b" * 40,
                failure_progress=FailureProgressState(
                    state=FailureRouteState.AWAITING_REPAIR,
                    history=[failure_decision(FailureClassification.SECURITY_OR_EXECUTION_POLICY_VIOLATION, ProgressionAction.REPAIR_CANDIDATE)],
                    retry_counts={RetryRoute.DEVELOPER_REPAIR.value: 1},
                    repair_packets=[RepairPacket(
                        kind=PacketKind.REPAIR,
                        role="Developer",
                        work_unit_id=step.step_id + "--green",
                        trusted_revision="b" * 40,
                        original_objective="repair objective",
                        allowed_paths=["reservation_book.py"],
                        classification=FailureClassification.SECURITY_OR_EXECUTION_POLICY_VIOLATION,
                        previous_candidate=None,
                        evidence=["Candidate modified docs/out_of_scope.md while allowed paths are reservation_book.py."],
                        originating_phase=TddPhase.GREEN.value,
                        changed_paths=["docs/out_of_scope.md"],
                    )],
                    blocker="security_or_execution_policy_violation: retrying Developer from trusted revision",
                ),
                blocked_reason="security_or_execution_policy_violation: retrying Developer from trusted revision",
            )
        },
    )
    gateway = FakeExecutionGateway({step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40)})
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([review_approved(step.step_id, "c" * 40), {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []}]),
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert gateway.calls[0][:2] == (step.step_id + "--green", "b" * 40)
    assert result.current_pool == "completed"


@pytest.mark.asyncio
async def test_resume_red_change_scope_violation_retry_preserves_tester_route_and_base():
    contract_state = single_requirement_contract()
    step = proposal()
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="a" * 40),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=step.step_id + "--red", status="checks_failed", error="changed_paths out-of-scope edit"),
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("a" * 40),
        current_trusted_revision="a" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="cycle_active",
                cycles=[cycle],
                contract_state=contract_state,
                semantic_base_revision="a" * 40,
                failure_progress=FailureProgressState(
                    state=FailureRouteState.AWAITING_REPAIR,
                    history=[failure_decision(FailureClassification.CHANGE_SCOPE_VIOLATION, ProgressionAction.REPAIR_CANDIDATE)],
                    retry_counts={RetryRoute.TESTER_REPAIR.value: 1},
                    repair_packets=[RepairPacket(
                        kind=PacketKind.REPAIR,
                        role="Tester",
                        work_unit_id=step.step_id + "--red",
                        trusted_revision="a" * 40,
                        original_objective="repair objective",
                        allowed_paths=["tests/test_reservation_book.py"],
                        classification=FailureClassification.CHANGE_SCOPE_VIOLATION,
                        previous_candidate=None,
                        evidence=["Candidate modified docs/out_of_scope.md while allowed paths are tests/test_reservation_book.py."],
                        originating_phase=TddPhase.RED.value,
                        changed_paths=["docs/out_of_scope.md"],
                    )],
                    blocker="change_scope_violation: retrying Tester from trusted revision",
                ),
                blocked_reason="change_scope_violation: retrying Tester from trusted revision",
            )
        },
    )
    gateway = FakeExecutionGateway({
        step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
        step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
    })
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([review_approved(step.step_id, "c" * 40), {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []}]),
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert gateway.calls[0][:2] == (step.step_id + "--red", "a" * 40)
    assert result.current_pool == "completed"


@pytest.mark.asyncio
async def test_red_security_violation_retry_can_recover_and_complete():
    contract_state = single_requirement_contract()
    step = proposal()
    repo = MemoryStateRepo()
    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({
            step.step_id + "--red": [
                rejected(
                    step.step_id + "--red",
                    error="unauthorized path_policy violation",
                    allowed_paths=["tests/test_reservation_book.py"],
                    changed_paths=["docs/out_of_scope.md"],
                ),
                accepted(step.step_id + "--red", "b" * 40),
            ],
            step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
        }),
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []},
            review_approved(step.step_id, "c" * 40),
            {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
        ]),
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    saved = repo.snapshot.contract_runs[contract_state.id]
    assert result.current_pool == "completed"
    assert saved.failure_progress.retry_counts == {RetryRoute.TESTER_REPAIR.value: 1}


@pytest.mark.asyncio
async def test_green_change_scope_violation_retry_can_recover_and_reach_review_normally():
    contract_state = single_requirement_contract()
    step = proposal()
    repo = MemoryStateRepo()
    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({
            step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
            step.step_id + "--green": [
                rejected(
                    step.step_id + "--green",
                    error="changed_paths out-of-scope edit",
                    allowed_paths=["reservation_book.py"],
                    changed_paths=["docs/out_of_scope.md"],
                ),
                accepted(step.step_id + "--green", "c" * 40),
            ],
        }),
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []},
            review_approved(step.step_id, "c" * 40),
            {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
        ]),
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    saved = repo.snapshot.contract_runs[contract_state.id]
    assert result.current_pool == "completed"
    assert saved.failure_progress.retry_counts == {RetryRoute.DEVELOPER_REPAIR.value: 1}


@pytest.mark.asyncio
async def test_syntax_failure_already_planned_dependency_defers_and_parent_resumes_after_resume():
    parent = proposal("RB-2", step_id="step-rb2")
    prereq = proposal("RB-1", step_id="step-rb1")
    repo = MemoryStateRepo()
    first_gateway = FakeExecutionGateway({
        parent.step_id + "--red": rejected(parent.step_id + "--red", error="SyntaxError: expected ':'"),
    })
    first_result = await BehaviorContractCoordinator(
        execution_gateway=first_gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Try the reservation behavior first.", "proposal": parent.to_dict(), "completed_requirement_refs": []},
            {
                "disposition": "already_planned",
                "parent_requirement_ref": "RB-2",
                "prerequisite_refs": ["RB-1"],
                "rationale": "The blocked reservation behavior depends on the already planned resource setup requirement.",
                "prerequisite_observable": None,
            },
        ]),
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(contract())

    deferred = repo.snapshot.contract_runs[contract().id]
    assert first_result.current_pool == "tdd_ready"
    assert deferred.failure_progress.state is FailureRouteState.DEFERRED_DEPENDENCY
    assert deferred.failure_progress.history[-1].dominant is FailureClassification.SYNTAX_OR_PARSE_FAILURE
    assert deferred.failure_progress.dependency_decisions[-1].disposition is DependencyDisposition.ALREADY_PLANNED
    assert deferred.failure_progress.prerequisite_links["RB-2"] == ["RB-1"]

    second_gateway = FakeExecutionGateway({
        prereq.step_id + "--red": accepted(prereq.step_id + "--red", "b" * 40),
        prereq.step_id + "--green": accepted(prereq.step_id + "--green", "c" * 40),
        parent.step_id + "--red": accepted(parent.step_id + "--red", "d" * 40),
        parent.step_id + "--green": accepted(parent.step_id + "--green", "e" * 40),
    })
    second_result = await BehaviorContractCoordinator(
        execution_gateway=second_gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Do the prerequisite first.", "proposal": prereq.to_dict(), "completed_requirement_refs": []},
            review_approved(prereq.step_id, "c" * 40),
            {"status": "propose", "rationale": "The deferred reservation behavior is now ready.", "proposal": parent.to_dict(), "completed_requirement_refs": ["RB-1"]},
            review_approved(parent.step_id, "e" * 40),
            {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": ["RB-1", "RB-2"]},
        ]),
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract())

    assert second_result.current_pool == "completed"
    assert [call[0] for call in second_gateway.calls] == [
        prereq.step_id + "--red",
        prereq.step_id + "--green",
        parent.step_id + "--red",
        parent.step_id + "--green",
    ]


@pytest.mark.asyncio
async def test_syntax_failure_add_prerequisite_synthesizes_requirement_and_parent_resumes_after_resume():
    parent = proposal(step_id="step-rb1")
    prerequisite = proposal("RB-0", step_id="step-rb0")
    contract_state = single_requirement_contract()
    repo = MemoryStateRepo()
    first_result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({
            parent.step_id + "--red": rejected(parent.step_id + "--red", error="SyntaxError: invalid syntax"),
        }),
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": parent.to_dict(), "completed_requirement_refs": []},
            {
                "disposition": "add_prerequisite",
                "parent_requirement_ref": "RB-1",
                "prerequisite_refs": ["RB-0"],
                "rationale": "A smaller observable prerequisite must be proven first.",
                "prerequisite_observable": "A new resource can be stored before reservation validation.",
            },
        ]),
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(contract_state)

    deferred = repo.snapshot.contract_runs[contract_state.id]
    requirement_refs = deferred.contract.requirement_refs()
    parent_requirement = next(item for item in deferred.contract.observable_requirements if item.ref == "RB-1")
    assert first_result.current_pool == "tdd_ready"
    assert "RB-0" in requirement_refs
    assert parent_requirement.depends_on == ["RB-0"]
    assert deferred.failure_progress.state is FailureRouteState.DEFERRED_DEPENDENCY
    assert deferred.failure_progress.history[-1].dominant is FailureClassification.SYNTAX_OR_PARSE_FAILURE
    assert deferred.failure_progress.dependency_decisions[-1].disposition is DependencyDisposition.ADD_PREREQUISITE

    second_gateway = FakeExecutionGateway({
        prerequisite.step_id + "--red": accepted(prerequisite.step_id + "--red", "b" * 40),
        prerequisite.step_id + "--green": accepted(prerequisite.step_id + "--green", "c" * 40),
        parent.step_id + "--red": accepted(parent.step_id + "--red", "d" * 40),
        parent.step_id + "--green": accepted(parent.step_id + "--green", "e" * 40),
    })
    second_result = await BehaviorContractCoordinator(
        execution_gateway=second_gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Prove the synthesized prerequisite first.", "proposal": prerequisite.to_dict(), "completed_requirement_refs": []},
            review_approved(prerequisite.step_id, "c" * 40),
            {"status": "propose", "rationale": "Return to the deferred RB-1 behavior.", "proposal": parent.to_dict(), "completed_requirement_refs": ["RB-0"]},
            review_approved(parent.step_id, "e" * 40),
            {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": ["RB-0", "RB-1"]},
        ]),
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert second_result.current_pool == "completed"
    assert [call[0] for call in second_gateway.calls] == [
        prerequisite.step_id + "--red",
        prerequisite.step_id + "--green",
        parent.step_id + "--red",
        parent.step_id + "--green",
    ]


@pytest.mark.asyncio
async def test_syntax_failure_reject_dependency_routes_to_tester_repair_from_semantic_base():
    step = proposal()
    repo = MemoryStateRepo()
    gateway = FakeExecutionGateway({
        step.step_id + "--red": [
            rejected(step.step_id + "--red", error="SyntaxError: invalid syntax"),
            accepted(step.step_id + "--red", "b" * 40),
        ],
        step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
    })
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []},
            {
                "disposition": "reject_dependency",
                "parent_requirement_ref": "RB-1",
                "prerequisite_refs": [],
                "rationale": "No prerequisite is required for this focused behavior.",
            },
            review_approved(step.step_id, "c" * 40),
            {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": ["RB-1"]},
        ]),
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(single_requirement_contract())

    retry_snapshot = next(item for item in saved_runs(repo, single_requirement_contract().id) if item.failure_progress.state is FailureRouteState.AWAITING_REPAIR)
    packet = retry_snapshot.failure_progress.repair_packets[-1]
    assert result.current_pool == "completed"
    assert retry_snapshot.failure_progress.history[-1].dominant is FailureClassification.SYNTAX_OR_PARSE_FAILURE
    assert packet.role == "Tester"
    assert packet.trusted_revision == "a" * 40
    assert gateway.calls[0][:2] == (step.step_id + "--red", "a" * 40)
    assert gateway.calls[1][:2] == (step.step_id + "--red", "a" * 40)
    assert gateway.calls[1][3] == step.step_id + "--red--retry-1"
    assert repo.snapshot.contract_runs[single_requirement_contract().id].failure_progress.retry_counts == {RetryRoute.TESTER_REPAIR.value: 1}


@pytest.mark.asyncio
async def test_candidate_repair_uses_attempt_scoped_change_key_for_live_retries():
    step = proposal()
    repo = MemoryStateRepo()
    gateway = FakeExecutionGateway({
        step.step_id + "--red": [
            rejected(step.step_id + "--red", error="acceptance failed"),
            accepted(step.step_id + "--red", "b" * 40),
        ],
        step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
    })
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []},
            review_approved(step.step_id, "c" * 40),
            {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": ["RB-1"]},
        ]),
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(single_requirement_contract())

    assert result.current_pool == "completed"
    assert gateway.calls[0][3] is None
    assert gateway.calls[1][3] == step.step_id + "--red--retry-1"


@pytest.mark.asyncio
async def test_build_link_failure_reject_dependency_routes_to_developer_repair_from_red_base():
    step = proposal()
    repo = MemoryStateRepo()
    gateway = FakeExecutionGateway({
        step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
        step.step_id + "--green": [
            rejected(step.step_id + "--green", error="build failed: linker could not resolve symbol"),
            accepted(step.step_id + "--green", "c" * 40),
        ],
    })
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []},
            {
                "disposition": "reject_dependency",
                "parent_requirement_ref": "RB-1",
                "prerequisite_refs": [],
                "rationale": "No prerequisite is required for this focused production change.",
            },
            review_approved(step.step_id, "c" * 40),
            {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": ["RB-1"]},
        ]),
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(single_requirement_contract())

    retry_snapshot = next(item for item in saved_runs(repo, single_requirement_contract().id) if item.failure_progress.state is FailureRouteState.AWAITING_REPAIR)
    packet = retry_snapshot.failure_progress.repair_packets[-1]
    assert result.current_pool == "completed"
    assert retry_snapshot.failure_progress.history[-1].dominant is FailureClassification.BUILD_OR_LINK_FAILURE
    assert packet.role == "Developer"
    assert packet.trusted_revision == "b" * 40
    assert gateway.calls[1][:2] == (step.step_id + "--green", "b" * 40)
    assert gateway.calls[2][:2] == (step.step_id + "--green", "b" * 40)
    assert gateway.calls[2][3] == step.step_id + "--green--retry-1"
    assert repo.snapshot.contract_runs[single_requirement_contract().id].failure_progress.retry_counts == {RetryRoute.DEVELOPER_REPAIR.value: 1}


@pytest.mark.asyncio
async def test_collection_bootstrap_failure_uses_dependency_deferral_route():
    step = proposal("RB-2", step_id="step-rb2")
    repo = MemoryStateRepo()
    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({
            step.step_id + "--red": rejected(step.step_id + "--red", error="ImportError while bootstrapping test collection"),
        }),
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Try the reservation behavior first.", "proposal": step.to_dict(), "completed_requirement_refs": []},
            {
                "disposition": "already_planned",
                "parent_requirement_ref": "RB-2",
                "prerequisite_refs": ["RB-1"],
                "rationale": "Reservation collection depends on the existing resource setup behavior.",
                "prerequisite_observable": None,
            },
        ]),
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(contract())

    saved = repo.snapshot.contract_runs[contract().id]
    assert result.current_pool == "tdd_ready"
    assert saved.failure_progress.state is FailureRouteState.DEFERRED_DEPENDENCY
    assert saved.failure_progress.history[-1].dominant is FailureClassification.TEST_COLLECTION_OR_BOOTSTRAP_FAILURE
    assert saved.failure_progress.dependency_decisions[-1].disposition is DependencyDisposition.ALREADY_PLANNED


@pytest.mark.asyncio
async def test_green_generic_candidate_failure_routes_as_developer_candidate_defect_and_recovers():
    step = proposal()
    repo = MemoryStateRepo()
    gateway = FakeExecutionGateway({
        step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
        step.step_id + "--green": [
            rejected(step.step_id + "--green", error="acceptance failed"),
            accepted(step.step_id + "--green", "c" * 40),
        ],
    })
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []},
            review_approved(step.step_id, "c" * 40),
            {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": ["RB-1"]},
        ]),
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(single_requirement_contract())

    retry_snapshot = next(item for item in saved_runs(repo, single_requirement_contract().id) if item.failure_progress.state is FailureRouteState.AWAITING_REPAIR)
    packet = retry_snapshot.failure_progress.repair_packets[-1]
    assert result.current_pool == "completed"
    assert retry_snapshot.failure_progress.history[-1].dominant is FailureClassification.DEVELOPER_CANDIDATE_DEFECT
    assert retry_snapshot.failure_progress.history[-1].action is ProgressionAction.REPAIR_DEVELOPER
    assert packet.role == "Developer"
    assert packet.trusted_revision == "b" * 40
    assert gateway.calls[1][:2] == (step.step_id + "--green", "b" * 40)
    assert gateway.calls[2][:2] == (step.step_id + "--green", "b" * 40)
    assert repo.snapshot.contract_runs[single_requirement_contract().id].failure_progress.retry_counts == {RetryRoute.DEVELOPER_REPAIR.value: 1}


@pytest.mark.asyncio
async def test_environment_recovery_success_reruns_from_trusted_revision():
    contract_state = single_requirement_contract()
    step = proposal()
    repo = MemoryStateRepo()
    gateway = FakeExecutionGateway({
        step.step_id + "--red": [
            rejected(step.step_id + "--red", error="pytest is unavailable in dependency environment"),
            accepted(step.step_id + "--red", "b" * 40),
        ],
        step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
    })
    recovery = FakeEnvironmentRecovery([True])
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []},
            review_approved(step.step_id, "c" * 40),
            {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
        ]),
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
        environment_recovery=recovery,
    ).run_contract(contract_state)

    assert recovery.calls == ["reservation-book"]
    assert [call[0] for call in gateway.calls[:2]] == [step.step_id + "--red", step.step_id + "--red"]
    assert [call[1] for call in gateway.calls[:2]] == ["a" * 40, "a" * 40]
    assert any(item.failure_progress.retry_counts.get(RetryRoute.ENVIRONMENT_RECOVERY.value) == 1 for item in saved_runs(repo, contract_state.id))
    assert result.current_pool == "completed"


@pytest.mark.asyncio
async def test_environment_recovery_exhaustion_blocks_environment_truthfully():
    step = proposal()
    repo = MemoryStateRepo()
    recovery = FakeEnvironmentRecovery([False])
    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({step.step_id + "--red": rejected(step.step_id + "--red", error="pytest is unavailable in dependency environment")}),
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []}
        ]),
        repository_binding=binding(),
        state_repo=repo,
        environment_recovery=recovery,
    ).run_contract(contract())

    saved = repo.snapshot.contract_runs[contract().id]
    assert result.current_pool == "blocked_environment"
    assert saved.semantic_base_revision == "a" * 40
    assert saved.failure_progress.state is FailureRouteState.BLOCKED_ENVIRONMENT
    assert saved.failure_progress.history[-1].dominant is FailureClassification.ENVIRONMENT_FAILURE
    assert saved.failure_progress.retry_counts == {}
    assert saved.failure_progress.repair_packets == []
    assert recovery.calls == ["reservation-book"]


@pytest.mark.asyncio
async def test_executor_failure_stops_safely_in_blocked_executor_pool():
    step = proposal()
    repo = MemoryStateRepo()
    gateway = FakeExecutionGateway({step.step_id + "--red": rejected(step.step_id + "--red", error="worker offline", status="transport_error")})
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []}
        ]),
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(contract())

    saved = repo.snapshot.contract_runs[contract().id]
    assert result.current_pool == "blocked_executor"
    assert saved.semantic_base_revision == "a" * 40
    assert saved.failure_progress.state is FailureRouteState.BLOCKED_EXECUTOR
    assert saved.failure_progress.history[-1].dominant is FailureClassification.EXECUTOR_INFRASTRUCTURE_FAILURE
    assert saved.failure_progress.retry_counts == {}
    assert saved.failure_progress.repair_packets == []
    assert gateway.calls[0][:2] == (step.step_id + "--red", "a" * 40)


@pytest.mark.asyncio
async def test_transport_timeout_exception_blocks_executor_without_advancing_trusted_revision():
    step = proposal()
    repo = MemoryStateRepo()

    class TransportTimeoutGateway:
        def __init__(self):
            self.calls = []

        async def execute(self, work_unit, repository_binding):
            self.calls.append((work_unit.id, repository_binding.base_sha))
            raise RackAiCliTransportError(
                "Rack AI CLI subprocess exceeded ATHBA transport deadline of 1s for request timeout 1s"
            )

    gateway = TransportTimeoutGateway()
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []}
        ]),
        repository_binding=binding(),
        state_repo=repo,
    ).run_contract(contract())

    saved = repo.snapshot.contract_runs[contract().id]
    assert result.current_pool == "blocked_executor"
    assert result.semantic_revision == "a" * 40
    assert saved.semantic_base_revision == "a" * 40
    assert saved.failure_progress.state is FailureRouteState.BLOCKED_EXECUTOR
    assert saved.failure_progress.history[-1].dominant is FailureClassification.EXECUTOR_INFRASTRUCTURE_FAILURE
    assert gateway.calls == [(step.step_id + "--red", "a" * 40)]


@pytest.mark.asyncio
async def test_review_repair_uses_review_state_and_preserves_runtime_flow():
    contract_state = single_requirement_contract()
    step = proposal()
    repo = MemoryStateRepo()
    await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({
            step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
            step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
            step.step_id + "--repair-1": accepted(step.step_id + "--repair-1", "d" * 40),
        }),
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []},
            review_repair(step.step_id, "c" * 40),
            review_approved(step.step_id, "d" * 40),
            {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
        ]),
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    repair_ready = next(item for item in saved_runs(repo, contract_state.id) if item.current_pool == "repair_ready")
    assert repair_ready.failure_progress.history == []
    assert repair_ready.failure_progress.retry_counts == {}
    assert repair_ready.current_pool == "repair_ready"
    assert repair_ready.current_cycle().review_result is not None
    assert repair_ready.current_cycle().review_result.verdict == "repair_required"


@pytest.mark.asyncio
async def test_semantic_replan_uses_review_result_and_replan_pool():
    contract_state = single_requirement_contract()
    step = proposal()
    repo = MemoryStateRepo()
    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({
            step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
            step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
        }),
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []},
            review_replan(step.step_id, "c" * 40),
        ]),
        repository_binding=binding(),
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    saved = repo.snapshot.contract_runs[contract_state.id]
    assert result.current_pool == "replan_ready"
    assert saved.failure_progress.history == []
    assert saved.current_cycle().review_result is not None
    assert saved.current_cycle().review_result.verdict == "replan_required"


@pytest.mark.asyncio
async def test_expected_red_success_path_does_not_create_failure_progression_entry():
    contract_state = single_requirement_contract()
    step = proposal()
    result = await BehaviorContractCoordinator(
        execution_gateway=FakeExecutionGateway({
            step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
            step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
        }),
        reasoning_gateway=FakeReasoningGateway([
            {"status": "propose", "rationale": "Start with RB-1.", "proposal": step.to_dict(), "completed_requirement_refs": []},
            review_approved(step.step_id, "c" * 40),
            {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []},
        ]),
        repository_binding=binding(),
        state_repo=MemoryStateRepo(),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert result.current_pool == "completed"
    assert result.blocked_reason is None


@pytest.mark.asyncio
async def test_resume_tester_repair_retry_preserves_transition_and_trusted_base():
    contract_state = single_requirement_contract()
    step = proposal()
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="a" * 40),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=step.step_id + "--red", status="checks_failed"),
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("a" * 40),
        current_trusted_revision="a" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="cycle_active",
                cycles=[cycle],
                contract_state=contract_state,
                failure_progress=repair_progress(FailureClassification.TESTER_CANDIDATE_DEFECT, RetryRoute.TESTER_REPAIR, "Tester"),
                blocked_reason="tester_candidate_defect: retrying Tester from trusted revision",
            )
        },
    )
    gateway = FakeExecutionGateway({
        step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
        step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
    })
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([review_approved(step.step_id, "c" * 40), {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []}]),
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert gateway.calls[0][:2] == (step.step_id + "--red", "a" * 40)
    assert result.current_pool == "completed"


@pytest.mark.asyncio
async def test_resume_developer_repair_retry_preserves_transition_and_red_base():
    contract_state = single_requirement_contract()
    step = proposal()
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="a" * 40),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=step.step_id + "--red", status="checks_passed", accepted_revision="b" * 40),
        green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id=step.step_id + "--green", status="checks_failed"),
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("a" * 40),
        current_trusted_revision="a" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="cycle_active",
                cycles=[cycle],
                contract_state=contract_state,
                failure_progress=repair_progress(FailureClassification.DEVELOPER_CANDIDATE_DEFECT, RetryRoute.DEVELOPER_REPAIR, "Developer"),
                blocked_reason="developer_candidate_defect: retrying Developer from trusted revision",
            )
        },
    )
    gateway = FakeExecutionGateway({step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40)})
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([review_approved(step.step_id, "c" * 40), {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []}]),
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert gateway.calls[0][:2] == (step.step_id + "--green", "b" * 40)
    assert result.current_pool == "completed"


@pytest.mark.asyncio
async def test_resume_environment_recovery_success_reruns_without_resetting_count():
    contract_state = single_requirement_contract()
    step = proposal()
    cycle = replace(
        ContractCycleRecord.from_step(step, base_revision="a" * 40),
        red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=step.step_id + "--red", status="checks_failed", error="pytest is unavailable in dependency environment"),
    )
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("a" * 40),
        current_trusted_revision="a" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="cycle_active",
                cycles=[cycle],
                contract_state=contract_state,
                failure_progress=FailureProgressState(retry_counts={RetryRoute.ENVIRONMENT_RECOVERY.value: 1}),
                blocked_reason="environment recovered; rerunning from trusted revision",
            )
        },
    )
    gateway = FakeExecutionGateway({
        step.step_id + "--red": accepted(step.step_id + "--red", "b" * 40),
        step.step_id + "--green": accepted(step.step_id + "--green", "c" * 40),
    })
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([review_approved(step.step_id, "c" * 40), {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []}]),
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract_state)

    assert gateway.calls[0][:2] == (step.step_id + "--red", "a" * 40)
    assert result.current_pool == "completed"


@pytest.mark.asyncio
async def test_resume_blocked_environment_is_terminal_and_does_not_execute():
    contract_state = single_requirement_contract()
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("a" * 40),
        current_trusted_revision="a" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="blocked_environment",
                contract_state=contract_state,
                failure_progress=FailureProgressState(
                    state=FailureRouteState.BLOCKED_ENVIRONMENT,
                    history=[failure_decision(FailureClassification.ENVIRONMENT_FAILURE)],
                    retry_counts={RetryRoute.ENVIRONMENT_RECOVERY.value: 1},
                    blocker="environment_failure: pytest is unavailable",
                ),
                blocked_reason="environment_failure: pytest is unavailable",
            )
        },
    )
    gateway = FakeExecutionGateway({})
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([]),
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
    ).run_contract(contract_state)

    assert result.current_pool == "blocked_environment"
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_resume_blocked_executor_is_terminal_and_does_not_execute():
    contract_state = single_requirement_contract()
    snapshot = TddSnapshot(
        project_id="reservation-book",
        repository_binding=binding("a" * 40),
        current_trusted_revision="a" * 40,
        contract_runs={
            contract_state.id: run_state(
                current_pool="blocked_executor",
                contract_state=contract_state,
                failure_progress=FailureProgressState(
                    state=FailureRouteState.BLOCKED_EXECUTOR,
                    history=[failure_decision(FailureClassification.EXECUTOR_INFRASTRUCTURE_FAILURE)],
                    blocker="executor_infrastructure_failure: worker offline",
                ),
                blocked_reason="executor_infrastructure_failure: worker offline",
            )
        },
    )
    gateway = FakeExecutionGateway({})
    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=FakeReasoningGateway([]),
        repository_binding=binding(),
        state_repo=MemoryStateRepo(snapshot),
    ).run_contract(contract_state)

    assert result.current_pool == "blocked_executor"
    assert gateway.calls == []
