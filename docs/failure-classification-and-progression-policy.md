# Failure Classification and Progression Policy

## Purpose

ATHBA must not treat every failed command, test, build, review, or execution attempt as an equivalent blocker. Development failures occur at different layers, and a higher-level semantic judgement is not trustworthy while a lower-level execution condition is broken.

This policy assumes ATHBA's orchestration implementation itself is correct. These classifications describe outcomes and failures encountered while ATHBA orchestrates development. A defect in ATHBA's own source code is not a recoverable development classification; it is an ATHBA product defect discovered outside this runtime state machine.

The system progression model is:

1. observe evidence;
2. identify supported classifications;
3. select exactly one dominant class using fixed priority;
4. execute the prescribed action for that class only;
5. rerun/reassess from trusted state.

## Core invariant: one dominant problem at a time

When multiple failures or plausible causes are observed, ATHBA MUST:

1. preserve the complete evidence;
2. identify all plausible failure classes supported by that evidence;
3. choose exactly one dominant failure class using the fixed priority hierarchy below;
4. act only on that dominant class;
5. never accept or promote the unaccepted candidate while repairing the dominant failure;
6. after the dominant condition is resolved, rerun the bounded work from the last trusted project state;
7. classify the new result from scratch;
8. ignore lower-priority diagnoses unless they reappear after the higher-priority condition has been removed.

ATHBA must not attempt several repair paths simultaneously for one candidate. Duplication of a small work packet is preferable to carrying several partially repaired obligations through the state machine.

The guiding rule is:

> The closer a failure is to the execution substrate, the higher its priority. Higher-level behavioural, semantic, review, and architecture judgements are only trustworthy after lower-level execution conditions are valid.

## Observation is not root classification

Mechanical observations such as `ModuleNotFoundError`, syntax failure, compile failure, test collection failure, timeout, assertion failure, or path-policy rejection are evidence. They do not automatically identify whose work is wrong or what ATHBA should do next.

However, ATHBA should not rely on one highly intelligent general-purpose diagnostic agent. Classification and recovery should be decomposed into small bounded decisions wherever possible.

## Priority hierarchy

| Priority | Classification | Meaning |
|---:|---|---|
| 1 | `EXECUTOR_INFRASTRUCTURE_FAILURE` | Rack AI/JCode/worktree/executor machinery cannot reliably execute or return evidence. ATHBA itself can no longer continue development safely. |
| 2 | `ENVIRONMENT_FAILURE` | The declared ATHBA development environment is unusable: runtime/tool unavailable or wrong, dependency environment corrupt, executable inaccessible, or equivalent environment defect. |
| 3 | `RESOURCE_LIMIT_FAILURE` | The bounded packet cannot complete within the available execution budget: timeout, memory/process/disk/resource exhaustion, or equivalent bounded-resource failure. |
| 4 | `SYNTAX_OR_PARSE_FAILURE` | Candidate source/test cannot be parsed by its intended runtime/compiler/interpreter, preventing meaningful build or test execution. |
| 5 | `BUILD_OR_LINK_FAILURE` | Candidate source reaches the intended toolchain but cannot build/link/package before behavioural execution. |
| 6 | `TEST_COLLECTION_OR_BOOTSTRAP_FAILURE` | The intended test/application evaluation cannot start because test collection, module/application bootstrap, import/loading, or equivalent pre-behaviour startup fails. |
| 7 | `SECURITY_OR_EXECUTION_POLICY_VIOLATION` | Candidate attempts something forbidden by Rack AI execution/security policy: unauthorized repository/environment/path/network/process/filesystem behavior or equivalent. |
| 8 | `CHANGE_SCOPE_VIOLATION` | Candidate changes files/artifacts outside the work unit's permitted change scope. |
| 9 | `DEPENDENCY_OR_PREREQUISITE_FAILURE` | Current work depends on some other capability/state that is not yet available. The Behavior Planner must determine whether the dependency is already planned, should be added to the plan, or is not a legitimate dependency. |
| 10 | `CONTRACT_OR_REQUIREMENT_AMBIGUITY` | The work cannot be judged reliably because the Behavior Contract/source requirement is contradictory, materially underspecified, or admits incompatible interpretations. |
| 11 | `TESTER_CANDIDATE_DEFECT` | After lower-level causes are ruled out, the Tester misunderstood the behavior or produced a test that does not actually exercise/prove the requested behavior. |
| 12 | `DEVELOPER_CANDIDATE_DEFECT` | A valid test/contract exists and the Developer implementation does not satisfy it. |
| 13 | `EXPECTED_BEHAVIOR_RED` | Tester candidate is valid, execution reaches the intended behavior, and it fails specifically because that behavior is not implemented. This is successful RED progression, not a defect. |
| 14 | `ACCUMULATED_REGRESSION` | New work may satisfy its focused behavior but breaks previously accepted behavior/tests. |
| 15 | `SEMANTIC_INTEGRATION_FAILURE` | Work functions locally but conflicts with accepted components or creates incorrect integrated behavior. |
| 16 | `REVIEW_QUALITY_FAILURE` | Senior Review finds maintainability, readability, unnecessary complexity, test gaming, poor design, or another requested quality failure after mechanical and behavioral validity. |
| 17 | `ARCHITECTURE_CONSTRAINT_VIOLATION` | Candidate behavior works but violates an explicit architectural/component constraint above the Behavior Planner's authority. For the current ATHBA architecture this is a blocker requiring Project Manager/human escalation. |
| 18 | `UNCLASSIFIED_FAILURE` | A genuine failure remains after known classes are considered. A dedicated classification-analysis agent may describe the unknown failure, but it may not invent an automatic recovery action. The result escalates as a missing ATHBA classification. |

