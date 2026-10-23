"""Real Git/execution proofs with controlled reasoning, never live model work."""
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil

import pytest

from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.consolidation_evidence import ActiveAcceptedEvidenceResolver, ActiveEvidenceRequest
from core.development.consolidation_git import TestReplacementInput as ReplacementInput
from core.development.consolidation_journal import ConsolidationJournal
from core.development.consolidation_material import checkpoint_identity
from core.development.microcycle_domain import BoundaryOutcome
from core.development.specification_domain import SourceRequirementClause
from core.development.strict_tdd_feature_application import FeatureReconciliationRequest
from core.development.strict_tdd_feature_execution import CompletedFeatureReconciler
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.project_revision_synchronization import TrustedProjectRevisionSynchronizer
from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.development.python_test_material import PythonTestMaterial
from core.development.specification_reconciliation import CompletedMicrocycleEvidenceCollector
from core.development.test_material import TestModuleMergeRequest as ModuleMerge
from tests.development.consolidation_helpers import (
    COMBINED, FIRST, LAST, PATH, ControlledReasoning, commit, git, make_fixture, save_completed,
)


@pytest.mark.asyncio
async def test_real_consolidation_preserves_cases_reduces_owned_alias_and_resolves_all_consumers(tmp_path):
    f = make_fixture(tmp_path)
    before = f.state.canonical_development_base
    original_tests = git(f.root, "show", before + ":" + PATH)
    original_prod = git(f.root, "show", before + ":shopping_basket.py")
    outcome = await f.service.advance(f.context)
    assert len(outcome.evidence_consolidations) == 1
    record = outcome.evidence_consolidations[0]
    assert record.member_refs == ("REQ-001", "REQ-004")
    tests = git(f.root, "show", outcome.canonical_development_base + ":" + PATH)
    production = git(f.root, "show", outcome.canonical_development_base + ":shopping_basket.py")
    assert "def test_REQ_001" not in tests and "def test_REQ_004" in tests
    assert "empty.total_price() == 0" in tests and "populated.total_price() == 5" in tests
    assert "def get_total_price" not in production
    assert "def unrelated" in production and "def total_price" in production
    assert git(f.root, "show", record.test_revision + ":shopping_basket.py") == original_prod
    assert git(f.root, "show", before + ":" + PATH) == original_tests
    active = f.active(outcome)
    assert {item.test_name for item in active} == {PATH + "::test_other", PATH + "::test_REQ_004"}
    replacement = next(item for item in active if item.supersession_id)
    assert replacement.red_revision is None and replacement.covered_requirement_refs == record.member_refs
    assert outcome.completed_behaviors == f.state.completed_behaviors
    assert len(f.gateway.requests) == 3
    assert "REQ-005" not in f.gateway.requests[0].prompt
    assert "REQ-005" in BehaviorContract.from_dict(outcome.contract_payload).requirement_refs()
    assert "REQ-005" not in {item.behavior_ref for item in outcome.completed_behaviors}
    reconciler = CompletedFeatureReconciler(f.root, MicrocycleStateRepo(f.state_root / "microcycles"),
        f.gateway, PythonTestMaterial())
    nodes = reconciler.active_test_nodes(FeatureReconciliationRequest(
        BehaviorContract.from_dict(outcome.contract_payload), outcome.completed_behaviors, {},
        outcome.canonical_development_base, evidence_consolidations=outcome.evidence_consolidations))
    assert set(nodes) == {PATH + "::test_other", PATH + "::test_REQ_004"}
    assert await f.service.advance(replace(f.context, state=outcome)) is None
    assert len(f.gateway.requests) == 3
    from core.development.strict_tdd_feature_application import (
        StrictTddFeatureApplicationService, StrictTddFeatureDependencies)
    from core.development.strict_tdd_feature_domain import StrictTddFeatureRequest
    from tests.development.consolidation_helpers import SOURCE
    captured = []
    class NextScenarioProbe:
        async def advance(self, request):
            captured.append(request)
            raise RuntimeError("captured next ordinary REQ")
    feature_store = StrictTddFeatureRepository(f.state_root / "features")
    feature_store.save(outcome)
    application = StrictTddFeatureApplicationService(StrictTddFeatureDependencies(
        f.environment, feature_store, object(), object(), NextScenarioProbe(), reconciler,
        prepare_project=lambda request: f.environment.create_or_load_python_project_with_disposition(
            request.project_id, request.production_paths), consolidation=f.service))
    request = StrictTddFeatureRequest("proof", SOURCE, "python", "pytest",
        ("shopping_basket.py",), (PATH,), "python", "resume", None, str(tmp_path / "evidence"))
    next_req = await application.advance(request)
    assert next_req.behavior_ref == "REQ-005" and next_req.kind.value == "behavior_selected"
    with pytest.raises(RuntimeError, match="captured next ordinary"):
        await application.advance(request)
    assert captured[0].canonical_development_base == outcome.canonical_development_base
    assert set(captured[0].prior_completed_test_nodes) == set(nodes)
    assert len(f.gateway.requests) == 3
    export = os.environ.get("ATHBA_CONSOLIDATION_PROOF_ROOT")
    if export:
        proof = Path(export)
        proof.mkdir(parents=True, exist_ok=True)
        (proof / "before-tests.py.txt").write_text(original_tests + "\n")
        (proof / "after-tests.py.txt").write_text(tests + "\n")
        (proof / "before-production.py.txt").write_text(original_prod + "\n")
        (proof / "after-production.py.txt").write_text(production + "\n")
        (proof / "supersession.json").write_text(json.dumps(record.to_dict(), indent=2))
        (proof / "feature.json").write_text(json.dumps(outcome.to_dict(), indent=2))
        (proof / "summary.json").write_text(json.dumps({
            "before": before, "test_revision": record.test_revision, "after": record.final_revision,
            "active_test_count_before": 3, "active_test_count_after": 2,
            "original_observations_preserved": [0, 5], "unaffected_result_preserved": 9,
            "model_calls": 0, "controlled_reasoning_responses": len(f.gateway.requests),
            "no_fabricated_red": replacement.red_revision is None,
        }, indent=2))
        shutil.copytree(f.state_root / "evidence-consolidations", proof / "checkpoints", dirs_exist_ok=True)
        shutil.copytree(f.state_root / "consolidation-reductions", proof / "reducer", dirs_exist_ok=True)
        if not (proof / "repository").exists():
            git(proof, "clone", "--no-hardlinks", str(f.root), "repository")


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["semantic_drop", "production_red", "no_consolidation"])
async def test_optional_rejection_preserves_accepted_pair_without_developer(tmp_path, mode):
    source = LAST if mode == "semantic_drop" else COMBINED.replace("== 5", "== 6")
    gateway = ControlledReasoning(source, approve=mode != "semantic_drop", propose=mode != "no_consolidation")
    f = make_fixture(tmp_path, gateway)
    before = git(f.root, "rev-parse", "HEAD")
    tree = git(f.root, "rev-parse", "HEAD^{tree}")
    outcome = await f.service.advance(f.context)
    assert outcome.canonical_development_base == before and outcome.evidence_consolidations == ()
    assert git(f.root, "rev-parse", "HEAD^{tree}") == tree
    assert len(outcome.completed_behaviors) == 3 and len(outcome.consolidation_checks) == 1
    assert await f.service.advance(replace(f.context, state=outcome)) is None
    assert len(gateway.requests) == (1 if mode == "no_consolidation" else 3)
    journal = ConsolidationJournal(f.state_root / "evidence-consolidations", checkpoint_identity(f.state))
    assert journal.load().outcome == ("no_consolidation" if mode == "no_consolidation" else "rejected")
    if mode == "semantic_drop":
        assert not (journal.root / "test-acceptance.json").exists()


