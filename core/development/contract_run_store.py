"""Persistence boundary for behavior-contract run state."""

from __future__ import annotations

from dataclasses import dataclass, replace

from core.development.tdd_cycle_coordination import TddStateRepository
from core.development.tdd_progression import BehaviorContractRunState, TddSnapshot
from core.execution.rack_ai_contract import RepositoryBinding


@dataclass(frozen=True)
class ContractRunStore:
    repository: TddStateRepository

    def load(self, project_id: str) -> TddSnapshot | None:
        return self.repository.load(project_id)

    def save(self, snapshot: TddSnapshot, run_state: BehaviorContractRunState) -> TddSnapshot:
        updated = replace(
            snapshot,
            repository_binding=run_state.repository_binding,
            current_trusted_revision=run_state.semantic_base_revision,
            contract_runs={**snapshot.contract_runs, run_state.contract.id: run_state},
        )
        self.repository.save(updated)
        return updated

    def initial(self, project_id: str, binding: RepositoryBinding) -> TddSnapshot:
        return TddSnapshot(
            project_id=project_id,
            repository_binding=binding,
            current_trusted_revision=binding.base_sha,
        )