`SPECIFICATION_COVERAGE_GAP` is deliberately NOT part of this runtime failure hierarchy. Gatekeeper reconciliation is a higher-level completion/audit outcome and has its own policy.

## Progression actions

### 1. EXECUTOR_INFRASTRUCTURE_FAILURE

This is a fundamental blocker.

ATHBA MUST stop development progression for the project. It must not attempt to repair Rack AI or ask Tester/Developer to compensate. The failure and evidence must propagate through ATHBA's supervision hierarchy to the Project Manager, which must surface the blocker to the human/operator when that interface exists.

The candidate is not trusted or promoted.

### 2. ENVIRONMENT_FAILURE

Suspend the affected work. ATHBA's environment-management capability repairs/recreates the declared development environment. No semantic judgement of Tester/Developer work is made while the environment is invalid.

Once environment health is proven, discard the unaccepted candidate as a progression base and rerun the same bounded job from the last trusted revision.

### 3. RESOURCE_LIMIT_FAILURE

Assume the packet is too large for the bounded worker unless clear evidence proves otherwise.

Return the work to a small bounded splitting function/role (for example a future `Behavior Splitter`) whose job is only to divide one work packet into smaller behavior-preserving packets. It does not need the authority or context of the full Behavior Planner.

Execute the smaller packets independently. Do not ask Tester/Developer to solve resource pressure through more complex code or prompts.

### 4-6. PRE-BEHAVIOR MECHANICAL FAILURES

`SYNTAX_OR_PARSE_FAILURE`, `BUILD_OR_LINK_FAILURE`, and `TEST_COLLECTION_OR_BOOTSTRAP_FAILURE` establish that intended behavior was not actually evaluated.

The system should report the observed problem and evidence without prescribing a solution.

These classes may expose a dependency/prerequisite problem. Before blaming the candidate-producing role, the failure must be checked against the current Behavior Plan by a bounded planner decision:

> Does this failure depend on planned or justifiably missing prerequisite work?

If yes, reclassify to `DEPENDENCY_OR_PREREQUISITE_FAILURE` and use that progression path.

If no legitimate dependency explains it, return the candidate to the role that produced it with the mechanical failure evidence and the original bounded job. Do not provide a repair recipe. The role retries from trusted state under its bounded retry budget.

### 7. SECURITY_OR_EXECUTION_POLICY_VIOLATION

Reject the candidate. Never weaken Rack AI policy automatically.

Provide the smallest useful violation evidence to the candidate-producing role and rerun the same bounded work. If the required work genuinely appears impossible inside current authorized scope, route that fact to the Behavior Planner rather than broadening policy autonomously.

### 8. CHANGE_SCOPE_VIOLATION

Reject the candidate. Return exact changed-path/scope evidence with the unchanged work unit to the producing role. Do not broaden allowed paths merely to accommodate the candidate.

If the role's required behavior genuinely requires broader work, route that fact to the Behavior Planner as a prerequisite/scope-planning question.

### 9. DEPENDENCY_OR_PREREQUISITE_FAILURE

All dependency questions route to the Behavior Planner. Downstream Tester/Developer roles do not decide dependency legitimacy.

The Behavior Planner makes one bounded classification decision:

1. **Already planned dependency**: record the dependency, mark the current work `DEFERRED_DEPENDENCY`, schedule/complete the prerequisite first, then reissue the original work from the new trusted state.
2. **Legitimate missing prerequisite**: add the smallest justified prerequisite work to the Behavior Plan with rationale/evidence, execute it, then reissue the blocked work.
3. **Not a legitimate dependency**: reject the dependency explanation and return the original work to the appropriate producing role with only the relevant evidence; the role must solve its own bounded task without inventing scope.

This single class replaces separate runtime classes for planned and missing prerequisites because the Behavior Planner is the authority required to distinguish them.

### 10. CONTRACT_OR_REQUIREMENT_AMBIGUITY

