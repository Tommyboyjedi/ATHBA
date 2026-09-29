"""Focused public RackAI reservation tests; no private workspace evidence access."""
from copy import deepcopy
import inspect
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from core.development.strict_tdd_run_domain import StrictTddRunState, StrictTddRunStatus
from core.development.strict_tdd_run_store import StrictTddRunStateRepository
from core.execution import rack_ai_service_limits as service_limits_source
from core.execution.rack_ai_reservation import RackAiReservation
from core.execution.rack_ai_reservation_state import ReservationBinding
from core.execution.rack_ai_service_limits import RackAiServiceLimits
from core.execution.rack_ai_runtime import RackAiRuntimeConfiguration, RackAiRuntimeError, RackAiResourceWait
from core.execution.rack_ai_scoped_access import RackAiScopedAccess
from core.execution.unsupported_workspace_execution import UnsupportedWorkspaceExecutionPort
from core.llm.contracts.provider import ProviderRequest
from core.llm.providers.openai_provider import OpenAIProvider


class Runtime:
    def __init__(self, tmp_path):
        token = tmp_path / "credential"
        token.write_text("fixture-token")
        self.configuration = RackAiRuntimeConfiguration(
            "http://127.0.0.1:8095",
            token,
            poll_seconds=0.001,
            refresh_seconds=0.002,
            resource_wait_seconds=0.002,
        )
        self.calls = []
        self.reservations = {}
        self.acquisitions = {}
        self.states = {"local-primary": "ready", "local-coder": "ready"}
        self.service_limits = {
            "local-primary": dict(max_input_tokens=32768, max_output_tokens=4096),
            "local-coder": dict(max_input_tokens=8192, max_output_tokens=2048),
        }
        self.inspect_hook = None
        self.fail_reserve = False

    def operation(self, payload):
        self.calls.append(deepcopy(payload))
        op = payload["operation"]
        if op == "reserve":
            request = payload["request"]
            key = request["acquisition_id"]
            if self.fail_reserve:
                self.fail_reserve = False
                raise RackAiRuntimeError("runtime_transport_uncertain")
            if any(self.states[name] == "unavailable" for name in request["services"]):
                return self._unavailable(request)
            if key not in self.acquisitions:
                identity = f"R{len(self.acquisitions) + 1}"
                view = dict(
                    id=identity,
                    priority=request["priority"],
                    services={
                        name: dict(
                            state=self.states[name],
                            model=name,
                            gateway_path=f"/scoped/{identity}/{name}/v1",
                            **self.service_limits[name],
                        )
                        for name in request["services"]
                    },
                )
                self.acquisitions[key] = identity
                self.reservations[identity] = view
            return deepcopy(self._reservation_view(self.reservations[self.acquisitions[key]]))
        if op == "inspect_reservation":
            try:
                view = self.reservations[payload["reservation_id"]]
            except KeyError as error:
                raise RackAiRuntimeError("not_found", 409) from error
            if self.inspect_hook:
                self.inspect_hook(view)
            return deepcopy(self._reservation_view(view))
        if op == "refresh_reservation":
            raise AssertionError("refresh_reservation is obsolete for active control flow")
        if op == "release_reservation":
            self.reservations[payload["reservation_id"]]["state"] = "released"
            for member in self.reservations[payload["reservation_id"]]["services"].values():
                member["state"] = "released"
            return deepcopy(self._reservation_view(self.reservations[payload["reservation_id"]]))
        raise AssertionError(op)

    def _unavailable(self, request):
        identity = "unavailable-" + request["acquisition_id"]
        return dict(
            id=identity,
            priority=request["priority"],
            state="unavailable",
            acquisition_id=request["acquisition_id"],
            retry_after=0.001,
            services={name: dict(state="unavailable", retry_after=0.001) for name in request["services"]},
        )

    def _reservation_view(self, view):
        view = deepcopy(view)
        if view.get("state") in {"released", "cancelled", "expired", "preempted"}:
            return view
        states = [member["state"] for member in view["services"].values()]
        if states and all(state == states[0] for state in states):
            view["state"] = states[0]
        elif states and all(state == "ready" for state in states):
            view["state"] = "ready"
        else:
            view["state"] = "partial"
        return view


