from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.development.tdd_progression_validation import enum_value, list_of_strings, require_text, validate_list_of_strings


class RegressionDisposition(str, Enum):
    REGRESSION_CLEAR = "regression_clear"
    ACCUMULATED_REGRESSION = "accumulated_regression"
    REGRESSION_INFRASTRUCTURE_FAILURE = "regression_infrastructure_failure"


@dataclass(frozen=True)
class RegressionGateResult:
    candidate_revision: str
    target_test_name: str
    suite_test_names: list[str]
    target_test_passed: bool
    complete_suite_passed: bool
    failing_prior_test_names: list[str] = field(default_factory=list)
    passing_prior_test_names: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    stdout: str | None = None
    stderr: str | None = None
    disposition: str = RegressionDisposition.REGRESSION_CLEAR.value

    def __post_init__(self) -> None:
        require_text(self.candidate_revision, "regression candidate revision")
        require_text(self.target_test_name, "regression target test name")
        validate_list_of_strings(self.suite_test_names, "regression suite test names")
        if self.target_test_name not in self.suite_test_names:
            raise ValueError("regression suite must include the target test")
        validate_list_of_strings(self.failing_prior_test_names, "regression failing prior test names")
        validate_list_of_strings(self.passing_prior_test_names, "regression passing prior test names")
        validate_list_of_strings(self.evidence_refs, "regression evidence refs")
        object.__setattr__(self, "disposition", enum_value(self.disposition, RegressionDisposition, "regression disposition"))
        if len(set(self.suite_test_names)) != len(self.suite_test_names):
            raise ValueError("regression suite test names must be unique")
        if len(set(self.failing_prior_test_names)) != len(self.failing_prior_test_names):
            raise ValueError("regression failing prior test names must be unique")
        if len(set(self.passing_prior_test_names)) != len(self.passing_prior_test_names):
            raise ValueError("regression passing prior test names must be unique")
        prior_names = set(self.suite_test_names) - {self.target_test_name}
        if not set(self.failing_prior_test_names).issubset(prior_names):
            raise ValueError("failing prior tests must belong to the prior accepted suite")
        if not set(self.passing_prior_test_names).issubset(prior_names):
            raise ValueError("passing prior tests must belong to the prior accepted suite")
        if set(self.failing_prior_test_names).intersection(self.passing_prior_test_names):
            raise ValueError("regression failing and passing prior tests must be disjoint")
        if self.disposition == RegressionDisposition.REGRESSION_CLEAR.value:
            if not self.target_test_passed or not self.complete_suite_passed:
                raise ValueError("regression_clear requires passing target and suite results")
        if self.disposition == RegressionDisposition.ACCUMULATED_REGRESSION.value and not self.failing_prior_test_names:
            raise ValueError("accumulated_regression requires failing prior tests")

    def conflict_test_names(self) -> list[str]:
        names = [self.target_test_name, *self.failing_prior_test_names]
        unique: list[str] = []
        for name in names:
            if name not in unique:
                unique.append(name)
        return unique

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_revision": self.candidate_revision,
            "target_test_name": self.target_test_name,
            "suite_test_names": list(self.suite_test_names),
            "target_test_passed": self.target_test_passed,
            "complete_suite_passed": self.complete_suite_passed,
            "failing_prior_test_names": list(self.failing_prior_test_names),
            "passing_prior_test_names": list(self.passing_prior_test_names),
            "evidence_refs": list(self.evidence_refs),
            "stdout": self.stdout,
            "stderr": self.stderr,
            "disposition": self.disposition,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RegressionGateResult":
        return cls(
            candidate_revision=str(payload["candidate_revision"]),
            target_test_name=str(payload["target_test_name"]),
            suite_test_names=list_of_strings(payload.get("suite_test_names", []), "regression suite test names"),
            target_test_passed=bool(payload.get("target_test_passed")),
            complete_suite_passed=bool(payload.get("complete_suite_passed")),
            failing_prior_test_names=list_of_strings(payload.get("failing_prior_test_names", []), "regression failing prior test names"),
            passing_prior_test_names=list_of_strings(payload.get("passing_prior_test_names", []), "regression passing prior test names"),
            evidence_refs=list_of_strings(payload.get("evidence_refs", []), "regression evidence refs"),
            stdout=payload.get("stdout"),
            stderr=payload.get("stderr"),
            disposition=str(payload.get("disposition", RegressionDisposition.REGRESSION_CLEAR.value)),
        )
