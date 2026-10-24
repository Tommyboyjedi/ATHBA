"""Preflight approved project setup; explicitly opt in to standard branch delivery."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import traceback

from bson import ObjectId

from core.atomic_json_file import write_json_atomically
from core.project_setup.architecture import PinnedArchitectureApproval, content_hash
from core.project_setup.composition import ProjectSetupCompositionRequest, compose_project_setup
from core.project_setup.delivery import DeliveryRequest
from core.project_setup.fixture import FixtureBinding, load_test_architecture
from core.project_setup.records import SetupStatus
from core.delivery_management.domain import DeliveryPhase

BACKEND_LOOKUP_TIMEOUT_SECONDS = 10.0
REPORT_SCHEMA = "athba/approved-project-campaign/v1"
FIXTURE_DIRECTORY = Path(__file__).resolve().parents[1] / "tests/fixtures/project_setup"
EXIT_READY = 0
EXIT_FAILED = 1
EXIT_BLOCKED = 2


@dataclass(frozen=True)
class CampaignArguments:
    project_id: str
    state_root: Path
    evidence_root: Path
    prepare: bool = False
    enable_live: bool = False


def _arguments() -> CampaignArguments:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-fixture", action="store_true", required=True,
                        help="Explicitly authorize the labelled test fixture for this existing test project.")
    parser.add_argument("--project-id", required=True, help="Existing Mongo-backed ATHBA test project ID.")
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true", help="Prepare the approved environment and dependency-ready behavior branches; no models.")
    parser.add_argument("--enable-live", action="store_true",
                        help="Explicitly dispatch dependency-ready behavior branches through standard BDE; never integrate main.")
    values = parser.parse_args()
    return CampaignArguments(values.project_id, values.state_root.resolve(),
                             values.evidence_root.resolve(), values.prepare, values.enable_live)


def _report_path(arguments: CampaignArguments) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return arguments.evidence_root / f"campaign-{stamp}.json"


def _error_evidence(error: Exception) -> dict[str, str]:
    text = "".join(traceback.format_exception(error))
    text = re.sub(r"mongodb(?:\+srv)?://[^\s'\"<>]+", "[REDACTED_MONGODB_URI]", text)
    for name in ("MONGO_USER", "MONGO_PASS"):
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return {"exception_type": type(error).__name__, "redacted_traceback": text}


async def _backend_lookup(project_id: str):
    from core.services.project_service import ProjectsService

    projects = ProjectsService()
    async with asyncio.timeout(BACKEND_LOOKUP_TIMEOUT_SECONDS):
        project = await projects.get_project_by_id(project_id)
        specification = await projects.get_latest_spec(project_id) if project is not None else None
    return projects, project, specification


async def execute(arguments: CampaignArguments) -> int:
    report_file = _report_path(arguments)
    report: dict[str, object] = {
        "schema": REPORT_SCHEMA,
        "project_id": arguments.project_id,
        "state_root": str(arguments.state_root),
        "evidence_root": str(arguments.evidence_root),
        "mode": "prepare" if arguments.prepare else "dry_run",
        "test_fixture_only": True,
        "prepare_requested": arguments.prepare,
        "live_requested": arguments.enable_live,
        "backend": {"kind": "existing_athba_mongo", "status": "not_checked"},
        "provisioning_attempted": False,
        "model_interactions": 0,
        "bde_execution_attempted": False,
        "bde_shared_handoff_supported": False,
        "bde_branch_handoff_supported": True,
        "delivery_model": "parallel_behavior_branches",
        "application_main_integration_requested": False,
        "public_linked_workspace_runtime_qualification": "not_established_by_launcher",
        "status": "preflight",
    }
    write_json_atomically(report_file, report)
    exit_code = EXIT_BLOCKED
    try:
        if not ObjectId.is_valid(arguments.project_id):
            raise ValueError("--project-id must identify an existing Mongo-backed ATHBA project")
        handoff = load_test_architecture(FixtureBinding(FIXTURE_DIRECTORY, arguments.project_id))
        approvals = PinnedArchitectureApproval(handoff.approval, arguments.project_id)
        approvals.require(handoff)
        report["approved_handoff"] = asdict(handoff)
        try:
            projects, project, specification = await _backend_lookup(arguments.project_id)
        except Exception as error:
            report["backend"] = {"kind": "existing_athba_mongo", "status": "unavailable",
                                 **_error_evidence(error)}
            report["status"] = "backend_unavailable"
            report["reason"] = "Existing project backend unavailable; no project or environment was provisioned."
            return EXIT_BLOCKED
        report["backend"] = {"kind": "existing_athba_mongo", "status": "available",
                             "project_found": project is not None}
        if project is None or str(project.id) != arguments.project_id:
            raise ValueError("the existing user-facing test project was not found")
        if (specification is None
                or specification.get("version") != handoff.decision.specification_version
                or content_hash(specification.get("content")) != handoff.decision.specification_sha256):
            raise ValueError("existing project specification version/hash differs from the frozen test fixture")
        report["specification_matched"] = True
        composition = compose_project_setup(ProjectSetupCompositionRequest(
            arguments.state_root, projects, approvals))
        setup = composition.records.load(arguments.project_id)
        if arguments.prepare:
            report["provisioning_attempted"] = True
            write_json_atomically(report_file, report)
            setup = await composition.setup.prepare(handoff)
        report["setup"] = None if setup is None else setup.to_dict()
        if arguments.prepare:
            if setup is None:
                raise ValueError("requested preparation returned no setup record")
            report["status"] = setup.status.value
            exit_code = EXIT_READY if setup.status == SetupStatus.READY else EXIT_BLOCKED
        else:
            report["status"] = "preflight_ready"
            exit_code = EXIT_READY
        requests = tuple(DeliveryRequest(handoff, item.id) for item in handoff.decision.behaviors)
        if (arguments.prepare or arguments.enable_live) and setup is not None and setup.status == SetupStatus.READY:
            prepared = []
            for request in requests:
                try:
                    branch = await composition.deliveries.prepare(request)
                    prepared.append({"behavior_id": request.behavior_id, "delivery": asdict(branch)})
                except ValueError as error:
                    prepared.append({"behavior_id": request.behavior_id, "waiting_reason": str(error)})
            report["branch_preparation"] = prepared
            if arguments.prepare and not arguments.enable_live:
                blocked = any("waiting_reason" in item for item in prepared)
                report["status"] = "branches_waiting_or_blocked" if blocked else "branches_prepared"
                exit_code = EXIT_BLOCKED if blocked else EXIT_READY
        if arguments.enable_live:
            if setup is None or setup.status != SetupStatus.READY:
                report["status"] = "setup_not_ready"
                report["reason"] = "Approved setup must be READY before explicit behavior dispatch."
                exit_code = EXIT_BLOCKED
            else:
                report["status"] = "dispatching"
                report["bde_execution_attempted"] = True
                report["model_interactions"] = None
                write_json_atomically(report_file, report)
                outcomes = await composition.deliveries.dispatch_ready(requests)
                report["deliveries"] = [asdict(item) for item in outcomes]
                phases = [item.delivery.phase if item.delivery is not None else None for item in outcomes]
                if all(phase == DeliveryPhase.COMPLETE for phase in phases):
                    report["status"] = "branches_complete_not_integrated"
                    exit_code = EXIT_READY
                elif DeliveryPhase.FAILED in phases:
                    report["status"] = "branch_failure"
                    exit_code = EXIT_FAILED
                else:
                    report["status"] = "branches_waiting_or_blocked"
                    exit_code = EXIT_BLOCKED
                report["delivery_management"] = composition.deliveries.inspect(arguments.project_id)
        return exit_code
    except Exception as error:
        report["status"] = "failed"
        report["error"] = _error_evidence(error)
        return EXIT_FAILED
    finally:
        write_json_atomically(report_file, report)
        print(json.dumps({"status": report["status"], "evidence_file": str(report_file)}))


def main() -> int:
    return asyncio.run(execute(_arguments()))


if __name__ == "__main__":
    raise SystemExit(main())
