# ATHBA reservation/work client

The current client targets RackAI runtime contract **1.4.0** through the
authenticated `POST /runtime/v1` API, with read-only contract discovery available
at `GET /runtime/v1/contract`. RackAI source/configuration remains RackAI-owned;
ATHBA is only a durable client of the deployed reservation/work contract.

## Transport and configuration

Set `ATHBA_RACK_AI_ORIGIN` to the authenticated runtime origin and
`ATHBA_RACK_AI_CREDENTIAL_FILE` to ATHBA's existing credential file. The inspected
gpurack origin is `http://127.0.0.1:8095`; its ATHBA credential file is
`/srv/rack-ai/deployments/idle-runtime/secrets/athba`. No credential value is
stored in ATHBA state.

The durable strict-TDD and post-behavior compositions bind RackAI reservations
for public scoped reasoning and public workspace work. Workspace mutation uses
the RackAI public work-execution contract: submit work, inspect work execution,
retrieve owner-checked opaque artifacts, and cancel work. ATHBA does not read
RackAI packets, worktrees, repository files, recovery analyses, process state,
GPU state, or private logs. Explicitly injected fixture ports remain available
for deterministic tests.

The old `rack-ai/work-unit/v2` document, CLI subprocess transport, private
review-packet reader, confined evidence-packet reader, worker provenance mapper,
and direct RackAI checkout/state inspection are not part of the active route.
ATHBA keeps public authentication, reservation, scoped model access, discovery,
service-limit persistence, cancellation/release, and reconciliation state for its
own pending scoped calls.

## Campaign lifecycle

ATHBA campaign reservations use **Low** priority. Priority is sent only on
`reserve`; it is never sent on `submit_work`, and ATHBA does not request High or
Paramount. If an old persisted state contains another permitted development
priority, the next acquisition is normalized back to Low.

The existing run/delivery JSON record contains an optional `rack_ai` field with a
campaign-derived work ID, lifecycle acquisition ID, service requirements,
reservation ID, release/reconciliation markers, whether full readiness has ever
been observed, and per-workspace-submission execution generations. Old records
without the newer fields remain readable. No scheduler, queue, or separate
reservation database is added.

A multi-service `reserve` is treated as one atomic acquisition. If RackAI returns
an initial aggregate `unavailable`, ATHBA keeps its logical campaign/acquisition
intent but does **not** persist or inspect the synthetic `unavailable-*`
reservation ID. The campaign remains in resource wait, no semantic attempt is
consumed, and a later bounded retry makes another explicit `reserve` attempt.
`refresh_reservation` is not part of active PR31 acquisition control flow.

For a persisted multi-service reservation, ATHBA does not expose any newly
requested member as usable until the authoritative reservation view has reached
aggregate `ready` and every requested service is `ready`. After that readiness has
been observed, unaffected Ready peers may continue to run while another service in
the same older reservation becomes `preempting` and then terminal `preempted`.

`preempting` is non-dispatchable for the affected service. `preempted`,
`released`, `cancelled`, and `expired` are terminal ownership states. RackAI does
not restore preempted ownership; if ATHBA still needs the resource and there is no
unresolved workspace or scoped inference, ATHBA explicitly releases/replaces the
old lifecycle and creates a new acquisition. Pending workspace reconciliation or
an unresolved scoped inference blocks replacement.

Direct model calls use the Ready member's model and scoped `gateway_path`. Prompts,
token/temperature settings and structured output schemas are retained. A scoped
transport uncertainty keeps the original idempotency key pending and prevents a
new call through a different reservation until authoritative reconciliation clears
that uncertainty.

## Workspace work identity

Historical run records may contain RackAI workspace execution generations,
`pending_workspace`, evidence locations, worktree paths, or worker provenance.
ATHBA preserves those records for audit compatibility, but active production code
no longer interprets or refreshes them through RackAI private storage.

New default workspace submissions create stable public RackAI work identities
under the active reservation and persist only ATHBA-owned submission, inspection,
and artifact snapshots. The workspace payload contains generic requirements
(`complexity` and `requires_large_context`) and public repository/acceptance
data; it does not send token limits, model-specific limits, RackAI private paths,
or JCode-specific controls. Pending public work remains a resource wait until
RackAI publishes a safe authoritative outcome. Known safe execution timeouts
become failed TDD attempts; transport uncertainty remains external infrastructure
state rather than a model-originated failure.

## Semantic and validation boundary

RackAI resource waiting propagates separately from model output failures. It does
not append Tester/Coder attempts, consume Planner repair/replan budgets, or create
Gatekeeper provider-failure attempts. Durable started-call markers are written
after resource readiness; waiting unwinds a racing marker without inventing model
output. Existing malformed-output, evidence, provenance, and accepted-revision
checks remain.

Focused fixture tests cover atomic unavailable, atomic readiness, preempting and
preempted ownership, scoped request dispatch blocking, scoped transport
uncertainty, resume, semantic budgets, release, and private-boundary tripwires.
The boundary tests assert that deleted private adapters are not importable, active
composition does not inspect `/srv/rack-ai`, private paths are not read, and
private worktree/provenance data from a port result is not persisted. These tests
do not qualify live models or demonstrate deployment. No RackAI source/configuration,
other application, live campaign, or service is changed.

## Scoped transport diagnostics

Scoped HTTP failures emit `scoped_transport_failure` JSON through Python logging,
so normal runner stderr/log capture retains the status, bounded sanitized body
(2,048 characters), content type, allowlisted correlation headers, service,
redacted gateway path, call/transition identity and existing retry disposition.
Bearer credentials and the scoped URL capability are redacted. Request prompts
and arbitrary request/response headers are not logged.

This is evidence only: retry counts, same-ID replay, pending-inference handling,
resource-wait classification and semantic attempt accounting remain unchanged.
`remote_execution_uncertain` describes the client's conservative retained pending
marker; it is not proof that a remote invocation exists. A status alone must not
be used to clear that marker: gateway conflicts can also describe uncertain or
previously accepted work. Authoritative rejection/reconciliation evidence is
needed to distinguish those cases.
