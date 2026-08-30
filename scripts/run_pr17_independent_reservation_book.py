"""Run PR17's independent ReservationBook planning and reconciliation proof."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from core.datastore.repos.tdd_state_repo import TddStateRepo
from core.development.behavior_contract_coordinator import (
    BehaviorContractCoordinator,
    BehaviorContractPlanner,
    ContractDeveloperWorkUnitFactory,
    ContractRepairWorkUnitFactory,
    ContractTesterWorkUnitFactory,
)
from core.development.project_environment import DevelopmentProject, ProjectEnvironmentService
from core.development.python_test_runtime import PythonPytestRuntime
from core.development.specification_gatekeeper import (
    ChecklistAtomizationRequest,
    SpecificationChecklistPlanner,
    _checklist_prompt,
)
from core.development.test_evidence_reconciliation import GitAcceptedTestCatalog, TestEvidenceReconciler
from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.execution.rack_ai_cli_gateway import RackAiCliExecutionGateway
from core.execution.rack_ai_contract import RepositoryBinding, to_rack_ai_request
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest, ReasoningResult
from core.execution.work_unit_gateway import WorkUnitExecutionResult
from core.llm.providers.openai_provider import OpenAIProvider


REQUIREMENT = """Build a small in-memory `ReservationBook` for reservable resources.

A resource has a unique id and a positive integer capacity.

Clients can add resources, create uniquely identified reservations for a number of units on a resource, cancel reservations, and query remaining availability.

Reject duplicate resource ids, duplicate reservation ids, reservations for unknown resources, cancellation of unknown reservations, zero or negative quantities, and reservations exceeding remaining capacity.

Failed operations must not corrupt existing state.

Cancelling a reservation restores that capacity.

The implementation must be in-memory only, dependency-free, small, direct, readable Python 3.14, suitable for pytest, and free of unnecessary abstractions."""


@dataclass
class RecordingGateway(ReasoningGateway):
    delegate: ReasoningGateway
    exchanges: list[dict[str, object]] = field(default_factory=list)

    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        result = await self.delegate.reason(request)
        self.exchanges.append({"purpose": request.purpose, "prompt": request.prompt, "response": result.text})
        return result


@dataclass
class PersistingExecutionGateway:
    """Persist each Rack AI accepted revision through ATHBA's project lifecycle."""

    delegate: RackAiCliExecutionGateway
    environment: ProjectEnvironmentService
    project_id: str
    accepted_revisions: list[str] = field(default_factory=list)
    rack_ai_events: list[dict[str, object]] = field(default_factory=list)

    async def execute(self, work_unit: object, repository_binding: RepositoryBinding) -> WorkUnitExecutionResult:
        event: dict[str, object] = {
            "request": to_rack_ai_request(self.delegate.workload_id, repository_binding, work_unit),
        }
        self.rack_ai_events.append(event)
        try:
            result = await self.delegate.execute(work_unit, repository_binding)
        except Exception as error:
            event["transport_error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        event["result"] = asdict(result)
        if result.accepted:
            if result.accepted_revision is None:
                raise RuntimeError("Rack AI accepted execution without a trusted revision")
            self.environment.record_trusted_revision(self.project_id, result.accepted_revision)
            self.accepted_revisions.append(result.accepted_revision)
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=f"pr17-independent-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}")
    parser.add_argument("--root", type=Path, default=Path("state/pr17-independent-runs"))
    parser.add_argument("--projects-root", type=Path, default=Path("/srv/ATHBA/state/projects"))
    return parser.parse_args()


def run(command: list[str], *, cwd: Path) -> str:
    return subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True).stdout


