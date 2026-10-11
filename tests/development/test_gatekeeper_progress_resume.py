"""Fake-only restarts through freshly loaded feature state and real Git evidence."""
from core.development.python_specification_evidence import PythonSpecificationEvidenceAdapter
from core.development.specification_evidence_policy import SpecificationEvidenceAdapters
from core.development.python_test_material import PythonTestMaterial
from collections import Counter
from dataclasses import replace
import json
import subprocess

import pytest

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.development.reconciliation_progress import ChecklistItemProgress
from core.development.reconciliation_response import ReconciliationFailure, ReconciliationFailureKind
from core.development.specification_domain import SpecificationChecklist, SpecificationChecklistItem, SpecificationGatekeeperRunState
from core.development.specification_reconciliation import AcceptedTestEvidence, CompletedMicrocycleEvidenceCollector
from core.development.strict_tdd_feature_application import FeatureReconciliationRequest
from core.development.strict_tdd_feature_domain import StrictTddFeatureState
from core.development.strict_tdd_feature_execution import CompletedFeatureReconciler
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.execution.reasoning_gateway import ReasoningResult
from tests.development.test_test_evidence_reconciliation import _contract

SOURCE = "Return the latest payload and retain history and report status."
NAMES = tuple(f"tests/test_values.py::test_{name}" for name in "ABC")


class Restart(BaseException):
    pass


def child(text):
    return {"text": text, "kind": "behavior", "modality": "required",
            "source_quote": SOURCE, "subject": "payload"}


def split(*texts):
    return {"disposition": "split", "rationale": "Separate source obligations",
            "children": [child(text) for text in texts]}


class Gateway:
    def __init__(self, answers=None, splits=None):
        self.answers = answers or {}
        self.splits = splits or {}
        self.tests = []
        self.split_calls = []
        self.prompts = []

    async def reason(self, request):
        prompt = json.loads(request.prompt)
        self.prompts.append(prompt)
        if request.purpose in {"athba_specification_checklist_split", "athba_specification_checklist_split_repair"}:
            ref = prompt["parent"]["ref"]
            self.split_calls.append(ref)
            response = self.splits.get(ref, {"disposition": "not_produced", "rationale": "No validated partition"})
        else:
            assert request.purpose == "athba_checklist_test_reconciliation"
            assert len(prompt["accepted_tdd_tests"]) == 1
            ref = prompt["checklist_item"]["ref"]
            name = prompt["accepted_tdd_tests"][0]["test_name"]
            self.tests.append((ref, name))
            answer = self.answers.get((ref, name), "NO")
            response = {"answer": answer, "selected_test_names": [name] if answer == "YES" else [],
                        "rationale": f"{name} independently answered {answer}"}
        return ReasoningResult(json.dumps(response))


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, text=True, capture_output=True).stdout.strip()


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path / "repository"
    (root / "tests").mkdir(parents=True)
    (root / "tests/test_values.py").write_text("\n\n".join(f"def test_{name}():\n    assert True" for name in "ABC"))
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "-c", "user.name=Fake", "-c", "user.email=fake@example.test", "commit", "-qm", "fixture")
    revision = git(root, "rev-parse", "HEAD")
    accepted = [AcceptedTestEvidence(name, "tests/test_values.py", str(index), [], "red", revision)
                for index, name in enumerate(NAMES)]
    monkeypatch.setattr(CompletedMicrocycleEvidenceCollector, "collect", lambda self, states: list(accepted))
    checklist = SpecificationChecklist("project-1", SOURCE, [SpecificationChecklistItem(
        "CHK-1", "Return the latest payload", "behavior", "required", SOURCE, "payload")])
    payload = SpecificationGatekeeperRunState(checklist).to_dict()
    repo = StrictTddFeatureRepository(tmp_path / "features")
    repo.save(StrictTddFeatureState("project-1", "source-hash", "running",
        contract_payload=_contract().to_dict(), gatekeeper_payload=payload,
        canonical_ref="refs/heads/main", canonical_development_base=revision))
    return root, repo, accepted


async def run(fixture, gateway, stop=None):
    root, prior_repo, _ = fixture
    repo = StrictTddFeatureRepository(prior_repo.root)
    current = repo.load("project-1")
    assert current is not None
    assert current.gatekeeper_payload is not None and current.canonical_development_base is not None

    def checkpoint(progress):
        state = repo.load("project-1")
        assert state is not None
        repo.save(replace(state, reconciliation_progress=progress))
        loaded = repo.load("project-1")
        assert loaded is not None
        if stop is not None and stop([ChecklistItemProgress.from_dict(item)
                                      for item in loaded.reconciliation_progress]):
            raise Restart()

    request = FeatureReconciliationRequest(_contract(), (), current.gatekeeper_payload,
        current.canonical_development_base, current.reconciliation_progress, checkpoint)
    return await CompletedFeatureReconciler(root, MicrocycleStateRepo(root / "microcycles"), gateway, test_material=PythonTestMaterial(), evidence_adapters=SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),))).reconcile(request)


