"""Controlled storage/BDE boundaries; real disposable Git and managed Python, no models."""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from core.dataclasses.project import Project
from core.development.project_environment_store import ProjectEnvironmentRepo
from core.project_setup.architecture import (
    ApprovedArchitecture, ApprovalStatus, PinnedArchitectureApproval, content_hash,
)
from core.project_setup.commands import CommandResult, SetupCommandRunner
from core.project_setup.composition import ProjectSetupCompositionRequest, compose_project_setup
from core.project_setup.delivery import (
    BdeOutcome, DeliveryDependencies, DeliveryRequest, ProjectBehaviorDeliveries,
)
from core.project_setup.fixture import FixtureBinding, fixture_specification, load_test_architecture
from core.project_setup.profile_domain import ProfileKind, ProfileSelection, ToolKind, ToolSelection
from core.project_setup.records import DeliveryStatus, ProjectSetupRepository, SetupStatus
from core.project_setup.workspace import ProjectSetupWorkspace

FIXTURE = Path(__file__).parent / "fixtures" / "project_setup"


def approved(project_id="existing-parent"):
    original = load_test_architecture(FixtureBinding(FIXTURE, project_id))
    tools = (
        ToolSelection(ToolKind.PYTHON, sys.executable, ".".join(map(str, sys.version_info[:3]))),
        ToolSelection(ToolKind.PYTEST, sys.executable, pytest.__version__),
    )
    return reapprove(original, replace(original.decision, profile=replace(original.decision.profile, tools=tools)))


def reapprove(handoff, decision):
    return replace(handoff, decision=decision, approval=replace(
        handoff.approval, project_id=decision.project_id, architecture_sha256=decision.digest))


@dataclass
class ControlledExistingProjects:
    """Unit-only substitute for the existing Mongo storage boundary."""
    project: Project
    spec: dict

    async def get_project_by_id(self, identity):
        return self.project if identity == self.project.id else None

    async def get_latest_spec(self, identity):
        return self.spec if identity == self.project.id else None


def environment(tmp_path, handoff=None):
    handoff = handoff or approved()
    projects = ControlledExistingProjects(Project(_id=handoff.decision.project_id, name="Existing project"), {
        "version": handoff.decision.specification_version, "content": fixture_specification(FIXTURE)})
    authority = PinnedArchitectureApproval(handoff.approval, handoff.decision.project_id)
    composition = compose_project_setup(ProjectSetupCompositionRequest(tmp_path, projects, authority))
    return handoff, projects, composition


def git(root, *args):
    return subprocess.run(("git", "-C", str(root), *args), check=True, text=True,
                          capture_output=True).stdout.strip()


class ControlledBde:
    """Only tests may inject this scripted OUTER port; it is not an actual BDE build."""
    def __init__(self, root, action=None):
        self.root, self.action, self.calls = root, action, []

    def unsupported_reason(self, request):
        return None

    async def deliver(self, request):
        self.calls.append(request)
        if self.action:
            return await self.action(request)
        repo = Path(request.repository_root)
        name = request.behavior.id
        production = request.behavior.production_paths[0]
        test = request.behavior.test_paths[0]
        (repo / production).write_text("MARKER = " + repr(name) + "\n")
        target = repo / test
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("def test_" + name + "_REQ001():\n    assert " + repr(name) + " == " + repr(name) + "\n")
        git(repo, "add", "--", production, test)
        git(repo, "-c", "user.name=Controlled", "-c", "user.email=controlled@example.test",
            "commit", "-m", "Unit-only boundary " + name)
        revision = git(repo, "rev-parse", "HEAD")
        store = ProjectEnvironmentRepo(self.root / "projects")
        store.save(replace(store.load(request.project_id), trusted_base_sha=revision))
        return BdeOutcome(DeliveryStatus.COMPLETE_WITH_UNPROVEN_ASSURANCE, revision,
                          (request.state_namespace + "/REQ001",), ("unit-only assurance",),
                          "NO", "NO", reservation_ids=("controlled-" + name,), work_ids=(request.run_id,))


def controlled_deliveries(tmp_path, handoff, projects, composition, engine):
    return ProjectBehaviorDeliveries(DeliveryDependencies(
        composition.records, ProjectSetupWorkspace(tmp_path / "projects", SetupCommandRunner()),
        engine, tmp_path, projects, PinnedArchitectureApproval(handoff.approval, handoff.decision.project_id)))


