"""Typed external execution ceilings for strict-TDD work units."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StrictTddWorkKind(str, Enum):
    SCENARIO_DRAFT = "scenario_draft"
    SCENARIO_REPAIR = "scenario_repair"
    FRONTIER_DEVELOPER = "frontier_developer"
    REGRESSION_REPAIR = "regression_repair"
    BEHAVIOR_REPAIR = "behavior_repair"
    GENERIC = "generic"


@dataclass(frozen=True)
class StrictTddExecutionBudgets:
    scenario_draft_seconds: int = 300
    scenario_repair_seconds: int = 300
    frontier_developer_seconds: int = 300
    regression_repair_seconds: int = 450
    behavior_repair_seconds: int = 600
    generic_seconds: int = 900

    def __post_init__(self) -> None:
        values = (
            self.scenario_draft_seconds,
            self.scenario_repair_seconds,
            self.frontier_developer_seconds,
            self.regression_repair_seconds,
            self.behavior_repair_seconds,
            self.generic_seconds,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("strict TDD execution budgets must be positive integer seconds")
        if any(value > self.generic_seconds for value in values[:-1]):
            raise ValueError("strict TDD tiny-work budgets must not exceed generic fallback")


@dataclass(frozen=True)
class StrictTddExecutionBudgetPolicy:
    budgets: StrictTddExecutionBudgets = StrictTddExecutionBudgets()

    def timeout_for(self, work_kind: StrictTddWorkKind) -> int:
        values = {
            StrictTddWorkKind.SCENARIO_DRAFT: self.budgets.scenario_draft_seconds,
            StrictTddWorkKind.SCENARIO_REPAIR: self.budgets.scenario_repair_seconds,
            StrictTddWorkKind.FRONTIER_DEVELOPER: self.budgets.frontier_developer_seconds,
            StrictTddWorkKind.REGRESSION_REPAIR: self.budgets.regression_repair_seconds,
            StrictTddWorkKind.BEHAVIOR_REPAIR: self.budgets.behavior_repair_seconds,
            StrictTddWorkKind.GENERIC: self.budgets.generic_seconds,
        }
        return values[work_kind]
