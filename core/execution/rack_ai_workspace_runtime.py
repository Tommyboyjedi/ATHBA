"""Workspace submission/reconciliation through RackAI's public work operations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time

from core.execution.rack_ai_reservation import RackAiReservation
from core.execution.rack_ai_runtime import RackAiResourceWait, RackAiRuntimeError
from core.execution.rack_ai_service_limits import RackAiServiceLimits
from core.filesystem_policy import resolve_confined_absolute_path


ACTIVE_WORK_STATES = frozenset({"queued", "running", "waiting", "preempting", "preempted"})
PREEMPTED_BEFORE_START = "reservation_superseded_by_higher_priority"
PUBLIC_WORKSPACE_REQUIREMENTS = ("complexity", "requires_large_context")


class RackAiWorkspaceRuntime:
    def __init__(self, reservation: RackAiReservation):
        self.reservation = reservation
        self.client = reservation.client

    def work_id(self, submission_id: str) -> str:
        return self.reservation.workspace_execution_identity(submission_id)

    def inspect(self, submission_id: str) -> dict | None:
        try:
            return self.client.operation({"operation": "inspect_work", "work_id": self.work_id(submission_id)})
        except RackAiRuntimeError as error:
            if error.code == "not_found":
                return None
            raise RackAiResourceWait(error.code) from error

    def submit(self, payload: dict) -> dict:
        identity = payload["work_id"]
        work = self.inspect(identity)
        if work is not None and _preempted_before_start(work):
            self.reservation.advance_workspace_generation(identity)
            raise RackAiResourceWait("workspace was cancelled by reservation preemption; retry after reacquisition")
        if work is None:
            member = self.reservation.ready(payload["service"])
            RackAiServiceLimits.from_reserved_service(payload["service"], member)
            reservation_id = member["reservation_id"]
        else:
            self.reservation.service_limits(payload["service"])
            reservation_id = work["reservation_id"]
        payload = _with_public_workspace_requirements(payload)
        self.reservation.mark_workspace(identity)
        request = {**payload, "work_id": self.work_id(identity), "reservation_id": reservation_id}
        try:
            # Exact replay also asks RackAI to reject changed payloads under an old ID.
            work = self.client.operation({"operation": "submit_work", "request": request})
        except RackAiRuntimeError as error:
            if error.status != 0:
                self.reservation.mark_workspace(None)
            raise RackAiResourceWait(error.code) from error
        result = self._wait(work, payload)
        self.reservation.mark_workspace(None)
        return result

    def _wait(self, work: dict, payload: dict) -> dict:
        config = self.client.configuration
        deadline = time.monotonic() + payload["payload"]["workspace"]["limits"]["timeout_seconds"] + config.resource_wait_seconds
        while work["state"] in ACTIVE_WORK_STATES:
            if time.monotonic() >= deadline:
                raise RackAiResourceWait("workspace is still pending; reconcile the existing work ID")
            time.sleep(config.poll_seconds)
            inspected = self.inspect(payload["work_id"])
            if inspected is None:
                raise RackAiResourceWait("queued workspace record is missing")
            work = inspected
            if _preempted_before_start(work):
                self.reservation.advance_workspace_generation(payload["work_id"])
                raise RackAiResourceWait("workspace was cancelled by reservation preemption; retry after reacquisition")
        return self.result(work)

    def result(self, work: dict) -> dict:
        if work["state"] == "completed" and isinstance(work.get("result"), dict):
            result = work["result"]
            if result.get("work_id") != work["work_id"]:
                raise RackAiResourceWait("workspace result identity mismatch")
            return WorkspacePacketReader().read(result)
        if _preempted_before_start(work):
            raise RackAiResourceWait("workspace was cancelled by reservation preemption; retry after reacquisition")
        if work["state"] in ACTIVE_WORK_STATES or work["state"] == "uncertain" or work.get("started") is None:
            raise RackAiResourceWait(f"workspace infrastructure state: {work['state']}: {work.get('error')}")
        raise RackAiResourceWait(f"workspace has no authoritative result: {work.get('error')}")

    def cancel(self, submission_id: str) -> bool:
        result = self.client.operation({"operation": "cancel_work", "work_id": self.work_id(submission_id)})
        return result["state"] == "cancelled" or result.get("cancellation") is not None


class WorkspacePacketReader:
    """Retain the existing confined evidence-packet reader, without the old CLI."""
    def read(self, result: dict) -> dict:
        root = Path(os.getenv("ATHBA_RACK_AI_EVIDENCE_ROOT", "/srv/rack-ai")).resolve()
        path = resolve_confined_absolute_path(root, Path(result["packet_path"]), "Rack AI packet path")
        packet = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(packet, dict):
            raise RackAiResourceWait("workspace evidence packet is not an object")
        selection = packet.get("selection_decision") or {}
        work_id, change_id = result.get("work_id"), result.get("change_id")
        if (not isinstance(work_id, str) or not work_id.strip()
                or not isinstance(change_id, str) or not change_id.strip()
                or not isinstance(selection, dict)
                or selection.get("work_id") != work_id
                or selection.get("submission_id") != change_id
                or packet.get("change_id") != change_id):
            raise RackAiResourceWait("workspace evidence identity mismatch")
        return {**packet, "packet_path": result["packet_path"]}


def _preempted_before_start(work: dict) -> bool:
    return (work.get("state") == "cancelled" and work.get("started") is None
            and work.get("error") == PREEMPTED_BEFORE_START)


def _with_public_workspace_requirements(payload: dict) -> dict:
    copied = {**payload}
    payload_body = _required_mapping(copied.get("payload"), "workspace payload")
    workspace = _required_mapping(payload_body.get("workspace"), "workspace body")
    requirements = _optional_mapping(workspace.get("requirements"))
    workspace["requirements"] = {
        key: requirements[key]
        for key in PUBLIC_WORKSPACE_REQUIREMENTS
        if key in requirements
    }
    payload_body["workspace"] = workspace
    copied["payload"] = payload_body
    return copied


def _required_mapping(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise RackAiResourceWait(f"RackAI {label} is malformed")
    return {**value}


def _optional_mapping(value: object) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RackAiResourceWait("RackAI workspace requirements are malformed")
    return {**value}