@pytest.mark.asyncio
async def test_no_provisioning_before_pinned_resolved_approval(tmp_path):
    handoff, projects, app = environment(tmp_path)
    for approval in (
        replace(handoff.approval, status=ApprovalStatus.PENDING),
        replace(handoff.approval, binding_conflicts_resolved=False),
    ):
        with pytest.raises(ValueError):
            await app.setup.prepare(replace(handoff, approval=approval))
        assert not (tmp_path / "projects").exists()
    with pytest.raises(ValueError, match="test-project"):
        PinnedArchitectureApproval(handoff.approval).require(handoff)
    projects.spec["version"] += 1
    with pytest.raises(ValueError, match="specification"):
        await app.setup.prepare(handoff)
    assert not (tmp_path / "projects").exists()


@pytest.mark.asyncio
async def test_approved_typescript_not_earlier_javascript_and_missing_tool_is_blocked(tmp_path):
    handoff = approved()
    profile = ProfileSelection(ProfileKind.TYPESCRIPT, ("typescript",), (
        ToolSelection(ToolKind.NODE, "/unavailable/node", "22.1.0"),
        ToolSelection(ToolKind.NPM, "/unavailable/npm", "10.1.0"),
        ToolSelection(ToolKind.TYPESCRIPT, "/unavailable/tsc", "5.1.0")), "node")
    handoff = reapprove(handoff, replace(handoff.decision, profile=profile))
    handoff, projects, app = environment(tmp_path, handoff)
    # The persisted fixture context is allowed an earlier NON-BINDING preference.
    projects.spec["content"]["meta"]["early_preference"] = "javascript"
    handoff = reapprove(handoff, replace(handoff.decision,
        specification_sha256=content_hash(projects.spec["content"])))
    _, _, app = environment(tmp_path, handoff)
    app.setup.dependencies.projects.spec = projects.spec
    result = await app.setup.prepare(handoff)
    assert result.profile_id == "typescript"
    assert result.status == SetupStatus.BLOCKED
    assert not result.environment_verified
    assert "node@22.1.0" in result.reason
    assert not (tmp_path / "projects" / handoff.decision.project_id / "repository").exists()


@pytest.mark.asyncio
async def test_real_git_runtime_setup_and_same_approval_reuse(tmp_path):
    handoff, _, app = environment(tmp_path)
    first = await app.setup.prepare(handoff)
    second = await app.setup.prepare(handoff)
    assert first == second
    assert first.status == SetupStatus.READY and first.environment_verified
    assert first.bde_language_compatible and not first.bde_shared_handoff_supported
    assert any("pytest" in result.argv and "1 passed" in result.stdout for result in first.commands)
    repo = Path(first.repository_root)
    assert git(repo, "rev-parse", "HEAD") == first.scaffold_revision
    assert git(repo, "rev-list", "--count", "HEAD") == "2"
    assert not git(repo, "status", "--porcelain")
    for behavior in handoff.decision.behaviors:
        assert (repo / behavior.production_paths[0]).read_bytes() == b""
        assert not (repo / behavior.test_paths[0]).exists()
    assert len(list((tmp_path / "projects").glob("*/repository"))) == 1
    print("REAL_GIT_RUNTIME_CONTROLLED_STORAGE_PROOF=" + json.dumps({
        "project": first.project_id, "repository": str(repo), "scaffold": first.scaffold_revision,
        "same_setup_reused": True, "tools": [item.__dict__ | {"result": item.result.__dict__} for item in first.tools],
        "commands": [item.__dict__ for item in first.commands],
        "storage": "controlled unit boundary, not Mongo/frontend proof"}))


@pytest.mark.asyncio
async def test_conflict_or_unsafe_scope_preserves_existing_setup(tmp_path):
    handoff, _, app = environment(tmp_path)
    first = await app.setup.prepare(handoff)
    before = app.records.path(first.project_id).read_bytes()
    different = reapprove(handoff, replace(handoff.decision, version=2))
    _, _, changed_app = environment(tmp_path, different)
    with pytest.raises(ValueError, match="incompatible"):
        await changed_app.setup.prepare(different)
    assert app.records.path(first.project_id).read_bytes() == before
    for path in ("../outside.py", ".", ".git/config", ".git\\config", "/absolute.py"):
        with pytest.raises(ValueError):
            replace(handoff.decision.behaviors[0], production_paths=(path,))


