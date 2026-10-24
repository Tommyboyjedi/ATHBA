"""Real linked worktrees with explicitly controlled OUTER execution; no live BDE/models."""
import asyncio
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import threading

import pytest

from core.delivery_management.bde import BdeBranchOutcome
from core.delivery_management.domain import DeliveryPhase, ManagementRequest, MergeStatus
from core.delivery_management.evidence import AcceptedContribution, AcceptedNode, AcceptedSourceReader
from core.delivery_management.store import RecordIdentity
from core.development.python_test_material import PythonTestMaterial
from core.project_setup.architecture import PinnedArchitectureApproval
from core.project_setup.composition import ProjectSetupCompositionRequest, compose_project_setup
from core.project_setup.delivery import DeliveryRequest
from tests.test_approved_project_setup import approved, environment, git, reapprove


class ControlledBranchExecutor:
    """This scripts the outer completion boundary; actual BDE proof is separate."""
    def __init__(self):
        self.barrier = threading.Barrier(3)
        self.release = threading.Event()
        self.calls = []
        self.failed = set()

    async def deliver(self, request):
        self.calls.append(request)
        self.barrier.wait(timeout=30)
        assert self.release.wait(timeout=30)
        record, env = request.delivery, request.environment
        if record.behavior.id in self.failed:
            return BdeBranchOutcome(DeliveryPhase.FAILED, reason="controlled branch failure")
        root = Path(record.worktree)
        production, test = record.behavior.production_paths[0], record.behavior.test_paths[0]
        (root / production).write_text("MARKER = " + repr(record.behavior.id) + "\n")
        (root / test).parent.mkdir(parents=True, exist_ok=True)
        (root / test).write_text("from " + production.removesuffix(".py") + " import MARKER\n\n"
            "def test_REQ001():\n    assert MARKER == " + repr(record.behavior.id) + "\n")
        git(root, "add", "--", production, test)
        git(root, "-c", "user.name=Controlled", "-c", "user.email=controlled@example.test",
            "commit", "-qm", "controlled accepted branch checkpoint")
        revision = git(root, "rev-parse", "HEAD")
        env.repo.save(replace(env.repo.load(record.project_id), trusted_base_sha=revision))
        name = test + "::test_REQ001"
        source = AcceptedSourceReader(root, PythonTestMaterial()).source((revision, name))
        node = AcceptedNode(name, test, sha256(source.encode()).hexdigest(), revision,
            ("REQ001",), ("SRC001",), production, record.id)
        contribution = AcceptedContribution(record.project_id, record.id, record.behavior.id,
            record.behavior.source_sha256, record.architecture_sha256, revision,
            record.behavior.source, (node,), ("controlled-outer-proof-only",))
        return BdeBranchOutcome(DeliveryPhase.COMPLETE, contribution, naming="NO", refactoring="NO")


async def prepared(tmp_path, engine):
    handoff = approved()
    one, two, three = handoff.decision.behaviors
    # Overlapping scope is legal; dependency order deliberately differs from display order.
    two = replace(two, production_paths=one.production_paths)
    three = replace(three, depends_on=(one.id,))
    handoff = reapprove(handoff, replace(handoff.decision, behaviors=(three, two, one)))
    handoff, projects, _ = environment(tmp_path, handoff)
    app = compose_project_setup(ProjectSetupCompositionRequest(tmp_path, projects,
        PinnedArchitectureApproval(handoff.approval, handoff.decision.project_id), engine))
    setup = await app.setup.prepare(handoff)
    return handoff, app, setup


