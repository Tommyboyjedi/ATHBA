"""Session 4 bounded scenario drafting; it deliberately does not run microcycles."""
from __future__ import annotations

import json
from hashlib import sha256
import subprocess
from dataclasses import dataclass, field, replace
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
    ScenarioSourceCandidate,
    ScenarioStaticAnalysis,
    SyntaxValidationRequest,
    TestScenarioDraft,
)
from core.development.scenario_drafting_domain import (
    MAX_TESTER_SCENARIO_ATTEMPTS,
    ScenarioAuthoringContract,
    ScenarioCandidateAssessment,
    ScenarioCandidateAssessmentRequest,
    ScenarioCandidateIssue,
    ScenarioCandidateIssueCode,
    ScenarioCandidateUnchangedDisposition,
    ScenarioCandidateUnchangedEvidence,
    ScenarioDraftAttempt,
    ScenarioDraftOutcome,
    ScenarioDraftRequest,
    ScenarioDraftRunState,
    ScenarioDraftStatus,
    ScenarioHarnessFailureEvidence,
    ScenarioHarnessFailureKind,
    ScenarioHarnessFailureStage,
    ScenarioSubmissionMode,
    ScenarioSubmissionOutcome,
)
from core.development.specification_domain import SourceRequirementClause
from core.development.scenario_observation_support import (
    ScenarioObservationResolver,
    ScenarioObservationSupport,
    ScenarioObservationSupportStatus,
)
from core.development.strict_tdd_execution_budget import (
    StrictTddExecutionBudgetPolicy,
    StrictTddWorkKind,
)
from core.development.athba_workspace_routing import AthbaModelWorkKind, AthbaWorkspaceIdentity
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.development.scenario_intent_review import (
    MAX_INTENT_RESPONSE_EVIDENCE_CHARACTERS,
    ScenarioIntentReviewOutcome,
    ScenarioIntentReviewStatus,
    ScenarioIntentReviewer,
)
from core.execution.work_unit_gateway import WorkUnitExecutionGateway, WorkUnitExecutionResult


class ScenarioDraftStateStore(Protocol):
    def load(self, scenario_id: str) -> ScenarioDraftRunState | None: ...
    def save(self, state: ScenarioDraftRunState) -> object: ...


class ScenarioCandidateSourceReader(Protocol):
    def read(self, revision: str, test_path: str) -> str: ...
    def resolve(self, ref: str) -> str: ...


@dataclass(frozen=True)
class ScenarioDraftWorkUnitRequest:
    request: ScenarioDraftRequest
    attempt_number: int
    feedback: str | None
    repair_attempt: ScenarioDraftAttempt | None = None
    observation_support: ScenarioObservationSupport | None = None


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
    observation_resolver: ScenarioObservationResolver | None = None


@dataclass(frozen=True)
class ScenarioDraftExecutionRecord:
    state: ScenarioDraftRunState
    request: ScenarioDraftRequest
    unit: DevelopmentWorkUnit
    result: WorkUnitExecutionResult

