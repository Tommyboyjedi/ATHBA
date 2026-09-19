"""Focused campaign lifecycle tests; no live RackAI or model calls."""
from copy import deepcopy
import json
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
            poll_seconds=0.001, refresh_seconds=0.002, resource_wait_seconds=0.002)
        self.calls = []
        self.reservations = {}
        self.acquisitions = {}
        self.states = {'local-primary': 'ready', 'local-coder': 'ready'}
        self.inspect_hook = None
        self.inspect_work_hook = None
        self.fail_reserve = False
        self.works = {}
        self.next_work_state = 'completed'
        self.executions = 0

    def operation(self, payload):
        self.calls.append(deepcopy(payload))
        op = payload['operation']
        if op == 'reserve':
            request = payload['request']
            key = request['acquisition_id']
            if self.fail_reserve:
                self.fail_reserve = False
                raise RackAiRuntimeError('runtime_transport_uncertain')
            if any(self.states[name] == 'unavailable' for name in request['services']):
                return self._unavailable(request)
            if key not in self.acquisitions:
                identity = f'R{len(self.acquisitions)+1}'
                view = dict(id=identity, priority=request['priority'], services={
                    name: dict(state=self.states[name], model=name, gateway_path=f'/scoped/{identity}/{name}/v1')
                    for name in request['services']})
                self.acquisitions[key] = identity
                self.reservations[identity] = view
            return deepcopy(self._reservation_view(self.reservations[self.acquisitions[key]]))
        if op == 'inspect_reservation':
            try:
                view = self.reservations[payload['reservation_id']]
            except KeyError as error:
                raise RackAiRuntimeError('not_found', 409) from error
            if self.inspect_hook:
                self.inspect_hook(view)
            return deepcopy(self._reservation_view(view))
        if op == 'refresh_reservation':
            raise AssertionError('refresh_reservation is obsolete for active PR31 control flow')
        if op == 'release_reservation':
            self.reservations[payload['reservation_id']]['state'] = 'released'
            for member in self.reservations[payload['reservation_id']]['services'].values():
                member['state'] = 'released'
            return deepcopy(self._reservation_view(self.reservations[payload['reservation_id']]))
        if op == 'inspect_work':
            work = self.works.get(payload['work_id'])
            if work is None:
                raise RackAiRuntimeError('not_found', 409)
            if self.inspect_work_hook:
                self.inspect_work_hook(work)
            return deepcopy(work)
        if op == 'submit_work':
            request = payload['request']
            existing = self.works.get(request['work_id'])
            if existing is not None:
                if all(existing[key] == value for key, value in request.items()):
                    return deepcopy(existing)
                raise RackAiRuntimeError('identity_conflict', 409)
            self.executions += 1
            state = self.next_work_state
            work = dict(request, state=state, started=None if state == 'queued' else 1)
            if state == 'completed':
                work['result'] = {'work_id': request['work_id'], 'status': 'checks_passed'}
            self.works[request['work_id']] = work
            return deepcopy(work)
        if op == 'cancel_work':
            work = self.works[payload['work_id']]
            work['state'] = 'cancelled'
            return deepcopy(work)
        raise AssertionError(op)

    def _unavailable(self, request):
        identity = 'unavailable-' + request['acquisition_id']
        return dict(id=identity, priority=request['priority'], state='unavailable',
                    acquisition_id=request['acquisition_id'], retry_after=0.001,
                    services={name: dict(state='unavailable', retry_after=0.001)
                              for name in request['services']})

    def _reservation_view(self, view):
        view = deepcopy(view)
        if view.get('state') in {'released', 'cancelled', 'expired', 'preempted'}:
            return view
        states = [member['state'] for member in view['services'].values()]
        if states and all(state == states[0] for state in states):
            view['state'] = states[0]
        elif states and all(state == 'ready' for state in states):
            view['state'] = 'ready'
        else:
            view['state'] = 'partial'
        return view

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


