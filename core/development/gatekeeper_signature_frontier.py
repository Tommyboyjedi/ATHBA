"""A known unmet source call shape can request one small normal TDD frontier."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import TYPE_CHECKING

from core.development.assurance_completion import CompletionAuthority, assess_completion
from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.gatekeeper_repair_domain import SpecificationRepairRecord
from core.development.project_environment import DevelopmentProject
from core.development.required_public_signature import RequiredPublicSignature
from core.development.source_obligation_semantics import ObligationType
from core.development.strict_tdd_feature_domain import StrictTddFeatureState, StrictTddFeatureStatus

if TYPE_CHECKING:
    from core.development.strict_tdd_feature_application import StrictTddFeatureApplicationService

SIGNATURE_POLICY = "source_public_signature"
GAP_SCHEMA = "athba/source-call-shape-gap/v1"
GAP_REFERENCE_DIGEST_LENGTH = 16


@dataclass(frozen=True)
class SignatureRepairContext:
    state: StrictTddFeatureState
    project: DevelopmentProject
    reasoning_invoked: bool = False


@dataclass(frozen=True)
class SourceCallShapeGap:
    signature: RequiredPublicSignature
    source_refs: tuple[str, ...]

    @property
    def behavior_ref(self) -> str:
        digest = sha256(json.dumps(self.signature.to_dict(), sort_keys=True).encode()).hexdigest()
        return "GK-CALL-" + digest[:GAP_REFERENCE_DIGEST_LENGTH]

    def requirement(self) -> BehaviorContractRequirement:
        owner = f"{self.signature.owner}." if self.signature.owner else ""
        operation = owner + self.signature.name
        outcome = (f"The public operation {operation} has exactly {len(self.signature.parameters)} required "
                   "explicit arguments in the supplied call form, without defaulted, optional, extra or variadic arguments. "
                   "Demonstrate only its public call shape; parameter spelling is not part of this obligation. "
                   "No particular exception type or invalid-input value behavior is required by this obligation.")
        return BehaviorContractRequirement(self.behavior_ref, list(self.source_refs),
            f"Required public call shape of {operation}", outcome, outcome)


def plan_signature_repair(state: StrictTddFeatureState) -> StrictTddFeatureState | None:
    if (state.status != StrictTddFeatureStatus.RUNNING.value or state.current_scenario_id
            or state.reconciliation_failure or state.atomization_failure
            or state.working_revision or not state.contract_payload
            or re.fullmatch(r"[0-9a-f]{40}", state.canonical_development_base or "") is None):
        return None
    contract = BehaviorContract.from_dict(state.contract_payload)
    if set(contract.requirement_refs()) != {item.behavior_ref for item in state.completed_behaviors}:
        return None
    records = [item for item in state.final_reconciliation if item.get("evidence_policy") == SIGNATURE_POLICY]
    if len(records) != 1:
        return None
    record = records[0]
    others = tuple(item for item in state.final_reconciliation if item is not record)
    if not assess_completion(CompletionAuthority(others, contract.requirement_source)).behaviorally_complete:
        return None
    gaps = _source_gaps(record, contract, str(state.canonical_development_base))
    if not gaps or any(gap.behavior_ref in contract.requirement_refs()
                       or any(old.behavior_ref == gap.behavior_ref for old in state.specification_repairs)
                       for gap in gaps):
        return None
    gap = gaps[0]
    requirement = gap.requirement()
    updated_contract = replace(contract, observable_requirements=[*contract.observable_requirements, requirement])
    archive = SpecificationRepairRecord(gap.behavior_ref, gap.source_refs, gap.signature,
        str(state.canonical_development_base), state.final_reconciliation, state.reconciliation_progress)
    return replace(state, contract_payload=updated_contract.to_dict(),
                   specification_repairs=(*state.specification_repairs, archive),
                   final_reconciliation=(), reconciliation_progress=(), blocked_reason=None)


def _source_gaps(record: dict[str, object], contract: BehaviorContract, revision: str) -> tuple[SourceCallShapeGap, ...]:
    if (record.get("checklist_ref") != "source-required-public-signatures"
            or record.get("answer") != "NO" or record.get("evidence_status") != "fail"
            or record.get("signature_gap_schema") != GAP_SCHEMA
            or record.get("snapshot_complete") is not True or record.get("unsupported_findings") != []
            or record.get("revision") != revision or not record.get("findings")
            or record.get("status") or record.get("blocked_reason")):
        return ()
    try:
        declared = _signatures(record.get("required_signatures"))
        failed = _signatures(record.get("failed_signatures"))
        if (declared != contract.required_signatures or not failed or len(set(failed)) != len(failed)
                or not set(failed) <= set(declared)):
            return ()
        gaps = []
        for signature in failed:
            clauses = [clause for clause in contract.source_clauses
                       if clause.obligation_type == ObligationType.BEHAVIOR.value and clause.source_quote
                       and signature.source_quote in clause.source_quote
                       and signature.source_quote in clause.source_context(contract.requirement_source)
                       and sum(item.source_quote in clause.source_quote for item in declared) == 1]
            if len(clauses) != 1:
                return ()
            gaps.append(SourceCallShapeGap(signature, (clauses[0].ref,)))
        return tuple(gaps)
    except (ValueError, KeyError, TypeError):
        return ()


def _signatures(value: object) -> tuple[RequiredPublicSignature, ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("source call-shape evidence requires structured signature identities")
    return tuple(RequiredPublicSignature.from_dict(item) for item in value)


def advance_signature_repair(service: StrictTddFeatureApplicationService, context: SignatureRepairContext):
    from core.development.strict_tdd_feature_application_advance import _result_for
    from core.development.strict_tdd_transitions import FeatureTransitionKind

    updated = plan_signature_repair(context.state)
    if updated is None:
        return None
    service.states.save(updated)
    return _result_for(FeatureTransitionKind.SPECIFICATION_REPAIR_PLANNED, updated, context.project,
                       behavior_ref=updated.specification_repairs[-1].behavior_ref,
                       reasoning=context.reasoning_invoked)
