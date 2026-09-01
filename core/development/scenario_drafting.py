"""Session 4 bounded scenario drafting; it deliberately does not run microcycles."""
from __future__ import annotations

import ast
import json
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from core.development.microcycle_domain import (
    FragmentationRequest,
    LanguageAdapterCatalog,
    MicrocycleState,
    RegressionContractRequest,
    RegressionState,
    RetryCounts,
    ScenarioCompletion,
    ScenarioFrontier,
    ScenarioIntentResult,
    ScenarioParseRequest,
    SyntaxValidationRequest,
    TestScenarioDraft,
)
from core.development.scenario_drafting_domain import (
    MAX_TESTER_SCENARIO_ATTEMPTS,
    ScenarioDraftAttempt,
    ScenarioDraftOutcome,
    ScenarioDraftRequest,
    ScenarioDraftRunState,
    ScenarioDraftStatus,
)
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest
from core.execution.work_unit_gateway import WorkUnitExecutionGateway, WorkUnitExecutionResult


class ScenarioDraftStateStore(Protocol):
    def load(self, scenario_id: str) -> ScenarioDraftRunState | None: ...
    def save(self, state: ScenarioDraftRunState) -> object: ...


class ScenarioCandidateSourceReader(Protocol):
    def read(self, revision: str, test_path: str) -> str: ...


@dataclass(frozen=True)
class ScenarioDraftWorkUnitRequest:
    request: ScenarioDraftRequest
    attempt_number: int
    feedback: str | None


@dataclass(frozen=True)
class ScenarioFreezeRequest:
    draft: TestScenarioDraft
    intent: ScenarioIntentResult
    adapter_catalog: LanguageAdapterCatalog
    base_revision: str


@dataclass(frozen=True)
class ScenarioDraftingDependencies:
    execution_gateway: WorkUnitExecutionGateway
    intent_reviewer: ScenarioIntentReviewer
    adapter_catalog: LanguageAdapterCatalog
    source_reader: ScenarioCandidateSourceReader
    state_store: ScenarioDraftStateStore
    work_units: ScenarioDraftWorkUnitFactory | None = None


@dataclass(frozen=True)
class ScenarioDraftExecutionRecord:
    state: ScenarioDraftRunState
    request: ScenarioDraftRequest
    unit: DevelopmentWorkUnit
    result: WorkUnitExecutionResult

@dataclass(frozen=True)
class ScenarioDraftWorkUnitFactory:
    python_executable: str = "python3"

    def build(self, request: ScenarioDraftWorkUnitRequest) -> DevelopmentWorkUnit:
        draft = request.request
        work_unit_id = f"{draft.ticket.step_id}--scenario-draft-{request.attempt_number}"
        return DevelopmentWorkUnit(
            id=work_unit_id,
            project_id=draft.ticket.step_id,
            parent_ticket_id=draft.ticket.step_id,
            objective=_tester_objective(draft, request.feedback),
            allowed_paths=[draft.allowed_test_path],
            acceptance=AcceptanceContract(
                commands=[[self.python_executable, "-B", "-m", "py_compile", draft.allowed_test_path]],
                required_artifacts=[draft.allowed_test_path],
            ),
            max_implementation_attempts=1,
            change_key=f"{work_unit_id}--attempt-{request.attempt_number}",
            status=WorkUnitStatus.READY,
        )


