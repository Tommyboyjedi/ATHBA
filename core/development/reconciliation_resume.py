"""Narrow controller recovery for feature-owned reconciliation checkpoints."""
from __future__ import annotations

from core.development.behavior_contract_domain import BehaviorContract
from core.development.strict_tdd_feature_domain import StrictTddFeatureState


def reconciliation_resume_available(state: StrictTddFeatureState | None) -> bool:
    if state is None or not state.reconciliation_progress or not state.gatekeeper_payload:
        return False
    if state.current_scenario_id is not None or state.pending_completed_behavior is not None:
        return False
    if state.status not in {"running", "blocked", "completed"}:
        return False
    contract = BehaviorContract.from_dict(dict(state.contract_payload or {}), load_options=None)
    completed = {item.behavior_ref for item in state.completed_behaviors}
    return all(item.ref in completed for item in contract.observable_requirements)
