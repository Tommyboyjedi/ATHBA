# Rack AI priority reservations — ATHBA companion

Date: 2026-09-13. Status: **implementation contract; documentation only at creation**.

Core dependency: [Rack AI PR35](https://github.com/Tommyboyjedi/rack-ai/pull/35), contract `docs/priority-runtime-reservations.md` on `design/priority-runtime-reservations`.

This PR is stacked on the active [ATHBA PR30](https://github.com/Tommyboyjedi/ATHBA/pull/30) branch `design/post-behavior-naming-refactoring`, reviewed head `3877371da8de79b1a97747179067a2f9fa8cd593`. That branch already contains the PR28 generic-execution implementation line. Do not base this integration on the older `master` tree, merge/close the existing stack, reset the live checkout, or restore withdrawn structural-refactoring/PR21 behavior. Retarget only after verified incorporation of the parent history.

## 1. Scope and preserved boundary

ATHBA remains the complete owner of software-development semantics: readiness, dependencies, attempts, stage mapping, repair/escalation, TDD, naming/refactoring, acceptance interpretation and trusted revision progression. Rack AI owns physical model/runtime/resource selection, priority admission, access gating, lifecycle, generic execution and evidence.

This change updates the replaceable workspace/reasoning connectors and necessary durable infrastructure-wait handling so the application cooperates with priority reservations. It does not redesign the development engine, change model prompts, loosen tool profiles, repair a historical live feature failure, rerun a product build, or grant Rack AI software-development knowledge.

Read `AGENTS.md`, `agent.MD`, `coding_principles.MD`, `docs/athba_rack_ai_workspace_boundary_rationale.md`, current PR30 rules and the core contract before implementation.

## 2. Reviewed gaps

`core/execution/rack_ai_workspace_connector.py` already rejects outbound priorities above Medium and serializes a `rack-ai/work-unit/v2` routing header. Preserve those protections. Its current result lookup is an in-memory dictionary and `cancel()` removes a local cache item; that is not durable remote reservation/status/cancellation support.

`core/execution/provider_reasoning_gateway.py` delegates directly to a configured provider. Local reasoning therefore needs an explicit managed Rack AI adapter, not the assumption that the workspace connector already governs every model call. Trace actual provider composition, Responses/Chat usage, local-only guards and live startup configuration before claiming full coverage or changing deployment.

Relevant starting points include `core/execution/{workspace_execution_port,rack_ai_workspace_connector,rack_ai_workspace_cli_transport,profiled_workspace_gateway,reasoning_gateway,provider_reasoning_gateway,local_only_post_behavior_reasoning}.py`, `core/development/athba_workspace_routing.py`, and their caller/persistence/tests. Preserve existing invocation/evidence and local-only restrictions.

## 3. Priority and logical requests

ATHBA emits **only Low or Medium**. Retain current operation-to-priority mappings rather than globally downgrading existing Medium tasks or upgrading Low tasks. Make mappings typed, validated configuration at ATHBA's internal profile-resolver boundary. Reject High/Paramount locally and independently at Rack AI admission.

An authorized request for the logical service alias `big-brain` uses Medium. Model size, being blocked, elapsed time or exhausting an internal model tier never grants High/Paramount. Stronger local reasoning is not a priority escalation. Requests to other applications' Paramount sessions cannot be borrowed or impersonated.

PR35 explicitly permits Rack-AI-published logical aliases while retaining internal concrete selection. Update the relevant ATHBA agent/boundary documents for this narrow amendment: a logical service alias is allowed; concrete model IDs, host backend names, GPU IDs, endpoint overrides, artifact paths and JCode profiles remain forbidden client routing fields. Existing broad-capability requests remain supported. Capabilities, complexity, context and limits must still be checked even when a tag is supplied.

Keep the choice to request stronger reasoning inside ATHBA's existing authorized stage/escalation configuration, not inside Rack AI. Do not silently redirect all reasoning to the largest model or alter four-attempt/TDD policies merely to exercise the feature.

## 4. Separate independent demand from workflow dependencies

The normal primary and coder represent independent access/reservation needs, not a single indivisible two-GPU reservation. ATHBA sends logical demand; only Rack AI knows their physical placements.

When the primary is preempted, persist only its affected request/reservation as held. Unrelated already-ready coder work remains dispatchable. This does not authorize parallel conflicting mutations of the same repository, dispatch of a semantic dependency that is not ready, or a new client scheduling engine. Existing readiness/trusted-revision rules remain authoritative.

When Rack AI restores the primary, resume valid not-yet-started work using its existing accepted identities and the unchanged required revision. If the project's canonical revision changed during the hold, do not execute/promote a stale mutation: follow existing ATHBA invalidation/replanning rules and create any necessary new semantic submission explicitly.

## 5. Durable states, denial and attempt accounting

Use typed connector/domain outcomes and persist remote request/reservation identity, generation/version, priority, hold/denial reason, deadlines and invocation evidence. Consume PR35's exact frozen schema/fixtures rather than inventing application-specific states in Rack AI.

Distinguish at least:

- `reservation_denied`: a new request lost to an equal/higher incumbent; no reservation or model invocation was admitted;
- preparing/starting: a granted transition is in progress;
- held/preempted: previously accepted demand is suspended, not semantically failed;
- running/completed: supported by actual invocation/result evidence;
- interrupted/uncertain: work may have started and cannot be blindly replayed;
- cancelled/expired/recovery-required/capability-unavailable: explicit separate meanings.

A priority denial or time spent held with proof of no invocation does not consume a Tester/Developer/reasoning attempt. Do not classify it as a bad model result or trigger stronger/paid fallback. Once invocation actually began, retain that fact; ATHBA alone applies the existing attempt policy. Unknown execution is not proof of zero calls.

A replay of a definitive denial retrieves the same denial. A later acquisition retry has a new reservation-request identity linked to the same logical work; admission retries do not manufacture semantic attempts. A retry after a possibly accepted request instead reconciles the same identity. Previously accepted, not-started held work is resumed, not submitted again under a fresh model-invocation ID.

Replace cache-only lookup/cancel behavior on the production path with durable remote status/result/cancel handling. Cancellation must be persisted and acknowledged/reconciled remotely; deleting a Python dictionary entry is not cancellation. Restart the application/adapter while held or starting without losing ownership, duplicating dispatch or resurrecting cancelled work. Bound polling/backoff and resource-wait deadlines separately from model-execution timeouts; do not spend the execution timeout entirely on a hold or hold an HTTP/shell call indefinitely.

Do not silently change the existing v1/v2 wire meanings. Implement new reservation-enabled operations through PR35's versioned contract and explicit capability/version negotiation. Keep historical stored requests/results readable and distinguish unavailable protocol support from model failure.

## 6. Managed reasoning and no bypass

Add a Rack AI implementation behind the existing provider-neutral ReasoningGateway boundary for local reasoning, including configured big-brain use. Preserve the actual protocols required by callers, structured-output parsing, bounded tokens/context/time, cancellation and evidence. Adding only a workspace priority field leaves direct local reasoning outside the scheduler and is insufficient.

Normal production access must use Rack AI's gated managed route or its qualified compatibility facade. ATHBA must not reach raw vLLM/llama.cpp services after cutover, restart those services, alter CUDA visibility, select a GPU, manipulate reservation files or install hosting software. Read-only connection checks do not activate a model.

Preserve explicitly controlled pre-execution cloud design options where applicable and all current post-seal/local-only guards. This PR adds no cloud fallback or new paid provider calls. A busy/unqualified big-brain leaves a truthful held/denied/capability result, not an external bill. Keep deterministic fake providers for development/tests.

## 7. Tests and implementation order

Freeze the core Rack AI schemas first; implement this companion on its own branch/worktree. For a coordinated authorized task, cross-repository edits are limited to each named PR's adapter responsibilities; this is not permission to fix ATHBA semantics from Rack AI or vice versa.

Required tests:

1. Existing Low/Medium mappings preserved; outbound High/Paramount rejected; big-brain remains Medium; server also rejects forged priority/source.
2. Primary held while genuinely independent coder work continues, without bypassing semantic readiness or repository write serialization.
3. Denial/hold with no invocation consumes no semantic attempts; a started/interrupted invocation has truthful evidence and no hidden rerun.
4. Application/adapter restart during hold/start/uncertain submission; stable identity, remote reconciliation and cancel; no late revision promotion.
5. Primary restoration resumes eligible pending work; expired/cancelled or revision-stale work does not restart incorrectly.
6. A new denied big-brain acquisition does not stop coder work; a deliberate later retry differs from replay of unknown outcome.
7. Real workspace and reasoning transports traverse the candidate Rack AI authority using fake models/GPUs; both respect the gate. Fake-only domain tests are not end-to-end proof.
8. Existing selection/provenance, accepted-revision, TDD, Gatekeeper, naming/refactoring, local-only and bounded-attempt regressions continue passing.

Use disposable worktrees, project identities, database/state and no-cost fake model services. Run coding-principles, applicable configured typing/compile checks, focused tests, full applicable tests and whitespace review. Preserve historical evidence unchanged. No live product run or prompt/model retuning merely to demonstrate the connector.

## 8. Deployment and handoff

The inspected branch is source evidence, not proof of the currently running configuration. Prepare a read-only inventory of actual local reasoning/workspace routes and the exact deployed SHA. Coordinate compatibility/cutover with Rack AI PR35 before global preemption is enabled.

No changes to live `/srv/ATHBA`, canonical project repositories, environments, durable run history or production services until a migration/rollback plan has been reported and the operator separately authorizes the window. No production database migration, lost-state reset, published-history rewrite or automatic merge.

Report `CODE_COMPLETE`, `CONTRACT_FIXTURES_COMPATIBLE`, `WORKSPACE_ROUTE_GATED`, `LOCAL_REASONING_ROUTE_GATED`, `HOLD_RESUME_FIXTURE_PASSED`, `LIVE_QUALIFIED` and `PRODUCTION_DEPLOYED` separately. Include exact tests, PR/SHAs, evidence, preserved attempt/revision invariants, remaining client cutover steps and precise blockers. A planning PR or mocked connector is not a working production priority integration.
