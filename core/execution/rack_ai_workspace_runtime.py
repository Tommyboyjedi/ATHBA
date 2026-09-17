"""Workspace submission/reconciliation through RackAI's public work operations."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time

from core.execution.rack_ai_reservation import RackAiReservation, runtime_identity
from core.execution.rack_ai_runtime import RackAiResourceWait, RackAiRuntimeError
from core.filesystem_policy import resolve_confined_absolute_path


class RackAiWorkspaceRuntime:
    def __init__(self, reservation: RackAiReservation):
        self.reservation = reservation
        self.client = reservation.client

    def work_id(self, submission_id: str) -> str:
        return runtime_identity(self.reservation._binding().identity + ":" + submission_id)

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
        if work is None:
            member = self.reservation.ready(payload["service"])
            reservation_id = member["reservation_id"]
        else:
            reservation_id = work["reservation_id"]
        self.reservation.mark_workspace(identity)
        request = {**payload, "work_id": self.work_id(identity), "reservation_id": reservation_id}
        try:
            # Exact replay also asks RackAI to reject changed payloads under an old ID.
            work = self.client.operation({"operation": "submit_work", "request": request})
        except RackAiRuntimeError as error:
            raise RackAiResourceWait(error.code) from error
        return self._wait(work, payload)

    def _wait(self, work: dict, payload: dict) -> dict:
        config = self.client.configuration
        deadline = time.monotonic() + payload["payload"]["workspace"]["limits"]["timeout_seconds"] + config.resource_wait_seconds
        while work["state"] in {"accepted", "waiting", "held", "started"}:
            if time.monotonic() >= deadline:
                raise RackAiResourceWait("workspace is still pending; reconcile the existing work ID")
            time.sleep(config.poll_seconds)
            inspected = self.inspect(payload["work_id"])
            if inspected is None:
                raise RackAiResourceWait("accepted workspace record is missing")
            work = inspected
        return self.result(work)

    def result(self, work: dict) -> dict:
        if work["state"] == "completed" and isinstance(work.get("result"), dict):
            result = work["result"]
            if result.get("work_id") != work["work_id"]:
                raise RackAiResourceWait("workspace result identity mismatch")
            return WorkspacePacketReader().read(result)
        if work["state"] in {"accepted", "waiting", "held", "started", "uncertain"} or work.get("started") is None:
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
        if selection.get("submission_id") != result["work_id"]:
            raise RackAiResourceWait("workspace evidence identity mismatch")
        return {**packet, "packet_path": result["packet_path"]}
