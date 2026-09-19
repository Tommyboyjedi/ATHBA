"""Transport diagnostics preserve request, retry and campaign accounting behavior."""
import json

import httpx
import pytest

from core.execution.rack_ai_runtime import RackAiResourceWait
from core.execution.rack_ai_scoped_access import RackAiScopedAccess
from core.execution.scoped_transport_evidence import BODY_LIMIT
from core.llm.contracts.provider import ProviderRequest
from core.llm.providers.openai_provider import OpenAIProvider
from tests.execution.test_rack_ai_runtime_reservations import session


def setup_provider(tmp_path, monkeypatch):
    reservation, client, store = session(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "unused-secret")
    monkeypatch.setattr("core.llm.providers.openai_provider.time.sleep", lambda _: None)
    provider = OpenAIProvider(max_retries=1)
    provider.runtime_access = RackAiScopedAccess(reservation, "local-primary")
    reservation.transition("checklist-transition")
    return provider, reservation, client, store


def events(caplog):
    return [json.loads(record.message.split("scoped_transport_failure ", 1)[1])
            for record in caplog.records if record.message.startswith("scoped_transport_failure ")]


@pytest.mark.parametrize("status,count", [(400, 2), (401, 2), (409, 1), (429, 2), (502, 2)])
def test_http_failures_retain_safe_evidence_without_changing_retries_or_state(tmp_path, monkeypatch, caplog, status, count):
    provider, reservation, client, store = setup_provider(tmp_path, monkeypatch)
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs)
        return httpx.Response(status, json={"error": "transport_rejected"}, headers={
            "x-request-id": "safe-id", "set-cookie": "secret-cookie"}, request=httpx.Request("POST", url))
    monkeypatch.setattr("core.llm.providers.openai_provider.httpx.post", post)
    before = store.load("campaign").to_dict()
    with pytest.raises(RackAiResourceWait):
        provider.invoke(ProviderRequest("unchanged-prompt", "local-primary"))
    rows = events(caplog)
    assert len(calls) == len(rows) == count
    assert all(call == calls[0] for call in calls)
    assert rows[-1]["status_code"] == status
    assert json.loads(rows[-1]["response_body"]) == {"error": "transport_rejected"}
    assert rows[-1]["content_type"] == "application/json"
    assert rows[-1]["response_headers"] == {"x-request-id": "safe-id"}
    assert rows[-1]["transition_identity"] == "checklist-transition"
    assert rows[-1]["retry_remaining"] is False
    assert rows[-1]["retryable_under_existing_policy"] == (status != 409)
    assert rows[-1]["remote_execution_uncertain"] is True
    assert store.load_reservation("campaign").pending_inference == calls[0]["headers"]["Idempotency-Key"]
    after = store.load("campaign").to_dict()
    assert {k: v for k, v in after.items() if k != "rack_ai"} == {k: v for k, v in before.items() if k != "rack_ai"}
    assert len([c for c in client.calls if c["operation"] == "reserve"]) == 1


def test_body_and_headers_redact_credentials_and_capability_before_bounding(tmp_path, monkeypatch, caplog):
    provider, reservation, client, store = setup_provider(tmp_path, monkeypatch)
    client.configuration.credential_file.write_text("known-super-secret")
    reservation.ready("local-primary")
    client.reservations["R1"]["services"]["local-primary"]["gateway_path"] = "/scoped/R1/capability-secret/v1"
    body = 'Bearer known-super-secret /scoped/R1/capability-secret/v1 "password":"another-secret" token=extra-secret ' + 'x' * 5000
    def post(url, **kwargs):
        return httpx.Response(502, text=body, headers={"x-request-id": "known-super-secret", "set-cookie": "cookie-secret"}, request=httpx.Request("POST", url))
    monkeypatch.setattr("core.llm.providers.openai_provider.httpx.post", post)
    with pytest.raises(RackAiResourceWait):
        provider.invoke(ProviderRequest("prompt", "local-primary"))
    row = events(caplog)[0]
    assert len(row["response_body"]) <= BODY_LIMIT
    assert row["response_body_truncated"] is True
    assert row["gateway_path"] == "/scoped/R1/[REDACTED]/v1/responses"
    for secret in ("known-super-secret", "capability-secret", "another-secret", "extra-secret", "cookie-secret", "unused-secret"):
        assert secret not in caplog.text


def test_timeout_keeps_pending_identity_and_existing_retry_count(tmp_path, monkeypatch, caplog):
    provider, reservation, client, store = setup_provider(tmp_path, monkeypatch)
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs)
        raise httpx.ReadTimeout("Bearer hidden", request=httpx.Request("POST", url))
    monkeypatch.setattr("core.llm.providers.openai_provider.httpx.post", post)
    with pytest.raises(RackAiResourceWait):
        provider.invoke(ProviderRequest("prompt", "local-primary"))
    assert len(calls) == 2
    assert store.load_reservation("campaign").pending_inference is not None
    assert events(caplog)[0]["status_code"] is None
    assert events(caplog)[0]["exception_type"] == "ReadTimeout"
    assert "hidden" not in caplog.text


@pytest.mark.parametrize("initial_failure", [False, True])
def test_success_and_recovery_preserve_output_payload_and_pending_clear(tmp_path, monkeypatch, caplog, initial_failure):
    provider, reservation, client, store = setup_provider(tmp_path, monkeypatch)
    calls = []
    response = {"output": [{"content": [{"text": "unchanged"}]}], "usage": {"input_tokens": 1, "output_tokens": 2}}
    def post(url, **kwargs):
        calls.append(kwargs)
        if initial_failure and len(calls) == 1:
            return httpx.Response(429, json={"error": "capacity_gateway_waiters"}, request=httpx.Request("POST", url))
        return httpx.Response(200, json=response, request=httpx.Request("POST", url))
    monkeypatch.setattr("core.llm.providers.openai_provider.httpx.post", post)
    result = provider.invoke(ProviderRequest("prompt", "local-primary", max_tokens=4096))
    assert result.text == "unchanged" and result.raw == response
    assert result.usage == {"input_tokens": 1, "output_tokens": 2}
    assert calls[0]["json"] == {"input": "prompt", "model": "local-primary", "temperature": 0.0, "max_output_tokens": 4096}
    assert len(calls) == 1 + initial_failure
    assert len(events(caplog)) == int(initial_failure)
    assert store.load_reservation("campaign").pending_inference is None
