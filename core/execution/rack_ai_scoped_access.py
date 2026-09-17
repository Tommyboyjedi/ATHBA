"""Bind existing OpenAI payloads to a Ready reservation's scoped access."""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from core.execution.rack_ai_reservation import RackAiReservation
from core.execution.rack_ai_runtime import RackAiResourceWait


class RackAiScopedAccess:
    def __init__(self, reservation: RackAiReservation, service: str):
        self.reservation = reservation
        self.service = service

    def prepare(self, payload: dict) -> tuple[str, dict, dict]:
        member = self.reservation.ready(self.service)
        path = member.get("gateway_path")
        if not isinstance(path, str) or not path.startswith("/scoped/") or urlsplit(path).netloc:
            raise RackAiResourceWait("Ready service did not return scoped model access")
        model = member.get("model")
        if not isinstance(model, str) or not model:
            raise RackAiResourceWait("Ready service did not identify its model")
        config = self.reservation.client.configuration
        body = {**payload, "model": model}
        if "response_format" in body:
            # Preserve the JSON-schema constraint in the Responses API's native field.
            schema = body.pop("response_format")["json_schema"]
            body["text"] = {"format": {"type": "json_schema", **schema}}
        key = self.reservation.call_identity(json.dumps(body, sort_keys=True))
        headers = {"Authorization": "Bearer " + config.credential_file.read_text().strip(),
                   "Idempotency-Key": key}
        return config.origin.rstrip("/") + path.rstrip("/") + "/responses", headers, body
