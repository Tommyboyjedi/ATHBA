"""Source-bound approved architecture inputs; no setup effects or model decisions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import PurePosixPath

from core.filesystem_policy import validate_filesystem_identifier
from core.project_setup.profile_domain import ProfileSelection


def content_hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class ApprovalKind(str, Enum):
    HUMAN = "human"
    TEST_FIXTURE = "test_fixture"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"


class RepositoryPolicy(str, Enum):
    CREATE_OR_REUSE = "create_or_reuse"
    EXISTING_APPROVED = "existing_approved"


@dataclass(frozen=True)
class FullBehavior:
    id: str
    source: str
    source_sha256: str
    production_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    depends_on: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_filesystem_identifier(self.id, "full behavior id")
        if not self.source.strip() or sha256(self.source.encode()).hexdigest() != self.source_sha256:
            raise ValueError("full behavior source hash does not match its frozen bytes")
        if not self.production_paths or not self.test_paths:
            raise ValueError("behavior requires production and test scopes")
        for path in (*self.production_paths, *self.test_paths):
            validate_scope(path)


def validate_scope(path: str) -> None:
    from core.filesystem_policy import resolve_relative_path
    from pathlib import Path

    resolve_relative_path(Path("/approved-project"), path, "approved source/test path")
    if path in ("", ".") or "\\" in path or PurePosixPath(path).as_posix() != path:
        raise ValueError("source/test paths require canonical relative POSIX file spelling")
    if ".git" in PurePosixPath(path).parts:
        raise ValueError("Git authority is not an application source scope")


@dataclass(frozen=True)
class ExistingRepository:
    root: str
    trusted_revision: str
    canonical_ref: str = "refs/heads/main"


@dataclass(frozen=True)
class ArchitectureDecision:
    project_id: str
    specification_version: int
    specification_sha256: str
    version: int
    application_kind: str
    profile: ProfileSelection
    behaviors: tuple[FullBehavior, ...]
    repository_policy: RepositoryPolicy = RepositoryPolicy.CREATE_OR_REUSE
    existing_repository: ExistingRepository | None = None

    def __post_init__(self) -> None:
        validate_filesystem_identifier(self.project_id, "project id")
        if self.version < 1 or self.specification_version < 1 or not self.application_kind.strip():
            raise ValueError("architecture and specification must be versioned")
        ids = [item.id for item in self.behaviors]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("full behavior identities must be unique")
        seen: set[str] = set()
        scopes: set[str] = set()
        for item in self.behaviors:
            if not set(item.depends_on) <= seen:
                raise ValueError("behavior dependencies must precede the delivery")
            paths = set((*item.production_paths, *item.test_paths))
            if any(a == b or PurePosixPath(a) in PurePosixPath(b).parents
                   or PurePosixPath(b) in PurePosixPath(a).parents for a in scopes for b in paths):
                raise ValueError("initial full-behavior scopes must be disjoint")
            scopes.update(paths)
            seen.add(item.id)
        if self.repository_policy == RepositoryPolicy.EXISTING_APPROVED and self.existing_repository is None:
            raise ValueError("existing repository requires explicit revision authority")

    @property
    def digest(self) -> str:
        return content_hash(asdict(self))


@dataclass(frozen=True)
class ArchitectureApproval:
    identity: str
    project_id: str
    architecture_sha256: str
    kind: ApprovalKind
    status: ApprovalStatus
    binding_conflicts_resolved: bool


@dataclass(frozen=True)
class ApprovedArchitecture:
    decision: ArchitectureDecision
    approval: ArchitectureApproval
    schema: str = "athba/approved-architecture/v1"


@dataclass(frozen=True)
class PinnedArchitectureApproval:
    """The upstream authority supplies this receipt; setup never issues approval."""
    receipt: ArchitectureApproval
    test_project_id: str | None = None

    def require(self, handoff: ApprovedArchitecture) -> None:
        approval = handoff.approval
        decision = handoff.decision
        if handoff.schema != "athba/approved-architecture/v1" or approval != self.receipt:
            raise ValueError("architecture does not match the pinned upstream approval")
        if approval.status != ApprovalStatus.APPROVED or not approval.identity.strip():
            raise ValueError("architecture approval is required before provisioning")
        if not approval.binding_conflicts_resolved:
            raise ValueError("binding product constraint approval is unresolved")
        if approval.project_id != decision.project_id or approval.architecture_sha256 != decision.digest:
            raise ValueError("approval must bind this project and exact architecture")
        if approval.kind == ApprovalKind.TEST_FIXTURE and self.test_project_id != decision.project_id:
            raise ValueError("fixture approval is permitted only in its explicit test-project scope")
