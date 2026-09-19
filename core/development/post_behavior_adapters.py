"""Translate trusted lifecycle state into intentionally tiny model requests."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import PurePosixPath
import re

from core.development.athba_workspace_routing import AthbaWorkspaceIdentity
from core.development.post_behavior_assessment import (
    NamingAssessor, NamingAssessmentInput, NamingMaterial, NamingDecision, RefactorAssessor,
)
from core.development.post_behavior_domain import ChangeCandidate, PostBehaviorAssessment, PostBehaviorState
from core.development.post_behavior_entry import AcceptedBehavioralDelivery
from core.development.post_behavior_evidence import PostBehaviorEvidenceStore
from core.development.post_behavior_validation import PostBehaviorSource
from core.development.post_behavior_workspace import PostBehaviorWorkspaceInput, PostBehaviorWorkspaceRequests
from core.execution.local_only_post_behavior_reasoning import LocalOnlyPostBehaviorReasoning, LocalReasoningEvidence
from core.execution.workspace_execution_port import AiWorkspaceExecutionPort, WorkspaceExecutionStatus


@dataclass(frozen=True)
class PostBehaviorReasoningRecorder:
    evidence: PostBehaviorEvidenceStore

    def record(self, event: LocalReasoningEvidence) -> None:
        self.evidence.record("local_reasoning", event)


@dataclass(frozen=True)
class PostBehaviorAssessorDependencies:
    delivery: AcceptedBehavioralDelivery
    source: PostBehaviorSource
    reasoning: LocalOnlyPostBehaviorReasoning
    evidence: PostBehaviorEvidenceStore


class PostBehaviorAssessors:
    """Project current accepted source, never the surrounding lifecycle state."""

    def __init__(self, dependencies: PostBehaviorAssessorDependencies):
        self.dependencies = dependencies

    async def assess_naming(self, state: PostBehaviorState) -> PostBehaviorAssessment:
        deps = self.dependencies
        production = deps.source.focused(state)
        material = focused_naming_material(deps.delivery)
        decision = await NamingAssessor(deps.reasoning).reason(NamingAssessmentInput(material, production))
        ref = deps.evidence.record("naming_assessment", {
            "revision": production.revision, "slice_identity": production.identity,
            "decision": None if decision.rename is None else {
                "current_name": decision.rename.current_name, "required_name": decision.rename.required_name}})
        return PostBehaviorAssessment(decision, production.identity, (ref,))

    async def assess_refactor(self, state: PostBehaviorState) -> PostBehaviorAssessment:
        deps = self.dependencies
        production = deps.source.focused(state)
        decision = await RefactorAssessor(deps.reasoning).reason(production)
        ref = deps.evidence.record("refactor_assessment", {
            "revision": production.revision, "slice_identity": production.identity,
            "decision": None if decision.opportunity is None else {
                "objective": decision.opportunity.objective, "reason": decision.opportunity.reason}})
        return PostBehaviorAssessment(decision, production.identity, (ref,))


NAMING_ENTITY_PATTERN = r"(?:class|object|function|method|property|field|attribute|identifier|event|command)"
NAMING_IDENTIFIER_PATTERN = r"([A-Za-z_][A-Za-z_0-9.]*)"
EXPLICIT_NAMING_PATTERNS = (
    re.compile(NAMING_ENTITY_PATTERN + r"\s+(?:named|called)\s+\x60?" + NAMING_IDENTIFIER_PATTERN),
    re.compile(NAMING_ENTITY_PATTERN + r"\s+\x60" + NAMING_IDENTIFIER_PATTERN + r"\x60"),
    re.compile(r"(?:class|object)\s+([A-Z][A-Za-z_0-9.]*)"),
    re.compile(r"(?:function|method)\s+" + NAMING_IDENTIFIER_PATTERN + r"\s*\("),
)


def focused_naming_material(delivery: AcceptedBehavioralDelivery) -> NamingMaterial:
    # Only accepted typed API declarations or explicit named-entity clauses confer authority.
    declarations = tuple(delivery.contract.public_api)
    names: set[str] = set()
    for declaration in declarations:
        match = re.match(r"\s*(?:(?:class|def|function|method|property|field)\s+)?([A-Za-z_][A-Za-z_0-9.]*)",
                         declaration)
        if match:
            names.update(match.group(1).split("."))
    clauses = []
    for clause in delivery.contract.source_clauses:
        for sentence in re.split(r"(?<=[.!?])\s+|\n", clause.text):
            identifiers = tuple(match.group(1).rstrip(".") for pattern in EXPLICIT_NAMING_PATTERNS
                                for match in pattern.finditer(sentence))
            if identifiers:
                clauses.append(sentence)
                for identifier in identifiers:
                    names.update(identifier.split("."))
    return NamingMaterial("\n".join((*declarations, *clauses)), tuple(sorted(names)))


@dataclass(frozen=True)
class PostBehaviorMutationDependencies:
    delivery: AcceptedBehavioralDelivery
    source: PostBehaviorSource
    port: AiWorkspaceExecutionPort
    evidence: PostBehaviorEvidenceStore


class PostBehaviorMutation:
    """Submit one persisted decision through the existing generic bounded execution port."""

    def __init__(self, dependencies: PostBehaviorMutationDependencies):
        self.dependencies = dependencies

    async def execute_change(self, state: PostBehaviorState) -> ChangeCandidate:
        deps = self.dependencies
        active = state.active_pass
        if active is None or active.assessment is None or active.submission_id is None:
            raise ValueError("mutation requires a persisted assessment and submission identity")
        production = deps.source.focused(state)
        if production.identity != active.assessment.slice_identity:
            raise ValueError("mutation source differs from assessed accepted revision")
        binding = replace(deps.delivery.project.binding(), base_sha=active.base_revision)
        resolved = deps.source.git.command(("rev-parse", "--verify", binding.base_ref)).strip()
        if resolved != active.base_revision:
            raise ValueError("mutation binding differs from current trusted base")
        identity = AthbaWorkspaceIdentity(
            sha256(f"{state.delivery_id}:{active.number}".encode()).hexdigest(),
            active.submission_id, sha256(active.submission_id.encode()).hexdigest())
        snapshot = deps.source.git.snapshot(active.base_revision)
        tests = tuple(file for file in snapshot.files if _accepted_test_path(file.path))
        decision = active.assessment.decision
        inputs = PostBehaviorWorkspaceInput(identity, binding, production, tests,
            (tuple(deps.delivery.project.runtime.test_command),), runtime=deps.delivery.project.runtime,
            rename_reference_sources=snapshot if isinstance(decision, NamingDecision) else None)
        factory = PostBehaviorWorkspaceRequests()
        if isinstance(decision, NamingDecision):
            if decision.rename is None:
                raise ValueError("NO has no mutation authority")
            request = factory.rename(inputs, decision.rename)
        else:
            if decision.opportunity is None:
                raise ValueError("NO has no mutation authority")
            request = factory.refactor(inputs, decision.opportunity)
        request_ref = deps.evidence.record("workspace_request", request)
        result = await asyncio.to_thread(deps.port.submit_workspace_change, request)
        result_ref = deps.evidence.record("workspace_result", result)
        if result.identity != request.identity:
            raise ValueError("workspace result identity differs from submission")
        return ChangeCandidate(result.candidate_revision or result.accepted_revision,
            (request_ref, result_ref, *result.evidence_refs),
            result.status == WorkspaceExecutionStatus.ACCEPTED,
            result.error or result.generic_failure or result.status.value,
            result.status == WorkspaceExecutionStatus.ACCEPTED or result.is_model_originated())



def _accepted_test_path(value: str) -> bool:
    path = PurePosixPath(value)
    return path.suffix == ".py" and (
        bool(set(path.parts) & {"tests", "test"}) or path.name.startswith("test_")
        or path.name == "conftest.py"
    )
