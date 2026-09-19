# PR29 TechnicalBindingResolver v2 qualification

## Scope and freeze

`technical-binding-resolver-v2` is an isolated two-stage resolver. Stage 1 answers applicability without selecting technical refs; Stage 2 runs only after `binding_required` and may select only supplied refs. It has no Behavior Planner, Tester, Developer, TDD/frontier, static-lint, Gatekeeper, Rack AI, JCode, PR21, or Observation Resolver integration.

The v1 resolver and its qualification record remain historical failed evidence at `f00e48318612dccf3880e25d97ba26c2b3edf70a`; its fixture SHA-256 remained `c05aa8904f2bedcc2492bb5036a568043b7535f679f570f82882cd430e976e9c`. BPQ-V1 was unchanged at SHA-256 `3b1c2deec2369d5edc7dba79af76b5c90ea3a9b7f70b895f78237c1184300352`.

Implementation was frozen before readiness and R1-1 at `a19c09803474b4ad2d3a17fbcac08b309be3b01d`.

- Stage 1 schema signature: `1ade6aba4c9c35eeffedf8d62f9ee3156a22ff94f7a0ca43aee3cb1fb3f59a13c`
- Stage 2 schema signature: `677c785f9a618d4e6948070c2a397d85142654f8d5c99e9a9ee182ed66a21425b`
- Frozen qualification contract signature: `4012ceb7c694b5d203ce347f5673f85dc4ee7f2228941e4d53c081aa114a26361`
- Local configuration: local-primary only; reasoning plus coding; medium complexity; no cloud fallback; one semantic request and at most one format-only repair per stage.

## Deterministic validation

Focused v1/v2 resolver tests passed: `36 passed`. The complete repository suite passed: `624 passed`. Coding-principles, mypy for the four v2 files, compileall, and `git diff --check` passed before the freeze.

## Live qualification result

The one readiness generation returned `READY` from `local-primary`. The frozen 12-case matrix was run exactly once. Evidence, including prompts, raw provider responses, repair responses, parsed outputs, validation, timing, and provenance, is retained under:

`/srv/ATHBA/evidence/technical-binding-resolver-v2-20260904T213248Z`

| Result | Count |
| --- | ---: |
| Terminal records | 12/12 |
| Mechanically valid | 6/12 |
| Semantically passing | 0/12 |
| Stage 1 format repairs | 6 |
| Stage 2 format repairs | 0 |
| Stage 2 calls | 6 |

`TECHNICAL_BINDING_RESOLVER_V2_QUALIFIED=NO`.

The failures were stable across all three repetitions of each fixture:

- R1 returned `binding_required`, but used technical refs (`R1-publish`, `R1-get-latest`) as evidence refs. The one permitted format-only repair preserved the invalid output, yielding `protocol_failure`; Stage 2 did not run.
- R2 was mechanically valid but selected only `R2-find-customer`, omitting required `R2-customer-repository`.
- R3 was mechanically valid but selected only `R3-update`, omitting required `R3-reservation-book`.
- R4 returned `binding_required` instead of `no_binding_required` and used `R4-approve` as an evidence ref. Its one repair preserved the invalid output, yielding `protocol_failure`; Stage 2 did not run.

No prompt, schema, fixture, model, route, timeout, or implementation change was made after R1-1. No cases were rerun, and no downstream integration was added.
