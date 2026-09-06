"""Real Git/pytest strict-TDD lifecycle with fake execution and reasoning only."""
import json
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from core.development.behavior_contract_coordinator import BehaviorContractPlanner
from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.behavior_replan_domain import BehaviorReplanPhase
from core.development.microcycle_revision_store import MicrocycleRevisionRepository
from core.development.specification_domain import SourceRequirementClause
from core.development.strict_tdd_feature_composition import StrictTddCompositionRequest, StrictTddFeatureCompositionFactory
from core.development.strict_tdd_feature_domain import StrictTddFeatureRequest
from core.development.strict_tdd_transitions import FeatureTransitionKind
from core.execution.reasoning_gateway import ReasoningResult
from core.execution.work_unit_gateway import WorkUnitExecutionResult
from tests.development.test_strict_tdd_feature_composition import Planner, Gatekeeper, run


class PipelineReasoning:
    def __init__(self, recursive):
        self.recursive = recursive
        self.requests = []
        self.replans = []

    async def reason(self, request):
        self.requests.append(request)
        if request.purpose == "athba_behavior_requirement_replan":
            context = json.loads(request.prompt)["request"]
            self.replans.append(context)
            parent = context["parent"]
            if parent["ref"] == "REQ-005":
                outcomes = ("The x value equals 5", "The y and z values satisfy their individual constraints")
            else:
                outcomes = ("The y value equals 6", "The z value equals 7")
            payload = {"disposition": "split", "rationale": "Independent observable values need separate evidence.",
                       "coverage_rationale": "The children partition all parent value constraints with no new behavior.",
                       "children": [dict(source_refs=parent["source_refs"], summary=outcome, observable_outcome=outcome,
                                         test_hint="Assert the specified value", error_expectation=None,
                                         preserves_state_on_failure=True, narrowing_rationale="One independent part of the source value constraints.") for outcome in outcomes]}
        elif request.purpose == "athba_scenario_intent_review":
            rejected = request.project_id == "REQ-005" or (self.recursive and request.project_id == "REQ-005-S002")
            payload = {"disposition": "insufficient_evidence" if rejected else "approved",
                       "feedback": "The scenario does not cover both independent constraints" if rejected else "The scenario proves this value constraint",
                       "evidence_refs": ["SRC-1"]}
        elif request.purpose == "athba_senior_behavior_review":
            payload = {"verdict": "approved", "rationale": "Scenario and regression prove the value", "findings": [], "evidence_refs": ["senior-approved"]}
        elif request.purpose == "athba_checklist_test_reconciliation":
            # Select the actual supplied accepted-test catalogue, never invented names.
            payload = {"answer": "YES", "selected_test_names": test_names(json.loads(request.prompt)),
                       "rationale": "Accepted child tests cover the independent source checklist."}
        else:
            raise AssertionError(f"unexpected reasoning purpose {request.purpose}")
        return ReasoningResult(json.dumps(payload))


def test_names(value):
    if isinstance(value, dict):
        return ([value["test_name"]] if "test_name" in value else []) + [name for item in value.values() for name in test_names(item)]
    if isinstance(value, list):
        return [name for item in value for name in test_names(item)]
    return []

test_names.__test__ = False