@pytest.mark.parametrize('waiting', ['preparing', 'recovery_required'])
def test_initial_preparing_poll_does_not_expose_ready_peer_or_refresh(tmp_path, waiting):
    reservation, client, store = session(tmp_path, {'local-primary': waiting})
    client.configuration = replace(client.configuration, resource_wait_seconds=0.02)
    seen = []
    def restore(view):
        seen.append(view['services']['local-primary']['state'])
        if len(seen) >= 4:
            view['services']['local-primary']['state'] = 'ready'
    client.inspect_hook = restore
    assert reservation.ready('local-coder')['state'] == 'ready'
    assert seen.count(waiting) == 4
    assert len(operations(client, 'reserve')) == 1
    assert not operations(client, 'refresh_reservation')
    assert store.load('campaign').total_application_transition_count == 0
    assert store.load_reservation('campaign').ready_observed is True


def test_initial_unavailable_is_not_persisted_or_inspected_and_retry_reacquires(tmp_path):
    reservation, client, store = session(tmp_path, {'local-primary': 'unavailable'})
    with pytest.raises(RackAiResourceWait, match='unavailable'):
        reservation.ready('local-coder')
    state = store.load_reservation('campaign')
    assert state.reservation_id is None
    assert state.ready_observed is False
    assert state.waiting_service == 'local-coder'
    assert not operations(client, 'inspect_reservation')
    assert not operations(client, 'refresh_reservation')
    assert store.load('campaign').total_application_transition_count == 0
    client.states['local-primary'] = 'ready'
    assert reservation.ready('local-coder')['state'] == 'ready'
    assert store.load_reservation('campaign').reservation_id == 'R1'


def test_resume_inspects_persisted_reservation_first_and_release_is_once(tmp_path):
    reservation, client, store = session(tmp_path)
    reservation.ready('local-coder')
    client.reservations['R1']['services']['local-primary']['state'] = 'preempting'
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
    reservation, client, store = session(tmp_path, {'local-primary': 'preparing'})
    with pytest.raises(RackAiResourceWait, match='preparing'):
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
    assert store.load_reservation('campaign').pending_inference is None



def test_scoped_reasoning_does_not_dispatch_through_preempting_or_preempted(tmp_path, monkeypatch):
    reservation, client, _ = session(tmp_path)
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture')
    provider = OpenAIProvider(max_retries=0)
    provider.runtime_access = RackAiScopedAccess(reservation, 'local-primary')
    sent = []
    def post(url, **kwargs):
        sent.append((url, kwargs))
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'model': 'local-primary', 'output': [{'content': [{'text': '{"ok":true}'}]}]})
    monkeypatch.setattr('core.llm.providers.openai_provider.httpx.post', post)
    reservation.ready('local-primary')
    client.reservations['R1']['services']['local-primary']['state'] = 'preempting'
    with pytest.raises(RackAiResourceWait, match='preempting'):
        provider.invoke(ProviderRequest('blocked prompt', 'local-primary'))
    assert sent == []
    client.reservations['R1']['services']['local-primary']['state'] = 'preempted'
    result = provider.invoke(ProviderRequest('fresh prompt', 'local-primary'))
    assert result.text == '{"ok":true}'
    assert sent[0][0] == 'http://127.0.0.1:8095/scoped/R2/local-primary/v1/responses'


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


def test_ready_observed_reservation_keeps_unaffected_peer_usable_during_preemption(tmp_path):
    reservation, client, _ = session(tmp_path)
    reservation.ready("local-coder")
    client.reservations["R1"]["services"]["local-primary"]["state"] = "preempting"
    assert reservation.ready("local-coder")["state"] == "ready"
    assert client.reservations["R1"]["services"]["local-primary"]["state"] == "preempting"
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
    reservation, client, store = session(tmp_path)
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
    client.reservations["R1"]["services"]["local-coder"]["state"] = "preempting"
    connector = RackAiWorkspaceConnector(RackAiWorkspaceRuntime(reservation))
    first_id = operations(client, "submit_work")[0]["request"]["work_id"]
    result = connector.submit_workspace_change(request)
    recovered = connector.get_result(request.identity)
    assert result.identity == recovered.identity == request.identity
    assert operations(client, "submit_work")[-1]["request"]["work_id"] == first_id
    assert client.executions == 1
    assert store.load_reservation("campaign").workspace_generations == {}
    assert len(operations(client, "reserve")) == 1
    assert not operations(client, "refresh_reservation")



