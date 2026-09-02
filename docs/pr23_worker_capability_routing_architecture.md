# PR23 Worker-Capability Routing Architecture

## Status

**Documentation-only proposed architecture.** No runtime, configuration, test, Rack AI, JCode, or model-service code is changed by this document.

This proposal is stacked on the implemented PR23 strict-TDD microcycle foundation at `624c666467b48fcfad72d5f0b5bfdaff6558bd97`.

PR23 remains open and incomplete because no real feature has yet completed the full path from scenario authoring through deterministic frontier progression, Developer GREEN, regression, restart, behavior review, and final Specification Gatekeeper reconciliation.

## Executive decision

The strict-TDD microcycle design is retained and frozen. The next problem is not another test-harness accommodation. It is assigning each kind of work to a worker that has been qualified for that kind of work.

The target route is:

```text
component behavior requirement
  -> Behavior Planner
  -> complete behavioral scenario authoring
       required capability: high reasoning + behavioral test design
       current preferred mapping: local-primary
  -> independent scenario-intent review
  -> deterministic language-adapter decomposition
  -> smallest syntactically complete frontier
  -> narrow production implementation
       required capability: bounded code edit + compiler/test repair
       current preferred mapping: local-coder
       bounded fallback mapping: local-primary
  -> deterministic focused GREEN and accumulated regression
  -> canonical promotion
  -> next frontier
  -> behavior-level review
  -> final Specification Gatekeeper reconciliation
```

The complete scenario is a semantic design artifact. It is larger and more demanding than a narrow frontier implementation task. The stronger local worker should therefore author and repair it first. The smaller coder should normally receive the decomposed, immutable active frontier and make the minimum production change required to pass it.

## Change-control invariant

Any further harness change must demonstrate that it restores the original generic contract rather than merely allowing a live proof to move one step forward.

Model output that violates an existing documented contract is not, by itself, evidence that the harness must change.

From this point:

- the strict scenario grammar is frozen;
- deterministic frontier decomposition is frozen;
- the four-submission limit within a model tier is frozen;
- typed execution budgets are frozen unless independent operational evidence justifies a generic policy revision;
- no tool is added merely because a model attempted to call it;
- no unsupported test form is accepted merely because a model generated it;
- bounded worker escalation replaces further small-model accommodation.

## Work taxonomy

ATHBA describes the software-development meaning of work through a small typed taxonomy. The work kind describes **what the task is**. Required capabilities describe **what a selected worker must be able to do**.

### Semantic and high-reasoning work

- `behavior_planning`
- `scenario_authoring`
- `scenario_repair`
- `scenario_intent_review`
- `senior_behavior_review`
- `final_gatekeeper_reconciliation`
- `semantic_behavior_repair`

Typical capabilities:

- `high_reasoning`
- `behavioral_test_design`
- `semantic_review`
- `code_artifact_authoring`

### Deterministic work

- scenario parsing and structural validation;
- frontier decomposition and materialisation;
- RED boundary analysis;
- focused test execution;
- accumulated regression execution;
- revision comparison and compare-and-swap promotion;
- evidence reconciliation where no semantic judgment is required.

No model is selected for deterministic work.

### Narrow model-executed work

- `frontier_implementation`
- `mechanical_implementation_repair`
- `narrow_regression_repair`

Typical capabilities:

- `bounded_code_edit`
- `repository_navigation`
- `compiler_test_repair`
- `exact_path_compliance`
- `structured_tool_use`

### Higher-complexity implementation work

- escalation of a narrow work item after local-coder exhaustion;
- semantic implementation repair;
- integration repair that exceeds the qualified narrow-worker envelope.

These require `high_reasoning` plus the relevant coding capabilities.

## Complete scenario authoring

A complete scenario must understand the full behavior ticket and express one coherent final observable behavior. It is not the active RED test and is not promoted into the project repository as trusted development state.

Required capabilities:

```text
high_reasoning
behavioral_test_design
code_artifact_authoring
```

Current deployment mapping:

```text
preferred worker: local-primary
local-coder preferred: no
```

The scenario-authoring worker operates through Rack AI because it creates a bounded candidate artifact in a trusted worktree. ATHBA requests capabilities; Rack AI chooses the concrete worker.