class PipelineGateway:
    def __init__(self, repository, recursive):
        self.repository = repository
        self.recursive = recursive
        self.tester = Counter()
        self.developer = Counter()
        self.bindings = []

    async def execute(self, unit, binding):
        self.bindings.append(binding)
        objective = json.loads(unit.objective)
        tester = objective.get("role") == "Tester"
        if tester:
            ref = objective["ticket"]["id"]
            self.tester[ref] += 1
            assert self.tester[ref] <= 4, "Tester attempt 5 is forbidden"
            if ref == "REQ-005" and self.tester[ref] == 2:
                return WorkUnitExecutionResult(unit.id, False, "timeout", selected_worker_id="fake-worker", evidence_location=f"fake/{unit.id}")
        else:
            ref = unit.id.split("--")[1]
            self.developer[ref] += 1
        worktree = Path(tempfile.mkdtemp(prefix="athba-replan-fake-"))
        worktree.rmdir()
        run(self.repository, "worktree", "add", "--detach", str(worktree), binding.base_sha)
        try:
            variable, expected = variable_for(ref)
            if tester:
                path = worktree / objective["allowed_test_path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                name = objective["ticket"]["planned_canonical_test_identity"].split("::")[-1]
                path.write_text(
                    f"# ATHBA-SCENARIO-RATIONALE: assert an observable value; candidate {self.tester[ref]}\n"
                    "# ATHBA-SOURCE-REFS: SRC-1\nimport widget\n\n"
                    f"def {name}():\n    assert widget.{variable} == {expected}\n"
                )
            else:
                path = worktree / "widget.py"
                path.write_text(path.read_text() + f"\n{variable} = {expected}\n")
            run(worktree, "add", ".")
            run(worktree, "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "-qm", unit.id)
            revision = run(worktree, "rev-parse", "HEAD").strip()
            return WorkUnitExecutionResult(unit.id, True, "checks_passed", branch=revision,
                                           accepted_revision=revision, evidence_location=f"fake/{unit.id}")
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=self.repository, capture_output=True, check=False)
            shutil.rmtree(worktree, ignore_errors=True)


def variable_for(ref):
    if ref == "REQ-005-S001":
        return "x", 5
    if ref in {"REQ-005-S002", "REQ-005-S002-S001"}:
        return "y", 6
    if ref == "REQ-005-S002-S002":
        return "z", 7
    return "v" + ref.replace("-", "_"), int(ref[-3:])


def fixture_contract():
    requirements = [BehaviorContractRequirement(f"REQ-{index:03d}", ["SRC-1"], f"Value {index}", f"Value {index} has its specified content", "Assert value") for index in range(1, 7)]
    requirements[4] = replace(requirements[4], observable_outcome="The x y and z values meet all required constraints")
    return BehaviorContract("contract-feature", "feature", "Widget", "values", "All six source value requirements hold.",
                            [SourceRequirementClause("SRC-1", "All six source value requirements hold.", "behavior")],
                            requirements, [], ["widget.py"], [f"tests/test_{i}.py" for i in range(12)])


def build(root, reasoning, gateway):
    return StrictTddFeatureCompositionFactory().build(StrictTddCompositionRequest(
        root, gateway.repository, "feature", reasoning, gateway,
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize("recursive", [False, True])
async def test_split_children_use_real_tdd_preserve_tests_and_resume_composition(tmp_path, recursive):
    from core.development.project_environment import ProjectEnvironmentService
    state_root = tmp_path / "state"
    environment = ProjectEnvironmentService(state_root / "projects")
    project = environment.create_or_load_python_project("feature", ("widget.py",))
    repository = Path(project.repository_root)
    reasoning = PipelineReasoning(recursive)
    gateway = PipelineGateway(repository, recursive)
    composition = build(state_root, reasoning, gateway)
    composition.application.contract_planner = Planner(fixture_contract())
    gatekeeper = Gatekeeper()
    composition.application.gatekeeper = gatekeeper
    request = StrictTddFeatureRequest("feature", fixture_contract().requirement_source, "python", "pytest", ("widget.py",),
                                      tuple(fixture_contract().test_paths), "python", "resume", None, "evidence")
    before = None
    frozen_files = {}
    test_blobs = {}
    child_restart_done = False
    selected = []
    transitions = []
    for _ in range(500):
        advanced = await composition.application.advance(request)
        transitions.append(advanced)
        if advanced.kind == FeatureTransitionKind.GATEKEEPER_PERSISTED:
            composition.application.contract_planner = BehaviorContractPlanner(reasoning)
        if advanced.kind == FeatureTransitionKind.BEHAVIOR_SELECTED:
            selected.append(advanced.behavior_ref)
        if advanced.kind == FeatureTransitionKind.BEHAVIOR_REPLAN_REQUIRED and advanced.behavior_ref == "REQ-005":
            before = composition.application.states.load("feature")
            assert len(before.completed_behaviors) == 4 and gateway.tester["REQ-005"] == 4
            assert not reasoning.replans
            frozen_files = {path: path.read_bytes() for directory in ("scenario-drafts", "microcycles", "revisions")
                            for path in (state_root / directory).rglob("*.json") if any(f"REQ-{i:03d}" in path.name for i in range(1, 5))}
            for name in run(repository, "ls-tree", "-r", "--name-only", before.canonical_development_base).splitlines():
                if name.startswith("tests/test_"):
                    test_blobs[name] = run(repository, "show", f"{before.canonical_development_base}:{name}")
        if advanced.kind == FeatureTransitionKind.BEHAVIOR_SPLIT_RECEIVED:
            composition = build(state_root, reasoning, gateway)
        if advanced.kind == FeatureTransitionKind.BEHAVIOR_SPLIT and advanced.behavior_ref == "REQ-005":
            after = composition.application.states.load("feature")
            assert after.canonical_development_base == before.canonical_development_base
            assert after.completed_behaviors == before.completed_behaviors
            assert after.gatekeeper_payload == before.gatekeeper_payload
            assert after.behavior_replans[0].phase == BehaviorReplanPhase.SUPERSEDED
            assert after.behavior_replans[0].child_refs == ("REQ-005-S001", "REQ-005-S002")
            composition = build(state_root, reasoning, gateway)
        if advanced.kind == FeatureTransitionKind.BEHAVIOR_RECORDED and advanced.behavior_ref == "REQ-005-S001" and not child_restart_done:
            composition = build(state_root, reasoning, gateway)
            child_restart_done = True
        assert advanced.kind != FeatureTransitionKind.BLOCKED, composition.application.states.load("feature").to_dict()
        if advanced.kind == FeatureTransitionKind.FEATURE_COMPLETED:
            break
    else:
        pytest.fail("bounded fake pipeline failed to complete")
    state = composition.application.states.load("feature")
    assert gateway.tester["REQ-005"] == 4
    assert gateway.tester["REQ-005-S001"] == 1
    assert gateway.tester["REQ-005-S002"] == (4 if recursive else 1)
    assert len(reasoning.replans) == (2 if recursive else 1)
    parent_draft = composition.scenario_drafting.state_store.load("feature--REQ-005")
    assert len(parent_draft.attempts) == 4 and parent_draft.status == "attempts_exhausted"
    assert parent_draft.attempts[1].no_candidate_outcome == "worker_model_timeout"
    assert all(parent_draft.attempts[index].intent.status == "insufficient_evidence" for index in (0, 2, 3))
    assert len(reasoning.replans[0]["tester_failures"]["attempts"]) == 4
    assert len(reasoning.replans[0]["completed_requirements"]) == 4
    assert len(gatekeeper.requests) == 1
    assert state.gatekeeper_payload == before.gatekeeper_payload
    assert state.final_reconciliation[0]["answer"] == "YES"
    accepted = state.final_reconciliation[0]["accepted_test_names"]
    assert any("REQ_005_S001" in name for name in accepted)
    assert any(("REQ_005_S002_S002" if recursive else "REQ_005_S002") in name for name in accepted)
    assert selected == ["REQ-001", "REQ-002", "REQ-003", "REQ-004", "REQ-005", "REQ-005-S001", "REQ-005-S002", *(["REQ-005-S002-S001", "REQ-005-S002-S002"] if recursive else []), "REQ-006"]
    assert all(path.read_bytes() == contents for path, contents in frozen_files.items())
    assert all(run(repository, "show", f"{state.canonical_development_base}:{name}") == source for name, source in test_blobs.items())
    for completed in state.completed_behaviors:
        lifecycle = MicrocycleRevisionRepository(state_root / "revisions").load(completed.scenario_id)
        assert lifecycle.status == "behavior_complete"
        assert gateway.developer[completed.behavior_ref] == 1
    before_counts = (dict(gateway.tester), dict(gateway.developer), len(reasoning.requests))
    assert (await build(state_root, reasoning, gateway).application.run(request)).current_status == "completed"
    assert before_counts == (dict(gateway.tester), dict(gateway.developer), len(reasoning.requests))
