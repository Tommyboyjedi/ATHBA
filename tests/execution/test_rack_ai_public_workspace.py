from __future__ import annotations

from copy import deepcopy
import subprocess
from pathlib import Path

import pytest

from core.development.athba_workspace_routing import (
    AthbaExecutionProfile,
    AthbaOutboundPriority,
    AthbaWorkspaceIdentity,
    GenericModelCapability,
    WorkspaceComplexity,
)
from core.development.strict_tdd_run_domain import StrictTddRunState, StrictTddRunStatus
from core.development.strict_tdd_run_store import StrictTddRunStateRepository
from core.execution import rack_ai_public_workspace as public_workspace
from core.execution.rack_ai_public_workspace import (
    RackAiPublicWorkEvidenceStore,
    RackAiPublicWorkspaceExecutionPort,
)
from core.execution.rack_ai_request import RepositoryBinding
from core.execution.rack_ai_reservation import RackAiReservation
from core.execution.rack_ai_reservation_state import ReservationBinding
from core.execution.rack_ai_runtime import RackAiResourceWait, RackAiRuntimeConfiguration, RackAiRuntimeError
from core.execution.workspace_execution_port import WorkspaceExecutionRequest, WorkspaceExecutionStatus


class StepClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class PublicRuntime:
    def __init__(self, tmp_path: Path):
        token = tmp_path / "credential"
        token.write_text("fixture-token")
        self.configuration = RackAiRuntimeConfiguration(
            "http://127.0.0.1:8095",
            token,
            poll_seconds=0.001,
            resource_wait_seconds=0.004,
        )
        self.calls: list[dict[str, object]] = []
        self.work: dict[str, list[dict[str, object]]] = {}
        self.pending_work: dict[str, list[dict[str, object]]] = {}
        self.artifacts: dict[str, dict[str, object]] = {}
        self.submit_errors: list[RackAiRuntimeError] = []

    def operation(self, payload):
        self.calls.append(deepcopy(payload))
        op = payload["operation"]
        if op == "discover":
            return {
                "work_execution_contract": {
                    "version": "1.4.0",
                    "operations": ["inspect_work_execution", "get_work_artifact"],
                    "artifact_authorization": "owner_checked_opaque_id",
                }
            }
        if op == "reserve":
            request = payload["request"]
            return _reservation_view("R1", request["services"])
        if op == "inspect_reservation":
            return _reservation_view(payload["reservation_id"], ("local-primary", "local-coder"))
        if op == "submit_work":
            work_id = payload["request"]["work_id"]
            if work_id in self.pending_work and work_id not in self.work:
                self.work[work_id] = self.pending_work.pop(work_id)
            if self.submit_errors:
                raise self.submit_errors.pop(0)
            return {
                "work_id": work_id,
                "reservation_id": payload["request"]["reservation_id"],
                "service": payload["request"]["service"],
                "state": "queued",
                "invocation_id": "receipt-invocation",
            }
        if op == "inspect_work_execution":
            snapshots = self.work.get(payload["work_id"], [])
            if not snapshots:
                raise RackAiRuntimeError("not_found", 404)
            if len(snapshots) > 1:
                return deepcopy(snapshots.pop(0))
            return deepcopy(snapshots[0])
        if op == "get_work_artifact":
            try:
                return deepcopy(self.artifacts[payload["artifact_id"]])
            except KeyError as error:
                raise RackAiRuntimeError("not_found", 404) from error
        if op == "cancel_work":
            return {"cancelled": True}
        raise AssertionError(op)


def _reservation_view(identity: str, services):
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