def test_preempted_queued_workspace_advances_execution_generation_without_semantic_retry(tmp_path, monkeypatch):
    from core.execution.rack_ai_workspace_connector import RackAiWorkspaceConnector
    from tests.execution.test_rack_ai_workspace_connector import request_for, approved_packet
    from core.development.athba_workspace_routing import AthbaModelWorkKind
    reservation, client, store = session(tmp_path)
    request = request_for(AthbaModelWorkKind.FRONTIER_IMPLEMENTATION)
    monkeypatch.setattr("core.execution.rack_ai_workspace_runtime.WorkspacePacketReader.read",
                        lambda _, result: approved_packet(result["work_id"]))
    client.next_work_state = "queued"
    def cancel_as_preempted(work):
        if work["state"] == "queued":
            client.reservations[work["reservation_id"]]["services"][work["service"]]["state"] = "preempted"
            work["state"] = "cancelled"
            work["error"] = "reservation_superseded_by_higher_priority"
    client.inspect_work_hook = cancel_as_preempted
    connector = RackAiWorkspaceConnector(RackAiWorkspaceRuntime(reservation))
    with pytest.raises(RackAiResourceWait, match="preemption"):
        connector.submit_workspace_change(request)
    first_id = operations(client, "submit_work")[0]["request"]["work_id"]
    state = store.load_reservation("campaign")
    assert state.workspace_generations[request.identity.submission_id] == 1
    assert state.pending_workspace is None
    client.inspect_work_hook = None
    client.next_work_state = "completed"
    result = connector.submit_workspace_change(request)
    second_id = operations(client, "submit_work")[-1]["request"]["work_id"]
    assert result.identity == request.identity
    assert second_id != first_id
    assert operations(client, "submit_work")[-1]["request"]["reservation_id"] == "R2"
    assert len(operations(client, "reserve")) == 2


def test_changed_workspace_payload_under_existing_work_id_fails_without_generation(tmp_path, monkeypatch):
    reservation, client, store = session(tmp_path)
    monkeypatch.setattr('core.execution.rack_ai_workspace_runtime.WorkspacePacketReader.read', lambda _, value: value)
    transport = RackAiWorkspaceRuntime(reservation)
    payload = dict(work_id='stable-submission', service='local-coder', payload=dict(kind='workspace', workspace=dict(
        limits=dict(timeout_seconds=10))))
    transport.submit(payload)
    changed = deepcopy(payload)
    changed['payload']['workspace']['limits']['timeout_seconds'] = 11
    with pytest.raises(RackAiResourceWait, match='identity_conflict'):
        transport.submit(changed)
    state = store.load_reservation('campaign')
    assert state.workspace_generations == {}
    assert state.pending_workspace is None

def test_terminal_lifecycle_renews_with_campaign_low_priority(tmp_path):
    reservation, client, store = session(tmp_path)
    reservation.ready("local-primary")
    previous = store.load_reservation("campaign")
    store.save_reservation("campaign", replace(previous, priority="medium"))
    client.reservations["R1"]["state"] = "expired"
    reservation.ready("local-primary")
    renewed = store.load_reservation("campaign")
    assert renewed.acquisition_id != previous.acquisition_id
    assert renewed.priority == "low"
    assert operations(client, "reserve")[-1]["request"]["priority"] == "low"


def workspace_evidence(tmp_path, monkeypatch):
    from tests.execution.test_rack_ai_workspace_connector import approved_packet
    reservation, client, _ = session(tmp_path)
    transport = RackAiWorkspaceRuntime(reservation)
    public_id = transport.work_id("submission")
    internal_id = "work-" + "a" * 64
    packet = approved_packet(internal_id)
    packet["change_id"] = internal_id
    packet["selection_decision"]["work_id"] = public_id
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet))
    monkeypatch.setenv("ATHBA_RACK_AI_EVIDENCE_ROOT", str(tmp_path))
    work = dict(state="completed", work_id=public_id, result=dict(
        work_id=public_id, change_id=internal_id, packet_path=str(path)))
    return transport, work, packet, path


