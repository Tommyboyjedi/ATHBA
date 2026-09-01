"""Durable one-transition controller over the typed feature application."""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
from typing import Protocol

from core.development.strict_tdd_feature_application import StrictTddFeatureApplicationService
from core.development.strict_tdd_lifecycle_evidence import (
    LifecycleEventAppendRequest,
    LifecycleEventDraft,
    StrictTddLifecycleEvent,
    StrictTddLifecycleEventKind,
    StrictTddLifecycleEventRepository,
    StrictTddLifecycleRunContext,
    StrictTddLifecycleStatus,
)
from core.development.strict_tdd_run_domain import (
    StrictTddRunMode,
    StrictTddRunRequest,
    StrictTddRunResult,
    StrictTddRunState,
    StrictTddRunStatus,
    StrictTddTransitionInFlight,
    StrictTddTransitionReceipt,
    StrictTddTransitionReceiptFactory,
)
from core.development.strict_tdd_run_reporting import (
    StrictTddRunEvidenceSnapshotCollector,
    StrictTddRunReportWriter,
)
from core.development.strict_tdd_run_store import StrictTddRunStateRepository
from core.development.strict_tdd_transition_provenance import (
    StrictTddCheckpoint,
    StrictTddTerminalDisposition,
    StrictTddTerminalPolicy,
    StrictTddTerminalPolicyRequest,
    StrictTddTransitionEventProjector,
    StrictTddTransitionProjectionRequest,
)


class StrictTddReceiptDeliveryError(Exception):
    pass


@dataclass(frozen=True)
class StrictTddRunControllerDependencies:
    application: StrictTddFeatureApplicationService
    states: StrictTddRunStateRepository
    lifecycle: StrictTddLifecycleEventRepository
    snapshots: StrictTddRunEvidenceSnapshotCollector
    reports: StrictTddRunReportWriter


class StrictTddRunController:
    """Owns durable delivery, stopping, and reporting, not feature routing."""

    def __init__(self, dependencies: StrictTddRunControllerDependencies):
        self.application = dependencies.application
        self.states = dependencies.states
        self.lifecycle = dependencies.lifecycle
        self.snapshots = dependencies.snapshots
        self.reports = dependencies.reports
        self.receipts = StrictTddTransitionReceiptFactory()
        self.projector = StrictTddTransitionEventProjector()
        self.terminals = StrictTddTerminalPolicy()

    async def start(self, request: StrictTddRunRequest) -> StrictTddRunResult:
        if request.mode != StrictTddRunMode.START:
            raise ValueError("start requires a start request")
        return await self.run(request)

    async def resume(self, request: StrictTddRunRequest) -> StrictTddRunResult:
        if request.mode != StrictTddRunMode.RESUME:
            raise ValueError("resume requires a resume request")
        return await self.run(request)

    async def advance(self, request: StrictTddRunRequest) -> StrictTddRunResult:
        return await self._advance(request, True)

    async def _advance(self, request: StrictTddRunRequest, announce_resume: bool) -> StrictTddRunResult:
        state, context = _prepare(self, request, announce_resume)
        if state.pending_transition_receipt is not None:
            return _deliver(self, request, state, context, state.pending_transition_receipt)
        if state.transition_in_flight is not None:
            return _recover_required(self, request, state, context)
        if state.status in {StrictTddRunStatus.COMPLETED, StrictTddRunStatus.BLOCKED, StrictTddRunStatus.STALLED, StrictTddRunStatus.RECOVERY_REQUIRED, StrictTddRunStatus.TRANSITION_LIMIT_REACHED}:
            return _report_result(self, context, state, None)
        marker = StrictTddTransitionInFlight(state.total_application_transition_count + 1)
        running = replace(state, status=StrictTddRunStatus.RUNNING, reason=None, transition_in_flight=marker)
        self.states.save(running)
        transition = await self.application.advance(request.feature_request())
        receipt = self.receipts.create(transition, marker.occurrence)
        pending = replace(running, transition_in_flight=None, pending_transition_receipt=receipt)
        self.states.save(pending)
        return _deliver(self, request, pending, context, receipt)

    async def run(self, request: StrictTddRunRequest) -> StrictTddRunResult:
        remaining = request.configuration.max_application_transitions_per_invocation
        while remaining > 0:
            result = await self._advance(request, remaining == request.configuration.max_application_transitions_per_invocation)
            if result.status != StrictTddRunStatus.RUNNING:
                return result
            remaining -= 1
        state = _required_state(self, request)
        limited = replace(state, status=StrictTddRunStatus.TRANSITION_LIMIT_REACHED, reason="controller_transition_limit_reached")
        self.states.save(limited)
        context = _context(self, request)
        terminal = _append_controller_event(self, context, limited, StrictTddLifecycleEventKind.RUN_BLOCKED, StrictTddLifecycleStatus.BLOCKED)
        self.states.save(replace(limited, last_lifecycle_event_id=terminal.event_id))
        return _report_result(self, context, limited, terminal)

