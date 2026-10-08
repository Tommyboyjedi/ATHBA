from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.athba_workspace_routing import AthbaExecutionProfileResolver
from core.development.microcycle_domain import LanguageAdapterCatalog
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.scenario_drafting import (
    GitCandidateScenarioSourceReader,
    ScenarioDraftingDependencies,
    ScenarioDraftingService,
    ScenarioIntentReviewer,
)
from core.development.scenario_drafting_domain import (
    ScenarioDraftRequest,
    ScenarioDraftStatus,
    ScenarioRepositoryFacts,
)
from core.development.specification_domain import SourceRequirementClause
from core.development.tdd_progression import TddStepProposal
from core.execution.profiled_workspace_gateway import (
    ProfiledWorkspaceExecutionGateway,
    ProfiledWorkspaceGatewayDependencies,
)
from core.execution.rack_ai_public_workspace import (
    RackAiPublicWorkEvidenceStore,
    RackAiPublicWorkspaceExecutionPort,
)
from core.execution.rack_ai_request import RepositoryBinding
from core.execution.rack_ai_reservation import RackAiReservation
from core.execution.rack_ai_reservation_state import ReservationBinding
from core.execution.rack_ai_runtime import RackAiRuntimeConfiguration, RackAiRuntimeError
from core.execution.reasoning_gateway import ReasoningResult
from core.development.strict_tdd_run_domain import StrictTddRunState, StrictTddRunStatus
from core.development.strict_tdd_run_store import StrictTddRunStateRepository


class PublicRuntime:
    def __init__(self, tmp_path: Path) -> None:
        credential = tmp_path / "credential"
        credential.write_text("fixture-token", encoding="utf-8")
        self.configuration = RackAiRuntimeConfiguration(
            "http://127.0.0.1:8095", credential, poll_seconds=0.001, resource_wait_seconds=0.02
        )
        self.calls: list[dict[str, object]] = []
        self.work: dict[str, list[dict[str, object]]] = {}
        self.pending_work: dict[str, list[dict[str, object]]] = {}

    def operation(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(deepcopy(payload))
        operation = payload["operation"]
        if operation == "discover":
            return {
                "work_execution_contract": {
                    "version": "1.4.0",
                    "operations": ["inspect_work_execution", "get_work_artifact"],
                    "artifact_authorization": "owner_checked_opaque_id",
                }
            }
        if operation == "reserve":
            request = payload["request"]
            return _reservation_view("R1", request["services"])
        if operation == "inspect_reservation":
            return _reservation_view(str(payload["reservation_id"]), ("local-primary", "local-coder"))
        if operation == "submit_work":
            request = payload["request"]
            work_id = str(request["work_id"])
            if work_id in self.pending_work and work_id not in self.work:
                self.work[work_id] = self.pending_work.pop(work_id)
            return {
                "work_id": work_id,
                "reservation_id": request["reservation_id"],
                "service": request["service"],
                "state": "queued",
                "invocation_id": "I1",
            }
        if operation == "inspect_work_execution":
            snapshots = self.work.get(str(payload["work_id"]), [])
            if not snapshots:
                raise RackAiRuntimeError("not_found", 404)
            return deepcopy(snapshots[-1])
        raise AssertionError(operation)


class FakeReasoningGateway:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        return ReasoningResult(self.responses.pop(0), "fake", "fake")


def _reservation_view(identity: str, services) -> dict[str, object]:
    return {
        "id": identity,
        "state": "ready",
        "priority": "low",
        "requested_services": list(services),
        "services": {
            service: {
                "state": "ready",
                "model": service,
                "gateway_path": f"/scoped/{identity}/{service}/v1",
                "max_input_tokens": 8192,
                "max_output_tokens": 2048,
            }
            for service in services
        },
    }


def _repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "catalog.py").write_text("class Catalog:\n    pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "catalog.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root, check=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=root, check=True)
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
    return root, base


