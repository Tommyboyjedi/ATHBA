"""Focused campaign lifecycle tests; no live RackAI or model calls."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from core.development.strict_tdd_run_domain import StrictTddRunState, StrictTddRunStatus
from core.development.strict_tdd_run_store import StrictTddRunStateRepository
from core.execution.rack_ai_reservation import RackAiReservation
from core.execution.rack_ai_reservation_state import ReservationBinding
from core.execution.rack_ai_runtime import RackAiRuntimeConfiguration, RackAiRuntimeError, RackAiResourceWait
from core.execution.rack_ai_scoped_access import RackAiScopedAccess
from core.execution.rack_ai_workspace_runtime import RackAiWorkspaceRuntime
from core.llm.contracts.provider import ProviderRequest
from core.llm.providers.openai_provider import OpenAIProvider


class Runtime:
    def __init__(self, tmp_path):
        token = tmp_path / 'credential'
        token.write_text('fixture-token')
        self.configuration = RackAiRuntimeConfiguration('http://127.0.0.1:8095', token,
            poll_seconds=0.001, refresh_seconds=0.002, resource_wait_seconds=0.02)
        self.calls = []
        self.reservations = {}
        self.acquisitions = {}
        self.states = {'local-primary': 'ready', 'local-coder': 'ready'}
        self.inspect_hook = None
        self.fail_reserve = False
        self.work = None
        self.executions = 0

    def operation(self, payload):
        self.calls.append(deepcopy(payload))
        op = payload['operation']
        if op == 'reserve':
            request = payload['request']
            key = request['acquisition_id']
            if key not in self.acquisitions:
                identity = f'R{len(self.acquisitions)+1}'
                view = dict(id=identity, priority=request['priority'], state='partial', services={
                    name: dict(state=self.states[name], model=name, gateway_path=f'/scoped/{identity}/{name}/v1')
                    for name in request['services']})
                self.acquisitions[key] = deepcopy(view)
                self.reservations[identity] = view
            if self.fail_reserve:
                self.fail_reserve = False
                raise RackAiRuntimeError('runtime_transport_uncertain')
            return deepcopy(self.acquisitions[key])
        if op == 'inspect_reservation':
            view = self.reservations[payload['reservation_id']]
            if self.inspect_hook:
                self.inspect_hook(view)
            return deepcopy(view)
        if op == 'refresh_reservation':
            view = self.reservations[payload['reservation_id']]
            for member in view['services'].values():
                if member['state'] == 'unavailable':
                    member['state'] = 'ready'
            return deepcopy(view)
        if op == 'release_reservation':
            self.reservations[payload['reservation_id']]['state'] = 'released'
            return deepcopy(self.reservations[payload['reservation_id']])
        if op == 'inspect_work':
            if self.work is None:
                raise RackAiRuntimeError('not_found', 409)
            return deepcopy(self.work)
        if op == 'submit_work':
            if self.work is not None:
                assert all(self.work[key] == value for key, value in payload['request'].items())
                return deepcopy(self.work)
            self.executions += 1
            self.work = dict(payload['request'], state='completed', started=1,
                             result={'work_id': payload['request']['work_id'], 'status':'checks_passed'})
            return deepcopy(self.work)
        if op == 'cancel_work':
            self.work['state'] = 'cancelled'
            return deepcopy(self.work)
        raise AssertionError(op)


def session(tmp_path, states=None):
    client = Runtime(tmp_path)
    if states:
        client.states.update(states)
    store = StrictTddRunStateRepository(tmp_path / 'runs')
    store.save(StrictTddRunState('campaign', 'project', 'identity', StrictTddRunStatus.READY))
    reservation = RackAiReservation(client, ('local-primary', 'local-coder'))
    reservation.bind(ReservationBinding(store, 'campaign'))
    return reservation, client, store


def operations(client, name):
    return [call for call in client.calls if call['operation'] == name]


def test_one_campaign_reserves_required_services_once_and_persists_identity(tmp_path):
    reservation, client, store = session(tmp_path)
    reservation.ready('local-primary')
    reservation.ready('local-coder')
    calls = operations(client, 'reserve')
    assert len(calls) == 1
    assert calls[0]['request']['services'] == ['local-primary', 'local-coder']
    assert calls[0]['request']['priority'] == 'low'
    assert store.load('campaign').rack_ai.reservation_id == 'R1'
    assert store.load('campaign').rack_ai.work_id == calls[0]['request']['work_id']
    # Unrelated semantic persistence cannot overwrite the access receipt.
    store.save(StrictTddRunState('campaign', 'project', 'identity', StrictTddRunStatus.RUNNING))
    assert store.load('campaign').rack_ai.reservation_id == 'R1'


def test_reserve_retry_keeps_acquisition_id_terminal_lifecycle_gets_new_id(tmp_path):
    reservation, client, store = session(tmp_path)
    client.fail_reserve = True
    with pytest.raises(RackAiRuntimeError):
        reservation.current()
    pending = store.load('campaign').rack_ai.acquisition_id
    resumed = RackAiReservation(client, reservation.services)
    resumed.bind(ReservationBinding(store, 'campaign'))
    resumed.ready('local-primary')
    assert [c['request']['acquisition_id'] for c in operations(client, 'reserve')] == [pending, pending]
    client.reservations['R1']['state'] = 'expired'
    resumed.ready('local-primary')
    assert store.load('campaign').rack_ai.acquisition_id != pending
    assert store.load('campaign').rack_ai.reservation_id == 'R2'


@pytest.mark.parametrize('waiting', ['preparing', 'held'])
def test_preparing_and_held_poll_without_refresh_or_replacement(tmp_path, waiting):
    reservation, client, store = session(tmp_path, {'local-primary': waiting})
    seen = []
    def restore(view):
        seen.append(view['services']['local-primary']['state'])
        if len(seen) >= 4:
            view['services']['local-primary']['state'] = 'ready'
    client.inspect_hook = restore
    assert reservation.ready('local-primary')['state'] == 'ready'
    assert seen.count(waiting) == 4
    assert len(operations(client, 'reserve')) == 1
    assert not operations(client, 'refresh_reservation')
    assert store.load('campaign').total_application_transition_count == 0


def test_unavailable_refreshes_same_reservation_and_ready_peer_remains_usable(tmp_path):
    reservation, client, store = session(tmp_path, {'local-primary':'unavailable'})
    assert reservation.ready('local-coder')['state'] == 'ready'
    assert not operations(client, 'refresh_reservation')
    assert reservation.ready('local-primary')['state'] == 'ready'
    assert operations(client, 'refresh_reservation') == [dict(operation='refresh_reservation', reservation_id='R1')]
    assert len(operations(client, 'reserve')) == 1


def test_resume_inspects_persisted_reservation_first_and_release_is_once(tmp_path):
    reservation, client, store = session(tmp_path, {'local-primary':'held'})
    reservation.ready('local-coder')
    client.calls.clear()
    resumed = RackAiReservation(client, reservation.services)
    resumed.bind(ReservationBinding(store, 'campaign'))
    assert resumed.ready('local-coder')['state'] == 'ready'
    assert client.calls[0] == dict(operation='inspect_reservation', reservation_id='R1')
    assert not operations(client, 'reserve')
    resumed.finish()
    resumed.finish()
    again = RackAiReservation(client, reservation.services)
    again.bind(ReservationBinding(store, 'campaign'))
    again.finish()
    assert len(operations(client, 'release_reservation')) == 1


def test_resource_bound_surfaces_wait_without_transition_or_semantic_failure(tmp_path):
    reservation, client, store = session(tmp_path, {'local-primary':'held'})
    with pytest.raises(RackAiResourceWait, match='held'):
        reservation.ready('local-primary')
    state = store.load('campaign')
    assert state.total_application_transition_count == 0
    assert state.status == StrictTddRunStatus.READY
    assert state.rack_ai.waiting_service == 'local-primary'
    assert not operations(client, 'refresh_reservation')


def test_model_payload_uses_returned_scoped_access_and_preserves_schema(tmp_path, monkeypatch):
    reservation, client, store = session(tmp_path)
    monkeypatch.setenv('OPENAI_API_KEY','unused-raw-provider-key')
    monkeypatch.setenv('OPENAI_API_BASE','http://127.0.0.1:8017/v1')
    provider = OpenAIProvider(max_retries=0)
    provider.runtime_access = RackAiScopedAccess(reservation, 'local-primary')
    sent = []
    def post(url, **kwargs):
        sent.append((url,kwargs))
        return httpx.Response(200, request=httpx.Request('POST',url), json={
            'model':'local-primary', 'output':[{'content':[{'text':'{"ok":true}'}]}]})
    monkeypatch.setattr('core.llm.providers.openai_provider.httpx.post',post)
    schema = {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok']}
    result = provider.invoke(ProviderRequest('unchanged prompt','local-primary',temperature=0.2,
                                             max_tokens=127,response_schema=schema))
    url, request = sent[0]
    assert url == 'http://127.0.0.1:8095/scoped/R1/local-primary/v1/responses'
    assert request['headers']['Authorization'] == 'Bearer fixture-token'
    assert request['headers']['Idempotency-Key']
    assert request['json'] == dict(model='local-primary',input='unchanged prompt',temperature=0.2,
        max_output_tokens=127,text={'format':dict(type='json_schema',name='pm_intent',schema=schema)})
    assert result.text == '{"ok": true}'


def test_workspace_reconciles_before_submit_and_cancels_remotely(tmp_path, monkeypatch):
    reservation, client, store = session(tmp_path)
    monkeypatch.setattr('core.execution.rack_ai_workspace_runtime.WorkspacePacketReader.read',lambda _, value:value)
    transport = RackAiWorkspaceRuntime(reservation)
    payload = dict(work_id='stable-submission',service='local-coder',payload=dict(kind='workspace',workspace=dict(
        limits=dict(timeout_seconds=10))))
    transport.submit(payload)
    first = operations(client,'submit_work')[0]['request']
    assert first['reservation_id'] == 'R1' and 'priority' not in first
    fresh = RackAiWorkspaceRuntime(reservation)
    fresh.submit(payload)
    assert client.executions == 1
    assert len(operations(client,'submit_work')) == 2
    assert fresh.cancel('stable-submission')
    assert operations(client,'cancel_work')[0]['work_id'] == first['work_id']


def test_old_workspace_contract_is_not_an_active_path():
    root = Path(__file__).resolve().parents[2]
    assert not (root/'core/execution/rack_ai_workspace_cli_transport.py').exists()
    for path in (root/'core').rglob('*.py'):
        assert 'rack-ai/work-unit/v2' not in path.read_text()


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


@pytest.mark.parametrize("state", ["held", "preparing", "unavailable", "recovery_required"])
def test_partial_reservation_uses_ready_peer_without_touching_waiting_member(tmp_path, state):
    reservation, client, _ = session(tmp_path, {"local-primary": state})
    assert reservation.ready("local-coder")["state"] == "ready"
    assert client.reservations["R1"]["services"]["local-primary"]["state"] == state
    assert not operations(client, "refresh_reservation")


@pytest.mark.asyncio
async def test_gatekeeper_wait_is_not_a_semantic_attempt():
    from core.development.reconciliation_submission import ReconciliationSubmission
    from core.execution.reasoning_gateway import ReasoningRequest
    class WaitingGateway:
        async def reason(self, request):
            raise RackAiResourceWait("recovery_required")
    with pytest.raises(RackAiResourceWait, match="recovery_required"):
        await ReconciliationSubmission(WaitingGateway()).submit(ReasoningRequest("gatekeeper", "prompt", "campaign"))


def test_live_composition_shares_one_session_for_workspace_and_reasoning(tmp_path, monkeypatch):
    from core.development.strict_tdd_live_run_composition import (
        StrictTddLiveRunCompositionFactory, StrictTddLiveRunCompositionRequest, StrictTddLiveRunConfiguration)
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
    config = StrictTddLiveRunConfiguration(tmp_path / "state", tmp_path / "evidence", tmp_path, "fixture",
                                          athba_revision="a", rack_ai_revision="b")
    result = StrictTddLiveRunCompositionFactory(preflight=preflight).build(StrictTddLiveRunCompositionRequest(config))
    reservation = result.controller.reservation
    assert set(reservation.services) == {"local-primary", "local-coder"}
    assert captured[0].reasoning_gateway.provider.runtime_access.reservation is reservation
    assert captured[0].execution_gateway.port.transport.reservation is reservation
    assert reservation.binding is None  # Composition itself acquires nothing.


def test_unknown_workspace_submit_is_reconciled_without_duplicate_execution(tmp_path, monkeypatch):
    from core.execution.rack_ai_workspace_connector import RackAiWorkspaceConnector
    from tests.execution.test_rack_ai_workspace_connector import request_for, approved_packet
    from core.development.athba_workspace_routing import AthbaModelWorkKind
    reservation, client, _ = session(tmp_path)
    request = request_for(AthbaModelWorkKind.FRONTIER_IMPLEMENTATION)
    monkeypatch.setattr("core.execution.rack_ai_workspace_runtime.WorkspacePacketReader.read",
                        lambda _, result: approved_packet(result["work_id"]))
    original = client.operation
    def uncertain(payload):
        result = original(payload)
        if payload["operation"] == "submit_work":
            raise RackAiRuntimeError("lost_submit_response")
        return result
    monkeypatch.setattr(client, "operation", uncertain)
    with pytest.raises(RackAiResourceWait):
        RackAiWorkspaceConnector(RackAiWorkspaceRuntime(reservation)).submit_workspace_change(request)
    monkeypatch.setattr(client, "operation", original)
    client.reservations["R1"]["services"]["local-coder"]["state"] = "held"
    connector = RackAiWorkspaceConnector(RackAiWorkspaceRuntime(reservation))
    result = connector.submit_workspace_change(request)
    recovered = connector.get_result(request.identity)
    assert result.identity == recovered.identity == request.identity
    assert client.executions == 1
    assert len(operations(client, "reserve")) == 1
    assert not operations(client, "refresh_reservation")


def test_terminal_lifecycle_preserves_persisted_campaign_priority(tmp_path):
    reservation, client, store = session(tmp_path)
    reservation.ready("local-primary")
    previous = store.load_reservation("campaign")
    store.save_reservation("campaign", replace(previous, priority="medium"))
    client.reservations["R1"]["state"] = "expired"
    reservation.ready("local-primary")
    renewed = store.load_reservation("campaign")
    assert renewed.acquisition_id != previous.acquisition_id
    assert renewed.priority == "medium"
    assert operations(client, "reserve")[-1]["request"]["priority"] == "medium"
