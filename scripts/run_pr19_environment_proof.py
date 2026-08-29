"""Run the bounded PR19 ATHBA environment integration proof."""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from core.development.project_environment import ProjectEnvironmentService
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_cli_gateway import RackAiCliExecutionGateway
from core.execution.rack_ai_contract import to_rack_ai_request


PROJECTS_ROOT = Path("/srv/ATHBA/state/projects")
MARKER_NAME = "athba_pr19_marker.txt"
MARKER_CONTENT = "ATHBA environment integration proof\n"


def verify_accepted_revision(repository_root: Path, seed_sha: str, accepted_sha: str) -> dict[str, object]:
    """Fail closed unless Rack AI's accepted revision materializes the marker."""
    if accepted_sha == seed_sha:
        raise ValueError("accepted revision must differ from the project seed revision")
    commit = subprocess.run(
        ["git", "rev-parse", "--verify", f"{accepted_sha}^{{commit}}"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    marker = subprocess.run(
        ["git", "show", f"{accepted_sha}:{MARKER_NAME}"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if marker != MARKER_CONTENT:
        raise ValueError("accepted revision does not contain the required marker content")
    return {
        "seed_sha": seed_sha,
        "accepted_sha": accepted_sha,
        "commit_sha": commit,
        "marker_path": MARKER_NAME,
        "marker_content_matches": True,
    }


async def run() -> int:
    project_id = f"pr19-live-proof-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    service = ProjectEnvironmentService(PROJECTS_ROOT)
    project = service.create_or_load_python_project(project_id)
    unit = DevelopmentWorkUnit(
        id="create-marker",
        project_id=project.project_id,
        parent_ticket_id="pr19-environment-management",
        objective=(
            f"Create only {MARKER_NAME} in this repository. Its complete UTF-8 content must be "
            f"exactly {MARKER_CONTENT!r}. Do not modify any other file."
        ),
        allowed_paths=[MARKER_NAME],
        acceptance=AcceptanceContract(
            commands=[["python3", "-c", (
                "from pathlib import Path; "
                f"assert Path({MARKER_NAME!r}).read_text(encoding='utf-8') == {MARKER_CONTENT!r}"
            )]],
            required_artifacts=[MARKER_NAME],
        ),
        status=WorkUnitStatus.READY,
    )
    workload_id = f"pr19-environment-proof-{project_id}"
    request = to_rack_ai_request(workload_id, project.binding(), unit)
    evidence_path = PROJECTS_ROOT / project_id / "live-proof.json"
    evidence: dict[str, object] = {
        "project_before": project.to_dict(),
        "request": request,
        "started_at": datetime.now(UTC).isoformat(),
    }

    try:
        result = await RackAiCliExecutionGateway(workload_id).execute(unit, project.binding())
        evidence["execution_result"] = asdict(result)
        if not result.accepted or result.accepted_revision is None:
            evidence["outcome"] = "execution_not_accepted"
            return 1
        evidence["revision_proof"] = verify_accepted_revision(
            Path(project.repository_root), project.trusted_base_sha, result.accepted_revision)
        updated = service.record_trusted_revision(project.project_id, result.accepted_revision)
        reloaded = service.create_or_load_python_project(project.project_id)
        retired = service.retire(project.project_id, remove_workspace=True)
        evidence["project_after_acceptance"] = updated.to_dict()
        evidence["project_reloaded"] = reloaded.to_dict()
        evidence["project_retired"] = retired.to_dict()
        evidence["shared_runtime_exists"] = Path(project.runtime.environment_path).is_file()
        evidence["outcome"] = "accepted_and_retired"
        return 0
    except Exception as error:
        evidence["outcome"] = "error"
        evidence["error"] = f"{type(error).__name__}: {error}"
        return 1
    finally:
        evidence["finished_at"] = datetime.now(UTC).isoformat()
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
        print(evidence_path)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