@dataclass(frozen=True)
class ScenarioDraftWorkUnitFactory:
    python_executable: str = "python3"
    budget_policy: StrictTddExecutionBudgetPolicy = field(
        default_factory=StrictTddExecutionBudgetPolicy
    )

    def build(self, request: ScenarioDraftWorkUnitRequest) -> DevelopmentWorkUnit:
        draft = request.request
        work_unit_id = f"{draft.ticket.step_id}--scenario-draft-{request.attempt_number}"
        workspace_scope = f"{draft.scenario_id}--scenario-draft"
        work_kind = (
            StrictTddWorkKind.SCENARIO_REPAIR
            if request.repair_attempt is not None
            else StrictTddWorkKind.SCENARIO_DRAFT
        )
        return DevelopmentWorkUnit(
            id=work_unit_id,
            project_id=draft.ticket.step_id,
            parent_ticket_id=draft.ticket.step_id,
            objective=_tester_objective(draft, request.feedback, request.repair_attempt, request.observation_support),
            allowed_paths=[draft.allowed_test_path],
            acceptance=AcceptanceContract(
                commands=[[self.python_executable, "-B", "-m", "py_compile", draft.allowed_test_path]],
                required_artifacts=[draft.allowed_test_path],
            ),
            max_implementation_attempts=1,
            timeout_seconds=self.budget_policy.timeout_for(work_kind),
            work_kind=work_kind,
            model_work_kind=(AthbaModelWorkKind.SCENARIO_REPAIR if request.repair_attempt is not None else AthbaModelWorkKind.COMPLETE_SCENARIO_AUTHORING),
            workspace_identity=AthbaWorkspaceIdentity(workspace_scope, f"{workspace_scope}-{request.attempt_number}", f"{workspace_scope}-{request.attempt_number}"),
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

    def resolve(self, ref: str) -> str:
        result = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ValueError(f"candidate scenario ref is unavailable: {detail}")
        return result.stdout.strip()


@dataclass(frozen=True)
class ScenarioIntentReviewRequest:
    scenario_id: str
    behavior_ref: str
    behavior_summary: str
    expected_result: str
    source_requirement_refs: tuple[str, ...]
    source_requirement_evidence: tuple[SourceRequirementClause, ...]
    complete_scenario_source: str
    static_fragment_kinds: tuple[str, ...]
    canonical_test_identity: str
    static_analysis: ScenarioStaticAnalysis


@dataclass(frozen=True)
class ScenarioCandidateFailureRequest:
    state: ScenarioDraftRunState
    attempt: ScenarioDraftAttempt
    source: str
    feedback: str
    prepared: "ScenarioCandidatePreparation | None" = None


@dataclass(frozen=True)
class ScenarioCandidatePreparation:
    candidate: ScenarioSourceCandidate
    assessment: ScenarioCandidateAssessment
    static_analysis: ScenarioStaticAnalysis | None
    draft: TestScenarioDraft | None


class ScenarioFreezeFactory:
    """Builds immutable microcycle planning state without exposing a frontier."""

    def freeze(self, request: ScenarioFreezeRequest) -> MicrocycleState:
        approved_draft = replace(request.draft, scenario_rationale=request.intent.rationale)
        adapter = request.adapter_catalog.for_language(approved_draft.language_id)
        model = adapter.parse_scenario(ScenarioParseRequest(approved_draft))
        adapter.validate_scenario_syntax(SyntaxValidationRequest(model))
        fragments = adapter.fragment_scenario(FragmentationRequest(model))
        first = fragments[0]
        frontier = ScenarioFrontier(approved_draft.scenario_id, 0, first.fragment_id, (first.fragment_id,))
        regression = adapter.regression_contract(RegressionContractRequest(model))
        return MicrocycleState(
            approved_draft,
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
        self.observation_resolver = dependencies.observation_resolver

    async def draft(
        self,
        request: ScenarioDraftRequest,
        binding: RepositoryBinding,
    ) -> ScenarioDraftOutcome:
        return await ScenarioDraftCompatibilityLoop(self).draft(request, binding)

    async def submit_candidate(
        self,
        request: ScenarioDraftRequest,
        binding: RepositoryBinding,
    ) -> ScenarioDraftOutcome:
        state = self.state_store.load(request.scenario_id) or _initial_state(request)
        _validate_resume(state, request)
        if state.approved_microcycle is not None or state.status in {
            ScenarioDraftStatus.INTENT_PROTOCOL_FAILURE.value,
            ScenarioDraftStatus.SCENARIO_HARNESS_FAILURE.value,
        ScenarioDraftStatus.OBSERVATION_SUPPORT_PROTOCOL_FAILURE.value,
        }:
            return ScenarioDraftOutcome(state, False)
        if len(state.attempts) >= MAX_TESTER_SCENARIO_ATTEMPTS:
            exhausted = replace(state, status=ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value)
            self.state_store.save(exhausted)
            return ScenarioDraftOutcome(exhausted, False)
        attempt_number = len(state.attempts) + 1
        repair = _last_candidate_attempt(state)
        repair_binding = _repair_binding(binding, request, repair, self.source_reader)
        unit = self.work_units.build(ScenarioDraftWorkUnitRequest(request, attempt_number, _last_feedback(state), repair, state.observation_support))
        result = await self.execution_gateway.execute(unit, repair_binding)
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
        source = self.source_reader.read(attempt.candidate_revision, request.allowed_test_path)
        try:
            prepared = _prepare_candidate(request, attempt, source, self.adapter_catalog)
        except (SyntaxError, ValueError) as error:
            outcome = _candidate_failure(ScenarioCandidateFailureRequest(state, attempt, source, str(error)))
            self.state_store.save(outcome.state)
            return outcome
        if not prepared.assessment.accepted:
            updated_state = state
            if _static_observation_trigger(prepared) and state.observation_support is None:
                updated_state = await _with_observation_support(state, request, self.observation_resolver)
                if _is_terminal_draft_state(updated_state):
                    self.state_store.save(updated_state)
                    return ScenarioDraftOutcome(updated_state, False)
            outcome = _candidate_failure(ScenarioCandidateFailureRequest(updated_state, attempt, source, prepared.assessment.repair_feedback(), prepared))
            self.state_store.save(outcome.state)
            return outcome
        pending = replace(
            attempt,
            status="intent_review_pending",
            candidate=prepared.candidate,
            static_analysis=prepared.static_analysis,
            candidate_assessment=prepared.assessment,
            candidate_source=source,
        )
        self.state_store.save(replace(state, attempts=(*state.attempts[:-1], pending)))
        intent_outcome = await self.intent_reviewer.review(
            _review_request(_approved_draft(prepared), request, self.adapter_catalog, _approved_analysis(prepared))
        )
        reviewed = replace(
            pending,
            status=_intent_attempt_status(intent_outcome.status),
            feedback=_intent_feedback(intent_outcome),
            intent=intent_outcome.result,
            candidate=prepared.candidate,
            static_analysis=prepared.static_analysis,
            candidate_assessment=prepared.assessment,
            candidate_source=source,
            intent_review_status=intent_outcome.status.value,
            intent_review_response_attempts=intent_outcome.response_attempts,
            intent_protocol_failure=intent_outcome.protocol_failure,
            intent_review_evidence_refs=intent_outcome.reasoning_evidence_refs,
        )
        if intent_outcome.status == ScenarioIntentReviewStatus.PROTOCOL_FAILURE:
            updated = replace(state, attempts=(*state.attempts[:-1], reviewed), status=ScenarioDraftStatus.INTENT_PROTOCOL_FAILURE.value)
            self.state_store.save(updated)
            return ScenarioDraftOutcome(updated, False)
        if intent_outcome.result is None:
            raise RuntimeError("semantic intent outcome requires a result")
        updated = replace(state, attempts=(*state.attempts[:-1], reviewed))
        if intent_outcome.status == ScenarioIntentReviewStatus.INSUFFICIENT_EVIDENCE and state.observation_support is None:
            updated = await _with_observation_support(updated, request, self.observation_resolver)
            if _is_terminal_draft_state(updated):
                self.state_store.save(updated)
                return ScenarioDraftOutcome(updated, False)
        if intent_outcome.status != ScenarioIntentReviewStatus.APPROVED:
            self.state_store.save(updated)
            return ScenarioDraftOutcome(updated, False)
        try:
            frozen = ScenarioFreezeFactory().freeze(
                ScenarioFreezeRequest(_approved_draft(prepared), intent_outcome.result, self.adapter_catalog, request.development_base_revision)
            )
        except (SyntaxError, ValueError) as error:
            blocked = _freeze_failure_state(updated, reviewed, error)
            self.state_store.save(blocked)
            return ScenarioDraftOutcome(blocked, False)
        approved = replace(updated, approved_microcycle=frozen, status=ScenarioDraftStatus.APPROVED.value)
        self.state_store.save(approved)
        return ScenarioDraftOutcome(approved, False)

    def _record_submission(self, record: ScenarioDraftExecutionRecord) -> ScenarioDraftOutcome:
        return _record_submission(self.source_reader, record)


@dataclass(frozen=True)
class ScenarioDraftCompatibilityLoop:
    service: ScenarioDraftingService

    async def draft(
        self,
        request: ScenarioDraftRequest,
        binding: RepositoryBinding,
    ) -> ScenarioDraftOutcome:
        for _ in range(MAX_TESTER_SCENARIO_ATTEMPTS * 2):
            state = self.service.state_store.load(request.scenario_id)
            if state is not None and (state.approved_microcycle is not None or _is_terminal_draft_state(state)):
                return ScenarioDraftOutcome(state, False)
            if state is not None and state.attempts and state.attempts[-1].status in {"candidate_submitted", "intent_review_pending"}:
                outcome = await self.service.review_intent(request)
            else:
                outcome = await self.service.submit_candidate(request, binding)
            if outcome.approved or _is_terminal_draft_state(outcome.state) or _requires_external_repair(outcome.state):
                return outcome
        raise RuntimeError("scenario draft compatibility transition guard exhausted")



async def _with_observation_support(
    state: ScenarioDraftRunState,
    request: ScenarioDraftRequest,
    resolver: ScenarioObservationResolver | None,
) -> ScenarioDraftRunState:
    if resolver is None or request.observation_context is None or state.observation_support is not None:
        return state
    support = await resolver.resolve(request.observation_context)
    if support.status == ScenarioObservationSupportStatus.PROTOCOL_FAILURE.value:
        return replace(
            state,
            observation_support=support,
            status=ScenarioDraftStatus.OBSERVATION_SUPPORT_PROTOCOL_FAILURE.value,
        )
    return replace(state, observation_support=support)


def _static_observation_trigger(prepared: ScenarioCandidatePreparation) -> bool:
    issues = prepared.assessment.issues
    product_codes = {
        ScenarioCandidateIssueCode.UNDECLARED_PRODUCT_MEMBER.value,
        ScenarioCandidateIssueCode.PRIVATE_PRODUCT_MEMBER.value,
    }
    return bool(issues) and all(item.code in product_codes for item in issues) and any(
        item.usage_role == "observation" for item in issues
    )

def _freeze_failure_state(
    state: ScenarioDraftRunState,
    attempt: ScenarioDraftAttempt,
    error: SyntaxError | ValueError,
) -> ScenarioDraftRunState:
    evidence = _freeze_failure_evidence(attempt, error)
    failed = replace(attempt, status="scenario_harness_failure", feedback=evidence.message)
    return replace(state, attempts=(*state.attempts[:-1], failed), status=ScenarioDraftStatus.SCENARIO_HARNESS_FAILURE.value, harness_failure_evidence=evidence)

def _is_terminal_draft_state(state: ScenarioDraftRunState) -> bool:
    return state.status in {
        ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value,
        ScenarioDraftStatus.INTENT_PROTOCOL_FAILURE.value,
        ScenarioDraftStatus.SCENARIO_HARNESS_FAILURE.value,
        ScenarioDraftStatus.OBSERVATION_SUPPORT_PROTOCOL_FAILURE.value,
    }



def _workspace_failure_evidence(
    unit: DevelopmentWorkUnit,
    result: WorkUnitExecutionResult,
) -> ScenarioHarnessFailureEvidence:
    return ScenarioHarnessFailureEvidence(
        ScenarioHarnessFailureStage.WORKSPACE_RESULT,
        ScenarioHarnessFailureKind.EXTERNAL_BLOCKER,
        _bounded_failure_text(result.error or result.status),
        _bounded_failure_text(result.status, 256),
        _bounded_failure_text(unit.id, 256),
        _optional_bounded_failure_text(result.change_id, 256),
        _failure_evidence_refs(result.evidence_location),
        _optional_bounded_failure_text(result.selected_worker_id, 256),
        result.worker_provenance,
    )


def _freeze_failure_evidence(
    attempt: ScenarioDraftAttempt,
    error: SyntaxError | ValueError,
) -> ScenarioHarnessFailureEvidence:
    return ScenarioHarnessFailureEvidence(
        ScenarioHarnessFailureStage.SCENARIO_FREEZE,
        ScenarioHarnessFailureKind.EXCEPTION,
        _bounded_failure_text(str(error)),
        _bounded_failure_text(type(error).__name__, 256),
        _bounded_failure_text(attempt.work_unit_id, 256),
        _optional_bounded_failure_text(attempt.change_id, 256),
        _failure_evidence_refs(attempt.evidence_location),
        _optional_bounded_failure_text(attempt.selected_worker_id, 256),
        attempt.worker_provenance,
    )


def _failure_evidence_refs(location: str | None) -> tuple[str, ...]:
    bounded = _optional_bounded_failure_text(location, 1024)
    return () if bounded is None else (bounded,)


def _optional_bounded_failure_text(value: str | None, limit: int) -> str | None:
    return None if value is None else _bounded_failure_text(value, limit)


def _bounded_failure_text(value: str, limit: int = 2048) -> str:
    bounded = value.strip()[:limit]
    return bounded or "unspecified scenario harness failure"

def _requires_external_repair(state: ScenarioDraftRunState) -> bool:
    return bool(state.attempts and state.attempts[-1].status != "candidate_submitted")


def _candidate_failure(request: ScenarioCandidateFailureRequest) -> ScenarioDraftOutcome:
    prepared = request.prepared
    invalid = replace(
        request.attempt,
        status="candidate_invalid",
        feedback=request.feedback,
        candidate=None if prepared is None else prepared.candidate,
        static_analysis=None if prepared is None else prepared.static_analysis,
        candidate_assessment=None if prepared is None else prepared.assessment,
        candidate_source=request.source,
    )
    updated = replace(request.state, attempts=(*request.state.attempts[:-1], invalid))
    return ScenarioDraftOutcome(updated, False)


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
        candidate_branch=result.branch,
        repair_parent_attempt=None if unit.id.endswith("-1") else int(unit.id.rsplit("-", 1)[1]) - 1,
        repair_mode="fresh_draft" if unit.id.endswith("-1") else "repair_previous_candidate",
        selected_worker_id=result.selected_worker_id,
        work_kind=unit.work_kind.value,
        timeout_seconds=unit.timeout_seconds,
        worker_provenance=result.worker_provenance,
    )



def _unchanged_evidence(previous: ScenarioDraftAttempt, returned: ScenarioDraftAttempt) -> ScenarioCandidateUnchangedEvidence | None:
    if previous.candidate_revision is None or returned.candidate_revision is None:
        return None
    previous_digest = _source_digest(previous.candidate_source)
    returned_digest = _source_digest(returned.candidate_source)
    same_revision = previous.candidate_revision == returned.candidate_revision
    same_source = previous_digest is not None and returned_digest is not None and previous_digest == returned_digest
    if not same_revision and not same_source:
        return None
    if same_revision and same_source:
        disposition = ScenarioCandidateUnchangedDisposition.SAME_REVISION_AND_SOURCE
    elif same_revision:
        disposition = ScenarioCandidateUnchangedDisposition.SAME_REVISION
    else:
        disposition = ScenarioCandidateUnchangedDisposition.SAME_SOURCE
    return ScenarioCandidateUnchangedEvidence(previous.candidate_revision, returned.candidate_revision, previous_digest, returned_digest, disposition.value)


def _source_digest(source: str | None) -> str | None:
    return None if source is None else sha256(source.encode("utf-8")).hexdigest()


def _unchanged_feedback(previous_feedback: str | None) -> str:
    prefix = "The repair produced no test-source change. The previous violations remain. Edit the existing candidate and resolve the listed issues."
    return prefix if previous_feedback is None else f"{prefix} {previous_feedback}"


def _unchanged_assessment(previous: ScenarioCandidateAssessment | None, feedback: str) -> ScenarioCandidateAssessment:
    issue = ScenarioCandidateIssue(ScenarioCandidateIssueCode.CANDIDATE_UNCHANGED.value, feedback)
    return ScenarioCandidateAssessment(False, (), issues=(issue,)) if previous is None else replace(previous, issues=(issue, *previous.issues))


def _append_attempt(
    state: ScenarioDraftRunState,
    attempt: ScenarioDraftAttempt,
) -> ScenarioDraftOutcome:
    attempts = (*state.attempts, attempt)
    status = (
        ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value
        if len(attempts) >= MAX_TESTER_SCENARIO_ATTEMPTS and attempt.status != "candidate_submitted"
        else ScenarioDraftStatus.DRAFTING.value
    )
    return ScenarioDraftOutcome(replace(state, attempts=attempts, status=status), True)


def _unrepairable_lineage_outcome(
    state: ScenarioDraftRunState,
    state_store: ScenarioDraftStateStore,
) -> ScenarioDraftOutcome:
    exhausted = replace(
        state, status=ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value
    )
    state_store.save(exhausted)
    return ScenarioDraftOutcome(exhausted, False)


def _last_feedback(state: ScenarioDraftRunState) -> str | None:
    return state.attempts[-1].feedback if state.attempts else None


def _prepare_candidate(
    request: ScenarioDraftRequest,
    attempt: ScenarioDraftAttempt,
    source: str,
    catalog: LanguageAdapterCatalog,
) -> ScenarioCandidatePreparation:
    if attempt.candidate_revision is None or attempt.evidence_location is None:
        raise ValueError("candidate preparation requires accepted Rack AI evidence")
    provisional = ScenarioSourceCandidate(
        request.scenario_id, request.ticket.step_id, request.language_id,
        request.allowed_test_path, source, request.ticket.test_name,
        attempt.candidate_revision, attempt.evidence_location,
    )
    adapter = catalog.for_language(request.language_id)
    assessor = getattr(adapter, "assess_candidate", None)
    if not callable(assessor):
        raise ValueError("language adapter does not implement scenario candidate assessment")
    assessment = assessor(ScenarioCandidateAssessmentRequest(provisional, request.ticket.production_path, _authoring_contract(request), request.product_surface))
    if not assessment.accepted:
        return ScenarioCandidatePreparation(provisional, assessment, None, None)
    analysis = adapter.analyse_candidate(provisional, request.ticket.production_path)
    candidate = replace(provisional, actual_test_identity=analysis.actual_test_identity)
    canonical = adapter.canonicalise_candidate(candidate, request.ticket.test_name)
    draft = TestScenarioDraft(
        request.scenario_id, request.ticket.step_id, request.language_id,
        canonical.source, request.ticket.test_name, request.allowed_test_path,
        "awaiting independent scenario intent review", request.source_requirement_refs,
    )
    return ScenarioCandidatePreparation(candidate, assessment, analysis, draft)


def _review_request(
    draft: TestScenarioDraft,
    request: ScenarioDraftRequest,
    catalog: LanguageAdapterCatalog,
    static_analysis: ScenarioStaticAnalysis,
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
        source_requirement_evidence=request.source_requirement_evidence,
        complete_scenario_source=draft.source,
        static_fragment_kinds=tuple(item.kind for item in fragments),
        canonical_test_identity=draft.canonical_test_identity,
        static_analysis=static_analysis,
    )


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


def _intent_attempt_status(status: ScenarioIntentReviewStatus) -> str:
    return "intent_review_protocol_failure" if status == ScenarioIntentReviewStatus.PROTOCOL_FAILURE else status.value


def _intent_feedback(outcome: ScenarioIntentReviewOutcome) -> str:
    result = outcome.result
    if result is not None:
        return result.rationale
    failure = outcome.protocol_failure
    return "intent review protocol failure" if failure is None else failure.parse_error or failure.schema_error or "intent review protocol failure"


def _approved_draft(prepared: ScenarioCandidatePreparation) -> TestScenarioDraft:
    if prepared.draft is None:
        raise ValueError("candidate assessment must pass before intent review")
    return prepared.draft


def _approved_analysis(prepared: ScenarioCandidatePreparation) -> ScenarioStaticAnalysis:
    if prepared.static_analysis is None:
        raise ValueError("candidate assessment must pass before semantic analysis")
    return prepared.static_analysis


def _authoring_contract(request: ScenarioDraftRequest) -> ScenarioAuthoringContract:
    return ScenarioAuthoringContract(
        request.language_id, request.test_framework, 1,
        ("imports", "module data assignments", "one ordinary test function"),
        ("module docstrings", "test-function docstrings", "standalone string-expression statements", "helper functions", "fixtures", "classes", "async tests"),
        ("test-function docstrings", "standalone string-expression statements", "parameterization", "nested functions/classes", "dynamic generation", "skip/xfail"),
        True, True, True, True, "adapter_normalises one submitted ordinary test",
    )


def _tester_objective(
    request: ScenarioDraftRequest,
    feedback: str | None,
    repair: ScenarioDraftAttempt | None,
    observation_support: ScenarioObservationSupport | None,
) -> str:
    payload: dict[str, object] = {
        "role": "Tester",
        "task": "REPAIR MODE. Refactor the existing submitted test candidate. The existing test file is present in your base revision. Make the smallest changes required to resolve the listed violations. Preserve correct behavior already expressed. Do not discard it and invent an unrelated test." if repair else ("Your previous Tester submission produced no candidate source or revision. Submit a new complete scenario from the unchanged development base. Use only tools actually exposed by the execution harness." if feedback and feedback.startswith("Your previous Tester submission") else "Draft one complete behavioral scenario conforming to the supplied strict authoring contract."),
        "repair_mode": "repair_previous_candidate" if repair else ("fresh_retry_after_no_candidate" if feedback and feedback.startswith("Your previous Tester submission") else "fresh_draft"),
        "authoring_contract": _authoring_contract(request).to_dict(),
        "ticket": {
            "id": request.ticket.step_id,
            "behavior": request.ticket.focused_behavior,
            "expected_result": request.ticket.expected_result,
            "planned_canonical_test_identity": request.ticket.test_name,
        },
        "source_requirement_refs": list(request.source_requirement_refs),
        "source_requirements": [item.to_dict() for item in request.source_requirement_evidence],
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
            "do not include a module docstring, test-function docstring, or standalone string-expression statement",
            "exercise the declared production path without a substitute implementation or behavior mock",
            "do not skip, xfail, or evade a missing production capability",
            "do not materialise a frontier or start implementation",
        ],
    }
    if (
        observation_support is not None
        and observation_support.status == ScenarioObservationSupportStatus.SUPPORT_SELECTED.value
    ):
        payload["observation_support"] = {
            "instruction": "The following declared product member may be used only as an observation instrument if required to demonstrate the active behavior. Do not test its independent semantics or broaden the scenario beyond the active ticket.",
            "members": list(observation_support.selected_members),
        }

    if repair is not None:
        payload["previous_candidate"] = {
            "attempt": repair.attempt_number,
            "ref": repair.candidate_branch,
            "sha": repair.candidate_revision,
            "source": repair.candidate_source,
            "assessment": None if repair.candidate_assessment is None else repair.candidate_assessment.to_dict(),
            "deterministic_feedback": repair.feedback,
            "intent_feedback": None if repair.intent is None else repair.intent.rationale,
        }
    return json.dumps(payload, sort_keys=True)



