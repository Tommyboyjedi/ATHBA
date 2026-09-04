# PR29 technical-decision propagation contract

## Phase 1 boundary

Technical specificity is allowed above the Tester and Developer layers. A binding technical decision is an explicit typed `TechnicalDecision` record in a `BehaviorContract`; an identifier mentioned in a summary, observable outcome, test hint, non-goal, completion criterion, rationale, or other ordinary prose has no binding authority and is never extracted heuristically.

A source-mandated identifier carries an exact source excerpt that is a literal substring of the authoritative requirement source and source-clause references that resolve inside the contract. Future architecture or design layers may carry decisions with opaque upstream provenance. The Behavior Planner may later create a binding decision where a higher layer did not fix one. These provenance categories remain explicit so a Planner-created name is never represented as a source-mandated name.

Lower layers may add detail when no binding decision exists, but cannot silently contradict a binding decision. The Planner will later associate decisions with micro-behaviors using focused semantic roles. TDD will later receive only the decisions relevant to its active frontier; no full component or application technical dump belongs in tiny Tester or Developer jobs. Static machinery should later transport or enforce those decisions, rather than asking new LLM calls to rediscover them.

Gatekeeper remains independent. Source-mandated identifiers must eventually be independently visible from authoritative source material, while Planner-created decisions must never be supplied to Gatekeeper as original specification. Capturing raw provider-response evidence is a separate supporting task.

## Deliberately unchanged in Phase 1

The current `public_api` whitelist, static lint, runtime behavior, frontier generation, RED classification, Tester and Developer prompts, Intent Review, Gatekeeper runtime, retry budgets, timeouts, BPQ-V1, and all behavior-planner qualification inputs remain unchanged. BPQ-V1 is permanent, immutable, and unsupersedable. Phase 1 persists and validates optional typed structures only; it neither requests them from an LLM nor applies them during execution.