def test_workspace_packet_validates_distinct_public_and_internal_identities(tmp_path, monkeypatch):
    transport, work, packet, _ = workspace_evidence(tmp_path, monkeypatch)
    result = transport.result(work)
    assert result["selection_decision"]["work_id"] == work["work_id"]
    assert result["selection_decision"]["submission_id"] == work["result"]["change_id"]
    assert work["work_id"] != work["result"]["change_id"]


@pytest.mark.parametrize("field", ["outer_work", "result_work", "result_change", "packet_change",
                                   "selection_work", "selection_submission", "missing_change"])
def test_workspace_packet_rejects_mismatched_corresponding_identities(tmp_path, monkeypatch, field):
    transport, work, packet, path = workspace_evidence(tmp_path, monkeypatch)
    if field == "outer_work":
        work["work_id"] = "wrong"
    elif field == "result_work":
        work["result"]["work_id"] = "wrong"
    elif field == "result_change":
        work["result"]["change_id"] = "wrong"
    elif field == "packet_change":
        packet["change_id"] = "wrong"
    elif field == "selection_work":
        packet["selection_decision"]["work_id"] = "wrong"
    elif field == "selection_submission":
        packet["selection_decision"]["submission_id"] = "wrong"
    else:
        del work["result"]["change_id"]
    path.write_text(json.dumps(packet))
    with pytest.raises(RackAiResourceWait, match="identity mismatch"):
        transport.result(work)


@pytest.mark.parametrize("terminal", ["expired", "released", "cancelled", "preempted"])
def test_required_terminal_member_releases_partial_reservation_and_starts_new_lifecycle(tmp_path, terminal):
    reservation, client, store = session(tmp_path)
    reservation.ready("local-coder")
    previous = store.load_reservation("campaign")
    client.reservations["R1"]["services"]["local-primary"]["state"] = terminal
    # Ready peer remains usable until the campaign actually requires the terminal member.
    assert reservation.ready("local-coder")["reservation_id"] == "R1"
    assert not operations(client, "release_reservation")
    assert reservation.ready("local-primary")["reservation_id"] == "R2"
    current = store.load_reservation("campaign")
    assert current.acquisition_id != previous.acquisition_id
    assert current.priority == previous.priority == "low"
    assert len(operations(client, "release_reservation")) == 1
    assert len(operations(client, "reserve")) == 2
    assert not operations(client, "refresh_reservation")
    lifecycle_ops = [call["operation"] for call in client.calls if call["operation"] in {"reserve", "release_reservation"}]
    assert lifecycle_ops == ["reserve", "release_reservation", "reserve"]


@pytest.mark.parametrize("aggregate_terminal", [False, True])
@pytest.mark.parametrize("pending", ["pending_workspace", "pending_inference"])
def test_terminal_replacement_blocks_unresolved_work_on_resume(tmp_path, aggregate_terminal, pending):
    reservation, client, store = session(tmp_path)
    reservation.ready("local-primary")
    state = store.load_reservation("campaign")
    store.save_reservation("campaign", replace(state, **{pending: "unresolved-work"}))
    client.reservations["R1"]["services"]["local-primary"]["state"] = "expired"
    if aggregate_terminal:
        client.reservations["R1"]["state"] = "expired"
    resumed = RackAiReservation(client, reservation.services)
    resumed.bind(ReservationBinding(store, "campaign"))
    with pytest.raises(RackAiResourceWait, match="unresolved work"):
        resumed.ready("local-primary")
    assert len(operations(client, "reserve")) == 1
    assert not operations(client, "release_reservation")
    assert store.load_reservation("campaign").acquisition_id == state.acquisition_id


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
    assert store.load_reservation("campaign").pending_inference == pending
    client.reservations["R1"]["services"]["local-primary"]["state"] = "expired"
    with pytest.raises(RackAiResourceWait, match="unresolved work"):
        reservation.ready("local-primary")
    assert not operations(client, "release_reservation")
