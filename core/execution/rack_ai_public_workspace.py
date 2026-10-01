"""Public RackAI workspace execution adapter for contract 1.4.0."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time
from typing import Any

from core.atomic_json_file import write_json_atomically
from core.development.athba_workspace_routing import (
    AthbaWorkspaceIdentity,
    GenericModelCapability,
)
from core.execution.rack_ai_reservation import RackAiReservation
from core.execution.rack_ai_runtime import RackAiResourceWait, RackAiRuntimeClient, RackAiRuntimeError
from core.execution.workspace_execution_port import (
    WorkspaceExecutionRequest,
    WorkspaceExecutionResult,
    WorkspaceExecutionStatus,
)
from core.filesystem_policy import resolve_identifier_path

PUBLIC_WORK_CONTRACT_VERSION = "1.4.0"
_REQUIRED_PUBLIC_WORK_OPERATIONS = frozenset({"inspect_work_execution", "get_work_artifact"})
ATHBA_DYNAMIC_PROJECTS_ROOT = "/srv/ATHBA/state/projects"
_ACCEPTED_REPLAY_SAFETY = frozenset({"closed_inspection_only"})


class RackAiPublicWorkspaceContractError(Exception):
    """The public RackAI work-execution contract cannot be consumed safely."""


@dataclass(frozen=True)
class RackAiPublicWorkspaceClock:
    """Clock seam for bounded public-work polling."""

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass(frozen=True)
class RackAiPublicWorkspaceServiceSelector:
    """Select a published RackAI service from ATHBA's generic workspace profile."""

    reasoning_service: str = "local-primary"
    coding_service: str = "local-coder"

    def select(self, request: WorkspaceExecutionRequest) -> str:
        capabilities = request.profile.required_capabilities
        if GenericModelCapability.REASONING in capabilities:
            return self.reasoning_service
        if GenericModelCapability.CODING in capabilities:
            return self.coding_service
        raise RackAiPublicWorkspaceContractError("workspace profile has no RackAI-compatible capability")


@dataclass(frozen=True)
class RackAiPublicWorkEvidenceRecord:
    work_id: str
    kind: str
    payload: Any


@dataclass
class RackAiPublicWorkEvidenceStore:
    """ATHBA-owned durable evidence for public RackAI work snapshots and artifacts."""

    root: Path

    def record(self, evidence: RackAiPublicWorkEvidenceRecord) -> str:
        directory = resolve_identifier_path(self.root, evidence.work_id, "RackAI work id")
        directory.mkdir(parents=True, exist_ok=True)
        index = len(tuple(directory.glob("*.json"))) + 1
        path = directory / f"{index:04d}-{_safe_kind(evidence.kind)}.json"
        write_json_atomically(path, evidence.payload)
        return str(path)


