# ATHBA reservation/work client

The current client targets RackAI runtime contract **1.2.0** through the
authenticated `POST /runtime/v1` API, with read-only contract discovery available
at `GET /runtime/v1/contract`. RackAI source/configuration remains RackAI-owned;
ATHBA is only a durable client of the deployed reservation/work contract.

## Transport and configuration

Set `ATHBA_RACK_AI_ORIGIN` to the authenticated runtime origin and
`ATHBA_RACK_AI_CREDENTIAL_FILE` to ATHBA's existing credential file. The inspected
gpurack origin is `http://127.0.0.1:8095`; its ATHBA credential file is
`/srv/rack-ai/deployments/idle-runtime/secrets/athba`. No credential value is
stored in ATHBA state.

The durable strict-TDD composition supplies one shared RackAI reservation session
to workspace execution and direct reasoning. Post-behavior continuation binds a
session to its existing delivery record. Explicitly injected fixture ports remain
available. Unbound production workspace composition fails closed.

The old `rack-ai/work-unit/v2` document, CLI subprocess transport, and in-memory
result/cancel cache are not part of the active workspace route. Workspace calls use
RackAI `submit_work`, `inspect_work`, and `cancel_work` with the existing profile
resolver, repository binding, path/network controls, acceptance commands, revision
handling, provenance checks, and confined evidence-packet reader.

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

ATHBA keeps the stable semantic submission identity separate from RackAI execution
identity. Generation 0 preserves the historical campaign/submission-derived
RackAI work ID. Only a definitively queued, not-started invocation cancelled with
`reservation_superseded_by_higher_priority` advances the persisted RackAI
execution generation for that same semantic submission. The next retry can then
execute under a new reservation and new RackAI work ID without consuming another
Tester/Developer/Gatekeeper semantic attempt.

Transport uncertainty and RackAI `uncertain` never advance the generation and are
never automatically replayed under a new work ID. Changed payload/reservation under
an existing RackAI work ID still fails closed through RackAI identity conflict.
Completed workspace packets still validate the public RackAI `work_id`, the
RackAI-generated `change_id`, and the retained evidence packet identities.

Workspace polling treats `queued`, `running`, `waiting`, `preempting`, and
`preempted` as active/unresolved infrastructure states. Terminal `completed`,
`cancelled`, `failed`, `expired`, and `uncertain` are reconciled according to their
authoritative RackAI result/error; `accepted`, `started`, and `held` are not active
control-flow states for the v1.2 client.

## Semantic and validation boundary

RackAI resource waiting propagates separately from model output failures. It does
not append Tester/Coder attempts, consume Planner repair/replan budgets, or create
Gatekeeper provider-failure attempts. Durable started-call markers are written
after resource readiness; waiting unwinds a racing marker without inventing model
output. Existing malformed-output, evidence, provenance, and accepted-revision
checks remain.

Focused fixture tests cover atomic unavailable, atomic readiness, preempting and
preempted ownership, scoped request dispatch blocking, work reconciliation/cancel,
preempted queued work generation, transport uncertainty, changed-payload conflict,
resume, semantic budgets and release. These tests do not qualify live models or
demonstrate deployment. No RackAI source/configuration, other application, live
campaign, or service is changed.

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
