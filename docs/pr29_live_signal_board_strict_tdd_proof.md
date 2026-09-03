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

## Scenario harness evidence integrity correction

**Documented contract.** Terminal fail-closed transitions must preserve enough evidence to classify the owning failure boundary.

**Observed behavior.** `scenario_harness_failure` persisted without diagnostic evidence.

**Why generic.** This applies to every scenario-draft external or harness failure, independent of feature, model, worker, or fixture.

**Correction.** Persist typed, bounded harness-failure evidence.

**Semantic behavior changed:** NO

**Attempt accounting changed:** NO

**Harness accommodation:** NO

## Local-primary runtime interruption before fresh proof

- ATHBA checkpoint: `d51d9d2925b44ba60f39fb47df2a27e1af99da3e`.
- Rack AI checkpoint: `56d2c69f1e815acd12fca9065945c5e46de5a36a`.
- The pre-existing proof handoff reported a stalled `/v1/responses` READY probe
  despite successful local-primary health and model metadata endpoints. It did
  not retain a curl exit code, HTTP status, or timing for that earlier stalled
  request, so those historical details are unavailable rather than inferred.
- At `2026-09-03T11:50:54Z`, `/health` and `/v1/models` each returned HTTP 200.
  The advertised model was `local-primary` backed by
  `cyankiwi/gemma-4-12B-it-AWQ-INT4`.
- Docker's existing `vllm-primary` service was `Up 11 days (healthy)` on port
  8017. Its EngineCore held 14,116 MiB on the RTX 4060 Ti at 0% utilization;
  no active TCP connection to port 8017 remained after probing. No active Rack
  AI durable work status was found.
- The current bounded READY probe returned curl exit 0, HTTP 200, and completed
  response text `READY` in 0.088474 seconds. A second probe after a short wait
  independently returned curl exit 0, HTTP 200, and `READY` in 0.087607 seconds.
- No restart was required: the existing service was already generating normally
  when rechecked. Local-coder `/health` and `/v1/models` also returned HTTP 200.
- No model identity, endpoint, GPU assignment, context limit, vLLM option,
  JCode tool profile, ATHBA source, or Rack AI source was changed for this
  operational check.

## Fresh SignalBoard run: stopped at typed scenario harness failure

- Fresh run and project: `pr29-signal-board-20260903T115600Z`.
- Real behavior planning and independent Gatekeeper atomization completed before
  the first selected behavior, `REQ-001` (`SignalBoard.create`).
- The scenario draft transition stopped at `scenario_harness_failure` with
  `failure_stage=workspace_result` and `failure_kind=external_blocker`.
- Durable harness evidence identifies work unit `REQ-001--scenario-draft-1` and
  reports that the new ATHBA repository is outside Rack AI trusted dynamic roots.
- Rack AI returned before creating a submission, selection decision, worker
  provenance, candidate revision, or durable Rack AI state for this work unit.
- This is a trusted-root operational-policy blocker, not a SignalBoard,
  local-primary, local-coder, ATHBA semantic, or Rack AI routing defect.
- The run was not retried or resumed. No source/configuration or test-grammar
  change was made to bypass the trusted-root policy.

## Trusted dynamic root proof correction

- Historical failed run/project: `pr29-signal-board-20260903T115600Z`.
- Its repository was `/srv/ATHBA/state/pr29-signal-board-20260903T115600Z/projects/pr29-signal-board-20260903T115600Z/repository`; Rack AI correctly rejected it as outside trusted dynamic roots.
- ATHBA derives project repositories from `state_root/projects`; the live Rack AI administrator policy already approves `/srv/ATHBA/state/projects`.
- The corrected live composition used state root `/srv/ATHBA/state`, without changing Rack AI configuration or static registration.
- New run/project: `pr29-signal-board-20260903T123300Z`.
- Its repository is `/srv/ATHBA/state/projects/pr29-signal-board-20260903T123300Z/repository`; its resolved realpath is identical and remains beneath the approved root.
- The project is ready, Git-initialized, and has trusted base revision `38d17b74dc41e733bdfaf346acabb868dc46d018`.

## Corrected SignalBoard run evidence

- Real behavior planning, independent Gatekeeper atomization, and Rack AI v2 scenario authoring crossed trust admission; scenario submissions selected and were executed by `local-primary` with matching provenance.
- REQ-001 produced an approved scenario and one accepted narrow `local-coder` change; its canonical test was retained.
- REQ-002's first scenario was rejected by independent intent review, and its second was structurally accepted but drifted to `SignalBoard.Publish` plus undocumented `payloads` behavior.
- ATHBA failed closed at `unsupported_language_boundary` after the resulting RED evidence; this is model-originated semantic drift, not a trusted-root or routing defect.
- A controlled terminal resume returned blocked (exit 2) without repeating submissions, frontiers, scenario attempts, or developer attempts.
- No ATHBA or Rack AI source, Rack AI trust policy, JCode profile, strict grammar, or execution budget was changed.
