"""Pre-fix regressions for completed-behavior review material and bounded repair."""
from core.development.python_test_material import PythonTestMaterial
from core.development.strict_microcycle import DeveloperFrontierWorkUnitFactory, RegressionRepairWorkUnitFactory
from core.development.behavior_repair import BehaviorRepairWorkUnitFactory
from dataclasses import replace
import json
from types import SimpleNamespace
import pytest

@pytest.mark.asyncio
async def test_approved_scenario_retains_only_selected_behavior_authority_for_review():
    from tests.development.test_scenario_drafting import components, request, binding, accepted, candidate, approval
    req=request("catalog")
    service, _, _, _=components(
        [accepted("catalog-ticket--scenario-draft-1","candidate","change")],
        [approval("SRC-CATALOG")], {"candidate":candidate("catalog")})
    outcome=await service.draft(req,binding())
    draft=outcome.state.approved_microcycle.scenario_draft
    assert getattr(draft,"behavior_summary",None)==req.ticket.focused_behavior
    assert getattr(draft,"expected_result",None)==req.ticket.expected_result
    from core.development.microcycle_domain import TestScenarioDraft
    assert TestScenarioDraft.from_dict(json.loads(json.dumps(draft.to_dict())))==draft

def test_behavior_reviewer_distinguishes_historical_red_from_current_green():
    from core.development.provider_behavior_reviewer import _request
    req=SimpleNamespace(behavior_ticket="one-behavior",approved_scenario="one accepted test",canonical_test_identity="tests/test_one::test_one",
        production_diff="one actual change",microcycle_evidence=("valid_missing_capability_red","green"),regression_evidence=("passed",),
        behavior_summary="Compute the selected aggregate",expected_result="Return its mean",completed_revision="a"*40,
        regression_status="regression_clear",production_material=None,source_requirement_refs=("SOURCE-ONE",))
    payload=json.loads(_request(req).prompt)
    assert payload.get("historical_boundary_outcomes")==["valid_missing_capability_red","green"]
    assert "microcycle_evidence" not in payload
    assert payload["current_execution"]["regression_status"]=="regression_clear"
    assert payload["selected_behavior"]["expected_result"]=="Return its mean"
    assert "required_signatures" not in payload

@pytest.mark.asyncio
async def test_normal_repair_transition_preserves_four_attempt_bound_and_resume(tmp_path):
    from tests.development.test_behavior_repair import reviewed_state, Gateway, Runtime
    from tests.development.test_strict_microcycle import MemoryStore, CandidateRepository, request
    from core.development.behavior_repair import BehaviorRepairDependencies, BehaviorRepairService
    from core.development.deterministic_regression import DeterministicRegressionService
    from core.development.microcycle_domain import MicrocycleState,MicrocyclePendingAction,LanguageAdapterCatalog
    from core.development.python_pytest_adapter import PythonPytestAdapter
    from core.development.strict_microcycle import StrictMicrocycleService,StrictMicrocycleDependencies
    store=MemoryStore();gateway=Gateway(False);candidates=CandidateRepository(tmp_path,{"base":""})
    regression=DeterministicRegressionService(Runtime())
    repair=BehaviorRepairService(BehaviorRepairDependencies(store,candidates,gateway,regression, factory=BehaviorRepairWorkUnitFactory(test_material=PythonTestMaterial())))
    service=StrictMicrocycleService(StrictMicrocycleDependencies(store,candidates,gateway,LanguageAdapterCatalog((PythonPytestAdapter(),)),regression,behavior_repair=repair, developer_factory=DeveloperFrontierWorkUnitFactory(test_material=PythonTestMaterial()), regression_repair_factory=RegressionRepairWorkUnitFactory(test_material=PythonTestMaterial())))
    state=replace(reviewed_state(),pending_action=MicrocyclePendingAction.SUBMIT_BEHAVIOR_REPAIR.value)
    store.save(state);seen=[]
    for attempt in range(1,5):
        outcome=await service.advance(request(tmp_path,state))
        assert outcome.kind.value=="behavior_repair_candidate_rejected"
        assert outcome.state.pending_action==MicrocyclePendingAction.SUBMIT_BEHAVIOR_REPAIR.value
        assert outcome.state.behavior_review.repair.attempts==attempt
        seen.append(outcome.fingerprint.retry_counts)
        state=MicrocycleState.from_dict(json.loads(json.dumps(outcome.state.to_dict())))
        store.save(state)
    exhausted=await service.advance(request(tmp_path,state))
    assert exhausted.kind.value=="attempts_exhausted"
    assert len(gateway.units)==4
    assert len(set(seen))==4
    assert {binding.base_sha for _,binding in gateway.units}=={"base"}
    assert exhausted.state.behavior_review.repair.attempts==4

