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

The source-controlled resolver-only fixtures are separate from BPQ-V1:

- R1: SignalBoard subject, publish action, get_latest observation.
- R2: CustomerRepository subject and find_customer observation, without save or delete distractors.
- R3: ReservationBook subject and inherited mandatory update action.
- R4: no_binding_required; no audit-timestamp technical candidate may be invented.

The frozen matrix is R1-1, R2-1, R3-1, R4-1, R1-2, R2-2, R3-2, R4-2, R1-3, R2-3, R3-3, R4-3. Qualification requires 12/12 mechanically valid terminal results and 12/12 exact semantic matches.

## Pre-live verification

Before this live matrix, focused deterministic resolver tests passed (18), the full ATHBA regression passed (606), coding principles passed, resolver-specific mypy passed, compileall passed, and diff-check passed. The earlier broad mypy hang is retained as unrelated tooling evidence and was not rerun for this frozen qualification.

The branch, frozen implementation head, contract version, schema signature, and R1-R4 fixture bytes were reverified immediately before the readiness call. No production source, prompt, schema, fixture, model configuration, BPQ-V1, Tester, Developer, Behavior Planner, Rack AI, JCode, Gatekeeper, frontier, or PR21 change occurred during qualification.

## Live qualification

One direct `/v1/responses` readiness generation through the provider-neutral local-primary path returned `READY`. The configured model and every recorded semantic/repair provenance record `local-primary`; no local-coder or cloud fallback was used.

Raw prompts, provider responses, parsed results, repair exchanges, timing, and provenance are retained outside BPQ-V1 at:

`evidence/pr29_technical_binding_resolver_qualification_20260904T205500Z`

| Run | Terminal result | Mechanical | Semantic | Verdict |
| --- | --- | --- | --- | --- |
| R1-1 | resolved | PASS | PASS | Exact R1 bindings. |
| R2-1 | resolved | PASS | FAIL | `find_customer` was classified as `action`, not required `observation`. |
| R3-1 | resolved | PASS | PASS | Exact inherited R3 bindings. |
| R4-1 | protocol_failure | FAIL | FAIL | One format repair still invented `R4-audit-timestamp`, an unknown technical ref. |
| R1-2 | resolved | PASS | PASS | Exact R1 bindings. |
| R2-2 | resolved | PASS | FAIL | `find_customer` was classified as `action`, not required `observation`. |
| R3-2 | resolved | PASS | PASS | Exact inherited R3 bindings. |
| R4-2 | protocol_failure | FAIL | FAIL | One format repair still invented `R4-audit-timestamp`, an unknown technical ref. |
| R1-3 | resolved | PASS | PASS | Exact R1 bindings. |
| R2-3 | resolved | PASS | FAIL | `find_customer` was classified as `action`, not required `observation`. |
| R3-3 | resolved | PASS | PASS | Exact inherited R3 bindings. |
| R4-3 | protocol_failure | FAIL | FAIL | One format repair still invented `R4-audit-timestamp`, an unknown technical ref. |

Results: `RUNS_COMPLETED=12/12`, `MECHANICAL_PASS_COUNT=9/12`, `SEMANTIC_PASS_COUNT=6/12`, and `FORMAT_REPAIR_COUNT=3`.

## Final decision

`TECHNICAL_BINDING_RESOLVER_QUALIFIED=NO`.

The failure pattern is stable across repetitions: local-primary selected the wrong semantic role for R2 on all three attempts, and R4 attempted to invent a missing technical identifier on every semantic answer and on its permitted format-only repair. No prompt, fixture, schema, threshold, model configuration, retry policy, or implementation tuning followed these failures.