def _prepare(self, request: StrictTddRunRequest, announce_resume: bool) -> tuple[StrictTddRunState, StrictTddLifecycleRunContext]:
    context = _context(self, request)
    if not announce_resume:
        return _continued(self, request), context
    if request.mode == StrictTddRunMode.START:
        return _start(self, request, context), context
    if announce_resume:
        return _resume(self, request, context), context
    return _continued(self, request), context

def _start(self, request: StrictTddRunRequest, context: StrictTddLifecycleRunContext) -> StrictTddRunState:
    if self.states.exists(request.run_id):
        raise ValueError("strict TDD run already exists")
    if self.application.states.load(request.project_id) is not None:
        raise ValueError("incompatible existing feature state for requested project")
    state = StrictTddRunState(request.run_id, request.project_id, request.immutable_identity_hash, StrictTddRunStatus.READY)
    self.states.save(state)
    event = _append_controller_event(self, context, state, StrictTddLifecycleEventKind.RUN_STARTED, StrictTddLifecycleStatus.STARTED)
    started = replace(state, last_lifecycle_event_id=event.event_id)
    self.states.save(started)
    return started

def _continued(self, request: StrictTddRunRequest) -> StrictTddRunState:
    state = _required_state(self, request)
    if state.project_id != request.project_id or state.immutable_identity_hash != request.immutable_identity_hash:
        raise ValueError("strict TDD resume request identity differs")
    return state

def _resume(self, request: StrictTddRunRequest, context: StrictTddLifecycleRunContext) -> StrictTddRunState:
    state = _required_state(self, request)
    if state.project_id != request.project_id or state.immutable_identity_hash != request.immutable_identity_hash:
        raise ValueError("strict TDD resume request identity differs")
    resumed = replace(state, current_invocation_count=state.current_invocation_count + 1)
    self.states.save(resumed)
    event = _append_controller_event(self, context, resumed, StrictTddLifecycleEventKind.RUN_RESUMED, StrictTddLifecycleStatus.STARTED)
    updated = replace(resumed, last_lifecycle_event_id=event.event_id)
    self.states.save(updated)
    return updated

def _deliver(self, request: StrictTddRunRequest, state: StrictTddRunState, context: StrictTddLifecycleRunContext, receipt: StrictTddTransitionReceipt) -> StrictTddRunResult:
    try:
        event = _append_application_event(self, context, receipt)
    except Exception as error:
        raise StrictTddReceiptDeliveryError("transition receipt delivery failed") from error
    delivered = _delivered_state(self, state, receipt, event)
    self.states.save(delivered)
    terminal = self.terminals.decide(StrictTddTerminalPolicyRequest(receipt.transition(), request.requested_checkpoint, frozenset(delivered.reached_checkpoints)))
    final = _terminal_state(self, delivered, receipt, terminal.disposition, terminal.checkpoint)
    self.states.save(final)
    if final.status != StrictTddRunStatus.RUNNING:
        kind = StrictTddLifecycleEventKind.CONTROLLED_CHECKPOINT_STOP
        status = StrictTddLifecycleStatus.CHECKPOINTED
        if final.status == StrictTddRunStatus.COMPLETED:
            kind, status = StrictTddLifecycleEventKind.RUN_COMPLETED, StrictTddLifecycleStatus.COMPLETED
        elif final.status != StrictTddRunStatus.CHECKPOINTED:
            kind, status = StrictTddLifecycleEventKind.RUN_BLOCKED, StrictTddLifecycleStatus.BLOCKED
        terminal_event = _append_controller_event(self, context, final, kind, status)
        final = replace(final, last_lifecycle_event_id=terminal_event.event_id)
        self.states.save(final)
        return _report_result(self, context, final, terminal_event)
    return _result(self, final, receipt, event)

def _delivered_state(self, state: StrictTddRunState, receipt: StrictTddTransitionReceipt, event: StrictTddLifecycleEvent) -> StrictTddRunState:
    stalled = _stalled(self, state, receipt)
    return replace(state, status=StrictTddRunStatus.STALLED if stalled else StrictTddRunStatus.RUNNING, total_application_transition_count=receipt.occurrence, pending_transition_receipt=None, last_delivered_fingerprint=receipt.fingerprint, last_delivered_path=receipt.path, last_lifecycle_event_id=event.event_id, reason="stable_transition_fingerprint_stalled" if stalled else None)

