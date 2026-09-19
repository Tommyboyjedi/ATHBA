"""Sanitized scoped HTTP diagnostics; no retry or lifecycle decisions."""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from urllib.parse import quote, urlsplit

import httpx

from core.execution.rack_ai_scoped_access import RackAiScopedAccess

LOGGER = logging.getLogger(__name__)
BODY_LIMIT = 2048
HEADER_LIMIT = 128
SAFE_RESPONSE_HEADERS = ("x-request-id", "request-id", "x-correlation-id", "traceparent")
REDACTED = "[REDACTED]"


@dataclass(frozen=True)
class ScopedTransportAttempt:
    access: RackAiScopedAccess | None
    url: str
    headers: dict[str, str]
    attempt: int
    max_retries: int


@dataclass(frozen=True)
class TransportSanitizer:
    secrets: tuple[str, ...]

    def text(self, value: str) -> str:
        for secret in self.secrets:
            if secret:
                for encoded in (secret, quote(secret, safe=""), json.dumps(secret)[1:-1]):
                    value = value.replace(encoded, REDACTED)
        value = re.sub(r"(?i)bearer\s+[^\s\"'<>]+", "Bearer " + REDACTED, value)
        value = re.sub(r"(/scoped/[^/\s]+/)[^/\s]+", r"\1" + REDACTED, value)
        value = re.sub(
            r"(?i)([\"']?(?:authorization|api[_-]?key|access[_-]?key|token|password|secret|credential)[\"']?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;}]+)",
            r"\1" + REDACTED, value,
        )
        return value


def record_scoped_failure(context: ScopedTransportAttempt, error: httpx.HTTPError) -> None:
    if context.access is None:
        return
    path = urlsplit(context.url).path
    parts = path.split("/")
    authorization = context.headers.get("Authorization", "")
    sanitizer = TransportSanitizer((authorization, authorization.removeprefix("Bearer "),
                                    parts[3] if len(parts) > 3 and parts[1] == "scoped" else ""))
    response = error.response if isinstance(error, httpx.HTTPStatusError) else None
    status = response.status_code if response is not None else None
    body = sanitizer.text(response.text) if response is not None else ""
    access = context.access
    evidence = {
        "exception_type": type(error).__name__,
        "status_code": status,
        "response_body": body[:BODY_LIMIT],
        "response_body_truncated": len(body) > BODY_LIMIT,
        "content_type": sanitizer.text(response.headers.get("content-type", ""))[:HEADER_LIMIT] if response is not None else None,
        "response_headers": {name: sanitizer.text(response.headers[name])[:HEADER_LIMIT]
                             for name in SAFE_RESPONSE_HEADERS if response is not None and name in response.headers},
        "logical_service": sanitizer.text(access.service),
        "gateway_path": sanitizer.text(path),
        "request_identity": sanitizer.text(context.headers.get("Idempotency-Key", "")),
        "transition_identity": sanitizer.text(access.reservation.transition_identity),
        "http_attempt": context.attempt + 1,
        "retryable_under_existing_policy": status != 409,
        "retry_remaining": status != 409 and context.attempt < context.max_retries,
        "remote_execution_uncertain": True,
        "uncertainty_basis": "pending inference retained; HTTP status alone does not reconcile remote execution",
    }
    LOGGER.warning("scoped_transport_failure %s", json.dumps(evidence, sort_keys=True))
