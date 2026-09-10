# Inter-behaviour Structural Refactoring

During incremental behavioural TDD, previously accepted behaviour is protected,
but implementation structure is allowed to evolve when a later behaviour exposes
a structural incompatibility.

Structural refactoring and behavioural implementation are intentionally assigned
to different model work units so small models receive one narrow reasoning
responsibility at a time.

This is an ATHBA development recovery lane. It is separate from the completed
delivery quality process in [PR30](post_behavior_naming_refactoring_lifecycle.md).

## Lifecycle

Tester -> Intent Review -> frontier execution has three distinct outcomes:

- Ordinary supported RED goes to the normal Developer.
- Proven structural incompatibility enters Structural Refactorer recovery.
- Unsupported language/runtime evidence remains blocked.

The generic boundary outcome is `structural_refactor_required`. Its normalized
authority records one description, a production path, a bounded source scope and
a subject. Generic state and recovery contain no language syntax or exception
recognition rules. Each language adapter owns recognition, focused source
selection and candidate scope verification.

The current Python probe proves a direct failed call of a non-callable data
member on an actual production instance. It binds the executing call instruction
and source span to the test frame and the owner to the declared production module.
It refuses descriptors, custom attribute lookup, inherited/opaque class effects,
exceptions originating inside production calls and unrelated runtime failures.
Neither exception wording nor a RunningTotal identifier triggers the route.

## Narrow work and authority

The runtime instruction is:

> You are the Structural Refactorer. Refactor the existing production code only
> enough to resolve the structural incompatibility described below. Preserve all
> previously accepted behaviour. Do not implement unrelated behaviour, redesign
> the application, edit tests, or perform general cleanup.

Its payload contains only focused production and one normalized structural
problem. The Python focus includes the affected class header and members that
reference the colliding subject, excluding unrelated members. No specification,
Behavior Contract, future frontier assertion, Gatekeeper material, architecture,
coding-principles prose, transcripts or history is supplied. Environment context
resources are omitted. Tests are never writable.

Generic structural authority permits changes needed to resolve that one problem;
it does not freeze internal representation or public call shape. The current
Python collision proof conservatively verifies relocation of the colliding state
and a thin callable accessor while preserving existing method logic under that
relocation. The accessor may return the relocated state or call an existing
equivalent getter. Unrelated logic, new behaviour, test edits and changes outside
the supplied production path are rejected. Transformations this adapter cannot
prove are rejected; this bounded implementation does not claim general program
equivalence or impose its Python rules on another language adapter.

## Candidate safety and continuation

Each attempt starts from the trusted passing prefix, not a previous failed
candidate. The generic workspace acceptance commands run the accepted suite and
protected prior nodes against that prefix. ATHBA independently runs all protected
prior tests, the passing prefix and the accepted suite against every returned
candidate; an exact Git comparison protects test contents and paths, and the
adapter checks the single structural scope.

A regression failure or out-of-scope change rejects the candidate. Otherwise
ATHBA reruns the current blocked frontier. Ordinary RED or GREEN makes the
candidate eligible for promotion. A remaining structural or unsupported boundary
rejects it. The original observation is retained.

Promotion updates the managed working ref and canonical trusted base through the
existing revision lifecycle. Normal frontier observation then resumes:
ordinary RED goes to Developer; GREEN goes through regression, canonical
promotion, frontier/scenario completion and normal review. Structural GREEN is
accepted without damaging the implementation to manufacture RED.

## Bounds and durable evidence

Default policy: four model submissions per frontier, 300 seconds per submission.
Each is a separate opaque work identity with one backend model attempt. Failed
candidates never become the next base. There is no escalating conversation,
additional requirement consumption or automatic model repair transcript.

The existing atomic microcycle store persists the original frontier and
observation, normalized problem, trusted base, unique attempt, returned candidate,
accepted-test results, current rerun observation, rejection/promotion and return
to normal TDD. Per-attempt evidence retains serialized regression and boundary
records even when a later attempt starts.

Transitions are explicit: pending -> started -> validating -> rerun -> promoting
-> promoted, or rejected -> next bounded attempt. Persist `started` before
submission and the candidate before validation. Unknown in-flight submissions
block with `structural_refactor_interrupted_submission`; they are never submitted
again. Deterministic validation/rerun can resume. A checkpoint after ref promotion
but before final microcycle save resumes promotion idempotently and never repeats
the model call. Exhaustion reports `structural_refactor_attempts_exhausted`.

## PR30 remains ordered

All behaviours complete -> final Specification Gatekeeper YES -> Naming
reconciliation -> post-behaviour Refactoring -> POST_BEHAVIOR_COMPLETE.

The inter-behaviour lane does not run a Refactor Assessor or Gatekeeper, and does
not replace or weaken those later gates. Post-behaviour refactoring still improves
finished implementation quality only after the final behavioural seal.

Rack AI sees the existing generic workspace envelope: opaque identifiers,
production-only paths, exact base, coding/small/low capability request, bounded
timeout, network policy, acceptance commands and an opaque objective. Stage
semantics remain in ATHBA. No Rack AI source or configuration changes are needed.