@pytest.mark.asyncio
async def test_failed_smoke_keeps_commands_without_ready_authority(tmp_path, monkeypatch):
    handoff, _, app = environment(tmp_path)
    runner = app.setup.dependencies.runner
    original = runner.run
    def fail_smoke(request):
        if "test_environment_smoke.py" in " ".join(request.argv):
            return CommandResult(request.argv, 1, "setup smoke failed", "")
        return original(request)
    monkeypatch.setattr(runner, "run", fail_smoke)
    with pytest.raises(Exception, match="smoke"):
        await app.setup.prepare(handoff)
    result = app.records.load(handoff.decision.project_id)
    assert result.status == SetupStatus.FAILED and not result.environment_verified
    assert result.commands[-1].stdout == "setup smoke failed"
    assert ProjectEnvironmentRepo(tmp_path / "projects").load(result.project_id) is None


@pytest.mark.asyncio
async def test_controlled_outer_deliveries_share_one_repo_accumulate_and_resume_without_replay(tmp_path):
    handoff, projects, app = environment(tmp_path)
    setup = await app.setup.prepare(handoff)
    engine = ControlledBde(tmp_path)
    deliveries = controlled_deliveries(tmp_path, handoff, projects, app, engine)
    previous = setup.scaffold_revision
    records = []
    for behavior in handoff.decision.behaviors:
        result = await deliveries.dispatch(DeliveryRequest(handoff, behavior.id))
        assert result.status == DeliveryStatus.COMPLETE_WITH_UNPROVEN_ASSURANCE
        assert result.entry_revision == previous
        assert result.unproven_assurance == ("unit-only assurance",)
        assert result.naming == result.refactoring == "NO"
        assert await deliveries.dispatch(DeliveryRequest(handoff, behavior.id)) == result
        records.append(result)
        previous = result.accepted_revision
    assert len(engine.calls) == 3
    assert len({item.state_namespace for item in engine.calls}) == 3
    assert len({item.run_id for item in engine.calls}) == 3
    assert {item.project_id for item in engine.calls} == {handoff.decision.project_id}
    assert {item.repository_root for item in engine.calls} == {setup.repository_root}
    assert app.records.load(setup.project_id).last_accepted_revision == previous
    assert len(list(Path(setup.repository_root).glob("tests/test_*.py"))) == 3
    assert all(item.evidence_refs[0].endswith("REQ001") for item in records)
    assert (await app.setup.prepare(handoff)).repository_root == setup.repository_root
    print("CONTROLLED_OUTER_ONLY_HANDOFF_PROOF=" + json.dumps({
        "project": setup.project_id, "repository": setup.repository_root,
        "deliveries": [item.__dict__ for item in records],
        "actual_bde_application_builds": False}))


@pytest.mark.asyncio
async def test_exception_keeps_accepted_baseline_and_stops_after_partial_progress(tmp_path):
    handoff, projects, app = environment(tmp_path)
    initial = await app.setup.prepare(handoff)
    async def dirty_then_raise(request):
        (Path(request.repository_root) / request.behavior.production_paths[0]).write_text("partial\n")
        raise RuntimeError("controlled entry failure")
    engine = ControlledBde(tmp_path, dirty_then_raise)
    deliveries = controlled_deliveries(tmp_path, handoff, projects, app, engine)
    result = await deliveries.dispatch(DeliveryRequest(handoff, "catalogue"))
    assert result.status == DeliveryStatus.FAILED and "controlled entry failure" in result.traceback
    assert result.repository_uncertain
    state = app.records.load(initial.project_id)
    assert state.last_accepted_revision == initial.scaffold_revision and state.active_delivery is None
    assert await deliveries.dispatch(DeliveryRequest(handoff, "catalogue")) == result
    with pytest.raises(ValueError, match="no safe"):
        await deliveries.dispatch(DeliveryRequest(handoff, "basket"))
    assert len(engine.calls) == 1