@pytest.mark.asyncio
async def test_mutating_production_or_unrelated_test_is_rejected(tmp_path):
    f = make_fixture(tmp_path)
    selected = f.service.dependencies.material.prepare((f.context, checkpoint_identity(f.state)))
    bad = COMBINED.replace("    empty = ShoppingBasket()",
        "    from pathlib import Path\n    Path('shopping_basket.py').write_text('corrupted')\n    empty = ShoppingBasket()")
    before = f.state.canonical_development_base
    f.gateway.source = bad
    with pytest.raises(ValueError, match="mutated immutable"):
        await f.service.advance(f.context)
    assert git(f.root, "rev-parse", "HEAD") == before
    assert (f.root / "shopping_basket.py").read_text().startswith("class ShoppingBasket")
    with pytest.raises(ValueError, match="overwrite an unselected"):
        f.service.dependencies.git.create(ReplacementInput(before, selected.previous_tests,
            "def test_other():\n    assert True\n", PATH + "::test_other"))


@pytest.mark.asyncio
async def test_verified_publication_resume_never_replays_reasoning_or_reduction(tmp_path, monkeypatch):
    f = make_fixture(tmp_path)
    original = f.service.dependencies.git.publish
    def interrupted(request, environment):
        original(request, environment)
        raise RuntimeError("crash after canonical CAS, before feature save")
    monkeypatch.setattr(f.service.dependencies.git, "publish", interrupted)
    with pytest.raises(RuntimeError, match="after canonical"):
        await f.service.advance(f.context)
    identity = checkpoint_identity(f.state)
    journal = ConsolidationJournal(f.state_root / "evidence-consolidations", identity)
    verified = journal.load()
    assert verified.outcome == "verified"
    trial_path = Path(verified.reduction_evidence).parent
    trial_bytes = {p.name: p.read_bytes() for p in trial_path.glob("trial-*.json")}
    monkeypatch.setattr(f.service.dependencies.git, "publish", original)
    outcome = await f.service.advance(f.context)
    assert outcome.canonical_development_base == verified.final_revision
    assert len(outcome.evidence_consolidations) == 1 and len(f.gateway.requests) == 3
    assert {p.name: p.read_bytes() for p in trial_path.glob("trial-*.json")} == trial_bytes
    assert await f.service.advance(replace(f.context, state=outcome)) is None


