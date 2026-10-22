"""Controlled completed histories backed by real disposable Git revisions."""
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.consolidation_composition import ConsolidationCompositionRequest, compose_consolidation
from core.development.consolidation_material import ConsolidationContext
from core.development.consolidation_reasoning import AUTHOR_PURPOSE, PROPOSAL_PURPOSE, REVIEW_PURPOSE
from core.development.deterministic_regression import DeterministicRegressionService, SubprocessProjectRuntimeExecutor
from core.development.microcycle_domain import (
    BehaviorReviewState, FragmentationRequest, MicrocycleState, RegressionState,
    RetryCounts, ScenarioCompletion, ScenarioFrontier, ScenarioIntentResult,
    ScenarioParseRequest, TestScenarioDraft as ScenarioDraft,
)
from core.development.project_environment import ProjectEnvironmentService
from core.development.project_revision_synchronization import TrustedProjectRevisionSynchronizer
from core.development.python_production_reduction import PythonProductionReductionAdapter
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.python_test_material import PythonTestMaterial
from core.development.scenario_drafting_domain import ScenarioDraftRunState
from core.development.specification_domain import SourceRequirementClause
from core.development.strict_tdd_feature_domain import CompletedBehaviorReference, StrictTddFeatureState
from core.execution.reasoning_gateway import ReasoningResult

PATH = "tests/test_shopping_basket.py"
SOURCE = ("Provide a ShoppingBasket class. A new basket is empty. unrelated() returns 9. "
          "add_item(name, price) records a price. total_price() returns the sum of prices. A third example has total 7.")
PREFIX = "from shopping_basket import ShoppingBasket\n\n"
FIRST = PREFIX + "def test_REQ_001():\n    empty = ShoppingBasket()\n    assert empty.get_total_price() == 0\n"
OTHER = PREFIX + "def test_other():\n    assert ShoppingBasket().unrelated() == 9\n"
LAST = (PREFIX + "def test_REQ_004():\n    populated = ShoppingBasket()\n"
        "    populated.add_item('apple', 2)\n    populated.add_item('banana', 3)\n"
        "    assert populated.total_price() == 5\n")
COMBINED = (PREFIX + "def test_REQ_004():\n    empty = ShoppingBasket()\n"
            "    assert empty.total_price() == 0\n    populated = ShoppingBasket()\n"
            "    populated.add_item('apple', 2)\n    populated.add_item('banana', 3)\n"
            "    assert populated.total_price() == 5\n")
PRODUCTION_FIRST = ("class ShoppingBasket:\n    def __init__(self):\n        self._items = []\n\n"
                    "    def get_total_price(self):\n        return sum(self._items)\n")
PRODUCTION_OTHER = PRODUCTION_FIRST + "\n    def unrelated(self):\n        return 9\n"
PRODUCTION_FINAL = (PRODUCTION_OTHER + "\n    def add_item(self, name, price):\n        self._items.append(price)\n\n"
                    "    def total_price(self):\n        return sum(self._items)\n")


def git(root, *arguments):
    return subprocess.run(("git", *arguments), cwd=root, text=True,
                          capture_output=True, check=True).stdout.strip()


def commit(root, message):
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


class ControlledReasoning:
    def __init__(self, source=COMBINED, approve=True, propose=True):
        self.source = source
        self.approve = approve
        self.propose = propose
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        body = json.loads(request.prompt)
        refs = body["authority_refs"]
        if request.purpose == PROPOSAL_PURPOSE:
            return ReasoningResult(json.dumps({"decision": "YES" if self.propose else "NO",
                "description": "Preserve empty and populated independent examples."}))
        if request.purpose == AUTHOR_PURPOSE:
            name = body["replacement_test_name"]
            return ReasoningResult(json.dumps({"source": self.source, "coverage": [
                {"authority_ref": ref, "replacement_test": name,
                 "description": "Preserve this exact original authority and its independent observation."}
                for ref in refs]}))
        assert request.purpose == REVIEW_PURPOSE
        return ReasoningResult(json.dumps({"disposition": "approved" if self.approve else "wrong_behavior",
            "feedback": "Both independent setups and original inputs/results preserved." if self.approve
                else "The empty-basket observation was omitted, even though the final-total test is GREEN.",
            "evidence_refs": refs}))


@dataclass
class ConsolidationFixture:
    root: Path
    state_root: Path
    environment: ProjectEnvironmentService
    state: StrictTddFeatureState
    service: object
    gateway: ControlledReasoning
    history: tuple[str, ...]

    @property
    def context(self):
        return ConsolidationContext(self.state, self.environment.repo.load("proof"))

    def active(self, state=None):
        return self.service.dependencies.material._active(state or self.state)