@dataclass
class RackAiPublicWorkspaceExecutionPort:
    """Execute bounded workspace work through RackAI's public work contract."""

    client: RackAiRuntimeClient
    reservation: RackAiReservation
    evidence: RackAiPublicWorkEvidenceStore
    selector: RackAiPublicWorkspaceServiceSelector = RackAiPublicWorkspaceServiceSelector()
    clock: RackAiPublicWorkspaceClock = RackAiPublicWorkspaceClock()
    _contract_verified: bool = False

    def submit_workspace_change(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        self._verify_contract()
        record = _record_or_recover_submission(
            self.reservation, self.selector, self.evidence, request, self.clock
        )
        receipt_ref = _submit_or_reconcile(self.client, self.evidence, request, record, self.clock)
        if isinstance(receipt_ref, WorkspaceExecutionResult):
            return receipt_ref
        return _wait_for_authoritative_result(
            self.client, self.reservation, self.evidence, request, record, receipt_ref, self.clock
        )

    def get_result(self, identity: AthbaWorkspaceIdentity) -> WorkspaceExecutionResult | None:
        record = self.reservation.workspace_submission(identity.submission_id)
        if record is None:
            return None
        try:
            snapshot = _inspect(self.client, str(record["work_id"]))
        except RackAiRuntimeError:
            return None
        refs = (_record_evidence(self.evidence, str(record["work_id"]), "inspection", snapshot),)
        result = _result_from_snapshot(identity, record, snapshot, refs, wait_if_pending=False)
        return result if isinstance(result, WorkspaceExecutionResult) else None

    def cancel(self, submission_id: str) -> bool:
        record = self.reservation.workspace_submission(submission_id)
        if record is None:
            return False
        try:
            self.client.operation({"operation": "cancel_work", "work_id": record["work_id"]})
        except RackAiRuntimeError as error:
            if error.code == "not_found":
                return False
            raise
        return True

    def _verify_contract(self) -> None:
        if self._contract_verified:
            return
        _verify_contract(self.client)
        self._contract_verified = True


def _record_evidence(evidence: RackAiPublicWorkEvidenceStore, work_id: str, kind: str, payload: Any) -> str:
    return evidence.record(RackAiPublicWorkEvidenceRecord(work_id, kind, payload))


def _record_phase(
    evidence: RackAiPublicWorkEvidenceStore,
    work_id: str,
    phase: str,
    request: WorkspaceExecutionRequest,
    clock: RackAiPublicWorkspaceClock,
    record: dict[str, object] | None = None,
    *,
    deadline_monotonic: float | None = None,
    elapsed_seconds: float | None = None,
    detail: str | None = None,
) -> str:
    record = record or {}
    payload: dict[str, object] = {
        "schema": "athba/rack-ai-public-work-phase/v1",
        "phase": phase,
        "monotonic": clock.monotonic(),
        "submission_id": request.identity.submission_id,
        "identity_work_id": request.identity.work_id,
        "idempotency_key": request.identity.idempotency_key,
        "work_id": work_id,
    }
    for key in ("reservation_id", "service"):
        value = record.get(key)
        if value is not None:
            payload[key] = str(value)
    if deadline_monotonic is not None:
        payload["deadline_monotonic"] = deadline_monotonic
    if elapsed_seconds is not None:
        payload["elapsed_seconds"] = elapsed_seconds
    if detail is not None:
        payload["detail"] = detail
    return _record_evidence(evidence, work_id, f"phase-{phase}", payload)


def _verify_contract(client: RackAiRuntimeClient) -> None:
    discovery = client.operation({"operation": "discover"})
    contract = discovery.get("work_execution_contract")
    if not isinstance(contract, dict):
        raise RackAiPublicWorkspaceContractError("RackAI discovery did not publish work_execution_contract")
    operations = contract.get("operations")
    if (
        contract.get("version") != PUBLIC_WORK_CONTRACT_VERSION
        or contract.get("artifact_authorization") != "owner_checked_opaque_id"
        or not isinstance(operations, list)
        or not _REQUIRED_PUBLIC_WORK_OPERATIONS.issubset({str(item) for item in operations})
    ):
        raise RackAiPublicWorkspaceContractError("RackAI public work contract 1.4.0 is unavailable")


def _record_or_recover_submission(
    reservation: RackAiReservation,
    selector: RackAiPublicWorkspaceServiceSelector,
    evidence: RackAiPublicWorkEvidenceStore,
    request: WorkspaceExecutionRequest,
    clock: RackAiPublicWorkspaceClock,
) -> dict[str, object]:
    existing = reservation.workspace_submission(request.identity.submission_id)
    if existing is not None:
        record = _validate_existing_submission(request, existing)
        _record_phase(evidence, str(record["work_id"]), "submission_record_recovered", request, clock, record)
        return record
    service = selector.select(request)
    work_id = reservation.workspace_execution_identity(request.identity.submission_id)
    _record_phase(evidence, work_id, "reservation_ready_enter", request, clock, {
        "work_id": work_id,
        "service": service,
    })
    member = reservation.ready(service)
    reservation_id = str(member["reservation_id"])
    payload = _submit_payload(request, reservation_id, service, work_id)
    record = {
        "submission_id": request.identity.submission_id,
        "identity_work_id": request.identity.work_id,
        "idempotency_key": request.identity.idempotency_key,
        "work_id": work_id,
        "reservation_id": reservation_id,
        "service": service,
        "repository_root": request.repository.registered_root,
        "request_digest": _digest(payload),
        "contract_version": PUBLIC_WORK_CONTRACT_VERSION,
    }
    _record_phase(evidence, work_id, "reservation_ready_exit", request, clock, record)
    reservation.record_workspace_submission(request.identity.submission_id, record)
    reservation.mark_workspace(request.identity.submission_id)
    _record_phase(evidence, work_id, "submission_record_recorded", request, clock, record)
    return record


def _submit_or_reconcile(
    client: RackAiRuntimeClient,
    evidence: RackAiPublicWorkEvidenceStore,
    request: WorkspaceExecutionRequest,
    record: dict[str, object],
    clock: RackAiPublicWorkspaceClock,
) -> str | WorkspaceExecutionResult | None:
    work_id = str(record["work_id"])
    _record_phase(evidence, work_id, "submission_reconcile_inspect_enter", request, clock, record)
    try:
        _inspect(client, work_id)
        _record_phase(evidence, work_id, "submission_reconcile_existing_work", request, clock, record)
        return None
    except RackAiRuntimeError as error:
        if error.code != "not_found":
            _record_phase(evidence, work_id, "submission_reconcile_inspect_error", request, clock, record, detail=error.code)
            raise RackAiResourceWait(f"RackAI workspace inspect: {error.code}") from error
        _record_phase(evidence, work_id, "submission_reconcile_not_found", request, clock, record)
    payload = _submit_payload(request, str(record["reservation_id"]), str(record["service"]), work_id)
    if _digest(payload) != record.get("request_digest"):
        ref = _record_evidence(evidence, work_id, "submission-conflict", {
            "error": "rack_ai_workspace_submission_payload_changed",
            "submission_id": request.identity.submission_id,
        })
        return _external_result(
            request.identity,
            WorkspaceExecutionStatus.MALFORMED_RESULT,
            "rack_ai_workspace_submission_payload_changed",
            (ref,),
        )
    _record_phase(evidence, work_id, "submit_work_enter", request, clock, record)
    try:
        receipt = client.operation({"operation": "submit_work", "request": payload})
    except RackAiRuntimeError as error:
        _record_phase(evidence, work_id, "submit_work_error", request, clock, record, detail=error.code)
        if error.status in {0, 429, 502, 503, 504}:
            try:
                _inspect(client, work_id)
            except RackAiRuntimeError:
                raise RackAiResourceWait(f"RackAI workspace submit: {error.code}") from error
            _record_phase(evidence, work_id, "submit_work_uncertain_existing_work", request, clock, record, detail=error.code)
            return None
        ref = _record_evidence(evidence, work_id, "submit-error", {
            "operation": "submit_work",
            "error": error.code,
            "status": error.status,
        })
        return _external_result(
            request.identity,
            WorkspaceExecutionStatus.MALFORMED_RESULT,
            f"submit_work failed: {error.code}",
            (ref,),
        )
    receipt_ref = _record_evidence(evidence, work_id, "submit-receipt", receipt)
    _record_phase(evidence, work_id, "submit_work_receipt", request, clock, record)
    return receipt_ref


def _wait_for_authoritative_result(
    client: RackAiRuntimeClient,
    reservation: RackAiReservation,
    evidence: RackAiPublicWorkEvidenceStore,
    request: WorkspaceExecutionRequest,
    record: dict[str, object],
    receipt_ref: str | None,
    clock: RackAiPublicWorkspaceClock,
) -> WorkspaceExecutionResult:
    start = clock.monotonic()
    deadline = start + reservation.client.configuration.resource_wait_seconds
    work_id = str(record["work_id"])
    _record_phase(evidence, work_id, "wait_for_result_enter", request, clock, record,
                  deadline_monotonic=deadline, elapsed_seconds=0.0)
    refs = tuple(item for item in (receipt_ref,) if item)
    last_reason = "workspace outcome unavailable"
    while True:
        try:
            snapshot = _inspect(client, work_id)
        except RackAiRuntimeError as error:
            raise RackAiResourceWait(f"RackAI workspace inspect: {error.code}") from error
        snapshot_ref = _record_evidence(evidence, work_id, "inspection", snapshot)
        try:
            artifact_refs = _fetch_artifacts(client, evidence, work_id, snapshot)
        except RackAiPublicWorkspaceContractError as error:
            return _external_result(
                request.identity,
                WorkspaceExecutionStatus.MALFORMED_RESULT,
                str(error),
                (*refs, snapshot_ref),
            )
        result = _result_from_snapshot(request.identity, record, snapshot, (*refs, snapshot_ref, *artifact_refs))
        if isinstance(result, WorkspaceExecutionResult):
            _record_phase(evidence, work_id, "wait_for_result_exit", request, clock, record,
                          deadline_monotonic=deadline, elapsed_seconds=clock.monotonic() - start,
                          detail=result.status.value)
            return result
        last_reason = result
        remaining = deadline - clock.monotonic()
        if remaining <= 0:
            _record_phase(evidence, work_id, "wait_for_result_deadline", request, clock, record,
                          deadline_monotonic=deadline, elapsed_seconds=clock.monotonic() - start,
                          detail=last_reason)
            raise RackAiResourceWait(f"RackAI workspace: {last_reason}; resource wait bound reached")
        clock.sleep(min(reservation.client.configuration.poll_seconds, remaining))


def _inspect(client: RackAiRuntimeClient, work_id: str) -> dict[str, object]:
    result = client.operation({"operation": "inspect_work_execution", "work_id": work_id})
    if not isinstance(result, dict):
        raise RackAiPublicWorkspaceContractError("inspect_work_execution returned a non-object result")
    return result


def _fetch_artifacts(
    client: RackAiRuntimeClient,
    evidence: RackAiPublicWorkEvidenceStore,
    work_id: str,
    snapshot: dict[str, object],
) -> tuple[str, ...]:
    artifact_ids = _artifact_ids(snapshot)
    if not artifact_ids:
        return ()
    refs: list[str] = []
    invocation_id = _work(snapshot).get("invocation_id")
    for artifact_id in artifact_ids:
        try:
            artifact = client.operation({"operation": "get_work_artifact", "artifact_id": artifact_id})
        except RackAiRuntimeError as error:
            refs.append(_record_evidence(evidence, work_id, "artifact-unavailable", {
                "artifact_id": artifact_id,
                "error": error.code,
                "status": error.status,
            }))
            continue
        if artifact.get("artifact_id") != artifact_id or artifact.get("invocation_id") != invocation_id:
            raise RackAiPublicWorkspaceContractError("RackAI artifact identity differs from requested work")
        refs.append(_record_evidence(evidence, work_id, f"artifact-{sha256(artifact_id.encode()).hexdigest()[:12]}", artifact))
    return tuple(refs)


def _result_from_snapshot(
    identity: AthbaWorkspaceIdentity,
    record: dict[str, object],
    snapshot: dict[str, object],
    evidence_refs: tuple[str, ...],
    wait_if_pending: bool = True,
) -> WorkspaceExecutionResult | str:
    try:
        _validate_snapshot_identity(snapshot, record)
        outcome = _outcome(snapshot)
        closure = _closure(snapshot)
        attempt = _attempt(outcome)
    except (KeyError, TypeError, ValueError, RackAiPublicWorkspaceContractError) as error:
        return _external_result(identity, WorkspaceExecutionStatus.MALFORMED_RESULT, str(error), evidence_refs)
    wait_reason = _pending_closure_reason(outcome, closure)
    if wait_reason is not None:
        return wait_reason if wait_if_pending else "pending"
    replay_error = _replay_safety_error(outcome, closure)
    if replay_error is not None:
        return _external_result(identity, WorkspaceExecutionStatus.MALFORMED_RESULT, replay_error, evidence_refs)
    if not bool(attempt["known"]):
        return _external_result(
            identity, WorkspaceExecutionStatus.MALFORMED_RESULT, "rack_ai_workspace_attempt_outcome_unknown", evidence_refs
        )
    workspace = outcome.get("workspace")
    if _attempt_accepted(attempt, outcome, workspace):
        return _accepted_result(identity, record, workspace, evidence_refs)
    failure_category = _failure_category(attempt, outcome)
    error = _failure_message(outcome, workspace, failure_category)
    if "transport" in failure_category:
        return _external_result(identity, WorkspaceExecutionStatus.BACKEND_UNAVAILABLE, error, evidence_refs)
    if failure_category == "execution_timeout" or ("timeout" in failure_category and "transport" not in failure_category):
        return WorkspaceExecutionResult(identity, WorkspaceExecutionStatus.TIMEOUT, error=error, evidence_refs=evidence_refs)
    return WorkspaceExecutionResult(identity, WorkspaceExecutionStatus.NO_CANDIDATE, error=error, evidence_refs=evidence_refs)


def _accepted_result(
    identity: AthbaWorkspaceIdentity,
    record: dict[str, object],
    workspace: object,
    evidence_refs: tuple[str, ...],
) -> WorkspaceExecutionResult:
    if not isinstance(workspace, dict):
        return _external_result(identity, WorkspaceExecutionStatus.MALFORMED_RESULT, "workspace acceptance evidence is missing", evidence_refs)
    revision = workspace.get("accepted_revision")
    if not isinstance(revision, str) or not revision.strip():
        return _external_result(
            identity,
            WorkspaceExecutionStatus.MALFORMED_RESULT,
            "accepted workspace result omitted accepted_revision",
            evidence_refs,
        )
    try:
        root = _validate_accepted_revision(revision, record)
    except RackAiPublicWorkspaceContractError as error:
        return _external_result(identity, WorkspaceExecutionStatus.MALFORMED_RESULT, str(error), evidence_refs)
    return WorkspaceExecutionResult(
        identity,
        WorkspaceExecutionStatus.ACCEPTED,
        candidate_revision=revision,
        accepted_revision=revision,
        changed_paths=tuple(str(item) for item in workspace.get("changed_paths", ())),
        acceptance_verdict=_optional_text(workspace.get("acceptance_verdict")),
        evidence_refs=evidence_refs,
        generic_failure=None,
        execution_provenance={"repository_root": root} if root is not None else None,
    )


def _validate_accepted_revision(revision: str, record: dict[str, object]) -> str | None:
    root = record.get("repository_root")
    if root is None:
        raise RackAiPublicWorkspaceContractError("accepted workspace result omitted ATHBA repository root")
    root_text = str(root)
    if root_text == "/srv/rack-ai" or root_text.startswith("/srv/rack-ai/"):
        raise RackAiPublicWorkspaceContractError("accepted revision validation refused RackAI-owned repository root")
    completed = subprocess.run(
        ["git", "-C", root_text, "cat-file", "-e", f"{revision}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RackAiPublicWorkspaceContractError(f"accepted revision is not present in ATHBA repository: {detail}")
    return root_text

def _validate_existing_submission(request: WorkspaceExecutionRequest, record: dict[str, object]) -> dict[str, object]:
    payload = _submit_payload(request, str(record["reservation_id"]), str(record["service"]), str(record["work_id"]))
    if record.get("request_digest") != _digest(payload):
        raise RackAiResourceWait("persisted RackAI workspace submission conflicts with active request")
    return record


def _submit_payload(
    request: WorkspaceExecutionRequest,
    reservation_id: str,
    service: str,
    work_id: str,
) -> dict[str, object]:
    if request.network_policy != "disabled":
        raise RackAiPublicWorkspaceContractError("RackAI public workspace contract only permits disabled network")
    repository = _repository_payload(request)
    workspace: dict[str, object] = {
        "repository": repository,
        "objective": request.objective,
        "allowed_paths": list(request.allowed_writable_paths),
        "acceptance": {
            "commands": [list(command) for command in request.acceptance_commands],
            "required_artifacts": list(request.required_artifacts),
        },
        "requirements": {
            "complexity": request.profile.complexity.value,
            "requires_large_context": request.profile.requires_large_context,
        },
        "limits": {
            "max_implementation_attempts": 1,
            "timeout_seconds": request.profile.timeout_seconds,
            "network": request.network_policy,
        },
    }
    if request.repository.environment_resources:
        workspace["environment_resources"] = list(request.repository.environment_resources)
    return {
        "reservation_id": reservation_id,
        "service": service,
        "work_id": work_id,
        "payload": {"kind": "workspace", "workspace": workspace},
    }


def _validate_snapshot_identity(snapshot: dict[str, object], record: dict[str, object]) -> None:
    if snapshot.get("schema") != "rack-ai/work-execution/v1":
        raise RackAiPublicWorkspaceContractError("inspect_work_execution returned an unsupported schema")
    if snapshot.get("contract_version") != PUBLIC_WORK_CONTRACT_VERSION:
        raise RackAiPublicWorkspaceContractError("inspect_work_execution returned an unsupported contract version")
    work = _work(snapshot)
    for field in ("work_id", "reservation_id", "service"):
        if work.get(field) != record.get(field):
            raise RackAiPublicWorkspaceContractError(f"RackAI work identity mismatch: {field}")


def _work(snapshot: dict[str, object]) -> dict[str, object]:
    work = snapshot["work"]
    if not isinstance(work, dict):
        raise RackAiPublicWorkspaceContractError("work execution record is malformed")
    return work


def _outcome(snapshot: dict[str, object]) -> dict[str, object]:
    outcome = snapshot["outcome"]
    if not isinstance(outcome, dict):
        raise RackAiPublicWorkspaceContractError("work outcome is malformed")
    if outcome.get("kind") != "workspace":
        raise RackAiPublicWorkspaceContractError("work outcome is not a workspace outcome")
    return outcome


def _closure(snapshot: dict[str, object]) -> dict[str, object]:
    closure = snapshot["closure"]
    if not isinstance(closure, dict):
        raise RackAiPublicWorkspaceContractError("work closure is malformed")
    return closure


def _attempt(outcome: dict[str, object]) -> dict[str, object]:
    attempt = outcome["attempt"]
    if not isinstance(attempt, dict):
        raise RackAiPublicWorkspaceContractError("work attempt outcome is malformed")
    return attempt


def _pending_closure_reason(outcome: dict[str, object], closure: dict[str, object]) -> str | None:
    if bool(closure.get("execution_active")):
        return "workspace execution is still active"
    if bool(_attempt(outcome).get("known")) and not bool(closure.get("safe_closure_known")):
        return "workspace attempt is known but closure is not yet safe"
    return None


def _replay_safety_error(outcome: dict[str, object], closure: dict[str, object]) -> str | None:
    attempt = _attempt(outcome)
    if not bool(attempt.get("known")):
        return None
    replay_safety = str(closure.get("replay_safety", ""))
    if replay_safety in _ACCEPTED_REPLAY_SAFETY:
        return None
    if "unsafe" in replay_safety.lower():
        return f"rack_ai_workspace_replay_not_permitted: {replay_safety}"
    return f"rack_ai_workspace_replay_safety_unknown: {replay_safety}"


def _repository_payload(request: WorkspaceExecutionRequest) -> dict[str, object]:
    repository: dict[str, object] = {
        "id": request.repository.repository_id,
        "base_ref": request.repository.base_ref,
        "base_sha": request.repository.base_sha,
    }
    root = request.repository.registered_root
    if _is_dynamic_repository_root(root):
        repository["root"] = root
    else:
        repository["registered_root"] = root
    return repository


def _is_dynamic_repository_root(root: str | None) -> bool:
    if root is None:
        return False
    dynamic = ATHBA_DYNAMIC_PROJECTS_ROOT.rstrip("/")
    return root == dynamic or root.startswith(dynamic + "/")


def _attempt_accepted(attempt: dict[str, object], outcome: dict[str, object], workspace: object) -> bool:
    if not bool(attempt.get("known")):
        return False
    values = {str(attempt.get("status", "")), str(attempt.get("category", "")), str(outcome.get("category", ""))}
    if "accepted" in values or "succeeded" in values or "success" in values:
        return True
    return isinstance(workspace, dict) and isinstance(workspace.get("accepted_revision"), str)


def _failure_category(attempt: dict[str, object], outcome: dict[str, object]) -> str:
    for value in (attempt.get("failure_category"), outcome.get("failure_category"), attempt.get("category"), outcome.get("category")):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "workspace_failed_without_candidate"


def _failure_message(outcome: dict[str, object], workspace: object, failure_category: str) -> str:
    if isinstance(workspace, dict) and isinstance(workspace.get("last_error"), str) and workspace["last_error"].strip():
        return str(workspace["last_error"])
    if isinstance(outcome.get("error"), str) and outcome["error"].strip():
        return str(outcome["error"])
    return failure_category


def _external_result(
    identity: AthbaWorkspaceIdentity,
    status: WorkspaceExecutionStatus,
    error: str,
    evidence_refs: tuple[str, ...],
) -> WorkspaceExecutionResult:
    return WorkspaceExecutionResult(identity, status, error=error, evidence_refs=evidence_refs)


def _artifact_ids(snapshot: dict[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    for item in snapshot.get("artifacts", ()):
        if isinstance(item, dict) and isinstance(item.get("artifact_id"), str):
            values.append(item["artifact_id"])
    workspace = snapshot.get("outcome", {})
    if isinstance(workspace, dict):
        workspace = workspace.get("workspace")
    if isinstance(workspace, dict):
        for command in workspace.get("commands", ()):
            if not isinstance(command, dict):
                continue
            for stream in ("stdout", "stderr"):
                value = command.get(stream)
                if isinstance(value, dict) and value.get("available") and isinstance(value.get("artifact_id"), str):
                    values.append(value["artifact_id"])
    return tuple(dict.fromkeys(values))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _safe_kind(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)[:80] or "evidence"