Scenario submissions remain bounded:

- attempt 1 is a fresh scenario draft;
- attempts 2–4 repair the immediately preceding candidate when candidate lineage exists;
- no-candidate outcomes use the existing fresh-retry semantics;
- model-originated failure consumes the selected tier's submission budget;
- executor/infrastructure failure does not;
- attempt 5 is impossible;
- after four primary scenario-authoring failures, the work enters an explicit capability-blocked state for later human/external handling.

The language adapter still validates the source. The independent intent reviewer still judges whether the scenario expresses the behavior. A scenario is never trusted merely because the stronger worker authored it.

The current deployment may use the same `local-primary` model for authoring and intent review, but the calls must be stateless and independently prompted. This gives contextual independence, not model diversity, and the evidence must say so.

## Deterministic frontier ownership

The approved complete scenario is frozen. The language adapter derives an ordered sequence of syntactically complete frontiers. No model invents replacement microtests.

A frontier is the smallest complete language/test-framework artifact that can expose the next missing capability. It is not necessarily one physical line.

### Python example

An `if` header cannot be emitted without a valid indented body. A `with pytest.raises(...)` block is materialised as a complete AST construct. The adapter may expose the import/type reference first, then constructor/setup, then operation, then final assertion or expected-exception block.

### C# example

A declaration or control-flow block must contain balanced braces and required terminators. The frontier can introduce a type reference or method call while retaining a compilable test method and class shell.

### VBA example

`If ... Then` is not a complete fragment without the matching `End If`; `For` requires `Next`; a test procedure retains its complete `Sub ... End Sub` envelope.

This is how the architecture enforces the second law of TDD without raw line slicing:

1. stop at the smallest syntactically complete fragment sufficient to fail;
2. ask Developer for only enough production code to make that frontier pass;
3. run deterministic regression;
4. expose the next fragment of the same canonical test.

## Narrow frontier implementation

Required capabilities:

```text
bounded_code_edit
repository_navigation
compiler_test_repair
exact_path_compliance
```

Current deployment mapping:

```text
preferred worker: local-coder
fallback worker: local-primary
```

The ordinary narrow work contract remains:

- Developer sees only the active frontier;
- future scenario fragments remain hidden;
- tests are immutable;
- only allowed production paths may change;
- the objective is only to make the active frontier pass;
- speculative future implementation is prohibited;
- focused GREEN and accumulated regression are deterministic and independent of the worker's claim;
- canonical promotion occurs only after those gates clear.

The current `300`-second frontier budget remains the version-1 default.

## Bounded tier escalation

One immutable narrow work item has two explicit capability tiers.

```text
Tier 1: narrow-worker tier
  preferred current mapping: local-coder
  maximum submissions: 4

Tier 2: stronger-worker fallback tier
  current mapping: local-primary
  maximum submissions: 4
```

These are not eight anonymous retries. The work identity remains stable while the tier and submission identity change.

Escalation occurs only after four genuine model-originated failures within the narrow tier. It does not occur for:

- executor unavailable;
- transport failure before worker invocation;
- malformed packet;
- missing required provenance;
- stale base;
- no eligible worker;
- an established harness/tool-policy contract violation.

When escalation occurs, ATHBA preserves:

- immutable objective and acceptance contract;
- active frontier and accepted tests;
- base ref and SHA;
- allowed paths;
- all candidate and no-candidate evidence;
- exact diagnostics;
- last safe repair candidate, if one exists;
- the exhausted tier's attempt history.

Rack AI then selects an eligible stronger worker. The fallback candidate still passes all normal structural, path, focused GREEN, regression, review, and promotion gates.

There is no automatic return from the primary tier to the coder tier. After four primary fallback submissions, the work enters `capability_blocked` with full evidence. Later human or separately approved external escalation may act on that state; PR23 does not invent another automatic tier.

## ATHBA and Rack AI ownership

### ATHBA owns

