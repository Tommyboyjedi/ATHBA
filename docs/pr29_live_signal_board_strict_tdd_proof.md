# PR29 live SignalBoard strict-TDD proof

## Scope

This document records the first real tiny strict-TDD feature attempt through the
ATHBA to Rack AI v2 workspace-execution path. SignalBoard is a fresh disposable
Python/pytest fixture. ReservationBook and concurrent work are out of scope.

## Pre-execution change gate: generic ATHBA execution-port composition

1. **Documented generic contract.** ATHBA's boundary rationale and PR23 routing
   architecture require artifact-producing work to cross the generic
   `RackAiWorkspaceConnector` boundary, which serializes `rack-ai/work-unit/v2`.
2. **Observed violation.** At ATHBA `0527113007d2d786cd801a190da29ce71590c569`,
   `StrictTddFeatureCompositionFactory` instead selected
   `RackAiCliExecutionGateway` whenever no test gateway was injected. That
   gateway serializes the pre-v2 `RackAiChangeRequest` schema, so the durable
   production runner could not exercise the qualified v2 connector.
3. **Generic reproduction.** The condition depends only on the composition
   request having no injected gateway; it is independent of SignalBoard,
   generated scenario content, model output, and Rack AI worker selection.
4. **Owning component.** ATHBA's strict-TDD feature composition and the
   existing profiled workspace gateway adapter.
5. **Required deterministic regression.** A composition test must prove that
   the default production gateway is the profiled v2 workspace adapter, and an
   adapter test must retain the candidate branch and complete worker provenance
   returned by the generic workspace port.

No model invocation was made before this gate. No Rack AI source or configuration
