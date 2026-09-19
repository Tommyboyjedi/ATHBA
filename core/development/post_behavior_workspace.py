"""Adapt exact post-behavior changes to the existing generic workspace port."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from collections.abc import Mapping
from pathlib import PurePosixPath

from core.development.athba_workspace_routing import (
    AthbaExecutionProfile, AthbaOutboundPriority, AthbaWorkspaceIdentity,
    GenericModelCapability, WorkspaceComplexity,
)
from core.development.post_behavior_assessment import IdentifierRename, RefactorOpportunity
from core.development.post_behavior_slice import FocusedProductionSlice
from core.development.post_behavior_test_context import RenameReferenceContext, affected_reference_sources
from core.development.post_behavior_rename import (
    FocusedRenameSelection, RenameSelection, RenameTarget, select_focused_target, select_target,
)
from core.development.specification_revision_snapshot import production_python
from core.development.project_environment_state import ProjectRuntime
from core.development.specification_evidence_policy import RevisionFile, SpecificationSnapshot
from core.execution.rack_ai_request import RepositoryBinding
from core.execution.workspace_execution_port import (
    AiWorkspaceExecutionPort, WorkspaceExecutionRequest, WorkspaceExecutionResult,
)

DEFAULT_CHANGE_TIMEOUT_SECONDS = 600
DISABLED_NETWORK = "disabled"
RENAME_INSTRUCTION = (
    "Perform only the exact identifier substitution below and update its references. "
    "Change production and the supplied affected tests only where that substitution is necessary. "
    "Preserve algorithms, control flow, values, assertions, expected results, test cases and all other identifiers. "
    "Do not perform unrelated cleanup. Preserve all observable behavior."
)
REFACTOR_CHANGE_INSTRUCTION = (
    "Apply only the single bounded objective below to the supplied production code. "
    "Tests are read-only. Preserve public/product identifiers, public signatures, inputs, outputs, "
    "observable exceptions, observable side effects and all accepted behavior. "
    "Internal variables, private helpers and internal structure may change where necessary."
)


@dataclass(frozen=True)
class PostBehaviorWorkspaceInput:
    identity: AthbaWorkspaceIdentity
    repository: RepositoryBinding
    production: FocusedProductionSlice
    accepted_tests: tuple[RevisionFile, ...]
    acceptance_commands: tuple[tuple[str, ...], ...]
    timeout_seconds: int = DEFAULT_CHANGE_TIMEOUT_SECONDS
    priority: AthbaOutboundPriority = AthbaOutboundPriority.LOW
    runtime: ProjectRuntime | None = None
    rename_reference_sources: SpecificationSnapshot | None = None

    def __post_init__(self) -> None:
        if self.repository.base_sha != self.production.revision:
            raise ValueError("workspace base must equal the accepted production slice revision")
        if not self.production.files:
            raise ValueError("workspace changes require focused production source")
        for value in self.identity.values():
            if re.fullmatch(r"[a-f0-9-]{32,64}", value) is None:
                raise ValueError("workspace identities must be opaque")
        for file in (*self.production.files, *self.accepted_tests):
            path = PurePosixPath(file.path)
            if path.is_absolute() or ".." in path.parts or any(mark in file.path for mark in ("*", "?", "\\")):
                raise ValueError("workspace authority requires exact relative paths")
        if self.rename_reference_sources is not None:
            if not self.rename_reference_sources.complete or self.rename_reference_sources.revision != self.production.revision:
                raise ValueError("rename references require the complete exact accepted revision")
        resources = self.runtime.resource_paths() if self.runtime is not None else []
        if self.repository.environment_resources != resources:
            raise ValueError("post-behavior changes do not authorize unrelated context resources")


class PostBehaviorWorkspaceRequests:
    """Build minimal generic task payloads and exact machine-enforced write envelopes."""

    def rename(self, request: PostBehaviorWorkspaceInput, rename: IdentifierRename) -> WorkspaceExecutionRequest:
        target = _rename_target(request, rename)
        affected_tests = affected_reference_sources(RenameReferenceContext(target, request.accepted_tests))
        sources = request.production.files
        if request.rename_reference_sources is not None:
            sources = tuple(file for file in request.rename_reference_sources.files if production_python(file))
        production = affected_reference_sources(RenameReferenceContext(target, sources))
        payload = {
            "identifier_substitution": {"current_name": rename.current_name, "required_name": rename.required_name},
            "production": _sources(production),
            "affected_tests": _sources(affected_tests),
        }
        writable = _writable_paths((*production, *affected_tests))
        return _request(request, _Task(RENAME_INSTRUCTION, payload, writable))

    def refactor(self, request: PostBehaviorWorkspaceInput, opportunity: RefactorOpportunity) -> WorkspaceExecutionRequest:
        payload = {"objective": opportunity.objective, "production": _sources(request.production.files)}
        writable = tuple(file.path for file in request.production.files)
        return _request(request, _Task(REFACTOR_CHANGE_INSTRUCTION, payload, writable))


class PostBehaviorWorkspaceExecutor:
    """Use the replaceable execution port without selecting physical resources."""

    def __init__(self, port: AiWorkspaceExecutionPort):
        self.port = port

    def execute(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        return self.port.submit_workspace_change(request)

    def recover(self, submission_id: str) -> WorkspaceExecutionResult | None:
        return self.port.get_result(submission_id)


@dataclass(frozen=True)
class _Task:
    instruction: str
    payload: Mapping[str, object]
    writable: tuple[str, ...]


def opaque_workspace_identity(identity: AthbaWorkspaceIdentity) -> AthbaWorkspaceIdentity:
    return AthbaWorkspaceIdentity(*(hashlib.sha256(value.encode()).hexdigest() for value in identity.values()))


def _request(request: PostBehaviorWorkspaceInput, task: _Task) -> WorkspaceExecutionRequest:
    return WorkspaceExecutionRequest(
        identity=request.identity,
        profile=AthbaExecutionProfile(
            frozenset({GenericModelCapability.CODING}), WorkspaceComplexity.SMALL,
            False, request.priority, request.timeout_seconds,
        ),
        repository=request.repository,
        allowed_writable_paths=task.writable,
        network_policy=DISABLED_NETWORK,
        acceptance_commands=request.acceptance_commands,
        required_artifacts=tuple(file.path for file in request.production.files),
        objective=task.instruction + "\n" + json.dumps(task.payload),
    )


def _sources(files: tuple[RevisionFile, ...]) -> list[dict[str, str]]:
    return [{"path": file.path, "source": file.source} for file in files]



def _rename_target(request: PostBehaviorWorkspaceInput, mapping: IdentifierRename) -> RenameTarget:
    if request.rename_reference_sources is not None:
        return select_target(RenameSelection(
            request.rename_reference_sources, request.production,
            mapping.current_name, mapping.required_name,
        ))
    return select_focused_target(FocusedRenameSelection(
        request.production.files, mapping.current_name, mapping.required_name,
    ))



def _writable_paths(files: tuple[RevisionFile, ...]) -> tuple[str, ...]:
    paths = tuple(file.path for file in files)
    for value in paths:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or any(mark in value for mark in ("*", "?", "\\")):
            raise ValueError("workspace authority requires exact relative paths")
    if len(set(paths)) != len(paths):
        raise ValueError("workspace authority contains duplicate paths")
    return paths
