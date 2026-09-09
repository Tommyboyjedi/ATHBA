# PR28 live Rack AI v2 connector qualification

## Scope

This qualification proves only the ATHBA semantic-profile to generic Rack AI workspace-execution boundary. It does not run a strict-TDD feature, multiple scenario frontiers, or ReservationBook.

- ATHBA published base before reconciliation: `eb1231e301947277e6c4d3b031228996a02dc14f`
- Rack AI PR32 branch/head: `pr32-generic-capability-routing` / `56d2c69f1e815acd12fca9065945c5e46de5a36a`
- Rack AI wire version: `rack-ai/work-unit/v2`
- Rack AI PR: [#32](https://github.com/Tommyboyjedi/rack-ai/pull/32)
- Fixture: `/srv/ATHBA/state/projects/pr28-rack-ai-v2-connector-20260903T0845Z`
- Retained Rack AI evidence: `/srv/rack-ai/state/pr28-athba-v2-connector-20260903T0845Z`

## Connector mapping

ATHBA semantic state resolves to an `AthbaExecutionProfile`, then produces a backend-neutral `WorkspaceExecutionRequest`. Only `RackAiV2WorkspaceSerializer` turns that request into the Rack AI document. The serializer emits the v2 routing header under `work_unit.routing`:

```json
{"source_system":"athba","work_id":"opaque","submission_id":"opaque","idempotency_key":"opaque","required_capabilities":["reasoning","coding"],"priority":"medium"}
```

It emits `complexity` and `requires_large_context` under `work_unit.requirements`. It does not serialize ATHBA dependencies, stage names, concrete worker IDs, GPU IDs, model IDs, endpoints, or JCode profiles. One ATHBA submission serializes Rack AI `max_implementation_attempts: 1` so a submission remains one requested model execution.

The terminal packet translator preserves the generic candidate revision, branch, changed paths, acceptance verdict/failure, selection decision, execution provenance, and packet reference. If a v2 selection decision and execution provenance name different workers, it returns the backend-neutral fail-closed mismatch status. Historical top-level evidence without v2 selection data remains readable.

## Deterministic gate

Focused ATHBA connector/routing suite passed: `24 passed`.

It covers the exact v2 request locations; scenario, frontier Tier 1, and stronger Tier 2 profiles; opaque identity round-trips; low/medium ceiling; absent dependencies/resource-routing inputs; accepted/rejected/capability/temporary/timeout translation; evidence retention; v2 mismatch failure; historical compatibility; and deterministic fake regression.

## Real sequential qualification

The ATHBA connector invoked the Rack AI `work-unit --emit-json` CLI. Request documents were captured by the connector transport, not manually constructed.

| Proof | ATHBA profile | Selected / executed | Terminal result |
| --- | --- | --- | --- |
| A | reasoning + coding, medium, no large context, medium | `local-primary` / `local-primary` | approved; candidate `58a79efe7a46efa29222ffc6c65ecc7935cc2f68` |
| B | coding, small, no large context, low | `local-coder` / `local-coder` | approved; candidate `00aceb97b0fb6e909d1f4d06041dccecc2977474` |
| C | reasoning + coding, medium, no large context, medium | `local-primary` / `local-primary` | approved; candidate `a1557c12f27534586e86d8a0d83784052a1bbabb` |

Each result retained the Rack AI selection decision and execution provenance. The durable packet references are under `state/changes/` in the retained evidence root; ATHBA-side translated results are `a-scenario-profile-result.json`, `b-narrow-coding-result.json`, and `c-stronger-profile-result.json`. Serialized v2 requests are retained under `request-inputs/`.

## Priority and idempotency

ATHBA's domain enum remains exactly `low` and `medium`; deterministic malformed-boundary coverage rejects a higher outbound value before transport. Rack AI PR32 independently qualifies its ATHBA admission ceiling.

A replay of proof A with its identical work ID, submission ID, and idempotency key returned backend-neutral `duplicate_submission` with `generic_failure: duplicate idempotent submission`. It has no new provenance or candidate; retained evidence is `idempotency-replay-result.json`. Rack AI's persisted packet count remains three, so the replay did not create another model execution.

## Cleanup

The neutral fixture was clean before cleanup and has been removed. The three Rack AI-managed proof worktrees were removed. ATHBA source/configuration/state records were not changed by the fixture. Rack AI source was not modified. Its administrator-owned `config/repositories.json` remains an unstaged pre-existing modification.

## Remaining gate

The remaining PR23/PR28 progression gate is a real tiny strict-TDD feature; ReservationBook has not been run.