def _commit_candidate(root: Path, source: str, message: str) -> str:
    target = root / "tests" / "test_catalog.py"
    target.parent.mkdir(exist_ok=True)
    target.write_text(source, encoding="utf-8")
    subprocess.run(["git", "add", "tests/test_catalog.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()


def _valid_source() -> str:
    return (
        "from catalog import Catalog\n\n"
        "def test_catalog_records_item():\n"
        "    catalog = Catalog()\n"
        "    catalog.add('a')\n"
        "    assert catalog.item_id('a') == 'a'\n"
    )


def _invalid_source() -> str:
    return (
        "\"\"\"not allowed\"\"\"\n"
        "from catalog import Catalog\n\n"
        "def test_model_catalog_behavior():\n"
        "    assert Catalog\n"
    )


def _ticket() -> TddStepProposal:
    return TddStepProposal(
        "catalog-ticket",
        ["SRC-CATALOG"],
        "Adding an item makes it visible by its identifier.",
        "tests/test_catalog.py::test_catalog_records_item",
        "item_id('a') returns 'a' after adding the item.",
        "tests/test_catalog.py",
        "catalog.py",
        "obsolete immediate red objective",
        "obsolete developer objective",
        "Catalog insertion is independently observable.",
    )


def _request(scenario_id: str, base_revision: str) -> ScenarioDraftRequest:
    proposal = _ticket()
    return ScenarioDraftRequest(
        scenario_id,
        proposal,
        tuple(proposal.requirement_refs),
        "python",
        "pytest",
        proposal.test_path,
        ScenarioRepositoryFacts(
            base_revision,
            (proposal.production_path, proposal.test_path),
            "class Catalog:\n    pass\n",
            "",
        ),
        base_revision,
        (SourceRequirementClause("SRC-CATALOG", "catalog.add(name) records the item.", "behavior"),),
    )


def _approval() -> str:
    return json.dumps({
        "disposition": "approved",
        "feedback": "The scenario covers the requested observable behavior.",
        "evidence_refs": ["SRC-CATALOG"],
    })


def _snapshot(work_id: str, revision: str, changed_path: str = "tests/test_catalog.py") -> dict[str, object]:
    return {
        "schema": "rack-ai/work-execution/v1",
        "contract_version": "1.4.0",
        "work": {
            "work_id": work_id,
            "reservation_id": "R1",
            "service": "local-primary",
            "invocation_id": "I1",
            "state": "completed",
        },
        "outcome": {
            "kind": "workspace",
            "category": "accepted",
            "workspace": {
                "status": "checks_passed",
                "accepted_revision": revision,
                "changed_paths": [changed_path],
                "commands": [],
            },
            "attempt": {"known": True, "status": "accepted", "category": "accepted"},
            "historical_invocation": {"state": "completed", "terminal": True, "outcome_known": True},
        },
        "closure": {
            "execution_active": False,
            "safe_closure_known": True,
            "replay_safety": "closed_inspection_only",
        },
        "activity": {},
        "artifacts": [],
        "build": {},
    }


def _service(tmp_path: Path, runtime: PublicRuntime, root: Path, state_store, responses: list[str]):
    run_store = StrictTddRunStateRepository(tmp_path / "runs")
    run_store.save(StrictTddRunState("run", "project", "identity", StrictTddRunStatus.READY))
    reservation = RackAiReservation(runtime, ("local-primary", "local-coder"))
    reservation.bind(ReservationBinding(run_store, "run"))
    port = RackAiPublicWorkspaceExecutionPort(
        runtime,
        reservation,
        RackAiPublicWorkEvidenceStore(tmp_path / "evidence"),
    )
    gateway = ProfiledWorkspaceExecutionGateway(
        ProfiledWorkspaceGatewayDependencies(port, AthbaExecutionProfileResolver())
    )
    reasoning = FakeReasoningGateway(responses)
    service = ScenarioDraftingService(
        ScenarioDraftingDependencies(
            gateway,
            ScenarioIntentReviewer(reasoning),
            LanguageAdapterCatalog((PythonPytestAdapter(),)),
            GitCandidateScenarioSourceReader(root),
            state_store,
        )
    )
    return service, reservation, reasoning


def _work_id(reservation: RackAiReservation, scenario_id: str, attempt: int) -> str:
    submission = f"{scenario_id}--scenario-draft-{attempt}"
    return reservation.workspace_execution_identity(submission)


@pytest.mark.asyncio
async def test_branchless_public_result_reaches_scenario_review_and_resumes(tmp_path):
    root, base = _repo(tmp_path)
    revision = _commit_candidate(root, _valid_source(), "candidate")
    runtime = PublicRuntime(tmp_path)
    state_store = ScenarioDraftStateRepo(tmp_path / "scenario-state")
    scenario_id = "branchless-public-candidate"
    service, reservation, reasoning = _service(tmp_path, runtime, root, state_store, [_approval()])
    runtime.pending_work[_work_id(reservation, scenario_id, 1)] = [_snapshot(_work_id(reservation, scenario_id, 1), revision)]

    outcome = await service.draft(_request(scenario_id, base), RepositoryBinding("repo", "main", base, str(root)))

    assert outcome.approved
    attempt = outcome.state.attempts[0]
    assert attempt.candidate_revision == revision
    assert attempt.candidate_branch is None
    assert attempt.candidate_source == _valid_source()
    assert outcome.state.approved_microcycle is not None
    assert len(reasoning.requests) == 1
    assert [call["operation"] for call in runtime.calls].count("submit_work") == 1

    resumed, _reservation, _reasoning = _service(tmp_path, runtime, root, state_store, [])
    resumed_outcome = await resumed.draft(_request(scenario_id, base), RepositoryBinding("repo", "main", base, str(root)))

    assert resumed_outcome.approved
    assert resumed_outcome.submitted_attempt is False
    assert [call["operation"] for call in runtime.calls].count("submit_work") == 1


@pytest.mark.asyncio
async def test_branchless_rejected_candidate_repairs_from_persisted_commit(tmp_path):
    root, base = _repo(tmp_path)
    invalid_revision = _commit_candidate(root, _invalid_source(), "invalid candidate")
    repaired_revision = _commit_candidate(root, _valid_source(), "repaired candidate")
    runtime = PublicRuntime(tmp_path)
    state_store = ScenarioDraftStateRepo(tmp_path / "scenario-state")
    scenario_id = "branchless-public-repair"
    service, reservation, _reasoning = _service(tmp_path, runtime, root, state_store, [_approval()])
    first_work_id = _work_id(reservation, scenario_id, 1)
    second_work_id = _work_id(reservation, scenario_id, 2)
    runtime.pending_work[first_work_id] = [_snapshot(first_work_id, invalid_revision)]

    first = await service.draft(_request(scenario_id, base), RepositoryBinding("repo", "main", base, str(root)))

    first_attempt = first.state.attempts[0]
    assert first_attempt.status == "candidate_invalid"
    assert first_attempt.candidate_revision == invalid_revision
    assert first_attempt.candidate_branch is None
    assert first_attempt.candidate_source == _invalid_source()

    runtime.pending_work[second_work_id] = [_snapshot(second_work_id, repaired_revision)]
    second = await service.draft(_request(scenario_id, base), RepositoryBinding("repo", "main", base, str(root)))

    assert second.approved
    submit_calls = [call for call in runtime.calls if call["operation"] == "submit_work"]
    repair_workspace = submit_calls[1]["request"]["payload"]["workspace"]
    assert repair_workspace["repository"]["base_ref"] == invalid_revision
    assert repair_workspace["repository"]["base_sha"] == invalid_revision
    objective = json.loads(repair_workspace["objective"])
    assert objective["task"].startswith("Repair only your previous test candidate")
    assert set(objective["previous_candidate"]) == {"source"}
    assert objective["previous_candidate"]["source"] == _invalid_source()
    assert second.state.attempts[-1].candidate_revision == repaired_revision
    assert second.state.attempts[-1].candidate_branch is None