- component and behavior meaning;
- TDD phase and semantic readiness;
- work kind;
- required and preferred capabilities;
- immutable work identity and acceptance contract;
- per-tier model-attempt accounting;
- candidate interpretation;
- scenario/frontier progression;
- escalation authorization;
- project revision trust and canonical promotion;
- final Specification Gatekeeper reconciliation.

ATHBA must not normally request a GPU, endpoint, concrete worker ID, model ID, or JCode profile.

### Rack AI owns

- registered workers, models, resources, and qualification metadata;
- concrete worker eligibility and selection;
- resource availability and leases;
- queueing of already-ready executable work;
- GPU/model placement;
- harness and tool profile;
- trusted worktrees and isolation;
- execution timeouts;
- worker selection evidence;
- worker execution provenance;
- terminal execution packets.

Current names such as `local-primary`, `local-coder`, `gpu-4060ti`, and `gpu-2060` are deployment mappings, not ATHBA semantic code.

## Cross-repository work contract

ATHBA submits an immutable descriptor conceptually equivalent to:

```text
DevelopmentWorkDescriptor
  work_id
  project_id
  behavior_ref
  work_kind
  required_capabilities
  preferred_capabilities
  priority
  escalation_tier
  attempt_number_within_tier
  global_submission_sequence
  execution_budget_seconds
  base_ref
  base_sha
  allowed_paths
  acceptance_contract
  evidence_refs
```

Rack AI returns two linked records.

### Selection evidence

```text
WorkerSelectionDecision
  decision_id
  work_id
  work_kind
  required_capabilities
  preferred_capabilities
  eligible_workers
  ineligible_workers_with_reasons
  selected_worker_id
  selection_reason
  capability_version
  qualification_evidence_refs
  escalation_tier
  priority
  resource_and_lease_evidence
  execution_budget_seconds
  policy_version
  created_at
```

Selection reasons are bounded values such as:

- `preferred`
- `capability_fallback`
- `capability_escalation`
- `idle_overflow`

### Execution provenance

The existing `WorkerExecutionProvenance` records what actually ran. Selection evidence explains why it was selected. A mismatch between selected and executed worker fails closed.

## Worker capability registry

Rack AI extends its current worker/model/resource registry with measured capabilities and qualification evidence.

Conceptual record:

```text
WorkerCapabilityRecord
  worker_id
  capabilities
  qualification_status
  qualification_evidence_refs
  capability_version
  execution_constraints
  concurrency_capacity
  active_leases
```

Qualification statuses:

- `qualified`
- `qualified_with_constraints`
- `unavailable`

Current initial mapping:

```text
local-primary
  high_reasoning
  behavioral_test_design
  semantic_review
  code_artifact_authoring
  bounded_code_edit
  repository_navigation
  compiler_test_repair

local-coder
  bounded_code_edit
  repository_navigation
  compiler_test_repair
  narrow_multi_file_edit
  exact_path_compliance
  structured_tool_use
  status: qualified_with_constraints
```

The registry must not grant `high_reasoning`, `behavioral_test_design`, or `semantic_review` to local-coder without new qualification evidence.

## Ready pool and execution queue

There are two layers with different authority.

### ATHBA ready-work pool

ATHBA owns semantic readiness and stores:

- project and behavior reference;
- TDD phase;
- dependency state;
- trusted base;
- work kind and capability requirements;
- escalation tier and attempts;
- priority;
- immutable acceptance contract.

### Rack AI execution queue

Rack AI owns physical execution readiness and stores:

- accepted immutable work request;
- eligible workers;
- resource/lease state;
- queue age and priority;
- selection decision;
- execution state;
- packet/evidence result.

Rack AI may not make a semantically blocked behavior ready. ATHBA may not claim that a physical worker or GPU is available.

One authoritative semantic state remains in ATHBA. One authoritative execution state remains in Rack AI. Idempotency keys, submission acknowledgements, lease IDs, transition receipts, and terminal packet IDs link them without duplicating authority.

## Priority and idle-primary overflow

Idle-primary overflow is part of the target architecture but is **not required for the first routing proof**.

Current priority order for local-primary eligibility:

1. blocking high-reasoning planning or semantic work;
2. complete scenario authoring and repair;
3. intent review, senior review, and final reconciliation;
4. narrow work escalated after coder exhaustion;
5. optional narrow overflow work.

