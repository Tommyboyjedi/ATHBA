"""Preserve verified completed-delivery test authority across Git integration."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from enum import Enum
from pathlib import Path
from typing import Any

from core.development.assurance_completion import AssuranceGap
from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.development.behavior_contract_domain import BehaviorContract
from core.development.behavior_replan_domain import BehaviorReplanPhase
from core.development.consolidation_evidence import ActiveAcceptedEvidenceResolver, ActiveEvidenceRequest
from core.development.specification_reconciliation import (
    CompletedMicrocycleEvidenceCollector, GitAcceptedTestCatalog, TestCatalogRevision,
)
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.post_behavior_domain import (
    PostBehaviorCall, PostBehaviorOutcome, PostBehaviorStatus,
)
from core.development.post_behavior_entry import AcceptedBehavioralDeliveryLoader
from core.development.post_behavior_store import PostBehaviorStateRepository
from core.development.post_behavior_validation import PostBehaviorCandidateAuthority, PostBehaviorPassAuthority
from core.development.project_environment_port import PreparedProjectEnvironment
from core.development.test_material import TestMaterialAdapter, TestSourceRequest
from core.development.post_behavior_git import PostBehaviorGit


class ContributionKind(str, Enum):
    COMPLETED = "completed"
    CHECKPOINT = "checkpoint"


@dataclass(frozen=True)
class AcceptedNode:
    test_name: str
    test_path: str
    source_sha256: str
    origin_revision: str
    requirement_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    production_path: str
    delivery_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AcceptedNode:
        return cls(**{**value, "requirement_refs": tuple(value["requirement_refs"]),
                      "source_refs": tuple(value["source_refs"])})


@dataclass(frozen=True)
class AcceptedContribution:
    project_id: str
    delivery_id: str
    behavior_id: str
    source_sha256: str
    architecture_sha256: str
    completion_revision: str
    source_text: str
    tests: tuple[AcceptedNode, ...]
    provenance_refs: tuple[str, ...]
    unproven_assurance: tuple[AssuranceGap, ...] = ()
    supersessions: tuple[dict[str, Any], ...] = ()
    naming_history: tuple[dict[str, Any], ...] = ()
    authority_digest: str = ""
    kind: ContributionKind = ContributionKind.COMPLETED

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ContributionKind(self.kind))
        if not self.tests or not self.provenance_refs:
            raise ValueError("accepted contribution requires actual tests and retained provenance")
        if len({item.test_name for item in self.tests}) != len(self.tests):
            raise ValueError("accepted contribution repeats a test identity")
        if any(not value for value in (self.project_id, self.delivery_id, self.behavior_id,
                                       self.architecture_sha256, self.completion_revision)):
            raise ValueError("accepted contribution identity is incomplete")
        if sha256(self.source_text.encode("utf-8")).hexdigest() != self.source_sha256:
            raise ValueError("accepted contribution source authority changed")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AcceptedContribution:
        return cls(**{**value, "tests": tuple(AcceptedNode.from_dict(item) for item in value["tests"]),
            "provenance_refs": tuple(value["provenance_refs"]),
            "unproven_assurance": tuple(AssuranceGap(**item) for item in value.get("unproven_assurance", ())),
            "supersessions": tuple(value.get("supersessions", ())),
            "naming_history": tuple(value.get("naming_history", ()))})


@dataclass(frozen=True)
class AcceptedSourceReader:
    repository_root: Path
    test_material: TestMaterialAdapter

    def source(self, identity: tuple[str, str]) -> str:
        revision, name = identity
        path = self.test_material.test_path(name)
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("accepted test path is not repository-relative")
        module = PostBehaviorGit(self.repository_root).command(("show", f"{revision}:{path}"))
        source = self.test_material.extract(TestSourceRequest(module, name))
        if source is None:
            raise ValueError("accepted test identity is unavailable: " + name)
        return source


@dataclass(frozen=True)
class CompletedEvidenceRequest:
    state_root: Path
    project_id: str
    delivery_id: str
    behavior_id: str
    source_sha256: str
    architecture_sha256: str
    prepared_environment: PreparedProjectEnvironment


@dataclass(frozen=True)
class CompletedEvidenceLoader:
    test_material: TestMaterialAdapter
    post_authority: PostBehaviorCandidateAuthority

    def load_checkpoint(self, request: CompletedEvidenceRequest) -> AcceptedContribution:
        return AcceptedCheckpointLoader(self.test_material).load(request)

    def load(self, request: CompletedEvidenceRequest) -> AcceptedContribution:
        delivery = AcceptedBehavioralDeliveryLoader(
            request.state_root, self.test_material, request.prepared_environment).load(request.project_id)
        state = PostBehaviorStateRepository(request.state_root / "post-behavior").load(request.project_id)
        if state is None or state.status not in {
                PostBehaviorStatus.POST_BEHAVIOR_COMPLETE,
                PostBehaviorStatus.POST_BEHAVIOR_COMPLETE_WITH_UNPROVEN_ASSURANCE}:
            raise ValueError("integration requires actual completed post-behavior authority")
        if state.entry != delivery.entry or state.active_pass is not None or state.pending_call != PostBehaviorCall.NONE:
            raise ValueError("completed branch has inconsistent or unresolved post-behavior authority")
        if delivery.feature.project_id != request.project_id:
            raise ValueError("completed feature belongs to a different project")
        if delivery.feature.source_requirement_hash != request.source_sha256:
            raise ValueError("completed feature source identity changed")
        if delivery.feature.delivery_identity != request.delivery_id:
            raise ValueError("completed feature belongs to a different delivery identity")
        source = delivery.contract.requirement_source
        if sha256(source.encode("utf-8")).hexdigest() != request.source_sha256:
            raise ValueError("completed source differs from approved full behavior")
        for change in state.passes:
            if change.outcome == PostBehaviorOutcome.PROMOTED:
                self.post_authority.verify_pass(PostBehaviorPassAuthority(state.entry, change))
        revision = state.current_post_behavior_revision
        git = PostBehaviorGit(Path(delivery.project.repository_root))
        git.command(("merge-base", "--is-ancestor", revision, delivery.project.trusted_base_sha))
        reader = AcceptedSourceReader(git.repository_root, self.test_material)
        tests = []
        for item in delivery.accepted_tests:
            current = reader.source((revision, item.test_name))
            tests.append(AcceptedNode(item.test_name, item.test_path,
                sha256(current.encode("utf-8")).hexdigest(), item.semantic_revision,
                tuple(item.covered_requirement_refs or (item.step_id,)), tuple(item.requirement_refs),
                delivery.contract.production_paths[0], request.delivery_id))
        refs = (str(request.state_root / "features" / (request.project_id + ".json")),
                str(request.state_root / "post-behavior" / (request.project_id + ".json")))
        return AcceptedContribution(request.project_id, request.delivery_id, request.behavior_id,
            request.source_sha256, request.architecture_sha256, revision, source, tuple(tests), refs,
            state.unproven_assurance,
            tuple(record.to_dict() for record in delivery.feature.evidence_consolidations),
            tuple(asdict(change) for change in state.passes),
            state.entry.behavioral_authority_digest)


@dataclass(frozen=True)
class EvidenceTreeRequest:
    repository_root: Path
    revision: str
    contributions: tuple[AcceptedContribution, ...]


@dataclass(frozen=True)
class AcceptedEvidenceUnion:
    test_material: TestMaterialAdapter

    def combine(self, contributions: tuple[AcceptedContribution, ...]) -> tuple[AcceptedNode, ...]:
        active: dict[str, AcceptedNode] = {}
        projects = {item.project_id for item in contributions}
        if len(projects) > 1:
            raise ValueError("accepted contributions belong to different application projects")
        owners: dict[str, AcceptedContribution] = {}
        for item in contributions:
            previous = owners.get(item.delivery_id)
            if previous is not None and previous != item:
                raise ValueError("delivery completion authority changed")
            owners[item.delivery_id] = item
            if sha256(item.source_text.encode("utf-8")).hexdigest() != item.source_sha256:
                raise ValueError("accepted contribution source authority changed")
            for test in item.tests:
                if test.delivery_id != item.delivery_id:
                    raise ValueError("accepted test belongs to a different delivery")
                if test.test_name in active and active[test.test_name] != test:
                    raise ValueError("accepted test identity ownership conflicts")
                active[test.test_name] = test
        return tuple(active.values())

    def verify(self, request: EvidenceTreeRequest) -> tuple[AcceptedNode, ...]:
        tests = self.combine(request.contributions)
        git = PostBehaviorGit(request.repository_root)
        for item in request.contributions:
            git.command(("merge-base", "--is-ancestor", item.completion_revision, request.revision))
        reader = AcceptedSourceReader(request.repository_root, self.test_material)
        for test in tests:
            if self.test_material.test_path(test.test_name) != test.test_path:
                raise ValueError("accepted test path differs from its identity")
            source = reader.source((request.revision, test.test_name))
            if sha256(source.encode("utf-8")).hexdigest() != test.source_sha256:
                raise ValueError("integration changed or removed accepted test evidence: " + test.test_name)
        return tests


@dataclass(frozen=True)
class AcceptedCheckpointLoader:
    """Read only quiescent completed-REQ evidence; no final completion is claimed."""
    test_material: TestMaterialAdapter

    def load(self, request: CompletedEvidenceRequest) -> AcceptedContribution:
        state = StrictTddFeatureRepository(request.state_root / "features").load(request.project_id)
        project = request.prepared_environment.repo.load(request.project_id)
        if state is None or project is None or not state.completed_behaviors:
            raise ValueError("synchronization checkpoint requires completed behavioral evidence")
        if state.project_id != request.project_id or state.delivery_identity != request.delivery_id or state.source_requirement_hash != request.source_sha256:
            raise ValueError("checkpoint source/delivery identity differs from approved authority")
        if (state.current_scenario_id or state.working_ref or state.working_revision
                or state.pending_completed_behavior or state.final_reconciliation):
            raise ValueError("synchronization checkpoint is not quiescent before final reconciliation")
        pending = {BehaviorReplanPhase.REQUIRED, BehaviorReplanPhase.STARTED,
                   BehaviorReplanPhase.RECEIVED, BehaviorReplanPhase.CORRECTION_STARTED}
        if any(item.phase in pending for item in state.behavior_replans):
            raise ValueError("synchronization checkpoint has unresolved semantic work")
        revision = state.canonical_development_base
        if not revision or project.trusted_base_sha != revision:
            raise ValueError("checkpoint differs from current trusted delivery revision")
        git = PostBehaviorGit(Path(project.repository_root))
        if (git.command(("rev-parse", "HEAD")).strip() != revision
                or state.canonical_ref != "refs/heads/" + project.default_ref
                or git.command(("symbolic-ref", "-q", "HEAD")).strip() != state.canonical_ref
                or git.command(("status", "--porcelain", "--untracked-files=no")).strip()):
            raise ValueError("checkpoint requires a clean exact trusted checkout")
        contract = BehaviorContract.from_dict(dict(state.contract_payload or {}))
        if sha256(contract.requirement_source.encode()).hexdigest() != request.source_sha256:
            raise ValueError("checkpoint contract source changed")
        store = MicrocycleStateRepo(request.state_root / "microcycles")
        states = [store.load(item.scenario_id) for item in state.completed_behaviors]
        if any(item is None for item in states):
            raise ValueError("checkpoint completed microcycle evidence is unavailable")
        original = CompletedMicrocycleEvidenceCollector().collect(tuple(item for item in states if item is not None))
        if len(original) != len(states):
            raise ValueError("checkpoint does not preserve every completed origin")
        accepted = ActiveAcceptedEvidenceResolver(git.repository_root, self.test_material).resolve(
            ActiveEvidenceRequest(tuple(original), state.evidence_consolidations, revision))
        catalog = GitAcceptedTestCatalog(git.repository_root, TestCatalogRevision(revision, self.test_material))
        if any(catalog.verified_source(item) is None for item in accepted):
            raise ValueError("checkpoint changed accepted tests without supersession authority")
        reader = AcceptedSourceReader(git.repository_root, self.test_material)
        tests = tuple(AcceptedNode(item.test_name, item.test_path,
            sha256(reader.source((revision, item.test_name)).encode()).hexdigest(),
            item.semantic_revision, tuple(item.covered_requirement_refs or (item.step_id,)),
            tuple(item.requirement_refs), contract.production_paths[0], request.delivery_id) for item in accepted)
        refs = (str(request.state_root / "features" / (request.project_id + ".json")),)
        return AcceptedContribution(request.project_id, request.delivery_id, request.behavior_id,
            request.source_sha256, request.architecture_sha256, revision, contract.requirement_source,
            tests, refs, supersessions=tuple(item.to_dict() for item in state.evidence_consolidations),
            kind=ContributionKind.CHECKPOINT)
