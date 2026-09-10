# PR30 implementation and validation

The runtime follows `post_behavior_naming_refactoring_lifecycle.md`: a completed
behavioral feature and its final independent Specification Gatekeeper acceptance
are the only entry authority. The behavioral coordinator retains its existing
meaning. The post-behavior continuation reports `POST_BEHAVIOR_COMPLETE` only
after naming and refactoring have finished or refactoring has reached its
documented deterministic stop.

## Runtime components

- `post_behavior_entry.py` loads the existing feature, contract, checklist and
  completed microcycle evidence. New behavioral runs record their trusted entry
  SHA. Older records without that SHA fail closed rather than guessing a slice.
- `post_behavior_domain.py`, the state repository, journal and small transition
  handlers persist the immutable behavioral baseline, separate accepted revision,
  exact decisions, submission identities, candidate/test/Gatekeeper evidence,
  promotion results and bounded terminal reason.
- `post_behavior_slice.py` reconstructs only changed Python syntax units from
  immutable Git revisions. It refreshes the slice after each accepted change and
  excludes unrelated units in the same file.
- The two assessor adapters send the source-controlled short questions and only
  their permitted input. Naming authority comes from explicit accepted API/entity
  declarations. Refactoring sees production code only.
- `post_behavior_workspace.py` uses the existing generic workspace execution port.
  Exact paths, acceptance commands, disabled network and authorized runtime
  resources are machine-envelope fields. Model input contains only the bounded
  change and focused source, plus statically affected production/test references for naming.
  Reference updates in otherwise unchanged consumer modules are projected narrowly;
  those modules do not enter either assessor or the refactoring context.
- Python write-authority adapters verify exact symbol substitutions for naming.
  Refactoring freezes all tests, public signatures/product identifiers and
  unrelated code, while permitting private implementation changes. Public field
  annotations and explicit exports/slots remain fixed.
- `post_behavior_validation.py` runs the complete configured accepted suite in
  a detached candidate worktree. Reports bind the exact candidate and submission.
- `post_behavior_gatekeeper.py` reuses the existing routed checklist reconciler
  and durable recursive reconciliation journal. Original accepted test identities,
  requirement references and historical semantic SHAs remain in the evidence.
  Tests are rebound to a candidate SHA only after the entire preceding exact
  rename/refactor chain is mechanically verified.
- `post_behavior_git.py` promotes only a descendant accepted by both tests and
  Gatekeeper. It uses the existing trusted-project synchronizer, checks for
  independent worktree/index edits and recovers an already applied identical CAS.
- The local-only provider wrapper rejects nonlocal endpoints, fallback wrappers
  and automatic retries before invocation. It records the exact request and raw
  response/error locally. No new mutation model/worker/GPU choice is introduced.

Rejected candidates remain recorded and leave trusted state unchanged. Unknown
in-flight assessor or mutation calls require human reconciliation; they are never
silently resubmitted. Persisted test results and individual Gatekeeper checkpoints
resume without replaying accepted work. Four promoted refactors is the maximum;
duplicate/substantially repeated objectives stop earlier. Naming cannot restart
after its `NO` result.

## Entry points

Continue an existing, freshly recorded completed behavioral feature with:

```sh
PYTHONPATH=. .venv/bin/python scripts/run_post_behavior_lifecycle.py \
  --state-root /srv/ATHBA/state --project-id PROJECT \
  --reasoning-model OPERATOR_CONFIGURED_LOCAL_REASONING_ID
```

The existing provider environment supplies its configured local endpoint. The
local-only wrapper validates that configuration before any post-behavior call.
The command can be run again to resume; its persisted entry identity must match.
The disposable proof runner composes the existing behavioral runner and this
continuation without editing target production or test files itself.

Durable runtime evidence is stored under `state/post-behavior`. Evidence includes
the original accepted delivery, each local model request/result, generic workspace
request/result and execution provenance, exact regression reports and reconciliation
results. Content-addressed evidence is atomic and immutable.

## Adapter limits

The current production language adapter is Python, matching the existing strict-TDD
path. Unsupported languages, dynamic/ambiguous symbol bindings, path or Git-mode
changes and unprovable source scopes fail closed. Neither stage creates/deletes
files. Ordinary module/class declarations, methods, read-only properties and
statically bound public fields are covered. This lane does not add a quality gate,
semantic reviewer, architecture replanner or cloud fallback.

## Validation record

Final commands, results, source identities and live-proof status are recorded in
[the PR30 evidence directory](evidence/pr30-20260910/README.md) and the PR description. A deterministic fake-provider
test is not classified as a live proof.
