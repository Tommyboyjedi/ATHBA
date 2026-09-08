"""Zero-provider reconciliation output contract and bounded recovery tests."""
import json
from typing import cast

import pytest

from core.development.specification_reconciliation import (
    AcceptedTestEvidence, ChecklistItemReconciler, ChecklistReconciliationRequest, GitAcceptedTestCatalog,
)
from core.development.reconciliation_response import ReconciliationFailure, ReconciliationFailureKind
from core.execution.reasoning_gateway import ReasoningResult


class Gateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return ReasoningResult(result)


class Catalog:
    def __init__(self, preserved=True):
        self.preserved = preserved
        self.calls = []

    def verified_source(self, evidence):
        self.calls.append(evidence)
        return "def test_value():\n    assert True" if self.preserved else None

    def contains(self, evidence):
        return self.preserved


def item():
    evidence = AcceptedTestEvidence('tests/test_value.py::test_value', 'tests/test_value.py', 'B-1', ['SRC-1'], 'red', 'final')
    return ChecklistReconciliationRequest('project-one', 'CHK-1', 'Independent item', [evidence])


def output(answer='NO', names=()):
    return json.dumps({'answer': answer, 'selected_test_names': list(names), 'rationale': 'previous decision'})


@pytest.mark.asyncio
@pytest.mark.parametrize('answer', ['YES', 'NO'])
async def test_valid_response_records_verified_result(answer):
    names = [item().accepted[0].test_name] if answer == 'YES' else []
    gateway, catalog = Gateway([output(answer, names)]), Catalog()
    result = await ChecklistItemReconciler(gateway, cast(GitAcceptedTestCatalog, catalog)).reconcile(item())
    assert result.answer == answer
    assert result.accepted_test_names == names
    assert len(catalog.calls) == 1
    assert len(result.response_attempts) == 1
    assert result.response_attempts[0].outcome == 'valid'
    assert result.supplied_test_names == (item().accepted[0].test_name,)


@pytest.mark.asyncio
@pytest.mark.parametrize('text', ['```json\n' + output() + '\n```', '```\n' + output() + '\n```'])
async def test_one_format_repair_succeeds_without_new_checklist_or_evidence(text):
    gateway = Gateway([text])
    result = await ChecklistItemReconciler(gateway, cast(GitAcceptedTestCatalog, Catalog())).reconcile(item())
    assert result.answer == 'NO'
    assert len(gateway.requests) == 1
    assert [attempt.format_repair for attempt in result.response_attempts] == [False]



@pytest.mark.asyncio
@pytest.mark.parametrize('text', [
    'before\n```json\n' + output() + '\n```',
    '```json\n' + output() + '\n```\nafter',
])
async def test_surrounding_prose_is_rejected(text):
    gateway = Gateway([text, '{'])
    with pytest.raises(ReconciliationFailure) as caught:
        await ChecklistItemReconciler(gateway, cast(GitAcceptedTestCatalog, Catalog())).reconcile(item())
    assert caught.value.kind == ReconciliationFailureKind.MALFORMED
    assert len(gateway.requests) == 2


@pytest.mark.asyncio
async def test_malformed_fenced_json_remains_malformed():
    gateway = Gateway(['```json\n{\n```', '{'])
    with pytest.raises(ReconciliationFailure) as caught:
        await ChecklistItemReconciler(gateway, cast(GitAcceptedTestCatalog, Catalog())).reconcile(item())
    assert caught.value.kind == ReconciliationFailureKind.MALFORMED
    assert len(gateway.requests) == 2


@pytest.mark.asyncio
async def test_fenced_wrong_schema_fails_without_format_repair():
    gateway = Gateway(['```\n{"answer": "NO", "selected_test_names": []}\n```'])
    with pytest.raises(ReconciliationFailure) as caught:
        await ChecklistItemReconciler(gateway, cast(GitAcceptedTestCatalog, Catalog())).reconcile(item())
    assert caught.value.kind == ReconciliationFailureKind.SCHEMA
    assert len(gateway.requests) == 1