def prepare_target(environment: ProjectEnvironmentService, project: DevelopmentProject) -> tuple[DevelopmentProject, list[str]]:
    """Add only ATHBA-owned TDD seed material to a lifecycle-created repository."""
    target = Path(project.repository_root)
    run(["git", "switch", "-c", "athba-tdd-seed"], cwd=target)
    (target / "scripts").mkdir(exist_ok=True)
    (target / "reservation_book.py").write_text("\"\"\"ReservationBook implementation is introduced through TDD.\"\"\"\n", encoding="utf-8")
    (target / "scripts" / "assert_test_fails.py").write_text(
        """import subprocess\nimport sys\n\nprobe = subprocess.run([sys.executable, '-B', '-m', 'pytest', '--version'])\nif probe.returncode != 0:\n    raise SystemExit(probe.returncode or 2)\n\ncommand = [sys.executable, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', sys.argv[1]]\nresult = subprocess.run(command)\nif result.returncode == 1:\n    raise SystemExit(0)\nraise SystemExit(result.returncode or 1)\n""",
        encoding="utf-8",
    )
    run(["git", "add", "."], cwd=target)
    run(["git", "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "-qm", "ATHBA ReservationBook TDD seed"], cwd=target)
    sha = run(["git", "rev-parse", "HEAD"], cwd=target).strip()
    run(["git", "switch", "main"], cwd=target)
    return environment.record_trusted_revision(project.project_id, sha), ["reservation_book.py", "scripts/assert_test_fails.py"]


def git_show(root: Path, revision: str, path: str) -> str:
    return run(["git", "show", f"{revision}:{path}"], cwd=root)


async def main() -> None:
    args = parse_args()
    run_root = args.root / args.run_id
    run_root.mkdir(parents=True, exist_ok=False)
    environment = ProjectEnvironmentService(args.projects_root)
    created_project = environment.create_or_load_python_project(args.run_id)
    project, source_files = prepare_target(environment, created_project)
    target = Path(project.repository_root)
    model = os.environ.get("ATHBA_REASONING_MODEL", "local-primary")
    gateway = RecordingGateway(
        ProviderReasoningGateway(OpenAIProvider(timeout=300, max_retries=1), model=model, max_tokens=4096)
    )
    project_id = args.run_id
    rack_ai_events: list[dict[str, object]] = []
    evidence: dict[str, object] = {
        "run_id": args.run_id,
        "architectural_requirement": REQUIREMENT,
        "target": {
            "project": project.to_dict(),
            "initial_sha": created_project.trusted_base_sha,
            "prepared_base_sha": project.trusted_base_sha,
            "source_files": source_files,
            "test_files": [],
            "runtime": {"python_executable": "/srv/ATHBA/.venv/bin/python", "pytest": True},
        },
        "rack_ai_modified": False,
    }
    try:
        checklist_planner = SpecificationChecklistPlanner(gateway)
        checklist = await checklist_planner.create_checklist(
            ChecklistAtomizationRequest(project_id=project_id, requirement_text=REQUIREMENT)
        )
        evidence["gatekeeper"] = {
            "prompt": _checklist_prompt(project_id=project_id, requirement_text=REQUIREMENT),
            "checklist": checklist.to_dict(),
        }

        contract_planner = BehaviorContractPlanner(gateway)
        contract = await contract_planner.create_contract(
            project_id=project_id,
            requirement_text=REQUIREMENT,
            production_paths=["reservation_book.py"],
            test_paths=["tests/test_reservation_book.py"],
        )
        evidence["behavior_contract"] = contract.to_dict()
        evidence["behavior_planner_received_checklist"] = False

        binding = project.binding()
        runtime = PythonPytestRuntime(project.runtime.environment_path)
        execution_gateway = PersistingExecutionGateway(
            RackAiCliExecutionGateway(workload_id=args.run_id), environment, project.project_id, rack_ai_events=rack_ai_events
        )
        coordinator = BehaviorContractCoordinator(
            execution_gateway=execution_gateway,
            reasoning_gateway=gateway,
            repository_binding=binding,
            state_repo=TddStateRepo(run_root / "tdd-state"),
            contract_planner=contract_planner,
            tester_factory=ContractTesterWorkUnitFactory(runtime),
            developer_factory=ContractDeveloperWorkUnitFactory(runtime),
            repair_factory=ContractRepairWorkUnitFactory(runtime),
        )
        result = await coordinator.run_contract(contract)
        state = TddStateRepo(run_root / "tdd-state").load(project_id)
        evidence["development_result"] = {
            "current_pool": result.current_pool,
            "semantic_revision": result.semantic_revision,
            "completed_requirement_refs": result.completed_requirement_refs,
            "blocked_reason": result.blocked_reason,
            "cycles": [cycle.to_dict() for cycle in result.cycles],
            "run_state": None if state is None else state.to_dict(),
            "persisted_accepted_revisions": execution_gateway.accepted_revisions,
            "project_after_development": environment.repo.load(project.project_id).to_dict(),
        }

        if result.current_pool == "completed" and state is not None and result.semantic_revision is not None:
            revision = result.semantic_revision
            final_test = git_show(target, revision, "tests/test_reservation_book.py")
            final_source = git_show(target, revision, "reservation_book.py")
            reconciler = TestEvidenceReconciler(gateway, GitAcceptedTestCatalog(target, revision))
            reconciliation = await reconciler.reconcile(checklist, state.contract_runs[contract.id])
            evidence["final_artifacts"] = {
                "semantic_revision": revision,
                "reservation_book.py": final_source,
                "tests/test_reservation_book.py": final_test,
                "accepted_test_node_ids": [cycle.step.test_name for cycle in result.cycles if cycle.semantic_revision],
            }
            evidence["checklist_reconciliation"] = [item.to_dict() for item in reconciliation]
        else:
            evidence["checklist_reconciliation"] = None
    except Exception as error:
        evidence["failure"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        evidence["reasoning_exchanges"] = gateway.exchanges
        evidence["rack_ai_events"] = rack_ai_events
        output = run_root / "evidence.json"
        output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
        print(f"EVIDENCE_FILE: {output.resolve()}")
        print(json.dumps({key: evidence.get(key) for key in ("target", "failure", "development_result")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
