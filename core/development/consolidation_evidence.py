"""Immutable accepted-test supersession authority and active evidence resolution."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.development.specification_reconciliation import AcceptedTestEvidence
    from core.development.test_material import TestMaterialAdapter

EVIDENCE_GIT_TIMEOUT_SECONDS = 15
CONSOLIDATED_GREEN_EVIDENCE = "consolidated_green"


def _text(value: str) -> None:
    if not value.strip():
        raise ValueError("consolidation authority contains an empty value")


def _unique(values: tuple[str, ...]) -> None:
    if not values or len(values) != len(set(values)):
        raise ValueError("consolidation authority must be nonempty and unique")
    for value in values:
        _text(value)


@dataclass(frozen=True)
class CaseSnapshot:
    name: str
    path: str
    source: str
    revision: str
    requirement_refs: tuple[str, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for value in (self.name, self.path, self.source, self.revision):
            _text(value)
        path = PurePosixPath(self.path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("accepted test path must be repository relative")
        _unique(self.requirement_refs)
        _unique(self.source_refs)

    @property
    def source_hash(self) -> str:
        return sha256(self.source.encode("utf-8")).hexdigest()

    @property
    def observation_ref(self) -> str:
        return f"accepted-test:{self.name}:{self.source_hash}"

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "path": self.path, "source": self.source,
                "revision": self.revision, "requirement_refs": list(self.requirement_refs),
                "source_refs": list(self.source_refs), "source_hash": self.source_hash}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CaseSnapshot":
        result = cls(str(value["name"]), str(value["path"]), str(value["source"]),
                     str(value["revision"]), tuple(value["requirement_refs"]),
                     tuple(value["source_refs"]))
        if value.get("source_hash", result.source_hash) != result.source_hash:
            raise ValueError("accepted test snapshot hash differs from its source")
        return result


@dataclass(frozen=True)
class CoverageLink:
    authority_ref: str
    replacement_test: str
    description: str

    def __post_init__(self) -> None:
        for value in (self.authority_ref, self.replacement_test, self.description):
            _text(value)

    def to_dict(self) -> dict[str, object]:
        return {"authority_ref": self.authority_ref, "replacement_test": self.replacement_test,
                "description": self.description}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CoverageLink":
        return cls(str(value["authority_ref"]), str(value["replacement_test"]), str(value["description"]))


@dataclass(frozen=True)
class SupersessionRecord:
    checkpoint_id: str
    member_refs: tuple[str, ...]
    previous_tests: tuple[CaseSnapshot, ...]
    replacement_tests: tuple[CaseSnapshot, ...]
    description: str
    coverage: tuple[CoverageLink, ...]
    production_revision: str
    test_revision: str
    final_revision: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for value in (self.checkpoint_id, self.description, self.production_revision,
                      self.test_revision, self.final_revision):
            _text(value)
        _unique(self.member_refs)
        _unique(self.evidence_refs)
        _unique(tuple(item.name for item in self.previous_tests))
        _unique(tuple(item.name for item in self.replacement_tests))
        previous_members = {ref for item in self.previous_tests for ref in item.requirement_refs}
        replacement_members = {ref for item in self.replacement_tests for ref in item.requirement_refs}
        previous_sources = {ref for item in self.previous_tests for ref in item.source_refs}
        replacement_sources = {ref for item in self.replacement_tests for ref in item.source_refs}
        if previous_members != set(self.member_refs) or replacement_members != previous_members:
            raise ValueError("test supersession does not preserve original requirement membership")
        if replacement_sources != previous_sources:
            raise ValueError("test supersession does not preserve original source authority")
        required = set(self.member_refs) | {item.observation_ref for item in self.previous_tests}
        if not required.issubset({item.authority_ref for item in self.coverage}):
            raise ValueError("test supersession omits prior observation coverage")
        names = {item.name for item in self.replacement_tests}
        if any(item.replacement_test not in names for item in self.coverage):
            raise ValueError("coverage points to an unknown replacement")
        if names != {item.replacement_test for item in self.coverage}:
            raise ValueError("replacement test lacks authority coverage")

    def to_dict(self) -> dict[str, object]:
        return {"checkpoint_id": self.checkpoint_id, "member_refs": list(self.member_refs),
                "previous_tests": [item.to_dict() for item in self.previous_tests],
                "replacement_tests": [item.to_dict() for item in self.replacement_tests],
                "description": self.description, "coverage": [item.to_dict() for item in self.coverage],
                "production_revision": self.production_revision, "test_revision": self.test_revision,
                "final_revision": self.final_revision, "evidence_refs": list(self.evidence_refs)}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SupersessionRecord":
        return cls(str(value["checkpoint_id"]), tuple(value["member_refs"]),
                   tuple(CaseSnapshot.from_dict(item) for item in value["previous_tests"]),
                   tuple(CaseSnapshot.from_dict(item) for item in value["replacement_tests"]),
                   str(value["description"]),
                   tuple(CoverageLink.from_dict(item) for item in value["coverage"]),
                   str(value["production_revision"]), str(value["test_revision"]),
                   str(value["final_revision"]), tuple(value["evidence_refs"]))


@dataclass(frozen=True)
class ActiveEvidenceRequest:
    original_tests: tuple[AcceptedTestEvidence, ...]
    supersessions: tuple[SupersessionRecord, ...]
    revision: str


@dataclass(frozen=True)
class _EvidenceGit:
    root: Path
    adapter: TestMaterialAdapter

    def source(self, revision: str, name: str) -> str:
        from core.development.test_material import TestSourceRequest
        path = self.adapter.test_path(name)
        normalized = PurePosixPath(path)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError("accepted evidence path is not relative")
        result = subprocess.run(("git", "show", f"{revision}:{path}"), cwd=self.root,
                                capture_output=True, text=True, timeout=EVIDENCE_GIT_TIMEOUT_SECONDS)
        source = self.adapter.extract(TestSourceRequest(result.stdout, name)) if result.returncode == 0 else None
        if source is None:
            raise ValueError("accepted evidence source is unavailable")
        return source

    def ancestor(self, previous: str, current: str) -> None:
        result = subprocess.run(("git", "merge-base", "--is-ancestor", previous, current),
                                cwd=self.root, capture_output=True, text=True,
                                timeout=EVIDENCE_GIT_TIMEOUT_SECONDS)
        if result.returncode != 0:
            raise ValueError("accepted evidence revision ancestry is not established")

    def snapshot(self, case: CaseSnapshot, revision: str) -> None:
        if self.adapter.test_path(case.name) != case.path:
            raise ValueError("accepted test identity differs from snapshot path")
        self.ancestor(case.revision, revision)
        if self.source(case.revision, case.name) != case.source or self.source(revision, case.name) != case.source:
            raise ValueError("accepted test snapshot hash/source changed")


class ActiveAcceptedEvidenceResolver:
    """Select only source-verified supersessions; never alter historical evidence."""

    def __init__(self, repository_root: Path, test_material: TestMaterialAdapter):
        self.git = _EvidenceGit(repository_root, test_material)

    def resolve(self, request: ActiveEvidenceRequest) -> tuple[AcceptedTestEvidence, ...]:
        active: dict[str, AcceptedTestEvidence] = {}
        checkpoints: set[str] = set()
        for item in request.original_tests:
            if item.test_name in active:
                raise ValueError("duplicate original accepted test")
            self.git.ancestor(item.semantic_revision, request.revision)
            self.git.source(item.semantic_revision, item.test_name)
            active[item.test_name] = item
        prior_revision: str | None = None
        for record in request.supersessions:
            if record.checkpoint_id in checkpoints:
                raise ValueError("duplicate accepted-test supersession checkpoint")
            checkpoints.add(record.checkpoint_id)
            if prior_revision is not None:
                self.git.ancestor(prior_revision, record.production_revision)
            self.git.ancestor(record.production_revision, record.test_revision)
            self.git.ancestor(record.test_revision, record.final_revision)
            self.git.ancestor(record.final_revision, request.revision)
            self._replace(active, record)
            prior_revision = record.final_revision
        for item in active.values():
            if self.git.source(item.semantic_revision, item.test_name) != self.git.source(request.revision, item.test_name):
                raise ValueError("active accepted test changed without supersession authority")
        return tuple(active.values())

    def _replace(self, active: dict[str, AcceptedTestEvidence], record: SupersessionRecord) -> None:
        from core.development.specification_reconciliation import AcceptedTestEvidence
        selected = {item.name for item in record.previous_tests}
        for case in record.previous_tests:
            prior = active.get(case.name)
            if prior is None:
                raise ValueError("supersession references unknown or retired test")
            members = prior.covered_requirement_refs or (prior.step_id,)
            if set(case.requirement_refs) != set(members) or set(case.source_refs) != set(prior.requirement_refs):
                raise ValueError("supersession changed accepted test provenance")
            if self.git.source(prior.semantic_revision, prior.test_name) != case.source:
                raise ValueError("supersession does not match historical accepted source")
            self.git.snapshot(case, record.production_revision)
        for case in record.replacement_tests:
            if case.name in active and case.name not in selected:
                raise ValueError("replacement overwrites unselected accepted evidence")
            self.git.snapshot(case, record.test_revision)
            self.git.snapshot(case, record.final_revision)
        for name in selected:
            del active[name]
        for case in record.replacement_tests:
            active[case.name] = AcceptedTestEvidence(
                case.name, case.path, record.checkpoint_id, list(case.source_refs), None,
                record.final_revision, case.source, evidence_kind=CONSOLIDATED_GREEN_EVIDENCE,
                supersession_id=record.checkpoint_id, superseded_tests=tuple(sorted(selected)),
                covered_requirement_refs=case.requirement_refs)