def _terminal_state(self, state: StrictTddRunState, receipt: StrictTddTransitionReceipt, disposition: StrictTddTerminalDisposition, checkpoint: StrictTddCheckpoint | None) -> StrictTddRunState:
    if state.status == StrictTddRunStatus.STALLED:
        return state
    if disposition == StrictTddTerminalDisposition.COMPLETED:
        return replace(state, status=StrictTddRunStatus.COMPLETED)
    if disposition == StrictTddTerminalDisposition.BLOCKED:
        return replace(state, status=StrictTddRunStatus.BLOCKED, reason=receipt.blocker_or_replan_reason or "no_further_transition_available")
    if disposition == StrictTddTerminalDisposition.CHECKPOINT:
        if checkpoint is None:
            raise ValueError("checkpoint terminal decision requires a checkpoint")
        reached = tuple(dict.fromkeys((*state.reached_checkpoints, checkpoint)))
        return replace(state, status=StrictTddRunStatus.CHECKPOINTED, reached_checkpoints=reached)
    return state

def _stalled(self, state: StrictTddRunState, receipt: StrictTddTransitionReceipt) -> bool:
    previous = state.last_delivered_fingerprint
    if previous is None or state.last_delivered_path != receipt.path:
        return False
    return previous == receipt.fingerprint

def _recover_required(self, request: StrictTddRunRequest, state: StrictTddRunState, context: StrictTddLifecycleRunContext) -> StrictTddRunResult:
    recovered = replace(state, status=StrictTddRunStatus.RECOVERY_REQUIRED, reason="transition_receipt_recovery_required")
    self.states.save(recovered)
    event = _append_controller_event(self, context, recovered, StrictTddLifecycleEventKind.RUN_BLOCKED, StrictTddLifecycleStatus.BLOCKED)
    self.states.save(replace(recovered, last_lifecycle_event_id=event.event_id))
    return _report_result(self, context, recovered, event)

def _append_application_event(self, context: StrictTddLifecycleRunContext, receipt: StrictTddTransitionReceipt) -> StrictTddLifecycleEvent:
    draft = self.projector.project(StrictTddTransitionProjectionRequest(context, receipt.transition(), receipt.occurrence))[0]
    return _append(self, context, draft)

def _append_controller_event(self, context: StrictTddLifecycleRunContext, state: StrictTddRunState, kind: StrictTddLifecycleEventKind, status: StrictTddLifecycleStatus) -> StrictTddLifecycleEvent:
    identity = _controller_identity(self, state, kind)
    draft = LifecycleEventDraft(identity, kind, status, (f"controller:{state.status.value}",), message=state.reason)
    return _append(self, context, draft)

def _append(self, context: StrictTddLifecycleRunContext, draft: LifecycleEventDraft) -> StrictTddLifecycleEvent:
    existing = next((item for item in self.lifecycle.events(context) if item.event_id == draft.event_id), None)
    sequence = self.lifecycle.next_sequence(context) if existing is None else existing.sequence_number
    event = draft.materialise(context, sequence)
    return self.lifecycle.append(LifecycleEventAppendRequest(context, event))

def _controller_identity(self, state: StrictTddRunState, kind: StrictTddLifecycleEventKind) -> str:
    payload = json.dumps((state.run_id, kind.value, state.total_application_transition_count, state.current_invocation_count), separators=(",", ":"))
    return "controller-" + sha256(payload.encode()).hexdigest()

def _context(self, request: StrictTddRunRequest) -> StrictTddLifecycleRunContext:
    return StrictTddLifecycleRunContext(request.run_id, request.project_id, request.source_requirement, request.athba_revision, request.rack_ai_revision)

def _required_state(self, request: StrictTddRunRequest) -> StrictTddRunState:
    state = self.states.load(request.run_id)
    if state is None:
        raise ValueError("strict TDD run state is required")
    return state

def _report_result(self, context: StrictTddLifecycleRunContext, state: StrictTddRunState, event: StrictTddLifecycleEvent | None) -> StrictTddRunResult:
    paths = self.reports.write(state.run_id, self.snapshots.collect(context, state))
    saved = replace(state, structured_report_path=paths.structured, markdown_report_path=paths.markdown)
    self.states.save(saved)
    return _result(self, saved, saved.pending_transition_receipt, event)

def _result(self, state: StrictTddRunState, receipt: StrictTddTransitionReceipt | None, event: StrictTddLifecycleEvent | None) -> StrictTddRunResult:
    final = () if receipt is None else receipt.final_reconciliation
    checkpoint = state.reached_checkpoints[-1] if state.status == StrictTddRunStatus.CHECKPOINTED and state.reached_checkpoints else None
    return StrictTddRunResult(state.run_id, state.project_id, state.status, state.last_delivered_path, None if receipt is None else receipt.canonical_ref, None if receipt is None else receipt.canonical_sha, None if receipt is None else receipt.working_ref, None if receipt is None else receipt.working_sha, checkpoint, state.reason, state.last_lifecycle_event_id if event is None else event.event_id, state.structured_report_path, state.markdown_report_path, final)