def _last_candidate_attempt(state: ScenarioDraftRunState) -> ScenarioDraftAttempt | None:
    for attempt in reversed(state.attempts):
        if _has_repair_lineage(attempt):
            return attempt
    return None


def _submission_mode(state: ScenarioDraftRunState) -> ScenarioSubmissionMode:
    if not state.attempts:
        return ScenarioSubmissionMode.FRESH_DRAFT
    candidate = _last_candidate_attempt(state)
    if candidate is None:
        return ScenarioSubmissionMode.FRESH_RETRY_AFTER_NO_CANDIDATE
    if state.attempts[-1].candidate_revision is None:
        return ScenarioSubmissionMode.RETRY_REPAIR_FROM_EXISTING_CANDIDATE
    return ScenarioSubmissionMode.REPAIR_PREVIOUS_CANDIDATE


def _submission_outcome(
    result: WorkUnitExecutionResult, accepted: bool,
) -> ScenarioSubmissionOutcome:
    if accepted:
        return ScenarioSubmissionOutcome.CANDIDATE_SUBMITTED
    detail = (result.error or result.status).lower()
    if result.selected_worker_id is None or ("advertised" in detail and "denied" in detail):
        return ScenarioSubmissionOutcome.EXTERNAL_BLOCKER
    if "tool" in detail and ("not allowed" in detail or "unknown" in detail or "disallowed" in detail):
        return ScenarioSubmissionOutcome.DISALLOWED_OR_UNKNOWN_TOOL_CALL
    if "timeout" in detail:
        return ScenarioSubmissionOutcome.WORKER_MODEL_TIMEOUT
    if "protocol" in detail:
        return ScenarioSubmissionOutcome.MODEL_PROTOCOL_FAILURE
    if "no candidate" in detail or "completed" in detail or "no change" in detail:
        return ScenarioSubmissionOutcome.MODEL_COMPLETED_WITHOUT_CANDIDATE
    return ScenarioSubmissionOutcome.EXTERNAL_BLOCKER


