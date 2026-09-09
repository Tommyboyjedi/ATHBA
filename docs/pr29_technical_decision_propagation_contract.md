# PR29 technical-decision propagation contract

> Historical evidence only. As of `pr29-live-tiny-strict-tdd-v2-proof` cleanup, the typed TechnicalDecision/TechnicalBinding pipeline, resolver implementations, qualification harnesses, and public-api name authority are removed from active behavioral development. This document records the superseded experiment; it is not an active architecture contract.

## Phase 1 boundary

Technical specificity is allowed above the Tester and Developer layers. A binding technical decision is an explicit typed `TechnicalDecision` record in a `BehaviorContract`; an identifier mentioned in a summary, observable outcome, test hint, non-goal, completion criterion, rationale, or other ordinary prose has no binding authority and is never extracted heuristically.

A source-mandated identifier carries an exact source excerpt that is a literal substring of the authoritative requirement source and source-clause references that resolve inside the contract. Future architecture or design layers may carry decisions with opaque upstream provenance. The Behavior Planner may later create a binding decision where a higher layer did not fix one. These provenance categories remain explicit so a Planner-created name is never represented as a source-mandated name.

Lower layers may add detail when no binding decision exists, but cannot silently contradict a binding decision. The Planner will later associate decisions with micro-behaviors using focused semantic roles. TDD will later receive only the decisions relevant to its active frontier; no full component or application technical dump belongs in tiny Tester or Developer jobs. Static machinery should later transport or enforce those decisions, rather than asking new LLM calls to rediscover them.

Gatekeeper remains independent. Source-mandated identifiers must eventually be independently visible from authoritative source material, while Planner-created decisions must never be supplied to Gatekeeper as original specification. Capturing raw provider-response evidence is a separate supporting task.

## Deliberately unchanged in Phase 1

The current `public_api` whitelist, static lint, runtime behavior, frontier generation, RED classification, Tester and Developer prompts, Intent Review, Gatekeeper runtime, retry budgets, timeouts, BPQ-V1, and all behavior-planner qualification inputs remain unchanged. BPQ-V1 is permanent, immutable, and unsupersedable. Phase 1 persists and validates optional typed structures only; it neither requests them from an LLM nor applies them during execution.

## Phase 2A Planner contract

The Behavior Contract Planner is now the producer and join point for typed technical decisions. Its frozen source-controlled identity is `technical-decisions-v1`, with canonical required-output-schema SHA-256 `f601e38508a568ddbad10037a3f512120c3f17b87bd9fa9f4074b7a670ce016a`.

A `source_requirement` decision preserves an exact source excerpt and valid source-clause references. A `behavior_planner` decision is a Planner-created technical choice and has no source excerpt. The current Planner never emits `upstream_design`, because it receives no typed upstream-design decisions. Every decision is bound only to the observable behavior(s) where it is relevant; each `public_api` entry is backed by an explicit typed decision, using exact qualified or leaf-identifier matching only.

The Planner persists `technical_decisions` and requirement `technical_bindings`; the existing `to_model_dict()` boundary keeps both dormant in Tester, Developer, and other current downstream model prompts. This phase does not change static lint, the public-api lint authority, frontiers, RED classification, Gatekeeper runtime, or BPQ-V1.

BPQ qualification has not run in Phase 2A. Phase 2B will use exactly the three permanent BPQ-V1 inputs, three repetitions each, with no prompt or schema tuning between runs.
