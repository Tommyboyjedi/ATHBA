"""Real RunningTotal source uses ordinary grounded checklist split routing."""
import json
from dataclasses import replace

import pytest

from core.development.specification_domain import SpecificationChecklistItem
from core.development.specification_atomization import ChecklistSplitRequest, SpecificationChecklistPlanner
from core.development.specification_evidence_policy import EvidencePolicyRouter
from core.development.specification_obligations import EvidencePolicy
from core.execution.reasoning_gateway import ReasoningResult

SOURCE = "Provide a RunningTotal class in running_total.py. A newly created RunningTotal starts with a total of zero. Calling add(amount) adds the signed integer amount to its running total. Calling total() returns the current total without changing it. Adding 3 and then -1 must expose a total of 2. Keep the implementation dependency-free and in memory."
QUOTE = "Keep the implementation dependency-free and in memory."
PARENT = SpecificationChecklistItem("REQ-006", QUOTE, "constraint", "required", QUOTE, "dependency-free and in memory")


class Gateway:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        return ReasoningResult(json.dumps(next(self.responses)))


def response():
    return {"disposition": "split", "rationale": "Two independently grounded obligations", "children": [
        {"text": "Keep the implementation " + subject + ".", "kind": "constraint",
         "modality": "required", "source_quote": QUOTE, "subject": subject}
        for subject in ("dependency-free", "in memory")]}


def request():
    return ChecklistSplitRequest("project", SOURCE, PARENT.ref, PARENT.text, PARENT.kind,
                                 PARENT.modality, PARENT.source_quote, PARENT.subject, (), "revision")


@pytest.mark.asyncio
async def test_atomic_source_children_route_to_separate_verifiers():
    assert EvidencePolicyRouter().route_source(PARENT, SOURCE).policy == EvidencePolicy.UNSUPPORTED
    gateway = Gateway([response()])
    split = await SpecificationChecklistPlanner(gateway).split_item(request())
    assert split.disposition == "split"
    assert [EvidencePolicyRouter().route_source(child, SOURCE).policy for child in split.children] == [
        EvidencePolicy.DEPENDENCY, EvidencePolicy.STORAGE]
    assert all(child.modality == PARENT.modality and child.source_quote == QUOTE for child in split.children)


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["missing", "invented", "modality"])
async def test_split_cannot_drop_invent_or_weaken_mechanical_obligations(mutation):
    invalid = response()
    if mutation == "missing":
        invalid["children"][1]["subject"] = "dependency-free"
    elif mutation == "invented":
        invalid["children"][1]["subject"] = "RunningTotal"
        invalid["children"][1]["source_quote"] = SOURCE
    else:
        invalid["children"][1]["modality"] = "non_goal"
    gateway = Gateway([invalid, invalid])
    split = await SpecificationChecklistPlanner(gateway).split_item(request())
    assert split.disposition != "split"
    assert len(gateway.requests) == 2


@pytest.mark.asyncio
async def test_real_completed_reconciliation_splits_mechanical_parent(fixture, monkeypatch):
    from tests.development.test_gatekeeper_progress_resume import run
    from core.development.specification_domain import SpecificationChecklist, SpecificationGatekeeperRunState
    root, repo, _ = fixture
    (root / "component.py").write_text("class RunningTotal:\n    def __init__(self):\n        self.value = 0\n")
    from tests.development.test_gatekeeper_progress_resume import git
    git(root, "add", "component.py")
    git(root, "-c", "user.name=Fake", "-c", "user.email=fake@example.test", "commit", "-qm", "production")
    revision = git(root, "rev-parse", "HEAD")
    current = repo.load("project-1")
    checklist = SpecificationChecklist("project-1", SOURCE, [PARENT])
    repo.save(replace(current, gatekeeper_payload=SpecificationGatekeeperRunState(checklist).to_dict(),
                      canonical_development_base=revision))
    gateway = Gateway([response()])
    from types import SimpleNamespace
    from core.development.strict_tdd_feature_execution import CompletedFeatureReconciler
    from core.development.strict_tdd_feature_application import FeatureReconciliationRequest
    from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
    from tests.development.test_test_evidence_reconciliation import _contract
    monkeypatch.setattr(CompletedFeatureReconciler, "_state", lambda self, identifier: SimpleNamespace(model=SimpleNamespace(language_id="python")))
    reconciler = CompletedFeatureReconciler(root, MicrocycleStateRepo(root / "microcycles"), gateway)
    result = await reconciler.reconcile(FeatureReconciliationRequest(
        _contract(), (SimpleNamespace(scenario_id="completed"),), SpecificationGatekeeperRunState(checklist).to_dict(), revision))
    assert result[0]["status"] == "superseded"
    assert [record["answer"] for record in result[1:]] == ["YES", "YES"]
    assert len(gateway.requests) == 1

from tests.development.test_gatekeeper_progress_resume import fixture
