from __future__ import annotations

from dataclasses import dataclass, replace

from core.development.behavior_contract_domain import BehaviorContract
from core.development.contract_run_domain import BehaviorContractRunState, ContractCycleRecord, SemanticReviewResult
from core.development.semantic_progression_domain import (
    ObligationResolutionRecord,
    OpenSemanticObligation,
    ProvisionalRequirementState,
    SemanticObligationDraft,
    SemanticObligationStatus,
    SemanticProgressLedger,
)
from core.development.tdd_progression_validation import require_text


@dataclass(frozen=True)
class ActionableRequirementSelectionRequest:
    contract: BehaviorContract
    run_state: BehaviorContractRunState


@dataclass(frozen=True)
class ProvisionalReviewRequest:
    run_state: BehaviorContractRunState
    cycle: ContractCycleRecord
    review: SemanticReviewResult


@dataclass(frozen=True)
class ProvisionalReviewState:
    development_base_revision: str
    ledger: SemanticProgressLedger


@dataclass(frozen=True)
class SemanticClosureRequest:
    run_state: BehaviorContractRunState


@dataclass(frozen=True)
class SemanticClosureResult:
    completed_requirement_refs: list[str]
    ledger: SemanticProgressLedger
    promoted_requirement_refs: list[str]


class ActionableRequirementSelector:
    def select(self, request: ActionableRequirementSelectionRequest) -> list[str]:
        approved_refs = set(request.run_state.completed_requirement_refs)
        provisional_refs = request.run_state.semantic_progress.provisional_requirement_refs()
        mechanically_available = approved_refs.union(provisional_refs)
        blocked_refs = request.run_state.semantic_progress.open_requirement_refs().union(provisional_refs)
        ordered = [
            requirement.ref
            for requirement in request.contract.observable_requirements
            if requirement.ref not in approved_refs
            and requirement.ref not in blocked_refs
            and set(requirement.depends_on).issubset(mechanically_available)
        ]
        targeted = request.run_state.targeted_requirement_ref
        if targeted in ordered:
            return [targeted, *[ref for ref in ordered if ref != targeted]]
        return ordered


class ProvisionalReviewRecorder:
    def record(self, request: ProvisionalReviewRequest) -> ProvisionalReviewState:
        candidate_revision = request.cycle.candidate_revision
        if candidate_revision is None:
            raise ValueError("provisional review requires a candidate revision")
        requirement_ref = _single_requirement_ref(request.cycle)
        drafts = _validated_drafts(request.review.open_obligations, requirement_ref)
        obligations = [
            OpenSemanticObligation(
                obligation_id=f"{request.cycle.step.step_id}::obligation::{index}",
                owning_requirement_ref=requirement_ref,
                blocking_requirement_refs=list(draft.blocking_requirement_refs),
                rationale=draft.rationale,
                evidence_refs=list(draft.evidence_refs),
                originating_step_id=request.cycle.step.step_id,
                introduced_revision=candidate_revision,
            )
            for index, draft in enumerate(drafts, start=1)
        ]
        prior = request.run_state.semantic_progress
        preserved_obligations = [
            item for item in prior.open_obligations if item.owning_requirement_ref != requirement_ref
        ]
        preserved_provisionals = [
            item for item in prior.provisional_requirements if item.requirement_ref != requirement_ref
        ]
        provisional = ProvisionalRequirementState(
            requirement_ref=requirement_ref,
            development_revision=candidate_revision,
            originating_step_id=request.cycle.step.step_id,
            accepted_test_names=[request.cycle.step.test_name],
            open_obligation_ids=[item.obligation_id for item in obligations],
        )
        return ProvisionalReviewState(
            development_base_revision=candidate_revision,
            ledger=SemanticProgressLedger(
                provisional_requirements=[*preserved_provisionals, provisional],
                open_obligations=[*preserved_obligations, *obligations],
                resolution_history=list(prior.resolution_history),
            ),
        )


class SemanticClosureService:
    def close(self, request: SemanticClosureRequest) -> SemanticClosureResult:
        approved_refs = set(request.run_state.completed_requirement_refs)
        prior = request.run_state.semantic_progress
        obligations: list[OpenSemanticObligation] = []
        history = list(prior.resolution_history)
        for obligation in prior.open_obligations:
            if obligation.status == SemanticObligationStatus.OPEN.value and set(obligation.blocking_requirement_refs).issubset(approved_refs):
                obligations.append(replace(obligation, status=SemanticObligationStatus.RESOLVED.value))
                history.append(
                    ObligationResolutionRecord(
                        obligation_id=obligation.obligation_id,
                        owning_requirement_ref=obligation.owning_requirement_ref,
                        resolved_by_requirement_refs=list(obligation.blocking_requirement_refs),
                        resolution_revision=_resolution_revision(request.run_state),
                        rationale=f"Resolved after semantic approval of {', '.join(obligation.blocking_requirement_refs)}.",
                    )
                )
                continue
            obligations.append(obligation)
        open_ids = {
            item.obligation_id
            for item in obligations
            if item.status == SemanticObligationStatus.OPEN.value
        }
        completed_refs = list(request.run_state.completed_requirement_refs)
        promoted: list[str] = []
        provisional_requirements: list[ProvisionalRequirementState] = []
        for provisional in prior.provisional_requirements:
            remaining_ids = [obligation_id for obligation_id in provisional.open_obligation_ids if obligation_id in open_ids]
            if not remaining_ids:
                if provisional.requirement_ref not in approved_refs:
                    completed_refs.append(provisional.requirement_ref)
                    promoted.append(provisional.requirement_ref)
                    approved_refs.add(provisional.requirement_ref)
                continue
            provisional_requirements.append(replace(provisional, open_obligation_ids=remaining_ids))
        return SemanticClosureResult(
            completed_requirement_refs=completed_refs,
            ledger=SemanticProgressLedger(
                provisional_requirements=provisional_requirements,
                open_obligations=obligations,
                resolution_history=history,
            ),
            promoted_requirement_refs=promoted,
        )


def _resolution_revision(run_state: BehaviorContractRunState) -> str:
    revision = run_state.semantic_base_revision or run_state.development_base_revision
    if revision is None:
        raise ValueError("semantic closure requires a persisted base revision")
    return revision


def _single_requirement_ref(cycle: ContractCycleRecord) -> str:
    requirement_refs = cycle.step.requirement_refs
    if len(requirement_refs) != 1:
        raise ValueError("provisional review requires exactly one requirement ref")
    return requirement_refs[0]


def _validated_drafts(drafts: list[SemanticObligationDraft], requirement_ref: str) -> list[SemanticObligationDraft]:
    if not drafts:
        raise ValueError("provisional review requires at least one semantic obligation")
    for draft in drafts:
        require_text(draft.owning_requirement_ref, "semantic obligation owning requirement ref")
        if draft.owning_requirement_ref != requirement_ref:
            raise ValueError("semantic obligation must retain the active requirement ref")
        if requirement_ref in draft.blocking_requirement_refs:
            raise ValueError("semantic obligations must reference other requirement refs")
    return drafts
