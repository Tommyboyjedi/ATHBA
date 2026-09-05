import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.behavior_completion import BehaviorCompletionDependencies, BehaviorCompletionService
from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.deterministic_regression import DeterministicRegressionService, SubprocessProjectRuntimeExecutor
from core.development.microcycle_domain import LanguageAdapterCatalog
from core.development.microcycle_revision_git import MicrocycleGitClient
from core.development.microcycle_revision_service import MicrocycleRevisionLifecycle, RevisionLifecycleDependencies
from core.development.microcycle_revision_store import MicrocycleRevisionRepository
from core.development.project_environment import ProjectEnvironmentService
from core.development.provider_behavior_reviewer import ProviderSeniorBehaviorReviewer
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.scenario_drafting import (
    GitCandidateScenarioSourceReader,
    ScenarioDraftingDependencies,
    ScenarioDraftingService,
    ScenarioIntentReviewer,
)
from core.development.specification_domain import (
    SourceRequirementClause,
    SpecificationChecklist,
    SpecificationChecklistItem,
    SpecificationGatekeeperRunState,
)
from core.development.strict_microcycle import (
    GitFrontierMaterialiser,
    StrictMicrocycleDependencies,
    StrictMicrocycleService,
)
from core.development.strict_tdd_feature_application import (
    StrictTddFeatureApplicationService,
    StrictTddFeatureDependencies,
)
from core.development.strict_tdd_feature_domain import StrictTddFeatureRequest
from core.development.strict_tdd_feature_execution import (
    CompletedFeatureReconciler,
    StrictFeatureScenarioDependencies,
    StrictFeatureScenarioExecutor,
)
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_feature_composition import StrictTddCompositionRequest, StrictTddFeatureCompositionFactory
from core.execution.profiled_workspace_gateway import ProfiledWorkspaceExecutionGateway
from core.execution.reasoning_gateway import ReasoningResult
from core.execution.work_unit_gateway import WorkUnitExecutionResult


class DeterministicReasoning:
    def __init__(self):
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        payload = {
            "athba_scenario_intent_review": {
                "disposition": "approved", "feedback": "scenario directly proves the behavior",
                "evidence_refs": ["SRC-1"],
            },
            "athba_senior_behavior_review": {
                "verdict": "approved", "rationale": "green regression and scenario evidence agree",
                "findings": [], "evidence_refs": ["review-approved"],
            },
            "athba_checklist_test_reconciliation": {
                "answer": "YES", "selected_test_names": ["tests/test_B_1.py::test_B_1"],
                "rationale": "accepted test remains at the final canonical revision",
            },
        }
        return ReasoningResult(json.dumps(payload[request.purpose]))


class GitGateway:
    def __init__(self, root):
        self.root = root
        self.bindings = []

    async def execute(self, unit, binding):
        self.bindings.append(binding)
        worktree = Path(tempfile.mkdtemp(prefix="athba-feature-gateway-"))
        worktree.rmdir()
        run(self.root, "worktree", "add", "--detach", str(worktree), binding.base_sha)
        try:
            if '"role": "Tester"' in unit.objective:
                target = worktree / "tests" / "test_B_1.py"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    "# ATHBA-SCENARIO-RATIONALE: visible module value\n"
                    "# ATHBA-SOURCE-REFS: SRC-1\n"
                    "from widget import value\n\n"
                    "def test_B_1():\n"
                    "    assert value == 1\n",
                    encoding="utf-8",
                )
            else:
                (worktree / "widget.py").write_text("value = 1\n", encoding="utf-8")
            run(worktree, "add", ".")
            run(worktree, "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "-qm", unit.id)
            revision = run(worktree, "rev-parse", "HEAD").strip()
            return WorkUnitExecutionResult(
                unit.id, True, "checks_passed", branch=revision, accepted_revision=revision,
                evidence_location=f"evidence/{unit.id}",
            )
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)],
                cwd=self.root, capture_output=True, text=True, check=False,
            )
            shutil.rmtree(worktree, ignore_errors=True)


class Planner:
    def __init__(self, contract):
        self.contract = contract
        self.requests = []

    async def create_contract(self, request):
        self.requests.append(request)
        return self.contract


class Gatekeeper:
    def __init__(self):
        self.requests = []

    async def ensure_state(self, request):
        self.requests.append(request)
        item = SpecificationChecklistItem("CHK-1", "Widget exposes value 1.", "behavior")
        checklist = SpecificationChecklist(request.contract.project_id, request.contract.requirement_source, [item])
        return SpecificationGatekeeperRunState(checklist)


