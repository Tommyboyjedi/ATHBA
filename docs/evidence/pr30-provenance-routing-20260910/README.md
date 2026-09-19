# PR30 downstream provenance consistency

Starting reviewed head: 648fcb63bfd03c6add9fb0781e016c9dc45508c5.

The preserved run pr30-omission-running-total-20260910T114333Z completed
four behaviors but failed final Gatekeeper reconciliation on pr30-007.
Its accepted quote, "Keep the implementation ... in memory", was rejected
by a downstream exact-substring guard before the storage adapter ran.
required_source_subjects also silently omitted that required subject.

## Compatibility rule and audit

The existing resolve_source_quote implementation and bounded omission rule
are unchanged. There is no second matcher, probabilistic decision, fuzzy
matching, extra model call, or source/checklist rewriting.

SpecificationChecklistItem.source_context centralizes the existing resolver,
retained-segment subject grounding, and grounded_modality check. Atomization
and split children use this same method. Checklist reload revalidates quoted
items against original requirement_text, including persisted tampering.

EvidencePolicyRouter.route_source consumes that verified original context.
Original words such as not, expose, implement and optional therefore still
control modality, forbidden-surface routing and permitted optional scope even
when absent from the rendered quote. The stored quote remains unchanged.
The original item-level modality check is retained; this change does not add
new atomizer quote forms or remove required explicit non-goal wording.

Both final reconciliation and required-subject collection use route_source.
Invalid quoted items fail closed; they cannot silently acquire required-subject
authority. Quote-less legacy behavioral paraphrases remain supported and do not
grant required-subject authority unless grounded in source. Legacy static facts
still require source grounding and retain their inferred modality.

The recursive tree revalidates each root and persisted split child before using
cached results or deciding whether a behavioral split is appropriate. A cached
YES is not authority for invalid provenance. Split identity, revision/evidence
binding, pending-call guards and the original bounded repair remain unchanged.

PR30 PostBehaviorGatekeeper and CompletedFeatureReconciler already delegate to
the shared reload, subject collection and reconciliation tree. Their stage,
test and revision semantics require no changes. Other source_quote uses are
serialization, prompt construction, split identity and traceable engineering
record checks; none needs a second provenance matcher. Engineering record
recognition has no original source authority and is not a substitute for the
revalidation done before record creation/reuse.

Provenance only permits actual evidence assessment. Behavioral tests still reach
the existing reconciler, and in-memory/dependency obligations still reach the
real Python storage/dependency adapters. Those adapters and Rack AI are unchanged.

## Deterministic coverage

The exact recorded response is copied into a small fixture with its origin;
the historical evidence, target repository, checklist and terminal state remain
untouched. Tests exercise atomization, JSON file persistence/reload, complete
required-subject collection, five real behavioral-boundary calls and real static
adapters. Storage use and external dependencies produce NO despite valid quotes.
Additional cases cover reversed/missing/paraphrased/malformed/cross-clause quotes,
omitted/spliced/empty subjects, hidden modality qualifiers, optional scope,
forbidden public surfaces, exact/legacy behavior and persisted split cached YES.

Separate PR30 composition tests reconstruct the lifecycle after every transition
and prove both rename and refactor candidates reach the unchanged storage adapter.
Its opaque-effect rejection retains the previous trusted baseline; provenance
does not manufacture Gatekeeper YES.

## Validation and live evidence

Exact commands, source hashes, exit codes and timings are recorded in
validation.json and its logs. Fresh proof planning and outcome are recorded
separately after deterministic validation. The original requirement remains
docs/evidence/pr30-20260910/live-requirement.txt.

The historical run is not resumed or altered. The fresh proof accepts legitimate
assessor NO decisions and does not force a rename/refactor. The existing runner's
positive-path proof classification will be distinguished from lifecycle completion
if the real outcome is a no-work path.

## Final validation

Implementation and live execution revision:
77e473e0d79792ded35ecfaac08a56765c0db29a.

| Check | Result |
| --- | --- |
| Focused provenance/Gatekeeper | 229 passed, 129.24 seconds |
| PR30 focused | 169 passed, 11.66 seconds |
| Full ATHBA pytest | 1,165 passed, 621.17 seconds |
| Coding-principles gate | PASS |
| Configured mypy | PASS, 55 source files |
| Compileall | PASS |
| Git diff whitespace checks | PASS |

There are 29 added deterministic cases: 27 downstream integration cases and two
PR30 candidate-path cases. Existing tests were not weakened or removed.
The validation manifest binds exact commands, exit codes, timings and source
hashes. Code and original requirement hashes stayed unchanged through the proof.

## Fresh live result

Run/project: pr30-provenance-routing-20260910T133659Z.
The unchanged original requirement SHA256 is
f94d99e83d826442c4d70d581dd46e91ebf1dc0e580eb3182f38a5c9d02e1f78.

The single local Responses readiness probe returned READY. Live atomization
again emitted "Keep the implementation ... in memory" and accepted seven items
on its first attempt. The persisted checklist reloaded successfully, and
required-subject collection included both dependency-free and in memory.
Those checkpoints are retained in live-checklist-created.json and the original
feature snapshot.

All four behaviors completed. After 143 transitions, final reconciliation
returned YES for REQ-001 through REQ-006, including the real dependency adapter.
REQ-007 passed provenance and reached python-specification version 1 with
evidence_policy=no_storage. Its actual result was NO:

> unsupported_evidence_policy; line 15: opaque decorator effects

The generated total accessor has a property decorator. The unchanged storage
adapter treats function decorators as opaque effects and cannot establish its
bounded no-storage proof. This is an evidence-adapter limit, not a provenance
rejection or unavailable infrastructure. No adapter, requirement, checklist,
generated target, model setting or proof harness was adapted after observing it.

Terminal status/reason: blocked / specification_gatekeeper_failed.
The runner exited 2 after 920.347 seconds. One initial 300-second scenario worker
timeout recovered through the existing bounded retry; both attempts are retained.

Last canonical target revision:
0039443078c3b591be8108d386c2606f4fe8affe.
This is not a final Gatekeeper-approved behavioral baseline. Naming and refactoring
did not start; no assessor answer or POST_BEHAVIOR_COMPLETE is claimed. The
runner's raw report has null final_revision; the canonical SHA above is independently
recorded in the terminal feature/project state and verified against target HEAD.

The requested provenance compatibility is demonstrated on the real path.
The full PR30 lifecycle remains unproven live because of the distinct decorator
evidence blocker. It remains outside this correction's scope.

## Preserved evidence

live-result.json records the exact terminal classification and all seven
reconciliation outcomes. live/ contains the frozen predeclaration, full reports
and content-addressed result records. runtime-state.tar.gz preserves 27 run,
feature, scenario, microcycle, revision, project, lifecycle and referenced Rack
packet files. The manifest records their original paths and hashes, verified
against the archive contents. target-repository.bundle preserves every target
ref and passed git bundle verify; the target checkout is clean.

The earlier pr30-omission-running-total-20260910T114333Z evidence, checklist,
runtime terminal state and target are untouched. Before/after integrity manifests
match its previously recorded hashes. No old run was resumed. Original and fresh
targets received no manual code edits.
