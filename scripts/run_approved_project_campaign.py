"""Preflight an explicitly test-scoped approved project; live BDE remains blocked."""
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
from core.project_setup.service import SHARED_BDE_BLOCKER

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
    parser.add_argument("--prepare", action="store_true", help="Prepare only the approved scaffold/environment.")
    parser.add_argument("--enable-live", action="store_true",
                        help="Request the normal handoff; currently reports the frozen BDE capability blocker.")
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
        "bde_handoff_reason": SHARED_BDE_BLOCKER,
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
        if arguments.enable_live:
            report["status"] = "bde_handoff_blocked"
            exit_code = EXIT_BLOCKED
            if setup is None or setup.status != SetupStatus.READY:
                report["reason"] = "Approved setup is not ready; the frozen shared-project BDE handoff is unsupported."
            else:
                first = handoff.decision.behaviors[0]
                delivery = await composition.deliveries.dispatch(DeliveryRequest(handoff, first.id))
                report["delivery"] = asdict(delivery)
                report["reason"] = delivery.reason
                report["remaining_deliveries"] = "not_dispatched_after_first_blocker"
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