@pytest.mark.asyncio
async def test_prior_production_cannot_be_modified_by_later_outer_delivery(tmp_path):
    handoff, projects, app = environment(tmp_path)
    await app.setup.prepare(handoff)
    engine = ControlledBde(tmp_path)
    deliveries = controlled_deliveries(tmp_path, handoff, projects, app, engine)
    first = await deliveries.dispatch(DeliveryRequest(handoff, "catalogue"))
    original = engine.deliver
    async def corrupt_prior(request):
        result = await original(request)
        repo = Path(request.repository_root)
        (repo / handoff.decision.behaviors[0].production_paths[0]).write_text("UNAUTHORIZED = True\n")
        git(repo, "add", ".")
        git(repo, "-c", "user.name=Controlled", "-c", "user.email=controlled@example.test",
            "commit", "-m", "Controlled forbidden prior mutation")
        store = ProjectEnvironmentRepo(tmp_path / "projects")
        revision = git(repo, "rev-parse", "HEAD")
        store.save(replace(store.load(request.project_id), trusted_base_sha=revision))
        return replace(result, last_trusted_revision=revision)
    engine.action = corrupt_prior
    # original delivers directly after temporarily clearing action, avoiding recursion.
    async def scripted(request):
        engine.action = None
        return await corrupt_prior(request)
    engine.action = scripted
    result = await deliveries.dispatch(DeliveryRequest(handoff, "basket"))
    assert result.status == DeliveryStatus.FAILED and "outside" in result.reason
    assert app.records.load(handoff.decision.project_id).last_accepted_revision == first.accepted_revision


@pytest.mark.asyncio
async def test_frozen_real_composition_entry_rejects_bad_protocol_without_models(tmp_path):
    from core.development.strict_tdd_live_run_composition import (
        StrictTddLiveRunCompositionFactory, StrictTddLiveRunCompositionRequest, StrictTddLiveRunConfiguration)
    from core.development.strict_tdd_run_domain import (
        StrictTddRunRequest, StrictTddRunMode, StrictTddRunControllerConfig)
    from core.execution.reasoning_gateway import ReasoningResult
    handoff, projects, app = environment(tmp_path)
    setup = await app.setup.prepare(handoff)
    reasoning = AsyncMock()
    reasoning.reason.return_value = ReasoningResult("{}", provider="controlled", model="no-model")
    execution = AsyncMock()
    execution.execute.side_effect = AssertionError("No agent execution permitted")
    async def real_entry(request):
        config = StrictTddLiveRunConfiguration(tmp_path, tmp_path / "entry-evidence",
            Path(request.repository_root), request.project_id, athba_revision="frozen-test",
            rack_ai_revision="no-rackai-execution")
        actual = StrictTddLiveRunCompositionFactory().build(
            StrictTddLiveRunCompositionRequest(config, reasoning, execution))
        behavior = request.behavior
        actual_result = await actual.controller.run(StrictTddRunRequest(
            request.run_id, request.project_id, behavior.source, "python", "pytest",
            behavior.production_paths, behavior.test_paths, "controlled-state", "controlled-evidence",
            StrictTddRunMode.START, None, "frozen-test", "no-rackai-execution",
            StrictTddRunControllerConfig(10)))
        print("FROZEN_ENTRY_RETURNED=" + repr(actual_result))
        assert actual_result.status.value == "blocked"
        return BdeOutcome(DeliveryStatus.BLOCKED, request.entry_revision,
                          reason=actual_result.reason)
    engine = ControlledBde(tmp_path, real_entry)
    result = await controlled_deliveries(tmp_path, handoff, projects, app, engine).dispatch(
        DeliveryRequest(handoff, "catalogue"))
    assert result.status == DeliveryStatus.FAILED
    assert "SourceClausePlanningFailure" in result.traceback, result.traceback
    assert reasoning.reason.await_count == 2
    execution.execute.assert_not_awaited()
    assert app.records.load(setup.project_id).last_accepted_revision == setup.scaffold_revision
    print("REAL_FROZEN_ENTRY_CONTROLLED_BLOCKER=" + result.traceback)


@pytest.mark.asyncio
async def test_frozen_shared_handoff_is_explicitly_blocked_and_no_dispatch_replay(tmp_path):
    handoff, _, app = environment(tmp_path)
    setup = await app.setup.prepare(handoff)
    with pytest.raises(ValueError, match="sequential"):
        await app.deliveries.dispatch(DeliveryRequest(handoff, "orders"))
    result = await app.deliveries.dispatch(DeliveryRequest(handoff, "catalogue"))
    assert result.status == DeliveryStatus.BLOCKED and "Frozen BDE" in result.reason
    assert await app.deliveries.dispatch(DeliveryRequest(handoff, "catalogue")) == result
    assert app.records.load(setup.project_id).active_delivery is None
    assert git(Path(setup.repository_root), "rev-parse", "HEAD") == setup.scaffold_revision