def session(tmp_path, states=None):
    client = Runtime(tmp_path)
    if states:
        client.states.update(states)
    store = StrictTddRunStateRepository(tmp_path / "runs")
    store.save(StrictTddRunState("campaign", "project", "identity", StrictTddRunStatus.READY))
    reservation = RackAiReservation(client, ("local-primary", "local-coder"))
    reservation.bind(ReservationBinding(store, "campaign"))
    return reservation, client, store


def operations(client, name):
    return [call for call in client.calls if call["operation"] == name]


def configure_runtime_env(tmp_path, monkeypatch):
    token = tmp_path / "credential"
    token.write_text("fixture-token")
    monkeypatch.setenv("ATHBA_RACK_AI_ORIGIN", "http://127.0.0.1:8095")
    monkeypatch.setenv("ATHBA_RACK_AI_CREDENTIAL_FILE", str(token))
    return token


def test_reserved_service_limits_parse_published_input_and_output_metadata():
    limits = RackAiServiceLimits.from_reserved_service(
        "local-primary",
        dict(max_input_tokens=12345, max_output_tokens=678),
    )
    assert limits.max_input_tokens == 12345
    assert limits.max_output_tokens == 678


def test_reserved_service_limits_parse_nested_limits_metadata():
    limits = RackAiServiceLimits.from_reserved_service(
        "local-primary",
        dict(limits=dict(max_input_tokens=23456, max_output_tokens=789)),
    )
    assert limits.max_input_tokens == 23456
    assert limits.max_output_tokens == 789


def test_rack_ai_limit_integration_has_no_fixed_local_primary_budget():
    source = inspect.getsource(service_limits_source)
    assert "65536" not in source


def test_runtime_configuration_defaults_resource_wait_for_cold_backend_start(tmp_path, monkeypatch):
    configure_runtime_env(tmp_path, monkeypatch)
    monkeypatch.delenv("ATHBA_RACK_AI_RESOURCE_WAIT_SECONDS", raising=False)
    configuration = RackAiRuntimeConfiguration.from_env()
    assert configuration.resource_wait_seconds == 960.0
    assert configuration.http_timeout_seconds == 30.0


def test_runtime_configuration_uses_positive_resource_wait_override(tmp_path, monkeypatch):
    configure_runtime_env(tmp_path, monkeypatch)
    monkeypatch.setenv("ATHBA_RACK_AI_RESOURCE_WAIT_SECONDS", "42.5")
    assert RackAiRuntimeConfiguration.from_env().resource_wait_seconds == 42.5


@pytest.mark.parametrize("value", ["", "not-a-number", "0", "-1", "nan", "inf"])
def test_runtime_configuration_rejects_invalid_resource_wait_override(tmp_path, monkeypatch, value):
    configure_runtime_env(tmp_path, monkeypatch)
    monkeypatch.setenv("ATHBA_RACK_AI_RESOURCE_WAIT_SECONDS", value)
    with pytest.raises(ValueError, match="ATHBA_RACK_AI_RESOURCE_WAIT_SECONDS.*positive numeric"):
        RackAiRuntimeConfiguration.from_env()


def test_one_campaign_reserves_required_services_once_and_persists_identity(tmp_path):
    reservation, client, store = session(tmp_path)
    reservation.ready("local-primary")
    reservation.ready("local-coder")
    calls = operations(client, "reserve")
    assert len(calls) == 1
    assert calls[0]["request"]["services"] == ["local-primary", "local-coder"]
    assert calls[0]["request"]["priority"] == "low"
    assert store.load("campaign").rack_ai.reservation_id == "R1"
    persisted_limits = store.load_reservation("campaign").service_limits
    assert persisted_limits["local-primary"] == client.service_limits["local-primary"]
    assert persisted_limits["local-coder"] == client.service_limits["local-coder"]
    store.save(StrictTddRunState("campaign", "project", "identity", StrictTddRunStatus.RUNNING))
    assert store.load("campaign").rack_ai.reservation_id == "R1"


def test_reserve_retry_keeps_acquisition_id_terminal_lifecycle_gets_new_id(tmp_path):
    reservation, client, store = session(tmp_path)
    client.fail_reserve = True
    with pytest.raises(RackAiRuntimeError):
        reservation.current()
    pending = store.load("campaign").rack_ai.acquisition_id
    resumed = RackAiReservation(client, reservation.services)
    resumed.bind(ReservationBinding(store, "campaign"))
    resumed.ready("local-primary")
    assert [c["request"]["acquisition_id"] for c in operations(client, "reserve")] == [pending, pending]
    client.reservations["R1"]["state"] = "expired"
    resumed.ready("local-primary")
    assert store.load("campaign").rack_ai.acquisition_id != pending
    assert store.load("campaign").rack_ai.reservation_id == "R2"


