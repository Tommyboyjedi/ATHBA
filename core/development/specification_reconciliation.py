"""Reconcile an independent checklist only against accepted TDD test evidence."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Callable

from core.development.reconciliation_response import ReconciliationAttempt, ReconciliationFailure
from core.development.reconciliation_submission import ReconciliationSubmission
from core.development.reconciliation_progress import IndividualEvidenceProgress, evidence_digest, incompatible
from core.development.microcycle_domain import MicrocycleState
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
    test_source: str | None = None
    final_revision_verified: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "test_name": self.test_name,
            "test_path": self.test_path,
            "step_id": self.step_id,
            "requirement_refs": list(self.requirement_refs),
            "red_revision": self.red_revision,
            "semantic_revision": self.semantic_revision,
            "test_source": self.test_source,
            "final_revision_verified": self.final_revision_verified,
        }


@dataclass(frozen=True)
class ChecklistTestReconciliation:
    checklist_ref: str
    answer: str
    accepted_test_names: list[str]
    rationale: str
    response_attempts: tuple[ReconciliationAttempt, ...] = ()
    supplied_test_names: tuple[str, ...] = ()
    individual_test_attempts: tuple[dict[str, object], ...] = ()

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
            "supplied_test_names": list(self.supplied_test_names),
            "response_attempts": [asdict(attempt) for attempt in self.response_attempts],
            "individual_test_attempts": [dict(attempt) for attempt in self.individual_test_attempts],
        }


@dataclass(frozen=True)
class ChecklistReconciliationRequest:
    project_id: str
    checklist_ref: str
    checklist_text: str
    accepted: list[AcceptedTestEvidence]
    progress: tuple[IndividualEvidenceProgress, ...] = ()
    checkpoint: Callable[[tuple[IndividualEvidenceProgress, ...]], None] | None = None
    before_call: Callable[[], None] | None = None


class GitAcceptedTestCatalog:
    """Read final test identities from a semantically approved repository revision."""

    def __init__(self, repository_root: str | Path, semantic_revision: str):
        self.repository_root = Path(repository_root)
        self.semantic_revision = semantic_revision

    def contains(self, evidence: AcceptedTestEvidence) -> bool:
        return self.verified_source(evidence) is not None

    def verified_source(self, evidence: AcceptedTestEvidence) -> str | None:
        accepted_source = self._test_source(evidence.semantic_revision, evidence.test_name)
        final_source = self._test_source(self.semantic_revision, evidence.test_name)
        if accepted_source is None or final_source is None:
            return None
        if hashlib.sha256(accepted_source.encode("utf-8")).hexdigest() != hashlib.sha256(final_source.encode("utf-8")).hexdigest():
            return None
        return final_source

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


class CompletedMicrocycleEvidenceCollector:
    """Expose only fully behavior-approved strict scenarios to the Gatekeeper."""

    def collect(self, states: list[MicrocycleState] | tuple[MicrocycleState, ...]) -> list[AcceptedTestEvidence]:
        accepted: list[AcceptedTestEvidence] = []
        for state in states:
            if (
                state.completion.status != "behavior_complete"
                or state.behavior_review.verdict != "approved"
                or state.completion.completed_revision is None
            ):
                continue
            red_revision = (
                state.developer_attempts[-1].base_revision
                if state.developer_attempts
                else state.completion.completed_revision
            )
            accepted.append(
                AcceptedTestEvidence(
                    test_name=state.model.canonical_test_identity,
                    test_path=state.model.test_path,
                    step_id=state.scenario_draft.behavior_ref,
                    requirement_refs=list(state.scenario_draft.source_requirement_refs),
                    red_revision=red_revision,
                    semantic_revision=state.completion.completed_revision,
                )
            )
        return accepted


class ChecklistItemReconciler:
    """Reconcile one checklist item against accepted tests and the final trusted revision."""

    def __init__(self, gateway: ReasoningGateway, catalog: GitAcceptedTestCatalog):
        self.gateway = gateway
        self.catalog = catalog

    async def reconcile(self, request: ChecklistReconciliationRequest) -> ChecklistTestReconciliation:
        """Ask the independent Gatekeeper about one verified test at a time.

        Test identity ordering is stable and no requirement, frontier, or planner
        provenance participates in selection.  A YES is terminal for this item.
        """
        attempts: list[dict[str, object]] = []
        submissions: list[ReconciliationAttempt] = []
        verified = []
        for evidence in sorted(request.accepted, key=lambda value: value.test_name):
            source = _catalog_verified_source(self.catalog, evidence)
            if source is not None:
                verified.append(replace(evidence, test_source=source, final_revision_verified=True))
        if len({evidence.test_name for evidence in verified}) != len(verified):
            raise incompatible("duplicate verified accepted-test identity")
        progress = list(request.progress)
        _validate_individual_progress(request, verified, self.catalog)
        for index, evidence in enumerate(verified):
            if index < len(progress):
                saved = progress[index]
                attempts.append(saved.to_dict())
                submissions.extend(saved.response_attempts)
                if saved.answer == "YES":
                    return ChecklistTestReconciliation(request.checklist_ref, "YES", [evidence.test_name],
                        saved.rationale, tuple(submissions), (evidence.test_name,), tuple(attempts))
                continue
            single = replace(request, accepted=[evidence])
            if request.before_call is not None:
                request.before_call()
            try:
                submission = await ReconciliationSubmission(self.gateway).submit(_reasoning_request(single))
            except ReconciliationFailure as error:
                raise replace(error, checklist_ref=request.checklist_ref,
                              accepted_test_names=(evidence.test_name,)) from error
            submissions.extend(submission.attempts)
            response = submission.response
            if response.answer == "YES":
                result = _verified_yes_or_no(request.checklist_ref, response.rationale,
                                             [evidence], list(response.selected_test_names), self.catalog)
            else:
                result = ChecklistTestReconciliation(request.checklist_ref, "NO", [], response.rationale)
            saved = IndividualEvidenceProgress(request.checklist_ref, evidence.test_name,
                evidence_digest(evidence.to_dict()), getattr(self.catalog, "semantic_revision", ""),
                index, result.answer, result.rationale, submission.attempts)
            progress.append(saved)
            if request.checkpoint is not None:
                request.checkpoint(tuple(progress))
            attempts.append(saved.to_dict())
            if result.answer == "YES":
                return replace(result, response_attempts=tuple(submissions),
                               supplied_test_names=(evidence.test_name,),
                               individual_test_attempts=tuple(attempts))
        rationale = (attempts[-1]["rationale"] if attempts else
                     "No accepted final-revision-verified test was available for this checklist item.")
        return ChecklistTestReconciliation(
            request.checklist_ref, "NO", [], str(rationale),
            tuple(submissions), tuple(item.test_name for item in verified), tuple(attempts),
        )


def _validate_individual_progress(request: ChecklistReconciliationRequest, verified: list[AcceptedTestEvidence],
                                  catalog: GitAcceptedTestCatalog) -> None:
    if len(request.progress) > len(verified):
        raise incompatible("stored individual evidence exceeds verified evidence")
    for index, saved in enumerate(request.progress):
        evidence = verified[index]
        if (saved.checklist_ref != request.checklist_ref or saved.test_name != evidence.test_name
                or saved.evaluation_order != index
                or saved.trusted_revision != getattr(catalog, "semantic_revision", "")
                or saved.evidence_identity != evidence_digest(evidence.to_dict())
                or (saved.answer == "YES" and index != len(request.progress) - 1)):
            raise incompatible("individual evidence identity, revision, or evaluation order changed")


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


def _catalog_verified_source(
    catalog: GitAcceptedTestCatalog,
    evidence: AcceptedTestEvidence,
) -> str | None:
    verified_source = getattr(catalog, "verified_source", None)
    if callable(verified_source):
        return verified_source(evidence)
    return None


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
            "question": "Does this one accepted unit test prove this checklist item?",
            "required_output": {
                "answer": "YES|NO",
                "selected_test_names": ["pytest node ids, only when answer is YES"],
                "rationale": "brief explanation",
            },
            "rules": [
                "read the supplied test_source and judge the observable behavior it actually proves",
                "answer YES only when the single listed accepted test directly proves the item",
                "answer NO when evidence is absent, indirect, or uncertain",
                "select only tests with final_revision_verified=true",
                "do not infer semantics merely from requirement references or test names",
                "never invent a test identifier",
                "do not use production code, review, mechanical checks, or assumptions as evidence",
            ],
        },
        sort_keys=True,
    )
