"""Controlled Git proofs for integration evidence, without models or reservations."""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import subprocess
import sys

import pytest

from core.delivery_management.evidence import (
    AcceptedContribution, AcceptedEvidenceUnion, AcceptedNode, AcceptedSourceReader,
    CompletedEvidenceLoader, CompletedEvidenceRequest, ContributionKind, EvidenceTreeRequest,
)
from core.delivery_management.validation import (
    IntegrationValidationDependencies, IntegrationValidationRequest, IntegrationValidator,
)
from core.development.consolidation_language import ConsolidationLanguage
from core.development.deterministic_regression import SubprocessProjectRuntimeExecutor
from core.development.post_behavior_authority import PythonPostBehaviorAuthority
from core.development.post_behavior_composition import PostBehaviorCompositionFactory, PostBehaviorCompositionRequest
from core.development.post_behavior_git import PostBehaviorGit
from core.development.post_behavior_slice import PythonProductionSlice
from core.development.post_behavior_validation import PostBehaviorCandidateAuthority, PostBehaviorSource
from core.development.project_environment import ProjectEnvironmentService, ProjectRuntime
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.python_test_material import PythonTestMaterial
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from tests.development.test_post_behavior_integration import (
    PROJECT, GenericGitExecution, configured_gateway, gatekeeper_yes, seeded_delivery,
)


def git(root, *args):
    return subprocess.run(("git", *args), cwd=root, text=True,
                          capture_output=True, check=True).stdout.strip()


def commit(root):
    git(root, "add", ".")
    git(root, "-c", "user.name=Controlled Proof", "-c",
        "user.email=proof@example.invalid", "commit", "-qm", "controlled accepted snapshot")
    return git(root, "rev-parse", "HEAD")


def repository(root):
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    (root / "value.py").write_text("def value():\n    return 2\n")
    (root / "tests").mkdir()
    (root / "tests/test_value.py").write_text(
        "from value import value\n\ndef test_one():\n    assert value() == 2\n")
    return commit(root)


def contribution(root, revision, name, owner):
    node = "tests/test_value.py::" + name
    source = AcceptedSourceReader(root, PythonTestMaterial()).source((revision, node))
    return AcceptedContribution("application", owner, owner,
        sha256(owner.encode()).hexdigest(), "architecture-sha", revision, owner,
        (AcceptedNode(node, "tests/test_value.py", sha256(source.encode()).hexdigest(),
                      revision, ("REQ001",), ("SRC001",), "value.py", owner),),
        ("controlled-test-only:" + owner,))


def validator():
    material = PythonTestMaterial()
    return IntegrationValidator(IntegrationValidationDependencies(material,
        ConsolidationLanguage(PythonPytestAdapter(), material), SubprocessProjectRuntimeExecutor()))


def runtime():
    return ProjectRuntime("python", sys.version.split()[0], sys.executable,
        [sys.executable, "-m", "pytest", "-q", "-p", "no:django", "-p", "no:asyncio"],
        [sys.executable, "-B", "-c", "import value"])


def test_combined_validation_retains_nodes_from_both_histories(tmp_path):
    root = tmp_path / "application"
    first = repository(root)
    one = contribution(root, first, "test_one", "catalogue")
    path = root / "tests/test_value.py"
    path.write_text(path.read_text() + "\ndef test_two():\n    assert value() * 2 == 4\n")
    second = commit(root)
    two = contribution(root, second, "test_two", "basket")
    observed = validator().validate(IntegrationValidationRequest(root, second, runtime(), (one, two)))
    assert observed.passed, observed.diagnostic
    assert [item.target for item in observed.commands][-2:] == [one.tests[0].test_name, two.tests[0].test_name]
    assert AcceptedContribution.from_dict(one.to_dict()) == one
    path.write_text(path.read_text().replace("assert value() == 2", "assert value() == 99"))
    changed = commit(root)
    with pytest.raises(ValueError, match="changed or removed"):
        AcceptedEvidenceUnion(PythonTestMaterial()).verify(EvidenceTreeRequest(root, changed, (one, two)))


def test_clean_merge_cannot_hide_cross_delivery_test_identity_ownership(tmp_path):
    root = tmp_path / "application"
    revision = repository(root)
    first = contribution(root, revision, "test_one", "catalogue")
    conflicting = contribution(root, revision, "test_one", "basket")
    with pytest.raises(ValueError, match="ownership conflicts"):
        AcceptedEvidenceUnion(PythonTestMaterial()).verify(EvidenceTreeRequest(root, revision, (first, conflicting)))