@pytest.mark.asyncio
async def test_uncertain_reasoning_is_not_resubmitted(tmp_path):
    f = make_fixture(tmp_path)
    calls = []
    async def uncertain(request):
        calls.append(request)
        raise ConnectionError("response lost")
    f.gateway.reason = uncertain
    with pytest.raises(ConnectionError):
        await f.service.advance(f.context)
    with pytest.raises(ValueError, match="will not replay"):
        await f.service.advance(f.context)
    assert len(calls) == 1
    assert git(f.root, "rev-parse", "HEAD") == f.state.canonical_development_base


@pytest.mark.asyncio
async def test_zero_reduction_and_later_group_consolidation_are_normal(tmp_path):
    both = COMBINED.replace("empty.total_price()", "empty.get_total_price()")
    f = make_fixture(tmp_path, ControlledReasoning(both))
    first = await f.service.advance(f.context)
    record = first.evidence_consolidations[0]
    checkpoint = json.loads(Path(record.evidence_refs[-1]).read_text())
    assert checkpoint["checkpoint"]["accepted"] == 0
    before = first.canonical_development_base
    extra_source = ("from shopping_basket import ShoppingBasket\n\ndef test_REQ_005():\n"
        "    example = ShoppingBasket()\n    example.add_item('third', 7)\n    assert example.total_price() == 7\n")
    old = (f.root / PATH).read_text()
    (f.root / PATH).write_text(PythonTestMaterial().merge(ModuleMerge(old, extra_source, PATH + "::test_REQ_005")))
    completed = commit(f.root, "controlled later accepted requirement")
    additional = save_completed(f, "REQ-005", extra_source, before, completed)
    TrustedProjectRevisionSynchronizer(f.environment).synchronize("proof", completed)
    f.state = replace(first, canonical_development_base=completed,
        completed_behaviors=(*first.completed_behaviors, additional))
    assert f.state.contract_payload == first.contract_payload
    assert f.state.source_requirement_hash == first.source_requirement_hash
    f.gateway.source = both.replace("def test_REQ_004()", "def test_REQ_005()") + (
        "    example = ShoppingBasket()\n    example.add_item('third', 7)\n    assert example.total_price() == 7\n")
    outcome = await f.service.advance(f.context)
    assert len(outcome.evidence_consolidations) == 2
    assert set(outcome.evidence_consolidations[-1].member_refs) == {"REQ-001", "REQ-004", "REQ-005"}
    assert len(f.active(outcome)) == 2
    assert len(f.gateway.requests) == 6
