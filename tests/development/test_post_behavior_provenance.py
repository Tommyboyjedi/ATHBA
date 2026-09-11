"""PR30 candidates reuse the original Gatekeeper's source provenance and storage policy."""
from dataclasses import replace

import pytest

from core.development.post_behavior_composition import PostBehaviorCompositionFactory, PostBehaviorCompositionRequest
from core.development.post_behavior_domain import PostBehaviorStatus
from core.development.specification_domain import SpecificationChecklistItem, SpecificationGatekeeperRunState
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from tests.development.test_post_behavior_integration import (
    PROJECT, REFACTORED, GenericGitExecution, configured_gateway, evidence_records, gatekeeper_yes, seeded_delivery,
)

SOURCE = "Keep the implementation dependency-free and in memory."


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["naming", "refactoring"])
async def test_post_behavior_candidates_reach_real_storage_and_reject_opaque_effects(tmp_path, monkeypatch, phase):
    state_root, root, entry, baseline = seeded_delivery(tmp_path)
    features = StrictTddFeatureRepository(state_root / "features")
    feature = features.load(PROJECT)
    keeper = SpecificationGatekeeperRunState.from_dict(feature.gatekeeper_payload)
    checklist = replace(keeper.checklist, requirement_text=keeper.checklist.requirement_text + " " + SOURCE,
        items=[*keeper.checklist.items, SpecificationChecklistItem(
            "memory", "Keep the implementation in memory.", "constraint", "required",
            "Keep the implementation ... in memory.", "in memory")])
    features.save(replace(feature, gatekeeper_payload=replace(keeper, checklist=checklist).to_dict(),
        final_reconciliation=(*feature.final_reconciliation, {"checklist_ref": "memory", "answer": "YES"})))
    assessment = ("LegacyCounter -> SumCounter" if phase == "naming" else
        "YES\nobjective: Replace duplicated accumulation with one sum calculation.\nreason: Removes an identical loop.")
    responses = (["NO"] if phase == "refactoring" else []) + [assessment, gatekeeper_yes()]
    gateway, calls = configured_gateway(monkeypatch, responses)
    import core.development.python_specification_evidence as evidence
    observed = []
    original = evidence.storage_findings
    def storage(trees):
        observed.append(trees)
        return original(trees)
    monkeypatch.setattr(evidence, "storage_findings", storage)
    execution = GenericGitExecution(root, tmp_path)
    execution.refactored_source = REFACTORED.replace("SumCounter", "LegacyCounter")
    request = PostBehaviorCompositionRequest(state_root, PROJECT, gateway, execution)
    for _ in range(30):
        state = await PostBehaviorCompositionFactory().build(request).advance(PROJECT)
        if state.terminal:
            break
    # Provenance only opens evidence assessment. Existing opaque-operator policy
    # rejects these loop/sum implementations; neither candidate may be promoted.
    assert state.status == PostBehaviorStatus.BLOCKED
    assert len(observed) == len(execution.calls) == 1
    assert len(calls) == (2 if phase == "naming" else 3)
    assert not responses
    assert state.behaviorally_accepted_revision == state.current_post_behavior_revision == baseline
    records = [item["payload"] for item in evidence_records(state_root)
               if item["kind"] == "specification_reconciliation"]
    assert len(records) == 1
    memory = next(item for item in records[0]["results"] if item["checklist_ref"] == "memory")
    assert memory["answer"] == "NO"
    assert memory["evidence_policy"] == "no_storage"
    assert "opaque" in memory["rationale"]
    assert "provenance mismatch" not in memory["rationale"]
    assert memory["source_item"]["source_quote"] == "Keep the implementation ... in memory."
    assert memory["adapter"]["id"] == "python-specification"
