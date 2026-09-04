# PR29 TechnicalBindingResolver qualification

## Responsibility boundary

`TechnicalBindingResolver` resolves technical bindings for exactly one already-created behavioral requirement against a bounded catalogue of supplied technical candidates. It selects no identifier outside that catalogue and classifies only `subject`, `action`, `observation`, `state`, `error`, or `other` roles. It does not create or rewrite behavior, tests, frontiers, implementations, reviews, source requirements, architecture, repository state, provider choice, or GPU selection.

The resolver uses the provider-neutral reasoning gateway, while the standalone qualification harness requires the local-only `local-primary` configuration with reasoning plus coding, medium complexity. It has one semantic request and at most one format-only repair; semantic disagreement never triggers a retry.

## Frozen contract

- Contract version: `technical-binding-resolver-v1`
- Output schema signature: `1029bba78d27efdb167b0f1029c320068c347ea4e17077dd4d9826a6e214ca4b`
- Frozen implementation head: `915fb8cf3d3ce34ce34f0bd11c223643e8192708`
- Local-only cloud fallback: disabled
- Fixture file: `tests/fixtures/technical_binding_resolver_v1.json`

The frozen source-controlled fixture catalogue contains exactly four resolver-only cases, separate from BPQ-V1:

- R1: SignalBoard subject, publish action, get_latest observation.
- R2: CustomerRepository subject and find_customer observation, without save or delete distractors.
- R3: ReservationBook subject and inherited mandatory update action.
- R4: no_binding_required; no audit-timestamp technical candidate may be invented.

The frozen matrix is R1-1, R2-1, R3-1, R4-1, R1-2, R2-2, R3-2, R4-2, R1-3, R2-3, R3-3, R4-3. Qualification requires 12/12 mechanically valid non-protocol results and 12/12 exact semantic matches.

## Pre-qualification result

No readiness generation or semantic resolution was started. Focused deterministic tests passed (18), the full ATHBA regression passed (606), coding principles passed, explicit resolver mypy passed, and compileall passed before the attempted configured mypy gate.

The repository-configured mypy invocation emitted no output for several minutes. A single bounded 120-second retry also failed to terminate cleanly and was interrupted. Under the frozen pre-live rule, this blocks model readiness and the 12-run matrix rather than allowing a live run with an incomplete validation gate.

| Run | Result |
| --- | --- |
| R1-1 through R4-3 | NOT STARTED: configured mypy blocker |

Final decision: `TECHNICAL_BINDING_RESOLVER_QUALIFIED=NO`. This is a pre-qualification infrastructure blocker, not a semantic qualification failure and not evidence about local-primary. Raw pre-qualification evidence is retained outside BPQ-V1 at `evidence/pr29_technical_binding_resolver_prequalification_20260904T200000Z/prequalification-summary.json`.