def _no_candidate_feedback(
    result: WorkUnitExecutionResult, outcome: ScenarioSubmissionOutcome,
) -> str:
    detail = result.error or result.status
    return (
        f"Your previous Tester submission ran on {result.selected_worker_id} but produced no candidate test. "
        f"{detail} No candidate source or revision exists to repair. Submit a new complete scenario from "
        "the unchanged development base. Use only tools actually exposed by the execution harness."
    )

def _has_repair_lineage(repair: ScenarioDraftAttempt) -> bool:
    return (
        repair.candidate_branch is not None
        and repair.candidate_revision is not None
        and repair.candidate_source is not None
    )

def _repair_binding(
    binding: RepositoryBinding,
    request: ScenarioDraftRequest,
    repair: ScenarioDraftAttempt | None,
    reader: ScenarioCandidateSourceReader,
) -> RepositoryBinding:
    if repair is None:
        return binding.with_base_sha(request.development_base_revision)
    if repair.candidate_branch is None or repair.candidate_revision is None or repair.candidate_source is None:
        raise ValueError("repair candidate lineage is unavailable")
    if reader.resolve(repair.candidate_branch) != repair.candidate_revision:
        raise ValueError("repair candidate ref does not resolve to its persisted SHA")
    return RepositoryBinding(
        binding.repository_id, repair.candidate_branch, repair.candidate_revision,
        binding.registered_root, binding.environment_resources,
    )