@pytest.mark.asyncio
async def test_second_malformed_output_stops_typed_without_third_submission():
    gateway = Gateway(['prose', '{', output()])
    with pytest.raises(ReconciliationFailure) as caught:
        await ChecklistItemReconciler(gateway, cast(GitAcceptedTestCatalog, Catalog())).reconcile(item())
    error = caught.value
    assert not isinstance(error, ValueError)
    assert error.kind == ReconciliationFailureKind.MALFORMED
    assert error.checklist_ref == 'CHK-1'
    assert error.accepted_test_names == (item().accepted[0].test_name,)
    assert [a.submission for a in error.attempts] == [1, 2]
    assert all(a.response_sha256 for a in error.attempts)
    assert len(gateway.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [[], None, {},
    {'answer': 'NO', 'selected_test_names': []},
    {'answer': 'NO', 'selected_test_names': [], 'rationale': 0},
    {'answer': 'YES', 'selected_test_names': 'test', 'rationale': ''},
    {'answer': 'YES', 'selected_test_names': [42], 'rationale': ''},
    {'answer': 'MAYBE', 'selected_test_names': [], 'rationale': ''},
    {'answer': [], 'selected_test_names': [], 'rationale': ''},
    {'answer': 'NO', 'selected_test_names': ['test'], 'rationale': ''},
    {'answer': 'NO', 'selected_test_names': [], 'rationale': '', 'extra': True},
])
async def test_invalid_schema_or_answer_fails_without_semantic_rereview(payload):
    gateway = Gateway([json.dumps(payload)])
    with pytest.raises(ReconciliationFailure) as caught:
        await ChecklistItemReconciler(gateway, cast(GitAcceptedTestCatalog, Catalog())).reconcile(item())
    assert caught.value.kind in {ReconciliationFailureKind.SCHEMA, ReconciliationFailureKind.SEMANTIC}
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('names,preserved', [(['invented'], True), ([], True), ([item().accepted[0].test_name], False)])
async def test_unverified_yes_is_legitimate_no_not_protocol_failure(names, preserved):
    gateway = Gateway([output('YES', names)])
    result = await ChecklistItemReconciler(gateway, cast(GitAcceptedTestCatalog, Catalog(preserved))).reconcile(item())
    assert result.answer == 'NO' and result.accepted_test_names == []
    assert len(gateway.requests) == (0 if not preserved else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure,kind', [
    (OSError('transport unavailable'), ReconciliationFailureKind.PROVIDER),
    (RuntimeError('gateway unavailable'), ReconciliationFailureKind.PROVIDER),
])
@pytest.mark.parametrize('repair', [False, True])
async def test_provider_failure_is_distinct_and_never_retried(failure, kind, repair):
    gateway = Gateway((['prose'] if repair else []) + [failure])
    with pytest.raises(ReconciliationFailure) as caught:
        await ChecklistItemReconciler(gateway, cast(GitAcceptedTestCatalog, Catalog())).reconcile(item())
    assert caught.value.kind == kind
    assert len(caught.value.attempts) == 1 + int(repair)
    assert len(gateway.requests) == 1 + int(repair)


@pytest.mark.asyncio
@pytest.mark.parametrize('first,second', [
    ('prose', output()),
    ('{', output()),
])
async def test_repair_cannot_invent_or_change_a_decision(first, second):
    gateway = Gateway([first, second])
    with pytest.raises(ReconciliationFailure):
        await ChecklistItemReconciler(gateway, cast(GitAcceptedTestCatalog, Catalog())).reconcile(item())
    assert len(gateway.requests) == 2


@pytest.mark.asyncio
async def test_behavioral_evidence_is_isolated_and_stops_on_third_yes():
    accepted = [
        AcceptedTestEvidence(f"tests/test_value.py::test_REQ_00{index}", "tests/test_value.py", f"B-{index}", [], "red", "final")
        for index in range(1, 6)
    ]
    gateway = Gateway([
        output("NO"), output("NO"), output("YES", [accepted[2].test_name]),
    ])
    result = await ChecklistItemReconciler(gateway, cast(GitAcceptedTestCatalog, Catalog())).reconcile(
        ChecklistReconciliationRequest("signal-board", "get_latest_payload",
            "The system must allow asking for the latest payload for a signal and return the most recently published value.", accepted)
    )
    assert result.answer == "YES"
    assert result.accepted_test_names == [accepted[2].test_name]
    assert [attempt["test_name"] for attempt in result.individual_test_attempts] == [item.test_name for item in accepted[:3]]
    assert len(gateway.requests) == 3
    assert all(len(json.loads(request.prompt)["accepted_tdd_tests"]) == 1 for request in gateway.requests)


@pytest.mark.asyncio
async def test_first_individual_yes_makes_one_call():
    accepted = [
        AcceptedTestEvidence("tests/test_value.py::test_REQ_001", "tests/test_value.py", "B-1", [], "red", "final"),
        AcceptedTestEvidence("tests/test_value.py::test_REQ_002", "tests/test_value.py", "B-2", [], "red", "final"),
    ]
    gateway = Gateway([output("YES", [accepted[0].test_name])])
    result = await ChecklistItemReconciler(gateway, cast(GitAcceptedTestCatalog, Catalog())).reconcile(
        ChecklistReconciliationRequest("project", "CHK-1", "Independent item", accepted)
    )
    assert result.answer == "YES"
    assert len(gateway.requests) == 1
    assert len(result.individual_test_attempts) == 1
