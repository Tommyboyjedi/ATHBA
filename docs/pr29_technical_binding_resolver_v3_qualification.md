# PR29 TechnicalBindingResolver v3 qualification

## Scope and freeze

`technical-binding-resolver-v3` performs one isolated semantic operation: select a subset of supplied technical refs for one behavior. Its output is exactly `behavior_ref` and `selected_refs`; empty selection is valid. The resolver has no status, roles, rationale, evidence refs, provenance, source clauses, or second semantic stage.

Selected member refs can be expanded mechanically to their qualified owner identifiers. This is generic deterministic post-processing, not a model call and not a second method selection.

V1 and v2 remain intact failed historical evidence. V2 documentation remains at `docs/pr29_technical_binding_resolver_v2_qualification.md`; BPQ-V1 remained SHA-256 `3b1c2deec2369d5edc7dba79af76b5c90ea3a9b7f70b895f78237c1184300352`.

The implementation was frozen before readiness and R1-1 at `d3c2de741e1944d94e5a7411906dcd07a7507025`.

- Schema signature: `0e9887d192069af173f9c1bd877dfa1ebbbe67757640cc3b063660f977f04e709`
- Qualification-contract signature: `52665cea4a8cc7ae5481195bd32df885147321a9fa0225aab395f1ddff922a382`
- Model configuration: local-primary only, reasoning plus coding, medium complexity, no cloud fallback, one semantic request, and at most one format-only repair.

## Deterministic validation

Focused resolver tests passed: `49 passed`. This includes valid single, multiple, and empty selections; unknown/duplicate refs; mandatory omission; behavior mismatch; one-repair maximum; no semantic retry; generic owner expansion; v1/v2/BPQ-V1 preservation; and no downstream or Observation Resolver integration.

Configured mypy passed (`29 source files`), resolver-specific mypy passed, compileall passed, and `git diff --check` passed. The coding-principles checker reported no v3 issue; its only output was the pre-existing v2 `_call_stage` size note. Full ATHBA regression passed: `637 passed`.

## Live qualification result

One bounded readiness response returned `READY` from `local-primary`. The frozen 12-case matrix ran exactly once. Raw prompts, responses, parsed results, deterministic validation, timings, and provenance are preserved at:

`/srv/ATHBA/evidence/technical-binding-resolver-v3-20260904T215432Z`

| Result | Count |
| --- | ---: |
| Terminal records | 12/12 |
| Mechanically valid | 12/12 |
| Semantically exact | 9/12 |
| Format repairs | 0 |

`TECHNICAL_BINDING_RESOLVER_V3_QUALIFIED=NO`.

R1, R2, and R3 were exactly correct in all three repetitions. R4 failed identically in all three repetitions: although the required selection was empty, local-primary returned both supplied refs, `R4-approve` and `R4-reject`. The output was structurally valid, so no repair was permitted or used.

No source, prompt, schema, fixture, model, routing, context, timeout, retry policy, or downstream integration changed after R1-1. No matrix case was rerun. This is preserved as final evidence that the empty-subset distinction remains unreliable for this local-primary role.