Version 1 is non-preemptive:

- a short bounded overflow task already running may finish;
- no new overflow work is leased while high-reasoning work is ready or queued;
- overflow is explicitly marked in selection evidence;
- overflow never changes the work's deterministic acceptance gates.

This later optimisation keeps the primary productive without allowing narrow work to starve its unique semantic responsibilities.

## Concurrency model

Version 1 is intentionally conservative:

- one active mutating work item per project;
- frontiers of one canonical scenario are sequential;
- canonical promotion is compare-and-swap serialized;
- independent projects may execute concurrently;
- immutable-input reasoning may overlap with code execution;
- speculative parallel mutation within one project is deferred.

This still enables useful two-GPU concurrency across independent projects and between non-mutating reasoning and a narrow code task, without introducing merge-queue complexity before the basic route is proven.

## Failure ownership

| Failure | Owner of interpretation/action |
| --- | --- |
| Candidate structural or semantic failure | ATHBA |
| Model no-candidate failure after verified invocation | ATHBA attempt accounting, using Rack AI evidence |
| Worker timeout after invocation | Rack AI evidence; ATHBA tier policy |
| Worker unavailable / no eligible worker | Rack AI selection blocker surfaced to ATHBA |
| Transport/executor/worktree failure | Rack AI |
| Stale base or failed CAS promotion | ATHBA trust lifecycle with Rack AI Git evidence |
| Deterministic regression failure | ATHBA |
| Local-coder capability exhaustion | ATHBA authorizes tier escalation |
| Local-primary fallback exhaustion | ATHBA records capability block |
| Selection/execution provenance mismatch | fail closed across the boundary |

Infrastructure failure never consumes a model submission. Model-originated failure consumes only the currently selected tier's budget.

## Version-1 scope required before PR23 completion

1. Typed cross-repository work kind and capability requirements.
2. Rack AI worker capability metadata and deterministic eligibility.
3. Durable worker selection decision linked to execution provenance.
4. Complete scenario authoring and repair through high-reasoning capability.
5. Deterministic scenario decomposition unchanged.
6. Local-coder preferred narrow frontier implementation.
7. Local-primary fallback after four coder-tier submissions.
8. Separate persisted per-tier attempt state and candidate lineage.
9. Stale-base rejection and serialized canonical promotion.
10. One fresh tiny-feature end-to-end proof.
11. One fresh ReservationBook end-to-end proof and Gatekeeper reconciliation.

## Deferred optimisation

The following are designed for compatibility but are not merge gates for the first PR23 proof:

- idle-primary overflow;
- sophisticated queue ageing;
- multiple same-project ready mutation tickets;
- adaptive routing from success history;
- dynamic model bake-offs;
- cross-project throughput optimisation;
- cloud escalation;
- preemption;
- speculative branch reconciliation.

PR23 must not absorb a general distributed scheduler before one project completes successfully.

## Stop conditions

- No runtime implementation begins before this design is reviewed.
- No tool or test grammar change is justified by one model output.
- No fifth submission exists within either tier.
- No coder-primary-coder bounce loop exists.
- No ReservationBook proof runs before the tiny capability-routing proof.
- No idle-overflow implementation precedes preferred/fallback routing.
- No cross-project scheduler sophistication precedes one-project completion.
- If both tiers cannot complete the same tiny feature under the frozen generic contract, PR23 stops for architecture simplification review rather than adding another harness subsystem.

## Definition of done

The capability-routing architecture is complete when:

- ATHBA requests semantic work and capabilities without naming hardware;
- Rack AI selects an eligible concrete worker and records why;
- local-primary authors and repairs one complete scenario;
- the deterministic adapter derives strict frontiers;
- local-coder is preferred for narrow implementation;
- local-primary receives bounded fallback work after truthful coder exhaustion;
- attempts, candidate lineage, selection, execution, revision trust, and restart state remain durable;
- a tiny feature completes end to end;
- a fresh ReservationBook application completes or reaches a legitimate capability/human blocker without feature-specific harness changes;
- every Gatekeeper checklist item receives final accepted-test YES/NO reconciliation.