def test_successful_suite_exit_does_not_accept_skipped_required_node(tmp_path):
    root = tmp_path / "application"
    repository(root)
    (root / "tests/test_value.py").write_text(
        "import pytest\nfrom value import value\n\ndef test_one():\n"
        "    pytest.skip('controlled unavailable test')\n    assert value() == 2\n")
    revision = commit(root)
    accepted = contribution(root, revision, "test_one", "catalogue")
    observed = validator().validate(IntegrationValidationRequest(root, revision, runtime(), (accepted,)))
    assert observed.commands[1].status == "passed"
    assert not observed.passed
    assert observed.commands[-1].status == "failed"


@pytest.mark.asyncio
async def test_real_post_naming_loader_preserves_new_hash_and_original_authority(tmp_path, monkeypatch):
    state_root, root, entry, baseline = seeded_delivery(tmp_path)
    features = StrictTddFeatureRepository(state_root / "features")
    feature = features.load(PROJECT)
    features.save(replace(feature, delivery_identity="scoped-delivery",
        source_requirement_hash=sha256(feature.contract_payload["requirement_source"].encode()).hexdigest()))
    responses = ["LegacyCounter -> SumCounter", gatekeeper_yes(), "NO", "NO"]
    gateway, calls = configured_gateway(monkeypatch, responses)
    execution = GenericGitExecution(root, tmp_path)
    request = PostBehaviorCompositionRequest(state_root, PROJECT, gateway, execution)
    for _ in range(30):
        state = await PostBehaviorCompositionFactory().build(request).advance(PROJECT)
        if state.terminal:
            break
    assert not responses
    authority = PostBehaviorCandidateAuthority(
        PostBehaviorSource(PostBehaviorGit(root), PythonProductionSlice()), PythonPostBehaviorAuthority())
    source = features.load(PROJECT).contract_payload["requirement_source"]
    accepted = CompletedEvidenceLoader(PythonTestMaterial(), authority).load(CompletedEvidenceRequest(
        state_root, PROJECT, "scoped-delivery", "counter", sha256(source.encode()).hexdigest(),
        "architecture-sha", ProjectEnvironmentService(state_root / "projects")))
    node = accepted.tests[0]
    reader = AcceptedSourceReader(root, PythonTestMaterial())
    assert node.origin_revision == baseline
    assert accepted.completion_revision == state.current_post_behavior_revision != baseline
    assert node.source_sha256 == sha256(reader.source((accepted.completion_revision, node.test_name)).encode()).hexdigest()
    assert node.source_sha256 != sha256(reader.source((baseline, node.test_name)).encode()).hexdigest()
    assert accepted.naming_history and accepted.authority_digest
    assert AcceptedEvidenceUnion(PythonTestMaterial()).verify(
        EvidenceTreeRequest(root, accepted.completion_revision, (accepted,))) == accepted.tests


def test_quiescent_req_checkpoint_is_not_full_delivery_completion(tmp_path):
    state_root, root, entry, baseline = seeded_delivery(tmp_path)
    features = StrictTddFeatureRepository(state_root / "features")
    feature = features.load(PROJECT)
    source = feature.contract_payload["requirement_source"]
    features.save(replace(feature, status="running", delivery_identity="scoped-delivery",
        source_requirement_hash=sha256(source.encode()).hexdigest(), final_reconciliation=()))
    authority = PostBehaviorCandidateAuthority(
        PostBehaviorSource(PostBehaviorGit(root), PythonProductionSlice()), PythonPostBehaviorAuthority())
    loader = CompletedEvidenceLoader(PythonTestMaterial(), authority)
    request = CompletedEvidenceRequest(state_root, PROJECT, "scoped-delivery", "counter",
        sha256(source.encode()).hexdigest(), "architecture-sha",
        ProjectEnvironmentService(state_root / "projects"))
    checkpoint = loader.load_checkpoint(request)
    assert checkpoint.kind == ContributionKind.CHECKPOINT
    assert checkpoint.completion_revision == baseline
    assert checkpoint.tests and not checkpoint.naming_history
    with pytest.raises(ValueError, match="completed behavioral delivery"):
        loader.load(request)
    features.save(replace(features.load(PROJECT), current_scenario_id="active-other-REQ"))
    with pytest.raises(ValueError, match="not quiescent"):
        loader.load_checkpoint(request)
