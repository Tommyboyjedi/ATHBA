"""Atomic serialization with immutable entry and append-only accepted history."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.atomic_json_file import read_json_file, write_json_atomically
from core.filesystem_policy import resolve_identifier_path
from core.development.post_behavior_assessment import (
    IdentifierRename, NamingDecision, RefactorDecision, RefactorOpportunity,
)
from core.development.post_behavior_domain import (
    POST_BEHAVIOR_SCHEMA, ChangeCandidate, PostBehaviorAssessment, PostBehaviorCall,
    PostBehaviorEntry, PostBehaviorOutcome, PostBehaviorPass, PostBehaviorPhase,
    PostBehaviorPolicy, PostBehaviorReason, PostBehaviorState, PostBehaviorStatus, ValidationEvidence,
)
from core.development.reconciliation_progress import ChecklistItemProgress
from core.development.workspace_attempt_policy import WorkspaceAttemptState


def _validation(value: dict[str, Any] | None) -> ValidationEvidence | None:
    if value is None:
        return None
    return ValidationEvidence(**{**value, "evidence_refs": tuple(value["evidence_refs"])})


def _assessment(value: dict[str, Any] | None) -> PostBehaviorAssessment | None:
    if value is None:
        return None
    decision = value["decision"]
    if set(decision) == {"rename"}:
        rename = decision["rename"]
        parsed: NamingDecision | RefactorDecision = NamingDecision(None if rename is None else IdentifierRename(**rename))
    elif set(decision) == {"opportunity"}:
        opportunity = decision["opportunity"]
        parsed = RefactorDecision(None if opportunity is None else RefactorOpportunity(**opportunity))
    else:
        raise ValueError("persisted post-behavior assessment is not one typed decision")
    return PostBehaviorAssessment(parsed, value["slice_identity"], tuple(value["evidence_refs"]))


class PostBehaviorPassCodec:
    @staticmethod
    def decode(value: dict[str, Any]) -> PostBehaviorPass:
        candidate = value["candidate"]
        return PostBehaviorPass(**{
            **value, "phase": PostBehaviorPhase(value["phase"]),
            "assessment": _assessment(value["assessment"]),
            "candidate": None if candidate is None else ChangeCandidate(**{
                **candidate, "evidence_refs": tuple(candidate["evidence_refs"])}),
            "tests": _validation(value["tests"]), "gatekeeper": _validation(value["gatekeeper"]),
            "reconciliation_progress": tuple(ChecklistItemProgress.from_dict(item)
                                             for item in value["reconciliation_progress"]),
            "outcome": PostBehaviorOutcome(value["outcome"]),
            "promotion_evidence": tuple(value["promotion_evidence"]),
            "stop_reason": None if value["stop_reason"] is None else PostBehaviorReason(value["stop_reason"]),
        })

    @staticmethod
    def encode(value: PostBehaviorPass) -> dict[str, Any]:
        return {**asdict(value), "reconciliation_progress": [
            item.to_dict() for item in value.reconciliation_progress]}


class PostBehaviorStateCodec:
    @staticmethod
    def encode(state: PostBehaviorState) -> dict[str, Any]:
        return {**asdict(state), "schema": POST_BEHAVIOR_SCHEMA,
                "active_pass": None if state.active_pass is None else PostBehaviorPassCodec.encode(state.active_pass),
                "passes": [PostBehaviorPassCodec.encode(item) for item in state.passes]}

    @staticmethod
    def decode(value: dict[str, Any]) -> PostBehaviorState:
        if value.get("schema") != POST_BEHAVIOR_SCHEMA:
            raise ValueError("unsupported post-behavior state schema")
        fields = {key: item for key, item in value.items() if key != "schema"}
        entry = value["entry"]
        gatekeeper = _validation(entry["gatekeeper_evidence"])
        if gatekeeper is None:
            raise ValueError("persisted behavioral entry has no final Gatekeeper evidence")
        return PostBehaviorState(**{
            **fields, "entry": PostBehaviorEntry(**{
                **entry, "production_paths": tuple(entry["production_paths"]),
                "gatekeeper_evidence": gatekeeper}),
            "status": PostBehaviorStatus(value["status"]),
            "active_pass": None if value["active_pass"] is None else PostBehaviorPassCodec.decode(value["active_pass"]),
            "passes": tuple(PostBehaviorPassCodec.decode(item) for item in value["passes"]),
            "pending_call": PostBehaviorCall(value["pending_call"]),
            "terminal_reason": None if value["terminal_reason"] is None else PostBehaviorReason(value["terminal_reason"]),
            "policy": PostBehaviorPolicy(**value["policy"]),
            "attempt_state": None if value["attempt_state"] is None else WorkspaceAttemptState.from_dict(value["attempt_state"]),
        })


class PostBehaviorStateRepository:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def load(self, delivery_id: str) -> PostBehaviorState | None:
        path = self._path(delivery_id)
        if not path.exists():
            return None
        try:
            return PostBehaviorStateCodec.decode(read_json_file(path))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("malformed post-behavior state document") from error

    def save(self, state: PostBehaviorState) -> None:
        prior = self.load(state.delivery_id)
        if prior == state:
            return
        if prior is not None:
            if prior.entry != state.entry or prior.policy != state.policy:
                raise ValueError("post-behavior baseline, authority and policy are immutable")
            if state.generation != prior.generation + 1 or state.passes[:len(prior.passes)] != prior.passes:
                raise ValueError("post-behavior checkpoint must advance without rewriting history")
            if prior.terminal:
                raise ValueError("terminal post-behavior state cannot restart autonomous work")
        elif state.generation != 0 or state.status != PostBehaviorStatus.BEHAVIOR_GATEKEEPER_ACCEPTED:
            raise ValueError("post-behavior state must begin at the accepted behavioral entry")
        write_json_atomically(self._path(state.delivery_id), PostBehaviorStateCodec.encode(state))

    def _path(self, delivery_id: str) -> Path:
        return resolve_identifier_path(self.root, delivery_id, "behavioral delivery id").with_suffix(".json")