Stop the affected behavior path. The Behavior Planner may clarify only ambiguity within its existing behavioral authority. If the ambiguity cannot be resolved without changing the architectural source requirement, the issue becomes a blocker and escalates through Project Manager to the human/operator.

Do not let Tester/Developer choose between competing interpretations.

### 11. TESTER_CANDIDATE_DEFECT

Reject only the test candidate. Preserve evidence explaining what was wrong, not how to repair it.

Reissue the same Tester job from the same trusted state with the original behavior plus the failure evidence. Bounded retries apply. Repeated inability to produce a valid test is a role/model capability escalation, not justification for progressively encoding the solution into the prompt.

### 12. DEVELOPER_CANDIDATE_DEFECT

Reject only the implementation candidate. Preserve the valid RED/trusted RED state and return the Developer's own candidate/diff plus the concrete failing evidence.

The repair packet is intentionally different from a fresh implementation packet: it may include the Developer's previous code and observed failure, but MUST NOT include a prescribed patch/solution.

Developer receives bounded repair attempts against the same accepted RED state.

### 13. EXPECTED_BEHAVIOR_RED

Successful progression.

Accept/promote the RED test revision, persist evidence and SHA, and send the corresponding behavior to Developer for GREEN.

### 14. ACCUMULATED_REGRESSION

Reject the candidate even if its focused behavior passes. Return the Developer's candidate plus both the successful focused evidence and the previously accepted regression failures. Developer repairs without weakening previously trusted tests.

If the requirements themselves genuinely conflict, reclassify to ambiguity or semantic integration rather than forcing a local patch.

### 15. SEMANTIC_INTEGRATION_FAILURE

Route the evidence to the Behavior Planner for bounded replanning of behavioral decomposition/integration. Existing trusted behavior remains trusted unless explicitly superseded by a later controlled design decision.

Do not locally patch interacting components blindly.

### 16. REVIEW_QUALITY_FAILURE

Reject the candidate as accepted production work, while acknowledging that it may already be mechanically/behaviorally correct.

Send a distinct `repair` packet to Developer containing:

- the Developer's previous candidate/code/diff;
- the original Behavior Contract and accepted tests;
- Senior Review's concrete quality findings;
- no prescribed implementation solution.

This is intentionally different from a fresh Developer packet. ATHBA should explicitly model fresh-work packets and repair-feedback packets separately.

### 17. ARCHITECTURE_CONSTRAINT_VIOLATION

For the current architecture, treat this as a blocker.

Do not permit the Behavior Planner, Developer, or Tester to redesign architecture automatically. Preserve evidence and propagate the issue through Project Manager to the human/operator.

Future ATHBA work may introduce controlled Architect-level replanning, but PR20 must not assume that capability exists today.

### 18. UNCLASSIFIED_FAILURE

Invoke a small dedicated classification-analysis agent with:

- the observed failure/evidence;
- the current defined classification taxonomy;
- the bounded work context necessary to understand the failure.

Its job is to describe the most likely missing failure category and why the existing taxonomy does not fit. It MUST NOT decide an automatic repair or silently map the result to an existing class.

The resulting `missing classification` blocker propagates through Project Manager to the human/operator and becomes input for a deliberate ATHBA taxonomy change.

## Candidate handling invariant

A failed/unaccepted candidate remains durable evidence but never becomes trusted project state.

After a recoverable dominant issue is handled, ATHBA reruns the relevant small bounded packet from the last trusted state. It does not carry several partially repaired obligations forward.

## Feedback packet invariant

ATHBA must distinguish at least two downstream packet forms:

1. **Fresh work packet** — requirement/Behavior Contract plus current trusted state and bounded scope.
2. **Repair feedback packet** — the role's own previous candidate plus observed evidence explaining what failed, while withholding a prescribed solution.

This distinction is especially important for Tester/Developer candidate defects, regressions, and Senior Review quality repairs.

The purpose is to let small models learn from concrete failed output without turning ATHBA into a hard-coded solution generator.

## Planning feedback invariant

The Behavior Plan is not immutable. Downstream execution can expose sequencing, dependency, prerequisite, or integration facts that require controlled replanning.

Only the Behavior Planner may decide whether a dependency/prerequisite is legitimate within behavioral scope. Downstream agents cannot alter the plan or broaden their own work packets.

Plan mutation must remain small, evidence-backed, and persisted with rationale.

## Gatekeeper coverage is separate

Final Gatekeeper reconciliation is an independent completion/audit process. A `NO` coverage result is preserved as a result; it does not participate in this per-work-item failure priority hierarchy and does not automatically trigger repair.

## Implementation boundary

The progression action for a class is determined by this policy, not improvised ad hoc by an LLM.

LLMs may perform bounded classification/planning decisions only where explicitly assigned above. System routing, priority ordering, candidate trust, retry budgets, defer/block transitions, and escalation targets are deterministic application behavior.
