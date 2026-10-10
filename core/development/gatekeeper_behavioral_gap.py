"""Return independently discovered behavioral gaps to the same Behavioral Planner."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.behavior_replan_domain import BehavioralFailure
from core.development.specification_domain import SourceRequirementClause, SpecificationChecklistItem, SpecificationGatekeeperRunState
from core.development.specification_evidence_policy import EvidencePolicyRouter
from core.development.specification_obligations import EvidencePolicy
from core.development.strict_tdd_feature_replan import FeatureReplanContext, require_replan
from core.development.strict_tdd_feature_application import StrictTddFeatureApplicationService
from core.development.strict_tdd_transitions import FeatureTransitionKind


def return_gatekeeper_gap(service: StrictTddFeatureApplicationService, context: FeatureReplanContext):
    from core.development.strict_tdd_feature_application_advance import _result_for

    state, project = context.state, context.project
    contract = BehaviorContract.from_dict(dict(state.contract_payload or {}))
    checklist = SpecificationGatekeeperRunState.from_dict(dict(state.gatekeeper_payload or {})).checklist
    items = {item.ref: item.to_dict() for item in checklist.items}
    for record in state.final_reconciliation:
        if record.get("answer") != "NO" or record.get("status") or record.get("blocked_reason"):
            continue
        # Evidence producers may identify several exact source obligations. All use this same route.
        candidates = record.get("remaining_obligations", [items.get(str(record.get("checklist_ref")))])
        if not isinstance(candidates, list):
            raise ValueError("Gatekeeper gap authority must be an array")
        for payload in candidates:
            if not isinstance(payload, dict):
                continue
            item = SpecificationChecklistItem.from_dict(payload)
            if EvidencePolicyRouter().route_source(item, contract.requirement_source).policy != EvidencePolicy.BEHAVIORAL:
                continue
            quote = item.source_quote or item.text
            if not item.source_quote and quote not in contract.requirement_source:
                raise ValueError("Gatekeeper gap has no original source authority")
            identity = sha256((item.ref + quote).encode()).hexdigest()[:12]
            ref = f"GAP-{identity}-{len(state.behavior_replans) + 1:03d}"
            clause = SourceRequirementClause(f"SRC-{ref}", item.text, item.kind,
                source_quote=quote, subject=item.subject or quote, obligation_type=item.obligation_type)
            parent = BehaviorContractRequirement(ref, [clause.ref], item.text, item.text,
                "Demonstrate only this remaining original source obligation.")
            updated_contract = replace(contract,
                source_clauses=[*contract.source_clauses, clause],
                observable_requirements=[*contract.observable_requirements, parent])
            updated = replace(state, contract_payload=updated_contract.to_dict(),
                reconciliation_history=(*state.reconciliation_history,
                    {"revision": state.canonical_development_base,
                     "results": list(state.final_reconciliation), "progress": list(state.reconciliation_progress)}),
                final_reconciliation=(), reconciliation_progress=(), reconciliation_failure=None)
            returned = require_replan(updated, BehavioralFailure(ref,
                str(record.get("rationale", "Original behavioral obligation is not demonstrated.")),
                (f"gatekeeper:{state.project_id}:{item.ref}:{state.canonical_development_base}",)))
            service.states.save(returned)
            return _result_for(FeatureTransitionKind.BEHAVIOR_REPLAN_REQUIRED, returned, project,
                               behavior_ref=ref, reasoning=True)
    return None
