"""Authenticated transport for the deployed RackAI runtime contract."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx


class RackAiResourceWait(Exception):
    """Infrastructure did not become dispatchable; no semantic failure implied."""


class RackAiRuntimeError(Exception):
    def __init__(self, code: str, status: int = 0):
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class RackAiRuntimeConfiguration:
    origin: str
    credential_file: Path
    ttl_seconds: int = 86400
    poll_seconds: float = 2.0
    refresh_seconds: float = 300.0
    resource_wait_seconds: float = 300.0
    http_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        url = urlsplit(self.origin)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise ValueError("RackAI requires an authenticated runtime origin")
        if url.path not in {"", "/"} or url.query or url.fragment:
            raise ValueError("RackAI origin must not include a backend or gateway path")
        if min(self.ttl_seconds, self.poll_seconds, self.refresh_seconds,
               self.resource_wait_seconds, self.http_timeout_seconds) <= 0:
            raise ValueError("RackAI time bounds must be positive")

    @classmethod
    def from_env(cls) -> RackAiRuntimeConfiguration:
        return cls(
            os.environ["ATHBA_RACK_AI_ORIGIN"],
            Path(os.environ["ATHBA_RACK_AI_CREDENTIAL_FILE"]),
        )


class RackAiRuntimeClient:
    def __init__(self, configuration: RackAiRuntimeConfiguration):
        self.configuration = configuration

    def operation(self, payload: dict[str, object]) -> dict[str, object]:
        response = self.post("/runtime/v1", payload)
        result = response.get("result")
        if response.get("schema") != "rack-ai/runtime/v1" or not isinstance(result, dict):
            raise RackAiRuntimeError("invalid_runtime_response")
        return result

    def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        # A relative scoped path must never redirect the principal credential.
        if not path.startswith("/") or path.startswith("//") or urlsplit(path).netloc:
            raise RackAiRuntimeError("invalid_runtime_path")
        token = self.configuration.credential_file.read_text(encoding="utf-8").strip()
        try:
            response = httpx.post(
                self.configuration.origin.rstrip("/") + path,
                headers={"Authorization": "Bearer " + token}, json=payload,
                timeout=self.configuration.http_timeout_seconds, follow_redirects=False,
            )
        except httpx.RequestError as error:
            raise RackAiRuntimeError("runtime_transport_uncertain") from error
        if not response.is_success:
            try:
                code = str(response.json().get("error", "runtime_http_failure"))
            except (ValueError, AttributeError):
                code = "runtime_http_failure"
            raise RackAiRuntimeError(code, response.status_code)
        try:
            value = response.json()
        except ValueError as error:
            raise RackAiRuntimeError("invalid_runtime_response") from error
        if not isinstance(value, dict):
            raise RackAiRuntimeError("invalid_runtime_response")
        return value