@pytest.mark.parametrize("waiting", ["preparing", "recovery_required"])
def test_initial_preparing_poll_does_not_expose_ready_peer_or_refresh(tmp_path, waiting):
    reservation, client, store = session(tmp_path, {"local-primary": waiting})
    client.configuration = replace(client.configuration, resource_wait_seconds=0.02)
    seen = []
    def restore(view):
        seen.append(view["services"]["local-primary"]["state"])
        if len(seen) >= 4:
            view["services"]["local-primary"]["state"] = "ready"
    client.inspect_hook = restore
    assert reservation.ready("local-coder")["state"] == "ready"
    assert seen.count(waiting) == 4
    assert len(operations(client, "reserve")) == 1
    assert not operations(client, "refresh_reservation")
    assert store.load_reservation("campaign").ready_observed is True


def test_initial_unavailable_is_not_persisted_or_inspected_and_retry_reacquires(tmp_path):
    reservation, client, store = session(tmp_path, {"local-primary": "unavailable"})
    with pytest.raises(RackAiResourceWait, match="unavailable"):
        reservation.ready("local-coder")
    state = store.load_reservation("campaign")
    assert state.reservation_id is None
    assert state.ready_observed is False
    assert state.waiting_service == "local-coder"
    assert not operations(client, "inspect_reservation")
    client.states["local-primary"] = "ready"
    assert reservation.ready("local-coder")["state"] == "ready"
    assert store.load_reservation("campaign").reservation_id == "R1"


def test_resume_inspects_persisted_reservation_first_and_release_is_once(tmp_path):
    reservation, client, store = session(tmp_path)
    reservation.ready("local-coder")
    client.reservations["R1"]["services"]["local-primary"]["state"] = "preempting"
    client.calls.clear()
    resumed = RackAiReservation(client, reservation.services)
    resumed.bind(ReservationBinding(store, "campaign"))
    assert resumed.ready("local-coder")["state"] == "ready"
    assert client.calls[0] == dict(operation="inspect_reservation", reservation_id="R1")
    assert not operations(client, "reserve")
    resumed.finish()
    resumed.finish()
    again = RackAiReservation(client, reservation.services)
    again.bind(ReservationBinding(store, "campaign"))
    again.finish()
    assert len(operations(client, "release_reservation")) == 1


def test_resource_bound_surfaces_wait_without_transition_or_semantic_failure(tmp_path):
    reservation, client, store = session(tmp_path, {"local-primary": "preparing"})
    with pytest.raises(RackAiResourceWait, match="preparing"):
        reservation.ready("local-primary")
    state = store.load("campaign")
    assert state.total_application_transition_count == 0
    assert state.status == StrictTddRunStatus.READY
    assert state.rack_ai.waiting_service == "local-primary"
    assert not operations(client, "refresh_reservation")


def test_model_payload_uses_returned_scoped_access_and_preserves_schema(tmp_path, monkeypatch):
    reservation, client, store = session(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "unused-raw-provider-key")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8017/v1")
    provider = OpenAIProvider(max_retries=0)
    provider.runtime_access = RackAiScopedAccess(reservation, "local-primary")
    sent = []
    def post(url, **kwargs):
        sent.append((url, kwargs))
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "model": "local-primary",
            "output": [{"content": [{"text": '{"ok":true}'}]}],
        })
    monkeypatch.setattr("core.llm.providers.openai_provider.httpx.post", post)
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    result = provider.invoke(ProviderRequest("unchanged prompt", "local-primary", temperature=0.2, max_tokens=127, response_schema=schema))
    url, request = sent[0]
    assert request["timeout"] == 30.0
    assert url == "http://127.0.0.1:8095/scoped/R1/local-primary/v1/responses"
    assert request["headers"]["Authorization"] == "Bearer fixture-token"
    assert request["headers"]["Idempotency-Key"]
    assert request["json"] == dict(
        model="local-primary",
        input="unchanged prompt",
        temperature=0.2,
        max_output_tokens=127,
        text={"format": dict(type="json_schema", name="pm_intent", schema=schema)},
    )
    assert result.text == '{"ok": true}'
    assert store.load_reservation("campaign").pending_inference is None
    assert store.load_reservation("campaign").service_limits["local-primary"] == client.service_limits["local-primary"]


