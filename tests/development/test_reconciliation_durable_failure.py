"""Exercise the real CLI/controller after fake-model TDD completes in disposable Git."""
import json
from typing import Any

import pytest

from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_run_store import StrictTddRunStateRepository
from core.development.strict_tdd_run_domain import StrictTddRunStatus
from core.development.reconciliation_response import ReconciliationFailureKind
from core.execution.reasoning_gateway import ReasoningResult
from scripts.run_pr23_strict_tdd_feature import main
from tests.development.test_pr23_strict_tdd_runner import (
    Factory, Reasoning, args, git, prevent_live_boundaries,
)


@pytest.mark.parametrize('failure,expected', [
    ('malformed', ReconciliationFailureKind.MALFORMED),
    ('provider', ReconciliationFailureKind.PROVIDER),
])
def test_completed_tdd_preserved_cli_blocks_and_restart_does_not_repeat(tmp_path, monkeypatch, capsys, failure, expected):
    state, evidence = tmp_path / 'state', tmp_path / 'evidence'
    log: list[Any] = []
    counts: list[Any] = []
    before: dict[str, Any] = {}
    original = Reasoning.reason
    features = StrictTddFeatureRepository(state / 'features')
    repository = state / 'projects/toggle-project/repository'

    def frozen_files():
        return {str(p.relative_to(state)): p.read_bytes()
                for folder in ('microcycles', 'scenario-drafts', 'revisions')
                for p in (state / folder).rglob('*.json')}

    async def reason(self, request):
        if request.purpose == 'athba_specification_checklist':
            result = await original(self, request)
            payload = json.loads(result.text)
            payload['items'].append({'ref': 'CHK-2', 'text': 'Second independent criterion.', 'kind': 'behavior'})
            return ReasoningResult(json.dumps(payload))
        if 'checklist_test_reconciliation' not in request.purpose:
            return await original(self, request)
        self.call_count += 1
        self.log.append(request)
        if not before:
            before['feature'] = features.load('toggle-project')
            before['files'] = frozen_files()
            before['sha'] = git(repository, 'rev-parse', 'refs/heads/main')
        if request.purpose == 'athba_checklist_test_reconciliation' and json.loads(request.prompt)['checklist_item']['ref'] == 'CHK-1':
            return ReasoningResult(json.dumps({'answer': 'NO', 'selected_test_names': [], 'rationale': 'no direct proof'}))
        if failure == 'provider':
            raise OSError('transport unavailable')
        return ReasoningResult('not JSON')

    monkeypatch.setattr(Reasoning, 'reason', reason)
    factory: Any = Factory(log, counts)
    assert main(args('start', state, evidence)[:-2], factory) == 2
    summary = json.loads(capsys.readouterr().out)
    assert summary['status'] == 'blocked'
    current = features.load('toggle-project')
    assert current is not None
    assert current.status == 'blocked'
    assert current.blocked_reason == expected.value
    assert current.completed_behaviors == before['feature'].completed_behaviors
    assert current.completed_behaviors
    assert current.contract_payload == before['feature'].contract_payload
    assert current.gatekeeper_payload == before['feature'].gatekeeper_payload
    assert current.evidence_refs == before['feature'].evidence_refs
    assert current.canonical_development_base == before['sha']
    assert frozen_files() == before['files']
    assert git(repository, 'rev-parse', 'refs/heads/main') == before['sha']
    diagnostic = current.reconciliation_failure
    assert diagnostic is not None
    assert diagnostic.checklist_ref == 'CHK-2'
    assert diagnostic.completed_results[0]['answer'] == 'NO'
    assert diagnostic.completed_results[0]['checklist_ref'] == 'CHK-1'
    assert diagnostic.accepted_test_names == ('tests/test_toggle_switch.py::test_B_1',)
    assert len(diagnostic.attempts) == (2 if failure == 'malformed' else 1)
    persisted = StrictTddRunStateRepository(state / 'runs').load('toggle-run')
    assert persisted is not None
    assert persisted.status == StrictTddRunStatus.BLOCKED
    assert persisted.transition_in_flight is None
    assert persisted.pending_transition_receipt is None
    assert persisted.last_delivered_fingerprint is not None
    assert persisted.last_delivered_fingerprint.pending_action == 'reconciliation'
    lifecycle = list((state / 'lifecycle-events').rglob('*'))
    assert any('run_blocked' in p.read_text() for p in lifecycle if p.is_file())
    assert any('feature_blocked' in p.read_text() for p in lifecycle if p.is_file())
    log_before = list(log)
    replay: Any = Factory(log, counts)
    assert main(args('resume', state, evidence)[:-2], replay) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'blocked'
    assert replay.reasoners[0].call_count == replay.gateways[0].call_count == 0
    assert replay.applications[0].transitions == []
    assert log == log_before
    assert features.load('toggle-project') == current
    assert frozen_files() == before['files']
    assert git(repository, 'rev-parse', 'refs/heads/main') == before['sha']