def test_default_composition_uses_profiled_v2_workspace_gateway(tmp_path):
    composition = StrictTddFeatureCompositionFactory().build(StrictTddCompositionRequest(tmp_path / "state", tmp_path / "repository", "feature", DeterministicReasoning()))
    assert isinstance(composition.rack_ai, ProfiledWorkspaceExecutionGateway)
    assert composition.rack_ai.port.__class__.__name__ == "RackAiWorkspaceConnector"
    assert composition.rack_ai.port.transport.__class__.__name__ == "RackAiWorkspaceCliTransport"


def feature_request():
    return StrictTddFeatureRequest(
        "feature", "Widget exposes value 1.", "python", "pytest", ("widget.py",),
        ("tests/test_B_1.py",), "python-3.14", "resume", "durable", "evidence",
    )


def feature_contract():
    clause = SourceRequirementClause("SRC-1", "Widget exposes value 1.", "behavior")
    behavior = BehaviorContractRequirement(
        "B-1", ["SRC-1"], "Widget value", "value equals 1", "assert value is one"
    )
    return BehaviorContract(
        "contract-feature", "feature", "Widget", "value", "Widget exposes value 1.",
        [clause], [behavior], [], ["widget.py"], ["tests/test_B_1.py"],
    )


@pytest.mark.asyncio
async def test_real_git_feature_composition_runs_lifecycle_and_reconciles_only_completed_evidence(tmp_path):
    state_root = tmp_path / "state"
    environment = ProjectEnvironmentService(
        state_root / "projects", python_executable="/srv/ATHBA/.venv/bin/python"
    )
    project = environment.create_or_load_python_project("feature")
    repository = Path(project.repository_root)
    reasoning = DeterministicReasoning()
    gateway = GitGateway(repository)
    adapters = LanguageAdapterCatalog((PythonPytestAdapter(),))
    microcycles = MicrocycleStateRepo(state_root / "microcycles")
    regression = DeterministicRegressionService(SubprocessProjectRuntimeExecutor())
    drafting = ScenarioDraftingService(
        ScenarioDraftingDependencies(
            gateway, ScenarioIntentReviewer(reasoning), adapters,
            GitCandidateScenarioSourceReader(repository), ScenarioDraftStateRepo(state_root / "drafts"),
        )
    )
    revisions = MicrocycleRevisionLifecycle(
        RevisionLifecycleDependencies(
            MicrocycleRevisionRepository(state_root / "revisions"), MicrocycleGitClient(repository)
        )
    )
    strict = StrictMicrocycleService(
        StrictMicrocycleDependencies(
            microcycles, GitFrontierMaterialiser(), gateway, adapters, regression,
            behavior_completion=BehaviorCompletionService(
                BehaviorCompletionDependencies(ProviderSeniorBehaviorReviewer(reasoning))
            ),
        )
    )
    scenarios = StrictFeatureScenarioExecutor(
        StrictFeatureScenarioDependencies(drafting, strict, revisions, environment)
    )
    planner = Planner(feature_contract())
    gatekeeper = Gatekeeper()
    application = StrictTddFeatureApplicationService(
        StrictTddFeatureDependencies(
            environment, StrictTddFeatureRepository(state_root / "features"), planner, gatekeeper,
            scenarios, CompletedFeatureReconciler(repository, microcycles, reasoning),
        )
    )

    result = await application.run(feature_request())

    assert result.current_status == "completed"
    assert result.working_ref is None and result.working_revision is None
    assert result.final_reconciliation[0]["answer"] == "YES"
    assert run(repository, "rev-parse", "refs/heads/main").strip() == result.canonical_development_base
    assert run(repository, "show", f"{result.canonical_development_base}:widget.py") == "value = 1\n"
    assert "def test_B_1" in run(repository, "show", f"{result.canonical_development_base}:tests/test_B_1.py")
    lifecycle = revisions.recover(type("Request", (), {"scenario_id": "feature--B-1"})())
    assert lifecycle.status == "behavior_complete"
    assert run(repository, "show-ref", "--verify", "--quiet", lifecycle.working_ref, check=False) == ""
    assert any(binding.base_ref.startswith("refs/heads/athba/microcycles/") for binding in gateway.bindings[1:])
    assert [item.purpose for item in reasoning.requests] == [
        "athba_scenario_intent_review", "athba_senior_behavior_review",
        "athba_checklist_test_reconciliation",
    ]
    resumed = await application.run(feature_request())
    assert resumed == result
    assert len(gateway.bindings) >= 2
    assert len(planner.requests) == len(gatekeeper.requests) == 1


def run(root, *args, check=True):
    completed = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    if check and completed.returncode:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.stdout