def progress(fixture):
    state = StrictTddFeatureRepository(fixture[1].root).load("project-1")
    assert state is not None
    return [ChecklistItemProgress.from_dict(item) for item in state.reconciliation_progress]


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2])
async def test_mid_item_restart_continues_at_next_test(fixture, count):
    first = Gateway()
    with pytest.raises(Restart):
        await run(fixture, first, lambda nodes: len(nodes[0].individual_attempts) == count)
    assert first.tests == [("CHK-1", name) for name in NAMES[:count]]
    restored = progress(fixture)[0]
    assert [attempt.evaluation_order for attempt in restored.individual_attempts] == list(range(count))
    assert all(attempt.trusted_revision == fixture[2][0].semantic_revision
               and attempt.evidence_identity and attempt.response_attempts for attempt in restored.individual_attempts)
    second = Gateway({("CHK-1", NAMES[-1]): "YES"})
    result = await run(fixture, second)
    assert second.tests == [("CHK-1", name) for name in NAMES[count:]]
    assert result[0]["answer"] == "YES"
    assert len(progress(fixture)[0].individual_attempts) == 3
    assert all(count == 1 for count in Counter(first.tests + second.tests).values())


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["answer", "completion"])
async def test_no_then_yes_restart_does_not_repeat_completed_item(fixture, boundary):
    first = Gateway({("CHK-1", NAMES[1]): "YES"})
    with pytest.raises(Restart):
        await run(fixture, first, lambda nodes: (
            len(nodes[0].individual_attempts) == 2 if boundary == "answer" else nodes[0].result is not None))
    for _ in range(3):
        resumed = Gateway()
        result = await run(fixture, resumed)
        assert result[0]["answer"] == "YES"
        assert resumed.tests == resumed.split_calls == []
    assert len(progress(fixture)) == 1
    assert len(progress(fixture)[0].individual_attempts) == 2










@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["revision", "evidence", "source", "missing_test"])
async def test_incompatible_progress_fails_closed_before_any_reasoning(fixture, change):
    with pytest.raises(Restart):
        await run(fixture, Gateway(), lambda nodes: len(nodes[0].individual_attempts) == 1)
    root, repo, accepted = fixture
    state = repo.load("project-1")
    if change == "revision":
        (root / "new.py").write_text("value = 1")
        git(root, "add", ".")
        git(root, "-c", "user.name=Fake", "-c", "user.email=fake@example.test", "commit", "-qm", "new revision")
        repo.save(replace(state, canonical_development_base=git(root, "rev-parse", "HEAD")))
    elif change == "evidence":
        accepted[0] = replace(accepted[0], red_revision="different")
    elif change == "missing_test":
        accepted.pop()
    else:
        payload = json.loads(json.dumps(state.gatekeeper_payload))
        payload["checklist"]["items"][0]["text"] = "Changed obligation"
        repo.save(replace(state, gatekeeper_payload=payload))
    resumed = Gateway()
    with pytest.raises(ReconciliationFailure) as caught:
        await run(fixture, resumed)
    assert caught.value.kind == ReconciliationFailureKind.INCOMPATIBLE_PROGRESS
    assert resumed.tests == resumed.split_calls == []


@pytest.mark.asyncio
async def test_unknown_inflight_result_is_not_resubmitted(fixture):
    with pytest.raises(Restart):
        await run(fixture, Gateway(), lambda nodes: bool(nodes[0].pending_call))
    replay = Gateway()
    with pytest.raises(ReconciliationFailure) as caught:
        await run(fixture, replay)
    assert caught.value.kind == ReconciliationFailureKind.INTERRUPTED
    assert replay.tests == replay.split_calls == []





@pytest.mark.asyncio
async def test_duplicate_accepted_test_identity_is_not_evaluated_twice(fixture):
    fixture[2].append(fixture[2][0])
    gateway = Gateway()
    with pytest.raises(ReconciliationFailure) as caught:
        await run(fixture, gateway)
    assert caught.value.kind == ReconciliationFailureKind.INCOMPATIBLE_PROGRESS
    assert gateway.tests == gateway.split_calls == []



@pytest.mark.asyncio
async def test_completed_root_moves_to_next_checklist_item_after_restart(fixture):
    repo = fixture[1]
    state = repo.load("project-1")
    payload = json.loads(json.dumps(state.gatekeeper_payload))
    payload["checklist"]["items"].append({**child("Report status"), "ref": "CHK-2"})
    repo.save(replace(state, gatekeeper_payload=payload))
    with pytest.raises(Restart):
        await run(fixture, Gateway({("CHK-1", NAMES[1]): "YES"}),
                  lambda nodes: len(nodes[0].individual_attempts) == 2)
    replay = Gateway({("CHK-2", NAMES[0]): "YES"})
    results = await run(fixture, replay)
    assert [item["checklist_ref"] for item in results] == ["CHK-1", "CHK-2"]
    assert replay.tests == [("CHK-2", NAMES[0])]
    assert all(item["answer"] == "YES" for item in results)

@pytest.mark.asyncio
async def test_behavioral_no_is_durable_without_independent_checklist_split(fixture):
    gateway = Gateway(splits={"CHK-1": split("Retain history", "Report status")})
    records = await run(fixture, gateway)
    assert records[0]["answer"] == "NO"
    assert gateway.split_calls == []
    assert len(gateway.tests) == 3
    replay = Gateway()
    assert await run(fixture, replay) == records
    assert replay.tests == replay.split_calls == []