@dataclass(frozen=True)
class GitCandidateScenarioSourceReader:
    repository_root: Path

    def read(self, revision: str, test_path: str) -> str:
        _safe_test_path(test_path)
        result = subprocess.run(
            ["git", "show", f"{revision}:{test_path}"],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ValueError(f"candidate scenario source is unavailable: {detail}")
        return result.stdout


@dataclass(frozen=True)
class ScenarioIntentReviewRequest:
    scenario_id: str
    behavior_ref: str
    behavior_summary: str
    expected_result: str
    source_requirement_refs: tuple[str, ...]
    complete_scenario_source: str
    static_fragment_kinds: tuple[str, ...]
    canonical_test_identity: str


class ScenarioIntentReviewer:
    """Independently judges ticket evidence and never receives solution material."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def review(self, request: ScenarioIntentReviewRequest) -> ScenarioIntentResult:
        response = await self.gateway.reason(
            ReasoningRequest(
                purpose="athba_scenario_intent_review",
                prompt=_intent_prompt(request),
                project_id=request.behavior_ref,
                requires_large_context=False,
            )
        )
        try:
            return _intent_result(request.scenario_id, response.text)
        except json.JSONDecodeError as error:
            repaired = await self.gateway.reason(
                ReasoningRequest(
                    purpose="athba_scenario_intent_json_repair",
                    prompt=_intent_repair_prompt(response.text, str(error)),
                    project_id=request.behavior_ref,
                    requires_large_context=False,
                )
            )
            return _intent_result(request.scenario_id, repaired.text)


class ScenarioFreezeFactory:
    """Builds immutable microcycle planning state without exposing a frontier."""

    def freeze(self, request: ScenarioFreezeRequest) -> MicrocycleState:
        adapter = request.adapter_catalog.for_language(request.draft.language_id)
        model = adapter.parse_scenario(ScenarioParseRequest(request.draft))
        adapter.validate_scenario_syntax(SyntaxValidationRequest(model))
        fragments = adapter.fragment_scenario(FragmentationRequest(model))
        first = fragments[0]
        frontier = ScenarioFrontier(request.draft.scenario_id, 0, first.fragment_id, (first.fragment_id,))
        regression = adapter.regression_contract(RegressionContractRequest(model))
        return MicrocycleState(
            request.draft,
            request.intent,
            model,
            fragments,
            frontier,
            request.base_revision,
            None,
            RetryCounts(),
            (),
            (),
            RegressionState("pending", regression.command),
            ScenarioCompletion("pending"),
        )


class ScenarioDraftingService:
    """Submits only a test-path draft and freezes it without base promotion."""

    def __init__(self, dependencies: ScenarioDraftingDependencies):
        self.execution_gateway = dependencies.execution_gateway
        self.intent_reviewer = dependencies.intent_reviewer
        self.adapter_catalog = dependencies.adapter_catalog
        self.source_reader = dependencies.source_reader
        self.state_store = dependencies.state_store
        self.work_units = dependencies.work_units or ScenarioDraftWorkUnitFactory()

    async def draft(
        self,
        request: ScenarioDraftRequest,
        binding: RepositoryBinding,
    ) -> ScenarioDraftOutcome:
        """Compatibility API that advances only through persisted draft transitions."""
        for _ in range(MAX_TESTER_SCENARIO_ATTEMPTS * 2):
            state = self.state_store.load(request.scenario_id)
            if state is not None and state.approved_microcycle is not None:
                return ScenarioDraftOutcome(state, False)
            if state is not None and state.status == ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value:
                return ScenarioDraftOutcome(state, False)
            if state is not None and state.attempts and state.attempts[-1].candidate_revision and state.attempts[-1].intent is None:
                outcome = await self.review_intent(request)
            else:
                outcome = await self.submit_candidate(request, binding)
            if outcome.approved or outcome.state.status == ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value:
                return outcome
            if outcome.state.attempts and outcome.state.attempts[-1].intent is not None:
                return outcome
        raise RuntimeError("scenario draft compatibility transition guard exhausted")

    async def submit_candidate(
        self,
        request: ScenarioDraftRequest,
        binding: RepositoryBinding,
    ) -> ScenarioDraftOutcome:
        state = self.state_store.load(request.scenario_id) or _initial_state(request)
        _validate_resume(state, request)
        if state.approved_microcycle is not None:
            return ScenarioDraftOutcome(state, False)
        if len(state.attempts) >= MAX_TESTER_SCENARIO_ATTEMPTS:
            exhausted = replace(state, status=ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value)
            self.state_store.save(exhausted)
            return ScenarioDraftOutcome(exhausted, False)
        attempt_number = len(state.attempts) + 1
        unit = self.work_units.build(ScenarioDraftWorkUnitRequest(request, attempt_number, _last_feedback(state)))
        result = await self.execution_gateway.execute(unit, binding.with_base_sha(request.development_base_revision))
        outcome = self._record_submission(ScenarioDraftExecutionRecord(state, request, unit, result))
        self.state_store.save(outcome.state)
        return outcome

    async def review_intent(self, request: ScenarioDraftRequest) -> ScenarioDraftOutcome:
        state = self.state_store.load(request.scenario_id)
        if state is None:
            raise ValueError("scenario intent review requires a submitted draft")
        _validate_resume(state, request)
        if state.approved_microcycle is not None:
            return ScenarioDraftOutcome(state, False)
        if not state.attempts:
            raise ValueError("scenario intent review requires a submitted draft attempt")
        attempt = state.attempts[-1]
        if attempt.candidate_revision is None or attempt.intent is not None:
            raise ValueError("scenario intent review requires an unreviewed accepted draft")
        try:
            source = self.source_reader.read(attempt.candidate_revision, request.allowed_test_path)
            draft = _draft_from_candidate(request, source)
            intent = await self.intent_reviewer.review(_review_request(draft, request, self.adapter_catalog))
            reviewed = replace(attempt, status=intent.status, feedback=intent.rationale, intent=intent)
            updated = replace(state, attempts=(*state.attempts[:-1], reviewed))
            if intent.status == "approved":
                frozen = ScenarioFreezeFactory().freeze(
                    ScenarioFreezeRequest(draft, intent, self.adapter_catalog, request.development_base_revision)
                )
                updated = replace(updated, approved_microcycle=frozen, status=ScenarioDraftStatus.APPROVED.value)
            self.state_store.save(updated)
            return ScenarioDraftOutcome(updated, False)
        except ValueError as error:
            invalid = replace(attempt, status="candidate_invalid", feedback=str(error))
            updated = replace(state, attempts=(*state.attempts[:-1], invalid))
            self.state_store.save(updated)
            return ScenarioDraftOutcome(updated, False)

    def _record_submission(self, record: ScenarioDraftExecutionRecord) -> ScenarioDraftOutcome:
        state = record.state
        unit = record.unit
        result = record.result
        if not result.accepted or result.accepted_revision is None:
            return _append_attempt(state, _attempt(unit, result, "candidate_rejected", result.error or result.status))
        return _append_attempt(state, _attempt(unit, result, "candidate_submitted", None))


def _initial_state(request: ScenarioDraftRequest) -> ScenarioDraftRunState:
    return ScenarioDraftRunState(
        scenario_id=request.scenario_id,
        behavior_ref=request.ticket.step_id,
        source_requirement_refs=request.source_requirement_refs,
        language_id=request.language_id,
        test_framework=request.test_framework,
        allowed_test_path=request.allowed_test_path,
        development_base_revision=request.development_base_revision,
    )


def _validate_resume(state: ScenarioDraftRunState, request: ScenarioDraftRequest) -> None:
    immutable = (
        (state.behavior_ref, request.ticket.step_id),
        (state.source_requirement_refs, request.source_requirement_refs),
        (state.language_id, request.language_id),
        (state.test_framework, request.test_framework),
        (state.allowed_test_path, request.allowed_test_path),
        (state.development_base_revision, request.development_base_revision),
    )
    if any(left != right for left, right in immutable):
        raise ValueError("stale scenario draft state must not be reused after ticket, source, or base changes")


def _attempt(
    unit: DevelopmentWorkUnit,
    result: WorkUnitExecutionResult,
    status: str,
    feedback: str | None,
    intent: ScenarioIntentResult | None = None,
) -> ScenarioDraftAttempt:
    return ScenarioDraftAttempt(
        attempt_number=int(unit.id.rsplit("-", 1)[1]),
        work_unit_id=unit.id,
        change_id=result.change_id,
        candidate_revision=result.accepted_revision,
        evidence_location=result.evidence_location,
        status=status,
        feedback=feedback,
        intent=intent,
    )


def _append_attempt(
    state: ScenarioDraftRunState,
    attempt: ScenarioDraftAttempt,
) -> ScenarioDraftOutcome:
    attempts = (*state.attempts, attempt)
    status = (
        ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value
        if len(attempts) >= MAX_TESTER_SCENARIO_ATTEMPTS
        else ScenarioDraftStatus.DRAFTING.value
    )
    return ScenarioDraftOutcome(replace(state, attempts=attempts, status=status), True)


def _last_feedback(state: ScenarioDraftRunState) -> str | None:
    return state.attempts[-1].feedback if state.attempts else None


def _draft_from_candidate(request: ScenarioDraftRequest, source: str) -> TestScenarioDraft:
    rationale, refs = _metadata(source)
    if refs != request.source_requirement_refs:
        raise ValueError("candidate source requirement refs do not match the requested ticket refs")
    identity = _canonical_python_identity(request.allowed_test_path, source)
    if identity != request.ticket.test_name:
        raise ValueError("candidate test identity does not match the behavior ticket")
    return TestScenarioDraft(
        request.scenario_id,
        request.ticket.step_id,
        request.language_id,
        source,
        identity,
        request.allowed_test_path,
        rationale,
        refs,
    )


def _review_request(
    draft: TestScenarioDraft,
    request: ScenarioDraftRequest,
    catalog: LanguageAdapterCatalog,
) -> ScenarioIntentReviewRequest:
    adapter = catalog.for_language(request.language_id)
    model = adapter.parse_scenario(ScenarioParseRequest(draft))
    fragments = adapter.fragment_scenario(FragmentationRequest(model))
    return ScenarioIntentReviewRequest(
        scenario_id=draft.scenario_id,
        behavior_ref=request.ticket.step_id,
        behavior_summary=request.ticket.focused_behavior,
        expected_result=request.ticket.expected_result,
        source_requirement_refs=request.source_requirement_refs,
        complete_scenario_source=draft.source,
        static_fragment_kinds=tuple(item.kind for item in fragments),
        canonical_test_identity=draft.canonical_test_identity,
    )


def _metadata(source: str) -> tuple[str, tuple[str, ...]]:
    rationale = _metadata_value(source, "# ATHBA-SCENARIO-RATIONALE:")
    refs = _metadata_value(source, "# ATHBA-SOURCE-REFS:")
    parsed_refs = tuple(item.strip() for item in refs.split(",") if item.strip())
    if not rationale or not parsed_refs:
        raise ValueError("candidate must return scenario rationale and source requirement refs")
    return rationale, parsed_refs


def _metadata_value(source: str, prefix: str) -> str:
    for line in source.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return ""


def _canonical_python_identity(test_path: str, source: str) -> str:
    module = ast.parse(source)
    functions = [node for node in module.body if isinstance(node, ast.FunctionDef)]
    if len(functions) != 1 or not functions[0].name.startswith("test_"):
        raise ValueError("candidate must define exactly one canonical pytest test")
    return f"{test_path}::{functions[0].name}"


def _safe_test_path(test_path: str) -> None:
    candidate = Path(test_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("candidate test path is unsafe")


def _intent_result(scenario_id: str, text: str) -> ScenarioIntentResult:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("scenario intent review must be a JSON object")
    disposition = value.get("disposition")
    rationale = value.get("feedback")
    evidence = value.get("evidence_refs", [])
    if not isinstance(disposition, str) or not isinstance(rationale, str) or not isinstance(evidence, list):
        raise ValueError("scenario intent review must include disposition, feedback, and evidence_refs")
    return ScenarioIntentResult(scenario_id, disposition, rationale, tuple(str(item) for item in evidence))


def _tester_objective(request: ScenarioDraftRequest, feedback: str | None) -> str:
    payload = {
        "role": "Tester",
        "task": "Draft one complete behavioral scenario; this is planning material, not the active RED test.",
        "ticket": {
            "id": request.ticket.step_id,
            "behavior": request.ticket.focused_behavior,
            "expected_result": request.ticket.expected_result,
            "canonical_test_identity": request.ticket.test_name,
        },
        "source_requirement_refs": list(request.source_requirement_refs),
        "language": request.language_id,
        "test_framework": request.test_framework,
        "allowed_test_path": request.allowed_test_path,
        "repository_facts": {
            "trusted_revision": request.repository_facts.trusted_revision,
            "visible_paths": list(request.repository_facts.visible_paths),
            "production_excerpt": request.repository_facts.production_excerpt,
            "test_excerpt": request.repository_facts.test_excerpt,
        },
        "development_base": request.development_base_revision,
        "repair_feedback": feedback,
        "requirements": [
            "edit only the allowed test path",
            "do not edit production code",
            "write one complete syntactically valid scenario",
            "include # ATHBA-SCENARIO-RATIONALE: followed by concise rationale",
            "include # ATHBA-SOURCE-REFS: followed by the supplied refs in order",
            "do not materialise a frontier or start implementation",
        ],
    }
    return json.dumps(payload, sort_keys=True)


def _intent_prompt(request: ScenarioIntentReviewRequest) -> str:
    payload = {
        "question": "Does this complete scenario, if eventually GREEN, demonstrate the requested Behavior Planner ticket?",
        "behavior_ticket": {
            "id": request.behavior_ref,
            "behavior": request.behavior_summary,
            "expected_result": request.expected_result,
        },
        "source_requirement_refs": list(request.source_requirement_refs),
        "complete_scenario_source": request.complete_scenario_source,
        "static_scenario_facts": {
            "canonical_test_identity": request.canonical_test_identity,
            "fragment_kinds": list(request.static_fragment_kinds),
        },
        "response_schema": {
            "disposition": "approved | repair_required | wrong_behavior | insufficient_evidence",
            "feedback": "descriptive feedback only; never replacement test code",
            "evidence_refs": ["source requirement ref"],
        },
    }
    return json.dumps(payload, sort_keys=True)


def _intent_repair_prompt(invalid: str, error: str) -> str:
    return json.dumps(
        {
            "task": "Return only one valid JSON object for the previous scenario-intent review.",
            "validation_error": error,
            "invalid_response": invalid,
            "schema": {
                "disposition": "approved | repair_required | wrong_behavior | insufficient_evidence",
                "feedback": "descriptive feedback only",
                "evidence_refs": ["source requirement ref"],
            },
        },
        sort_keys=True,
    )