def test_scoped_reasoning_rejects_output_budget_above_reserved_ceiling(tmp_path, monkeypatch):
    reservation, client, _store = session(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    provider = OpenAIProvider(max_retries=0)
    provider.runtime_access = RackAiScopedAccess(reservation, "local-primary")
    client.service_limits["local-primary"]["max_output_tokens"] = 128
    sent = []
    def post(url, **kwargs):
        sent.append((url, kwargs))
        raise AssertionError("output ceiling failure must happen before transport")
    monkeypatch.setattr("core.llm.providers.openai_provider.httpx.post", post)
    with pytest.raises(RackAiResourceWait, match="max_output_tokens"):
        provider.invoke(ProviderRequest("prompt", "local-primary", max_tokens=129))
    assert sent == []


def test_release_cleanup_can_resume_after_uncertain_response(tmp_path, monkeypatch):
    reservation, client, store = session(tmp_path)
    reservation.ready("local-primary")
    original = client.operation
    def uncertain(payload):
        result = original(payload)
        if payload["operation"] == "release_reservation":
            raise RackAiRuntimeError("lost_release_response")
        return result
    monkeypatch.setattr(client, "operation", uncertain)
    with pytest.raises(RackAiRuntimeError):
        reservation.finish()
    assert store.load("campaign").rack_ai.release_requested
    monkeypatch.setattr(client, "operation", original)
    reservation.bind(ReservationBinding(store, "campaign"))
    reservation.ready("local-primary")
    assert store.load("campaign").rack_ai.reservation_id == "R2"
    assert len(operations(client, "reserve")) == 2
    assert len(operations(client, "release_reservation")) == 1


def test_uncertain_scoped_inference_blocks_terminal_member_replacement(tmp_path, monkeypatch):
    reservation, client, store = session(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    provider = OpenAIProvider(max_retries=0)
    provider.runtime_access = RackAiScopedAccess(reservation, "local-primary")
    def timeout(url, **kwargs):
        raise httpx.ReadTimeout("response lost", request=httpx.Request("POST", url))
    monkeypatch.setattr("core.llm.providers.openai_provider.httpx.post", timeout)
    with pytest.raises(RackAiResourceWait):
        provider.invoke(ProviderRequest("prompt", "local-primary"))
    pending = store.load_reservation("campaign").pending_inference
    assert pending is not None
    with pytest.raises(RackAiResourceWait, match="original identity"):
        provider.invoke(ProviderRequest("different prompt", "local-primary"))
    client.reservations["R1"]["services"]["local-primary"]["state"] = "expired"
    with pytest.raises(RackAiResourceWait, match="unresolved work"):
        reservation.ready("local-primary")
    assert not operations(client, "release_reservation")


def test_live_composition_uses_public_scoped_reasoning_and_unavailable_workspace_port(tmp_path, monkeypatch):
    from core.development.strict_tdd_live_run_composition import (
        StrictTddLiveRunCompositionFactory,
        StrictTddLiveRunCompositionRequest,
        StrictTddLiveRunConfiguration,
    )
    token = tmp_path / "credential"
    token.write_text("fixture")
    monkeypatch.setenv("ATHBA_RACK_AI_ORIGIN", "http://127.0.0.1:8095")
    monkeypatch.setenv("ATHBA_RACK_AI_CREDENTIAL_FILE", str(token))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    captured = []
    def build(_, request):
        captured.append(request)
        return SimpleNamespace(application=SimpleNamespace())
    monkeypatch.setattr("core.development.strict_tdd_live_run_composition.StrictTddFeatureCompositionFactory.build", build)
    preflight = SimpleNamespace(check=lambda _: SimpleNamespace(kind="green"))
    config = StrictTddLiveRunConfiguration(
        tmp_path / "state",
        tmp_path / "evidence",
        tmp_path,
        "fixture",
        athba_revision="a",
        rack_ai_revision="b",
    )
    result = StrictTddLiveRunCompositionFactory(preflight=preflight).build(StrictTddLiveRunCompositionRequest(config))
    reservation = result.controller.reservation
    assert set(reservation.services) == {"local-primary"}
    assert captured[0].reasoning_gateway.provider.runtime_access.reservation is reservation
    assert isinstance(captured[0].execution_gateway.port, UnsupportedWorkspaceExecutionPort)
    assert reservation.binding is None