@pytest.mark.asyncio
async def test_existing_projects_service_additive_query_and_default_behavior(tmp_path, monkeypatch):
    import core.services.project_service as module
    stores = []
    for name in ("ProjectRepo", "TicketRepo", "CodeRepo", "SpecVersionRepo"):
        store = AsyncMock()
        stores.append(store)
        monkeypatch.setattr(module, name, lambda value=store: value)
    stores[0].get_by_id.return_value = Project(_id="existing-parent", name="Existing project")
    stores[0].list_all.return_value = [stores[0].get_by_id.return_value]
    normal = module.ProjectsService()
    assert len(await normal.list_projects()) == 1
    assert await normal.get_development_setup("existing-parent") is None
    handoff, _, app = environment(tmp_path)
    setup = await app.setup.prepare(handoff)
    query = module.ProjectsService(tmp_path / "projects")
    result = await query.get_development_setup("existing-parent")
    assert result["project_id"] == "existing-parent" and len(result["behaviors"]) == 3
    assert result["repository_root"] == setup.repository_root
    stores[0].get_by_id.return_value = None
    assert await query.get_development_setup("missing") is None


def test_frozen_sources_and_all_bde_files_remain_byte_identical():
    frozen = json.loads((FIXTURE / "bde-freeze.json").read_text())
    root = Path(__file__).resolve().parents[1]
    for name, digest in frozen["files"].items():
        assert sha256((root / name).read_bytes()).hexdigest() == digest, name
    handoff = load_test_architecture(FixtureBinding(FIXTURE, "existing-parent"))
    assert len(handoff.decision.behaviors) == 3
    assert all(sha256(item.source.encode()).hexdigest() == item.source_sha256
               for item in handoff.decision.behaviors)


@pytest.mark.asyncio
async def test_git_inspection_failure_is_recorded_uncertain_without_stranded_active_marker(tmp_path, monkeypatch):
    handoff, projects, app = environment(tmp_path)
    initial = await app.setup.prepare(handoff)
    async def broken_git(request):
        monkeypatch.setattr(deliveries.dependencies.workspace.authority, "verify_project",
                            lambda project: (_ for _ in ()).throw(
                                subprocess.CalledProcessError(128, ("git", "rev-parse"))))
        raise RuntimeError("controlled transport/engine exception")
    engine = ControlledBde(tmp_path, broken_git)
    deliveries = controlled_deliveries(tmp_path, handoff, projects, app, engine)
    result = await deliveries.dispatch(DeliveryRequest(handoff, "catalogue"))
    assert result.status == DeliveryStatus.FAILED and result.repository_uncertain
    assert "controlled transport/engine exception" in result.traceback
    state = app.records.load(initial.project_id)
    assert state.active_delivery is None and state.last_accepted_revision == initial.scaffold_revision
    with pytest.raises(ValueError, match="no safe"):
        await deliveries.dispatch(DeliveryRequest(handoff, "basket"))


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("authority_missing", "revision_changed", "scaffold_conflict"))
async def test_existing_repository_conflicts_are_preserved_before_smoke(tmp_path, failure):
    from core.project_setup.architecture import ExistingRepository, RepositoryPolicy
    handoff = approved()
    repo = tmp_path / "projects" / handoff.decision.project_id / "repository"
    repo.mkdir(parents=True)
    subprocess.run(("git", "init", "-b", "main", str(repo)), check=True, capture_output=True)
    (repo / "README.md").write_text("Existing user-owned application\n")
    if failure == "scaffold_conflict":
        (repo / "pyproject.toml").write_text("# existing different environment\n")
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Existing", "-c", "user.email=existing@example.test",
        "commit", "-m", "Existing authorized application")
    revision = git(repo, "rev-parse", "HEAD")
    original = {path.name: path.read_bytes() for path in repo.iterdir() if path.is_file()}
    if failure != "authority_missing":
        decision = replace(handoff.decision, repository_policy=RepositoryPolicy.EXISTING_APPROVED,
                           existing_repository=ExistingRepository(str(repo),
                               "0" * 40 if failure == "revision_changed" else revision))
        handoff = reapprove(handoff, decision)
    handoff, _, app = environment(tmp_path, handoff)
    with pytest.raises(ValueError):
        await app.setup.prepare(handoff)
    assert {path.name: path.read_bytes() for path in repo.iterdir() if path.is_file()} == original
    assert git(repo, "rev-parse", "HEAD") == revision
    assert not git(repo, "status", "--porcelain")
    assert not list(repo.glob("tests"))
    assert not app.records.load(handoff.decision.project_id).commands
