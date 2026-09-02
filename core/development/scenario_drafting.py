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
)
from core.development.strict_tdd_execution_budget import (
    StrictTddExecutionBudgetPolicy,
    StrictTddWorkKind,
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
    def resolve(self, ref: str) -> str: ...


@dataclass(frozen=True)
class ScenarioDraftWorkUnitRequest:
    request: ScenarioDraftRequest
    attempt_number: int
    feedback: str | None
    repair_attempt: ScenarioDraftAttempt | None = None


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
    budget_policy: StrictTddExecutionBudgetPolicy = field(
        default_factory=StrictTddExecutionBudgetPolicy
    )

    def build(self, request: ScenarioDraftWorkUnitRequest) -> DevelopmentWorkUnit:
        draft = request.request
        work_unit_id = f"{draft.ticket.step_id}--scenario-draft-{request.attempt_number}"
        work_kind = (
            StrictTddWorkKind.SCENARIO_REPAIR
            if request.repair_attempt is not None
            else StrictTddWorkKind.SCENARIO_DRAFT
        )
        return DevelopmentWorkUnit(
            id=work_unit_id,
            project_id=draft.ticket.step_id,
            parent_ticket_id=draft.ticket.step_id,
            objective=_tester_objective(draft, request.feedback, request.repair_attempt),
            allowed_paths=[draft.allowed_test_path],
            acceptance=AcceptanceContract(
                commands=[[self.python_executable, "-B", "-m", "py_compile", draft.allowed_test_path]],
                required_artifacts=[draft.allowed_test_path],
            ),
            max_implementation_attempts=1,
            timeout_seconds=self.budget_policy.timeout_for(work_kind),
            work_kind=work_kind,
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
    complete_scenario_source: str
    static_fragment_kinds: tuple[str, ...]
    canonical_test_identity: str
    static_analysis: ScenarioStaticAnalysis


@dataclass(frozen=True)
class ScenarioCandidatePreparation:
    candidate: ScenarioSourceCandidate
    assessment: ScenarioCandidateAssessment
    static_analysis: ScenarioStaticAnalysis | None
    draft: TestScenarioDraft | None


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
            if state is not None and state.attempts and state.attempts[-1].status == "candidate_submitted":
                outcome = await self.review_intent(request)
            else:
                outcome = await self.submit_candidate(request, binding)
            if outcome.approved or outcome.state.status == ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value:
                return outcome
            if outcome.state.attempts and outcome.state.attempts[-1].status != "candidate_submitted":
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
        repair = state.attempts[-1] if state.attempts else None
        if repair is not None and not _has_repair_lineage(repair):
            return _unrepairable_lineage_outcome(state, self.state_store)
        repair_binding = _repair_binding(binding, request, repair, self.source_reader)
        unit = self.work_units.build(ScenarioDraftWorkUnitRequest(request, attempt_number, _last_feedback(state), repair))
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
        source: str | None = None
        try:
            source = self.source_reader.read(attempt.candidate_revision, request.allowed_test_path)
            prepared = _prepare_candidate(request, attempt, source, self.adapter_catalog)
            feedback = prepared.assessment.repair_feedback()
            if not prepared.assessment.accepted:
                invalid = replace(
                    attempt,
                    status="candidate_invalid",
                    feedback=feedback,
                    candidate=prepared.candidate,
                    static_analysis=prepared.static_analysis,
                    candidate_assessment=prepared.assessment,
                    candidate_source=source,
                )
                updated = replace(state, attempts=(*state.attempts[:-1], invalid))
                self.state_store.save(updated)
                return ScenarioDraftOutcome(updated, False)
            intent = await self.intent_reviewer.review(
                _review_request(_approved_draft(prepared), request, self.adapter_catalog, _approved_analysis(prepared))
            )
            reviewed = replace(
                attempt,
                status=intent.status,
                feedback=intent.rationale,
                intent=intent,
                candidate=prepared.candidate,
                static_analysis=prepared.static_analysis,
                candidate_assessment=prepared.assessment,
                candidate_source=source,
            )
            updated = replace(state, attempts=(*state.attempts[:-1], reviewed))
            if intent.status == "approved":
                frozen = ScenarioFreezeFactory().freeze(
                    ScenarioFreezeRequest(_approved_draft(prepared), intent, self.adapter_catalog, request.development_base_revision)
                )
                updated = replace(updated, approved_microcycle=frozen, status=ScenarioDraftStatus.APPROVED.value)
            self.state_store.save(updated)
            return ScenarioDraftOutcome(updated, False)
        except (SyntaxError, ValueError) as error:
            invalid = replace(
                attempt,
                status="candidate_invalid",
                feedback=str(error),
                candidate_source=source,
            )
            updated = replace(state, attempts=(*state.attempts[:-1], invalid))
            self.state_store.save(updated)
            return ScenarioDraftOutcome(updated, False)

    def _record_submission(self, record: ScenarioDraftExecutionRecord) -> ScenarioDraftOutcome:
        state = record.state
        unit = record.unit
        result = record.result
        accepted = result.accepted and result.accepted_revision is not None and result.branch is not None
        status = "candidate_submitted" if accepted else "candidate_rejected"
        feedback = None if accepted else result.error or (
            "accepted candidate is missing a durable candidate branch/ref" if result.accepted else result.status
        )
        attempt = _attempt(unit, result, status, feedback)
        if state.attempts and attempt.candidate_revision is not None:
            try:
                returned_source = self.source_reader.read(attempt.candidate_revision, record.request.allowed_test_path)
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
            attempt, status="candidate_unchanged", feedback=feedback,
            candidate=parent.candidate, static_analysis=parent.static_analysis,
            candidate_assessment=assessment, candidate_source=parent.candidate_source,
            unchanged_evidence=unchanged,
        )
        return _append_attempt(state, rejected)


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
    assessment = assessor(ScenarioCandidateAssessmentRequest(provisional, request.ticket.production_path, _authoring_contract(request)))
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


def _tester_objective(request: ScenarioDraftRequest, feedback: str | None, repair: ScenarioDraftAttempt | None) -> str:
    payload: dict[str, object] = {
        "role": "Tester",
        "task": "REPAIR MODE. Refactor the existing submitted test candidate. The existing test file is present in your base revision. Make the smallest changes required to resolve the listed violations. Preserve correct behavior already expressed. Do not discard it and invent an unrelated test." if repair else "Draft one complete behavioral scenario conforming to the supplied strict authoring contract.",
        "repair_mode": "repair_previous_candidate" if repair else "fresh_draft",
        "authoring_contract": _authoring_contract(request).to_dict(),
        "ticket": {
            "id": request.ticket.step_id,
            "behavior": request.ticket.focused_behavior,
            "expected_result": request.ticket.expected_result,
            "planned_canonical_test_identity": request.ticket.test_name,
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
            "do not include a module docstring, test-function docstring, or standalone string-expression statement",
            "exercise the declared production path without a substitute implementation or behavior mock",
            "do not skip, xfail, or evade a missing production capability",
            "do not materialise a frontier or start implementation",
        ],
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