def test_repair_promotion_updates_completed_revision_before_rereview(tmp_path):
    from tests.development.test_behavior_repair import reviewed_state,Store,Gateway,Runtime,request
    from tests.development.test_strict_microcycle import CandidateRepository
    from core.development.behavior_repair import BehaviorRepairDependencies,BehaviorRepairService
    from core.development.deterministic_regression import DeterministicRegressionService
    state=reviewed_state()
    state=replace(state,behavior_review=replace(state.behavior_review,repair=replace(state.behavior_review.repair,current_candidate_revision="repair")),
                  candidate_chain_revision="repair")
    service=BehaviorRepairService(BehaviorRepairDependencies(Store(),CandidateRepository(tmp_path,{}),Gateway(),DeterministicRegressionService(Runtime()), factory=BehaviorRepairWorkUnitFactory(test_material=PythonTestMaterial())))
    outcome=service.promote(request(tmp_path,state))
    assert outcome.state.completion.completed_revision=="repair"


def git_fixture(tmp_path):
    import subprocess
    def git(*args):
        return subprocess.check_output(("git", *args), cwd=tmp_path, text=True).strip()
    git("init", "-b", "main")
    git("config", "user.name", "ATHBA fixture")
    git("config", "user.email", "fixture@example.invalid")
    (tmp_path / "widget.py").write_text("class Widget:\\n    pass\\n")
    (tmp_path / "unrelated.txt").write_text("before")
    git("add", "."); git("commit", "-m", "fixture entry")
    entry=git("rev-parse", "HEAD")
    (tmp_path / "widget.py").write_text("class Widget:\\n    def grow(self):\\n        return 1\\n")
    (tmp_path / "unrelated.txt").write_text("UNRELATED_FUTURE_SPECIFICATION")
    git("add", "."); git("commit", "-m", "fixture accepted")
    accepted=git("rev-parse", "HEAD")
    return entry, accepted


def test_production_reader_is_pinned_and_scoped_despite_working_tree_changes(tmp_path):
    from core.development.behavior_review_material import BehaviorProductionReadRequest
    from core.development.git_behavior_review_material import GitBehaviorProductionReader
    entry, accepted=git_fixture(tmp_path)
    original=(tmp_path / "widget.py").read_text()
    (tmp_path / "widget.py").write_text("UNTRUSTED_WORKING_TREE")
    material=GitBehaviorProductionReader().read(BehaviorProductionReadRequest(tmp_path,"widget.py",entry,accepted))
    assert material.source==original
    assert "return 1" in material.diff and "UNRELATED" not in material.diff
    assert material.revision==accepted and material.entry_revision==entry


@pytest.mark.parametrize("path,revision", [("../outside.txt","a"*40), ("/absolute.txt","a"*40), ("widget.py","main")])
def test_production_reader_refuses_unpinned_or_unbounded_authority(tmp_path,path,revision):
    from core.development.behavior_review_material import BehaviorProductionReadRequest
    from core.development.git_behavior_review_material import GitBehaviorProductionReader
    with pytest.raises(ValueError):
        GitBehaviorProductionReader().read(BehaviorProductionReadRequest(tmp_path,path,"a"*40,revision))


@pytest.mark.asyncio
async def test_normal_review_transition_supplies_immutable_current_material_and_selected_authority(tmp_path):
    from tests.development.test_strict_microcycle import MemoryStore,initial_state,request,Gateway,regression,CandidateRepository
    from tests.development.test_behavior_completion import Reviewer
    from core.development.behavior_completion import BehaviorCompletionDependencies,BehaviorCompletionService
    from core.development.git_behavior_review_material import GitBehaviorProductionReader
    from core.development.microcycle_domain import MicrocyclePendingAction,ScenarioCompletion,LanguageAdapterCatalog
    from core.development.python_pytest_adapter import PythonPytestAdapter
    from core.development.strict_microcycle import StrictMicrocycleDependencies,StrictMicrocycleService
    entry,accepted=git_fixture(tmp_path)
    initial=initial_state()
    start=replace(initial,development_base_revision=entry,scenario_draft=replace(initial.scenario_draft,behavior_summary="One selected behavior",expected_result="One expected result"))
    state=replace(start,scenario_draft=replace(start.scenario_draft,behavior_summary="One selected behavior",expected_result="One expected result"),
                  development_base_revision=accepted,completion=ScenarioCompletion("scenario_complete",accepted),
                  pending_action=MicrocyclePendingAction.REVIEW_BEHAVIOR.value)
    reviewer=Reviewer("approved"); store=MemoryStore(); store.save(state)
    service=StrictMicrocycleService(StrictMicrocycleDependencies(store,CandidateRepository(tmp_path,{}),Gateway([]),
        LanguageAdapterCatalog((PythonPytestAdapter(),)),regression(),
        behavior_completion=BehaviorCompletionService(BehaviorCompletionDependencies(reviewer)),
        behavior_production_reader=GitBehaviorProductionReader(), developer_factory=DeveloperFrontierWorkUnitFactory(test_material=PythonTestMaterial()), regression_repair_factory=RegressionRepairWorkUnitFactory(test_material=PythonTestMaterial())))
    await service.advance(request(tmp_path,start))
    req=reviewer.requests[0]
    assert req.behavior_summary=="One selected behavior" and req.expected_result=="One expected result"
    assert req.production_material.revision==accepted
    assert req.production_material.entry_revision==entry
    assert "return 1" in req.production_material.source and "return 1" in req.production_diff
    assert "UNRELATED" not in req.production_diff
    assert req.completed_revision==accepted