@pytest.mark.asyncio
async def test_independent_workers_duplicate_dispatch_pending_sync_and_dependency_integration(tmp_path):
    engine = ControlledBranchExecutor()
    handoff, app, setup = await prepared(tmp_path, engine)
    requests = tuple(DeliveryRequest(handoff, identity) for identity in ("catalogue", "basket"))
    running = asyncio.create_task(app.deliveries.dispatch_ready(requests))
    await asyncio.to_thread(engine.barrier.wait, 30)
    records = app.management.records.deliveries(setup.project_id)
    assert len(records) == 2 and all(item.phase == DeliveryPhase.RUNNING for item in records)
    assert len({item.worktree for item in records}) == 2
    assert len({item.state_root for item in records}) == 2
    assert all((Path(item.worktree) / ".git").is_file() for item in records)
    assert git(Path(setup.repository_root), "rev-parse", "HEAD") == setup.scaffold_revision
    duplicate = await app.deliveries.dispatch(requests[0])
    assert duplicate.phase == DeliveryPhase.RUNNING and len(engine.calls) == 2
    with pytest.raises(ValueError, match="dependency"):
        await app.deliveries.prepare(DeliveryRequest(handoff, "orders"))
    deferred = app.deliveries.synchronize(ManagementRequest(setup.project_id, duplicate.id, "manager"))
    assert deferred.status == MergeStatus.DEFERRED
    engine.release.set()
    results = await running
    assert all(result.delivery.phase == DeliveryPhase.COMPLETE for result in results)
    assert not app.management.records.delivery(RecordIdentity(setup.project_id, duplicate.id)).pending_sync
    assert git(Path(setup.repository_root), "rev-parse", "HEAD") == setup.scaffold_revision
    completed = await app.deliveries.dispatch(requests[0])
    assert completed.completion_revision and len(engine.calls) == 2
    operation = app.deliveries.submit(ManagementRequest(setup.project_id, completed.id, "manager"))
    assert operation.status == MergeStatus.VALIDATED, operation.reason
    identity = RecordIdentity(setup.project_id, operation.id)
    approval = app.management.merges.approve(identity, "human-manager")
    result = app.management.merges.promote(identity, approval)
    assert result.status == MergeStatus.PUBLISHED
    dependent = await app.deliveries.prepare(DeliveryRequest(handoff, "orders"))
    assert dependent.fork_revision == result.candidate_revision
    view = app.deliveries.inspect(setup.project_id)
    assert view["application_integrated_revision"] == result.candidate_revision
    assert sum(item["integrated"] for item in view["deliveries"]) == 1
    assert all(node.requirement_refs == ("REQ001",) for call in engine.calls
               for node in AcceptedContribution.from_dict(
                   __import__("json").loads(Path(app.management.records.delivery(
                       RecordIdentity(setup.project_id, call.delivery.id)).authority_file).read_text())).tests)
    print("CONTROLLED_PARALLEL_GIT_GRAPH=" + git(Path(setup.repository_root),
        "log", "--all", "--graph", "--oneline"))


@pytest.mark.asyncio
async def test_failed_branch_does_not_cancel_independent_worker_and_explicit_resume_is_stable(tmp_path):
    engine = ControlledBranchExecutor()
    engine.failed.add("catalogue")
    handoff, app, setup = await prepared(tmp_path, engine)
    requests = tuple(DeliveryRequest(handoff, identity) for identity in ("catalogue", "basket"))
    task = asyncio.create_task(app.deliveries.dispatch_ready(requests))
    await asyncio.to_thread(engine.barrier.wait, 30)
    engine.release.set()
    results = await task
    assert [result.delivery.phase for result in results] == [DeliveryPhase.FAILED, DeliveryPhase.COMPLETE]
    failed = results[0].delivery
    assert (await app.deliveries.dispatch(requests[0])).id == failed.id
    assert len(engine.calls) == 2
    engine.failed.clear()
    engine.barrier = threading.Barrier(1)
    resumed = await app.deliveries.resume(requests[0])
    assert resumed.phase == DeliveryPhase.COMPLETE and resumed.id == failed.id
    assert resumed.fork_revision == failed.fork_revision and len(engine.calls) == 3
    assert len(app.management.records.deliveries(setup.project_id)) == 2
    assert git(Path(setup.repository_root), "rev-parse", "HEAD") == setup.scaffold_revision


@pytest.mark.asyncio
async def test_branch_publication_intent_recovers_exact_checkpoint_without_advancing_main(tmp_path, monkeypatch):
    from core.delivery_management.branch_environment import BranchEnvironment, BranchEnvironmentBinding
    engine = ControlledBranchExecutor()
    handoff, app, setup = await prepared(tmp_path, engine)
    record = await app.deliveries.prepare(DeliveryRequest(handoff, "catalogue"))
    key = RecordIdentity(setup.project_id, record.id)
    env = BranchEnvironment(BranchEnvironmentBinding(app.management.parent_environment,
        app.management.records, key))
    root = Path(record.worktree)
    # Build a detached candidate while leaving the live accepted checkout unchanged.
    (root / record.behavior.production_paths[0]).write_text("MARKER = 'candidate'\n")
    git(root, "add", record.behavior.production_paths[0])
    tree = git(root, "write-tree")
    candidate = git(root, "-c", "user.name=Controlled", "-c", "user.email=controlled@example.test",
        "commit-tree", tree, "-p", record.trusted_revision, "-m", "controlled candidate")
    git(root, "restore", "--source", record.trusted_revision, "--staged", "--worktree", ".")
    original = env.repo.save
    def interrupted(project):
        raise OSError("controlled metadata interruption after CAS")
    monkeypatch.setattr(env.repo, "save", interrupted)
    with pytest.raises(OSError, match="interruption"):
        env.record_trusted_revision(setup.project_id, candidate)
    assert app.management.records.delivery(key).revision_intent == (record.trusted_revision, candidate)
    monkeypatch.setattr(env.repo, "save", original)
    recovered = app.deliveries.recover_delivery(key)
    assert recovered.trusted_revision == candidate and recovered.revision_intent is None
    assert git(Path(setup.repository_root), "rev-parse", "HEAD") == setup.scaffold_revision