def _intent_prompt(request: ScenarioIntentReviewRequest) -> str:
    payload = {
        "question": "Does this complete scenario, if eventually GREEN, demonstrate the requested Behavior Planner ticket?",
        "behavior_ticket": {
            "id": request.behavior_ref,
            "behavior": request.behavior_summary,
            "expected_result": request.expected_result,
        },
        "source_requirement_refs": list(request.source_requirement_refs),
        "source_requirements": [item.to_dict() for item in request.source_requirement_evidence],
        "complete_scenario_source": request.complete_scenario_source,
        "static_scenario_facts": {
            "canonical_test_identity": request.canonical_test_identity,
            "fragment_kinds": list(request.static_fragment_kinds),
            "production_reference_paths": list(request.static_analysis.production_reference_paths),
            "substitute_definitions": list(request.static_analysis.substitute_definitions),
            "mocked_behavior_targets": list(request.static_analysis.mocked_behavior_targets),
            "evasion_markers": list(request.static_analysis.evasion_markers),
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


def _record_submission(
    source_reader: ScenarioCandidateSourceReader,
    record: ScenarioDraftExecutionRecord,
) -> ScenarioDraftOutcome:
    state = record.state
    unit = record.unit
    result = record.result
    accepted = result.accepted and result.accepted_revision is not None and result.branch is not None
    outcome = _submission_outcome(result, accepted)
    if outcome is ScenarioSubmissionOutcome.EXTERNAL_BLOCKER:
        blocked = replace(
            state,
            status=ScenarioDraftStatus.SCENARIO_HARNESS_FAILURE.value,
            harness_failure_evidence=_workspace_failure_evidence(unit, result),
        )
        return ScenarioDraftOutcome(blocked, False)
    status = outcome.value
    feedback = None if accepted else _no_candidate_feedback(result, outcome)
    attempt = replace(
        _attempt(unit, result, status, feedback),
        repair_mode=_submission_mode(state).value,
        no_candidate_outcome=None if accepted else outcome.value,
    )
    if state.attempts and attempt.candidate_revision is not None:
        try:
            returned_source = source_reader.read(attempt.candidate_revision, record.request.allowed_test_path)
        except ValueError:
            returned_source = None
        attempt = replace(attempt, candidate_source=returned_source)
    if not state.attempts:
        return _append_attempt(state, attempt)
    parent = state.attempts[-1]
    attempt = replace(
        attempt,
        repair_base_ref=parent.candidate_branch or parent.candidate_revision,
        repair_base_sha=parent.candidate_revision,
    )
    unchanged = _unchanged_evidence(parent, attempt)
    if unchanged is None:
        return _append_attempt(state, attempt)
    feedback = _unchanged_feedback(parent.feedback)
    assessment = _unchanged_assessment(parent.candidate_assessment, feedback)
    rejected = replace(
        attempt,
        status="candidate_unchanged",
        feedback=feedback,
        candidate=parent.candidate,
        static_analysis=parent.static_analysis,
        candidate_assessment=assessment,
        candidate_source=parent.candidate_source,
        unchanged_evidence=unchanged,
    )
    return _append_attempt(state, rejected)