def save_completed(fixture, ref, source, before, after):
    adapter = PythonPytestAdapter()
    name = PATH + "::" + ("test_other" if ref == "OTHER" else "test_" + ref.replace("-", "_"))
    scenario = "proof--" + ref
    refs = ("S-" + ref,)
    draft = ScenarioDraft(scenario, ref, "python", source, name, PATH,
                          source_requirement_refs=refs, behavior_summary=ref, expected_result="source observation")
    model = adapter.parse_scenario(ScenarioParseRequest(draft))
    fragments = adapter.fragment_scenario(FragmentationRequest(model))
    frontier = ScenarioFrontier(scenario, len(fragments) - 1, fragments[-1].fragment_id,
                                tuple(item.fragment_id for item in fragments))
    state = MicrocycleState(draft, ScenarioIntentResult(scenario, "approved", "controlled original evidence"),
        model, fragments, frontier, after, None, RetryCounts(), (), (),
        RegressionState("regression_clear", (sys.executable, "-m", "pytest", "-q")),
        ScenarioCompletion("behavior_complete", after),
        behavior_review=BehaviorReviewState(verdict="approved", reviewed_candidate_revision=after))
    MicrocycleStateRepo(fixture.state_root / "microcycles").save(state)
    ScenarioDraftStateRepo(fixture.state_root / "scenario-drafts").save(ScenarioDraftRunState(
        scenario, ref, refs, "python", "pytest", PATH, before,
        approved_microcycle=state, status="approved", project_synchronised=True))
    return CompletedBehaviorReference(ref, scenario, after, ("controlled-accepted:" + after,))


def make_fixture(tmp_path, gateway=None):
    state_root = tmp_path / "state"
    environment = ProjectEnvironmentService(state_root / "projects")
    project = environment.create_or_load_python_project("proof", ("shopping_basket.py",))
    root = Path(project.repository_root)
    git(root, "config", "user.name", "Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    first_base = project.trusted_base_sha
    placeholder = ConsolidationFixture(root, state_root, environment, None, None,
                                       gateway or ControlledReasoning(), ())
    completed = []
    material = PythonTestMaterial()
    testfile = root / PATH
    testfile.parent.mkdir(exist_ok=True)
    for ref, source, production in [
            ("REQ-001", FIRST, PRODUCTION_FIRST),
            ("OTHER", OTHER, PRODUCTION_OTHER),
            ("REQ-004", LAST, PRODUCTION_FINAL)]:
        before = git(root, "rev-parse", "HEAD")
        (root / "shopping_basket.py").write_text(production)
        old = testfile.read_text() if testfile.exists() else ""
        identity = PATH + "::" + ("test_other" if ref == "OTHER" else "test_" + ref.replace("-", "_"))
        from core.development.test_material import TestModuleMergeRequest
        testfile.write_text(material.merge(TestModuleMergeRequest(old, source, identity)))
        after = commit(root, "controlled accepted history " + ref)
        completed.append(save_completed(placeholder, ref, source, before, after))
    snippets = [("REQ-001", "A new basket is empty"),
                ("OTHER", "unrelated() returns 9"),
                ("REQ-004", "total_price() returns the sum of prices"),
                ("REQ-005", "A third example has total 7")]
    clauses = [SourceRequirementClause("S-" + ref, text, "behavior", source_quote=text, subject=text)
               for ref, text in snippets]
    requirements = [BehaviorContractRequirement(ref, ["S-" + ref], text, text, text,
                    depends_on=(["REQ-001"] if ref == "REQ-004" else ["REQ-004"] if ref == "REQ-005" else [])) for ref, text in snippets]
    contract = BehaviorContract("contract", "proof", "ShoppingBasket", "track prices", SOURCE,
        clauses, requirements, [], ["shopping_basket.py"], [PATH])
    baseline = completed[-1].canonical_revision
    TrustedProjectRevisionSynchronizer(environment).synchronize("proof", baseline)
    state = StrictTddFeatureState("proof", hashlib.sha256(SOURCE.encode()).hexdigest(), "running",
        contract.to_dict(), completed_behaviors=tuple(completed), canonical_ref="refs/heads/main",
        canonical_development_base=baseline, behavioral_entry_revision=first_base)
    service = compose_consolidation(ConsolidationCompositionRequest(state_root, root, environment,
        PythonPytestAdapter(), PythonProductionReductionAdapter(), material,
        DeterministicRegressionService(SubprocessProjectRuntimeExecutor()), placeholder.gateway))
    return replace(placeholder, state=state, service=service,
                   history=(first_base, *(item.canonical_revision for item in completed)))
