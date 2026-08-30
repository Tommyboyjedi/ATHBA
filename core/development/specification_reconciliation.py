"""Reconcile an independent checklist only against accepted TDD test evidence."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from core.development.tdd_progression import BehaviorContractRunState, SpecificationChecklist
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


@dataclass(frozen=True)
class ChecklistReconciliationRequest:
    project_id: str
    checklist_ref: str
    checklist_text: str
    accepted: list[AcceptedTestEvidence]


class GitAcceptedTestCatalog:
    """Read final test identities from a semantically approved repository revision."""

    def __init__(self, repository_root: str | Path, semantic_revision: str):
        self.repository_root = Path(repository_root)
        self.semantic_revision = semantic_revision

    def contains(self, evidence: AcceptedTestEvidence) -> bool:
        accepted_digest = self._test_digest(evidence.semantic_revision, evidence.test_name)
        final_digest = self._test_digest(self.semantic_revision, evidence.test_name)
        if accepted_digest is None or final_digest is None:
            return False
        return accepted_digest == final_digest

    def _test_digest(self, revision: str, test_name: str) -> str | None:
        source = self._test_source(revision, test_name)
        if source is None:
            return None
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    def _test_source(self, revision: str, test_name: str) -> str | None:
        path, separator, function = test_name.partition("::")
        if not separator or not path or not function or "::" in function:
            return None
        normalized = PurePosixPath(path)
        if normalized.is_absolute() or ".." in normalized.parts:
            return None
        try:
            source = self._git("show", f"{revision}:{normalized.as_posix()}")
        except subprocess.CalledProcessError:
            return None
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function:
                segment = ast.get_source_segment(source, node)
                return None if segment is None else segment.strip()
        return None

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout


class AcceptedTestEvidenceCollector:
    """Collect accepted test evidence from approved TDD history."""

    def collect(self, run_state: BehaviorContractRunState) -> list[AcceptedTestEvidence]:
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


class ChecklistItemReconciler:
    """Reconcile one checklist item against accepted tests and the final trusted revision."""

    def __init__(self, gateway: ReasoningGateway, catalog: GitAcceptedTestCatalog):
        self.gateway = gateway
        self.catalog = catalog

    async def reconcile(self, request: ChecklistReconciliationRequest) -> ChecklistTestReconciliation:
        result = await self.gateway.reason(_reasoning_request(request))
        payload = _json_object(result.text)
        answer = str(payload.get("answer", ""))
        selected = payload.get("selected_test_names", [])
        rationale = str(payload.get("rationale", ""))
        if answer not in {"YES", "NO"} or not isinstance(selected, list):
            raise ValueError("reconciler response must contain YES or NO and a selected_test_names list")
        if answer == "NO":
            return ChecklistTestReconciliation(request.checklist_ref, "NO", [], rationale)
        return _verified_yes_or_no(request.checklist_ref, rationale, request.accepted, selected, self.catalog)


class TestEvidenceReconciler:
    """Reconcile every checklist item only against accepted final-revision unit-test evidence."""

    __test__ = False

    def __init__(self, gateway: ReasoningGateway, catalog: GitAcceptedTestCatalog):
        self.collector = AcceptedTestEvidenceCollector()
        self.item_reconciler = ChecklistItemReconciler(gateway, catalog)

    async def reconcile(
        self,
        checklist: SpecificationChecklist,
        run_state: BehaviorContractRunState,
    ) -> list[ChecklistTestReconciliation]:
        accepted = self.collector.collect(run_state)
        results: list[ChecklistTestReconciliation] = []
        for item in checklist.items:
            results.append(
                await self.item_reconciler.reconcile(
                    ChecklistReconciliationRequest(checklist.project_id, item.ref, item.text, accepted)
                )
            )
        return results


def _verified_yes_or_no(
    checklist_ref: str,
    rationale: str,
    accepted: list[AcceptedTestEvidence],
    selected: list[object],
    catalog: GitAcceptedTestCatalog,
) -> ChecklistTestReconciliation:
    names = [str(name) for name in selected]
    if not names:
        return ChecklistTestReconciliation(
            checklist_ref,
            "NO",
            [],
            "The reconciler claimed YES without naming accepted test evidence.",
        )
    by_name = {evidence.test_name: evidence for evidence in accepted}
    for name in names:
        evidence = by_name.get(name)
        if evidence is None:
            return ChecklistTestReconciliation(
                checklist_ref,
                "NO",
                [],
                "The reconciler named a test that is not present in accepted semantically approved history.",
            )
        if not catalog.contains(evidence):
            return ChecklistTestReconciliation(
                checklist_ref,
                "NO",
                [],
                "The reconciler named a test whose accepted body is not preserved at the final trusted revision.",
            )
    return ChecklistTestReconciliation(checklist_ref, "YES", list(dict.fromkeys(names)), rationale)


def _reasoning_request(request: ChecklistReconciliationRequest) -> ReasoningRequest:
    return ReasoningRequest(
        purpose="athba_checklist_test_reconciliation",
        prompt=_reconciliation_prompt(request.checklist_ref, request.checklist_text, request.accepted),
        project_id=request.project_id,
        requires_large_context=False,
    )


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
