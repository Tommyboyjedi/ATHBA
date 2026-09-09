# PR23 Latch intent-review-boundary live proof

## Revisions and boundaries

- ATHBA generic intent boundary correction: `10ae48846b347de9e6c2b04622b9acee3031161d`.
- ATHBA generic empty-candidate correction: `ce8b9a886a395b450b859ecd6e3859318f76e053`.
- Rack AI inspection reference: `de6b8f441038e24120bca382135a1a84703611f9` on
  `pr-worker-execution-provenance`.
- Legacy remained `8334f42a8865b9360972f5e0422a8f61d02dedb6`.
- Rack AI source and its administrator-owned `config/repositories.json` change
  were not modified.

## Historical correction and deterministic validation

`docs/pr23_latch_intent_protocol_forensics.md` establishes that historical
Latch attempt three was structurally accepted before an unretained malformed
intent response was misrouted as `candidate_invalid`. The first correction
persists typed intent-review protocol facts, accepts only raw JSON or exactly
one ordinary JSON fence, makes one bounded repair request, and blocks without
another Tester call if both responses fail. Its full validation passed `488`
tests in `142.87s`.

A first fresh project, `pr23-live-latch-intent-boundary-20260902T143158Z`, then
exposed a generic ATHBA defect: an accepted candidate with an empty test source
raised a domain constructor error before the adapter could emit its typed
`no_test` structural assessment. The run was stopped with durable evidence and
is contaminated. Commit `ce8b9a8` allows an empty submitted source to reach the
strict adapter as a typed structural candidate failure. Its non-Latch regression
and full validation passed `489` tests in `143.32s`. This correction did not
change the four-attempt cap, strict Python grammar, execution budgets, model
routing, or canonical base behavior.

## Terminal brand-new live proof

- Project: `pr23-live-latch-intent-boundary-20260902T143909Z`.
- Run: `pr23-live-latch-intent-boundary-20260902T143909Z-run`.
- tmux session: `pr23-latch-intent-boundary-20260902T143909Z`.
- Durable log: `state/live-logs/pr23-latch-intent-boundary-20260902T143909Z.log`.
- Requirement, production path, and test path were exactly the requested
  in-memory Latch, `latch.py`, and `tests/test_latch.py`.

The real local-primary planning/gatekeeper path created the fresh project and
selected `REQ-001`. ATHBA submitted one real Tester work unit through Rack AI;
its packet records `worker_id=local-coder`, `provider_profile=local-coder`, and
`model=local-coder`. Rack AI's real worker then terminated before producing a
candidate because the worker attempted the `grep` tool while the immutable
`minimal` tool profile reported `Tool 'grep' is not allowed`.

The persisted attempt is `candidate_rejected`, has no candidate revision or
source, and the bounded route stops with `attempts_exhausted` rather than
inventing a repair parent. This is a Rack AI execution-policy/tool-profile
blocker. It is not a candidate structural failure, semantic intent failure,
intent-review protocol failure, local-coder capability exhaustion, or an ATHBA
harness defect. No second Tester packet, intent-review request, Developer work,
frontier, checkpoint, resume, reconciliation, or target pytest was reached.

## Terminal classification

`RACK_AI_EXECUTION_POLICY_BLOCKER`: **FAIL CLOSED**. The evidence is retained;
Rack AI was not modified and no replacement run is authorized without an
external Rack AI policy change. The final ATHBA source validation follows this
terminal record and is committed separately.

## Later audit clarification

The preserved run contained one actual Tester submission and produced no candidate. It did not prove four-attempt exhaustion. The later audit classified the grep event as TOOL_NOT_ADVERTISED_MODEL_CALLED; no grep or tool-policy change was made merely to advance the proof.