def _git_repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "running_total.py").write_text("class RunningTotal:\n    pass\n")
    subprocess.run(["git", "add", "running_total.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root, check=True)
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
    return root, revision


def _request(root: Path, revision: str, *, capabilities=frozenset({GenericModelCapability.CODING})):
    return WorkspaceExecutionRequest(
        AthbaWorkspaceIdentity("work", "submission", "attempt"),
        AthbaExecutionProfile(capabilities, WorkspaceComplexity.SMALL, False, AthbaOutboundPriority.LOW, 300),
        RepositoryBinding("repo", "main", revision, registered_root=str(root)),
        ("running_total.py",),
        "disabled",
        (("python", "-m", "pytest"),),
        ("running_total.py",),
        "bounded objective",
    )


def _port(
    tmp_path: Path,
    runtime: PublicRuntime,
    *,
    clock: StepClock | None = None,
) -> RackAiPublicWorkspaceExecutionPort:
    store = StrictTddRunStateRepository(tmp_path / "runs")
    store.save(StrictTddRunState("run", "project", "identity", StrictTddRunStatus.READY))
    reservation = RackAiReservation(runtime, ("local-primary", "local-coder"))
    reservation.bind(ReservationBinding(store, "run"))
    return RackAiPublicWorkspaceExecutionPort(
        runtime,
        reservation,
        RackAiPublicWorkEvidenceStore(tmp_path / "evidence"),
        clock=clock or public_workspace.RackAiPublicWorkspaceClock(),
    )


def _snapshot(work_id: str, revision: str | None, *, known=True, category="accepted", failure_category=None,
              active=False, safe=True, replay="closed_inspection_only", historical_state="completed",
              reservation_id="R1", service="local-coder", artifact_id=None, artifact_bytes=0):
    workspace = {
        "status": category,
        "acceptance_verdict": "passed" if revision else None,
        "accepted_revision": revision,
        "changed_paths": ["running_total.py"] if revision else [],
        "commands": [],
        "last_error": None if revision else failure_category,
        "evidence_status": "available",
    }
    if artifact_id:
        workspace["commands"] = [{
            "index": 0,
            "argv": ["python", "-m", "pytest"],
            "exit_code": 0 if revision else None,
            "timed_out": False,
            "succeeded": bool(revision),
            "outcome": "passed" if revision else "failed",
            "started": 1,
            "completed": 2,
            "duration_seconds": 1,
            "stdout": {"available": True, "bytes": artifact_bytes, "artifact_id": artifact_id, "truncated": False},
            "stderr": {"available": False, "bytes": 0, "artifact_id": None, "truncated": False},
        }]
    return {
        "schema": "rack-ai/work-execution/v1",
        "contract_version": "1.4.0",
        "work": {
            "work_id": work_id,
            "reservation_id": reservation_id,
            "service": service,
            "invocation_id": "I1",
            "state": historical_state,
            "archived": False,
            "created": 1,
            "started": 1,
            "completed": None if active else 2,
        },
        "outcome": {
            "kind": "workspace",
            "terminal": not active,
            "outcome_known": known,
            "category": category,
            "failure_category": failure_category,
            "error": failure_category,
            "workspace": workspace,
            "model_usage": {"available": False, "prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "finish_reason": None},
            "attempt": {
                "known": known,
                "status": category,
                "category": category,
                "failure_category": failure_category,
                "execution_budget_seconds": 300,
                "deadline_ended_attempt": failure_category,
            },
            "historical_invocation": {
                "state": historical_state,
                "terminal": historical_state not in {"queued", "running"},
                "outcome_known": known,
                "uncertainty_reason": "backend_timeout" if historical_state == "uncertain" else None,
            },
        },
        "closure": {
            "execution_active": active,
            "cleanup_state": "closed" if safe else "pending",
            "original_outcome_known": known,
            "safe_closure_known": safe,
            "replay_safety": replay,
            "blocker": None if safe else "cleanup_pending",
            "retry_after_seconds": 0 if not safe else None,
        },
        "activity": {
            "activity_id": "A1",
            "sequence": 1,
            "current": "closed" if safe else "running",
            "last_observed_at": 2,
            "terminal_reason": failure_category,
            "counts": {name: {"value": None, "availability": "unavailable"} for name in ["model_calls", "scoped_children", "unresolved_scoped_children", "command_errors", "tool_calls"]},
            "timings": {name: {"value": None, "availability": "unavailable"} for name in ["queue_seconds", "setup_seconds", "agent_seconds", "acceptance_seconds"]},
            "budget": {"execution_seconds": {"value": 300, "availability": "recorded"}, "deadline_ended_attempt": failure_category},
            "events": [],
        },
        "artifacts": [],
        "build": {"runtime_schema": "rack-ai/runtime/v1", "contract_version": "1.4.0", "owner": "athba"},
    }


def _work_id(port: RackAiPublicWorkspaceExecutionPort, submission="submission") -> str:
    return port.reservation.workspace_execution_identity(submission)


def test_successful_public_workspace_result_reaches_validation_and_uses_public_payload(tmp_path):
    root, revision = _git_repo(tmp_path)
    runtime = PublicRuntime(tmp_path)
    port = _port(tmp_path, runtime)
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [_snapshot(work_id, revision)]

    result = port.submit_workspace_change(_request(root, revision))

    assert result.status is WorkspaceExecutionStatus.ACCEPTED
    assert result.accepted_revision == revision
    submit = [call for call in runtime.calls if call["operation"] == "submit_work"][0]
    workspace = submit["request"]["payload"]["workspace"]
    assert workspace["requirements"] == {"complexity": "small", "requires_large_context": False}
    assert "context_window" not in workspace["requirements"]
    assert "max_input_tokens" not in workspace["requirements"]
    assert "max_output_tokens" not in workspace["requirements"]
    assert workspace["repository"]["registered_root"] == str(root)
    assert "root" not in workspace["repository"]
    assert submit["request"]["service"] == "local-coder"


def test_dynamic_athba_project_repository_is_submitted_as_root(tmp_path, monkeypatch):
    root, revision = _git_repo(tmp_path)
    monkeypatch.setattr(public_workspace, "ATHBA_DYNAMIC_PROJECTS_ROOT", str(tmp_path))
    runtime = PublicRuntime(tmp_path)
    port = _port(tmp_path, runtime)
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [_snapshot(work_id, revision)]

    result = port.submit_workspace_change(_request(root, revision))

    assert result.status is WorkspaceExecutionStatus.ACCEPTED
    submit = [call for call in runtime.calls if call["operation"] == "submit_work"][0]
    repository = submit["request"]["payload"]["workspace"]["repository"]
    assert repository["root"] == str(root)
    assert "registered_root" not in repository
    assert repository["id"] == "repo"
    assert repository["base_ref"] == "main"
    assert repository["base_sha"] == revision


def test_reasoning_and_coding_profile_selects_primary_service(tmp_path):
    root, revision = _git_repo(tmp_path)
    runtime = PublicRuntime(tmp_path)
    port = _port(tmp_path, runtime)
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [_snapshot(work_id, revision, service="local-primary")]

    result = port.submit_workspace_change(_request(root, revision, capabilities=frozenset({GenericModelCapability.REASONING, GenericModelCapability.CODING})))

    assert result.accepted_revision == revision
    submit = [call for call in runtime.calls if call["operation"] == "submit_work"][0]
    assert submit["request"]["service"] == "local-primary"


def test_known_timeout_with_no_candidate_counts_once_after_safe_closure(tmp_path):
    root, revision = _git_repo(tmp_path)
    runtime = PublicRuntime(tmp_path)
    port = _port(tmp_path, runtime)
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [_snapshot(work_id, None, category="failed", failure_category="execution_timeout", historical_state="uncertain")]

    result = port.submit_workspace_change(_request(root, revision))

    assert result.status is WorkspaceExecutionStatus.TIMEOUT
    assert result.accepted_revision is None
    assert "execution_timeout" in result.error


def test_known_timeout_waits_until_public_safe_closure(tmp_path):
    root, revision = _git_repo(tmp_path)
    runtime = PublicRuntime(tmp_path)
    clock = StepClock()
    port = _port(tmp_path, runtime, clock=clock)
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [
        _snapshot(work_id, None, category="failed", failure_category="execution_timeout", historical_state="uncertain", safe=False),
        _snapshot(work_id, None, category="failed", failure_category="execution_timeout", historical_state="uncertain", safe=True),
    ]

    result = port.submit_workspace_change(_request(root, revision))

    assert result.status is WorkspaceExecutionStatus.TIMEOUT
    assert clock.sleeps
    assert len([call for call in runtime.calls if call["operation"] == "inspect_work_execution"]) >= 3


def test_known_timeout_with_never_safe_closure_remains_resource_wait(tmp_path):
    root, revision = _git_repo(tmp_path)
    runtime = PublicRuntime(tmp_path)
    clock = StepClock()
    port = _port(tmp_path, runtime, clock=clock)
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [_snapshot(work_id, None, category="failed", failure_category="execution_timeout", safe=False)]

    with pytest.raises(RackAiResourceWait, match="closure is not yet safe|resource wait bound"):
        port.submit_workspace_change(_request(root, revision))
    assert clock.sleeps
    assert len([call for call in runtime.calls if call["operation"] == "submit_work"]) == 1


def test_unknown_replay_safety_fails_closed(tmp_path):
    root, revision = _git_repo(tmp_path)
    runtime = PublicRuntime(tmp_path)
    port = _port(tmp_path, runtime)
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [_snapshot(work_id, revision, replay="safe_to_replay")]

    result = port.submit_workspace_change(_request(root, revision))

    assert result.status is WorkspaceExecutionStatus.MALFORMED_RESULT
    assert "replay_safety_unknown" in result.error


def test_lost_submit_response_reconciles_original_work_without_duplicate(tmp_path):
    root, revision = _git_repo(tmp_path)
    runtime = PublicRuntime(tmp_path)
    runtime.submit_errors.append(RackAiRuntimeError("runtime_transport_uncertain"))
    port = _port(tmp_path, runtime)
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [_snapshot(work_id, revision)]

    result = port.submit_workspace_change(_request(root, revision))

    assert result.status is WorkspaceExecutionStatus.ACCEPTED
    assert len([call for call in runtime.calls if call["operation"] == "submit_work"]) == 1
    again = port.submit_workspace_change(_request(root, revision))
    assert again.status is WorkspaceExecutionStatus.ACCEPTED
    assert len([call for call in runtime.calls if call["operation"] == "submit_work"]) == 1


def test_unknown_outcome_and_identity_conflict_fail_safely(tmp_path):
    root, revision = _git_repo(tmp_path)
    runtime = PublicRuntime(tmp_path)
    port = _port(tmp_path, runtime)
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [_snapshot(work_id, None, known=False, category="unknown")]

    unknown = port.submit_workspace_change(_request(root, revision))
    assert unknown.status is WorkspaceExecutionStatus.MALFORMED_RESULT
    assert "unknown" in unknown.error

    other = PublicRuntime(tmp_path)
    other_port = _port(tmp_path / "other", other)
    other_work_id = _work_id(other_port)
    other.work[other_work_id] = [_snapshot(other_work_id, revision, reservation_id="different")]
    conflict = other_port.submit_workspace_change(_request(root, revision))
    assert conflict.status is WorkspaceExecutionStatus.MALFORMED_RESULT
    assert "reservation_id" in conflict.error


def test_transport_timeout_is_external_blocker_not_model_failure(tmp_path):
    root, revision = _git_repo(tmp_path)
    runtime = PublicRuntime(tmp_path)
    port = _port(tmp_path, runtime)
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [_snapshot(work_id, None, category="failed", failure_category="transport_timeout")]

    result = port.submit_workspace_change(_request(root, revision))

    assert result.status is WorkspaceExecutionStatus.BACKEND_UNAVAILABLE
    assert not result.is_model_originated()


def test_artifact_retrieval_uses_api_and_validates_identity(tmp_path):
    root, revision = _git_repo(tmp_path)
    runtime = PublicRuntime(tmp_path)
    port = _port(tmp_path, runtime)
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [_snapshot(work_id, revision, artifact_id="artifact-1", artifact_bytes=4)]
    runtime.artifacts["artifact-1"] = {
        "schema": "rack-ai/work-artifact/v1",
        "artifact_id": "artifact-1",
        "invocation_id": "I1",
        "kind": "stdout",
        "index": 0,
        "content_type": "text/plain; charset=utf-8",
        "text": "pass",
        "bytes": 4,
        "truncated": False,
    }

    result = port.submit_workspace_change(_request(root, revision))

    assert result.status is WorkspaceExecutionStatus.ACCEPTED
    assert [call["operation"] for call in runtime.calls].count("get_work_artifact") == 1
    assert any("artifact" in ref for ref in result.evidence_refs)


def test_artifact_identity_mismatch_is_structured_integration_failure(tmp_path):
    root, revision = _git_repo(tmp_path)
    runtime = PublicRuntime(tmp_path)
    port = _port(tmp_path, runtime)
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [_snapshot(work_id, revision, artifact_id="artifact-1", artifact_bytes=4)]
    runtime.artifacts["artifact-1"] = {
        "schema": "rack-ai/work-artifact/v1",
        "artifact_id": "artifact-1",
        "invocation_id": "different",
        "kind": "stdout",
        "index": 0,
        "content_type": "text/plain; charset=utf-8",
        "text": "pass",
        "bytes": 4,
        "truncated": False,
    }

    result = port.submit_workspace_change(_request(root, revision))

    assert result.status is WorkspaceExecutionStatus.MALFORMED_RESULT
    assert "artifact identity" in result.error


def test_accepted_revision_validation_refuses_rackai_owned_root_without_shelling_into_it(tmp_path, monkeypatch):
    root, revision = _git_repo(tmp_path)
    runtime = PublicRuntime(tmp_path)
    port = _port(tmp_path, runtime)
    request = _request(root, revision)
    request = WorkspaceExecutionRequest(
        request.identity,
        request.profile,
        RepositoryBinding("repo", "main", revision, registered_root="/srv/rack-ai/private"),
        request.allowed_writable_paths,
        request.network_policy,
        request.acceptance_commands,
        request.required_artifacts,
        request.objective,
    )
    work_id = _work_id(port)
    runtime.pending_work[work_id] = [_snapshot(work_id, revision)]
    calls = []

    def guarded_run(args, **kwargs):
        calls.append(args)
        raise AssertionError("should not shell into RackAI root")

    monkeypatch.setattr("core.execution.rack_ai_public_workspace.subprocess.run", guarded_run)

    result = port.submit_workspace_change(request)

    assert result.status is WorkspaceExecutionStatus.MALFORMED_RESULT
    assert "RackAI-owned" in result.error
    assert calls == []
