"""Reconcile an independent checklist only against accepted TDD test evidence."""

from __future__ import annotations

import ast
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from core.development.tdd_progression import (
    BehaviorContractRunState,
    SpecificationChecklist,
)
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest


@dataclass(frozen=True)
class AcceptedTestEvidence:
    test_name: str
    test_path: str
    step_id: str
    requirement_refs: list[str]
    red_revision: str
    semantic_revision: str

    def to_dict(self) -> dict[str, object]:
        return {
            "test_name": self.test_name,
            "test_path": self.test_path,
            "step_id": self.step_id,
            "requirement_refs": list(self.requirement_refs),
            "red_revision": self.red_revision,
            "semantic_revision": self.semantic_revision,
        }


@dataclass(frozen=True)
class ChecklistTestReconciliation:
    checklist_ref: str
    answer: str
    accepted_test_names: list[str]
    rationale: str

    def __post_init__(self) -> None:
        if self.answer not in {"YES", "NO"}:
            raise ValueError("reconciliation answer must be YES or NO")
        if self.answer == "YES" and not self.accepted_test_names:
            raise ValueError("YES reconciliation requires accepted test evidence")
        if self.answer == "NO" and self.accepted_test_names:
            raise ValueError("NO reconciliation must not claim test evidence")

    def to_dict(self) -> dict[str, object]:
        return {
            "checklist_ref": self.checklist_ref,
            "answer": self.answer,
            "accepted_test_names": list(self.accepted_test_names),
            "rationale": self.rationale,
        }


class GitAcceptedTestCatalog:
    """Read final test identities from a semantically approved repository revision."""

    def __init__(self, repository_root: str | Path, semantic_revision: str):
        self.repository_root = Path(repository_root)
        self.semantic_revision = semantic_revision

    def contains(self, test_name: str) -> bool:
        path, separator, function = test_name.partition("::")
        if not separator or not path or not function or "::" in function:
            return False
        normalized = PurePosixPath(path)
        if normalized.is_absolute() or ".." in normalized.parts:
            return False
        try:
            source = self._git("show", f"{self.semantic_revision}:{normalized.as_posix()}")
        except subprocess.CalledProcessError:
            return False
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False
        return any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function for node in tree.body)

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout


class TestEvidenceReconciler:
    """Ask one narrow question per fact and fail closed on untrusted test IDs."""

    __test__ = False

    def __init__(self, gateway: ReasoningGateway, catalog: GitAcceptedTestCatalog):
        self.gateway = gateway
        self.catalog = catalog

    async def reconcile(
        self,
        checklist: SpecificationChecklist,
        run_state: BehaviorContractRunState,
    ) -> list[ChecklistTestReconciliation]:
        accepted = _accepted_tests(run_state)
        results: list[ChecklistTestReconciliation] = []
        for item in checklist.items:
            results.append(await self._reconcile_item(checklist.project_id, item.ref, item.text, accepted))
        return results

    async def _reconcile_item(
        self,
        project_id: str,
        checklist_ref: str,
        checklist_text: str,
        accepted: list[AcceptedTestEvidence],
    ) -> ChecklistTestReconciliation:
        request = ReasoningRequest(
            purpose="athba_checklist_test_reconciliation",
            prompt=_reconciliation_prompt(checklist_ref, checklist_text, accepted),
            project_id=project_id,
            requires_large_context=False,
        )
        result = await self.gateway.reason(request)
        payload = _json_object(result.text)
        answer = str(payload.get("answer", ""))
        rationale = str(payload.get("rationale", ""))
        selected = payload.get("selected_test_names", [])
        if answer not in {"YES", "NO"} or not isinstance(selected, list):
            raise ValueError("reconciler response must contain YES or NO and a selected_test_names list")
        if answer == "NO":
            return ChecklistTestReconciliation(checklist_ref, "NO", [], rationale)
        by_name = {evidence.test_name: evidence for evidence in accepted}
        names = [str(name) for name in selected]
        if not names:
            return ChecklistTestReconciliation(
                checklist_ref,
                "NO",
                [],
                "The reconciler claimed YES without naming accepted test evidence.",
            )
        if any(name not in by_name or not self.catalog.contains(name) for name in names):
            return ChecklistTestReconciliation(
                checklist_ref,
                "NO",
                [],
                "The reconciler named a test that is not present in accepted semantically approved history.",
            )
        return ChecklistTestReconciliation(checklist_ref, "YES", list(dict.fromkeys(names)), rationale)


def _accepted_tests(run_state: BehaviorContractRunState) -> list[AcceptedTestEvidence]:
    accepted: list[AcceptedTestEvidence] = []
    for cycle in run_state.cycles:
        if cycle.red_phase is None or cycle.red_phase.accepted_revision is None or cycle.semantic_revision is None:
            continue
        if cycle.green_phase is None or cycle.green_phase.accepted_revision is None:
            continue
        accepted.append(
            AcceptedTestEvidence(
                test_name=cycle.step.test_name,
                test_path=cycle.step.test_path,
                step_id=cycle.step.step_id,
                requirement_refs=list(cycle.step.requirement_refs),
                red_revision=cycle.red_phase.accepted_revision,
                semantic_revision=cycle.semantic_revision,
            )
        )
    return accepted


def _reconciliation_prompt(
    checklist_ref: str,
    checklist_text: str,
    accepted: list[AcceptedTestEvidence],
) -> str:
    return json.dumps(
        {
            "instruction": "Act as ATHBA's test-evidence reconciler. Return raw JSON only.",
            "checklist_item": {"ref": checklist_ref, "text": checklist_text},
            "accepted_tdd_tests": [entry.to_dict() for entry in accepted],
            "question": "Is there an accepted unit test that proves this checklist item?",
            "required_output": {
                "answer": "YES|NO",
                "selected_test_names": ["pytest node ids, only when answer is YES"],
                "rationale": "brief explanation",
            },
            "rules": [
                "answer YES only when one or more listed accepted tests directly prove the item",
                "answer NO when evidence is absent, indirect, or uncertain",
                "never invent a test identifier",
                "do not use production code, review, mechanical checks, or assumptions as evidence",
            ],
        },
        sort_keys=True,
    )


def _json_object(text: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("reconciler response was not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("reconciler response must be a JSON object")
    return payload
