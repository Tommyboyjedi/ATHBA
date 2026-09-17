# ATHBA reservation/work client

The current client targets the authenticated deployed `GET /runtime/v1/contract`,
contract version **1.1.0**, schema `rack-ai/runtime-contract/v1`. This replaces the
previous PR35 planning contract. `discover` retains its service-discovery meaning.
The contract was read on gpurack before implementation; the read-only snapshot is
in `evidence/reservation-work-migration/deployed-contract.json` (local evidence,
not a credential or deployment artifact).

## Transport and configuration

Set `ATHBA_RACK_AI_ORIGIN` to the authenticated runtime origin and
`ATHBA_RACK_AI_CREDENTIAL_FILE` to ATHBA's existing credential file. The inspected
gpurack origin is `http://127.0.0.1:8095`; its ATHBA credential file is
`/srv/rack-ai/deployments/idle-runtime/secrets/athba`. No credential value is stored
in ATHBA state. No production environment file or service was changed.

The durable strict-TDD composition supplies one shared RackAI session to workspace
execution and direct reasoning. Post-behavior continuation binds a session to its
existing delivery record. Explicitly injected fixture ports remain available.
Unbound production workspace composition fails closed.

The old `rack-ai/work-unit/v2` document, CLI subprocess transport, and in-memory
result/cancel cache are removed from the active workspace route. The existing
profile resolver, repository binding, path/network controls, acceptance commands,
revision handling, provenance checks, and confined evidence-packet reader remain.
The latter still requires access to the returned review packet under
`ATHBA_RACK_AI_EVIDENCE_ROOT` (default `/srv/rack-ai`); this is an existing evidence
boundary, not a raw model access route.

## Campaign lifecycle

A campaign reserves only the logical services its configured ports need, normally
`local-primary` and `local-coder`. The user-selected campaign priority is **Low**.
Existing ATHBA work profiles retain their semantic capabilities and attempt policy;
priority is sent only in `reserve`, never in `submit_work`.

The existing run/delivery JSON record contains an optional `rack_ai` field with a
campaign-derived work ID, lifecycle-specific acquisition ID, service requirements,
reservation ID, and cleanup/reconciliation markers. New lifecycles retain the persisted
campaign priority. Old records without the field
remain readable. No separate scheduler, queue, or reservation database is added.

Reserve retries reuse the persisted acquisition ID. Resume inspects the persisted
reservation first. A still-live reservation is reused; a terminal reservation gets
a new acquisition ID only when work actually needs resources again. Reserve replay
is never treated as status inspection or refresh.

Each service is checked independently. Ready peers can run while another member is
Preparing, Held, unavailable, or recovery_required. Preparing/Held are inspected;
Held is never refreshed or replaced. Unavailable triggers explicit refresh of the
same reservation, normally no more often than every 300 seconds during a wait.
Polling defaults to two seconds, bounded by a 300-second resource wait. Expiry is
RackAI authority; refresh does not extend TTL. A bound or recovery_required surfaces
`RackAiResourceWait` / strict-TDD `resource_waiting`, preserving the lifecycle for
resume rather than recording a semantic failure. No autonomous background queue is
introduced.

Direct model calls use the Ready member's model and scoped `gateway_path`. Prompts,
token/temperature settings and structured output schemas are retained (Responses
JSON schema uses `text.format`). Workspace calls use `submit_work`, `inspect_work`
and `cancel_work`. A stable campaign/submission-derived work ID is inspected first;
exact replay reconciles the original reservation and detects changed payloads,
including after a process restart. Unknown/pending work is never duplicated under
a new ID. Cancellation is an explicit remote work operation.

Completion, controlled stops, terminal failures and explicit `stop()` release the
reservation. Successful cleanup is persisted and not repeated; an uncertain release
is reconciled on resume; an inspected terminal reservation completes cleanup without
sending a duplicate release. A still-live reservation retries release. Resource waiting is resumable and retains the same
reservation. Cancellation is not silently substituted for release.

## Semantic and validation boundary

RackAI resource waiting propagates separately from model output failures. It does
not append Tester/Coder attempts, consume Planner repair/replan budgets, or create
Gatekeeper provider-failure attempts. Durable started-call markers are written after
resource readiness; waiting unwinds a racing marker without inventing model output.
Existing malformed-output, evidence, provenance, and accepted-revision checks remain.

Focused fixture tests cover lifecycle identity, partial readiness, Held/restoration,
refresh, scoped request payloads, work reconciliation/cancel, resume, semantic budgets
and release. These tests do not qualify live models or demonstrate deployment.
No RackAI source/configuration, other application, live campaign, or service is changed.
