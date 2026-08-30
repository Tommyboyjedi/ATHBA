# Failure Classification and Progression Policy

## Purpose

ATHBA must not treat every failed command, test, build, review, or execution attempt as an equivalent blocker. Development failures occur at different layers, and a higher-level semantic judgement is not trustworthy while a lower-level execution condition is broken.

This document defines the system invariant for failure classification and priority. The follow-on implementation must make progression deterministic: observe evidence, classify plausible causes, select one dominant class, execute the prescribed action for that class, and then rerun/reassess from the last trusted state.

## Core invariant

When multiple failures or plausible causes are observed, ATHBA MUST:

1. preserve the complete evidence;
2. identify all plausible failure classes supported by that evidence;
3. choose exactly one dominant failure class using the fixed priority hierarchy below;
4. act only on that dominant class;
5. never accept or promote the unaccepted candidate while repairing the dominant failure;
6. after the dominant failure is resolved, rerun the bounded work from the last trusted project state;
7. classify the new result from scratch;
8. ignore lower-priority diagnoses unless they reappear after the higher-priority failure has been removed.

ATHBA must not attempt several repair paths simultaneously for one candidate.

The guiding rule is:

> The closer a failure is to the execution substrate, the higher its priority. Higher-level behavioural, semantic, review, and architecture judgements are only trustworthy after lower-level execution conditions are valid.

A higher-level classification may only become dominant after materially relevant lower-level classes have been ruled out or shown not to explain the observed failure.

## Observation is not classification

Mechanical observations such as `ModuleNotFoundError`, compile failure, pytest collection failure, timeout, assertion failure, or path-policy rejection are evidence. They are not automatically the final root classification.

Example: a pytest collection failure because a production module is absent could ultimately classify as:

- an environment failure;
- an unmet planned dependency;
- a missing plan prerequisite;
- a Tester candidate defect;
- an implementation defect.

ATHBA must use the plan, trusted repository state, current work unit, environment evidence, and agent output to determine the dominant root classification before deciding progression.

## Priority hierarchy

| Priority | Classification | Meaning |
|---:|---|---|
| 1 | `EXECUTOR_INFRASTRUCTURE_FAILURE` | Rack AI/JCode/process/worktree/executor machinery failed, crashed, lost state, could not create or manage the workspace, or otherwise could not reliably execute the requested operation. |
| 2 | `ENVIRONMENT_FAILURE` | The declared development environment is unusable: runtime missing/wrong, required tool unavailable, dependency/environment corrupt, executable inaccessible, or equivalent environment defect. |
| 3 | `COMMAND_INVOCATION_FAILURE` | ATHBA supplied a mechanically invalid execution request: malformed command, nonexistent executable/path, invalid arguments, invalid working-directory assumptions, or equivalent request-construction failure. |
| 4 | `BUILD_COMPILE_COLLECTION_FAILURE` | The candidate reached the intended environment but could not reach behavioural execution: syntax error, compilation failure, import/bootstrap failure, linker failure, test collection failure, or equivalent pre-behaviour mechanical failure. |
| 5 | `RESOURCE_LIMIT_FAILURE` | Execution was prevented by bounded operational resources: genuine timeout, memory exhaustion, disk exhaustion, process limit, unavailable reserved compute, concurrency/lease conflict, or similar resource exhaustion. |
| 6 | `SECURITY_OR_EXECUTION_POLICY_VIOLATION` | Candidate/request attempted something forbidden by Rack AI execution/security policy: unauthorized repository/environment/path, network violation, prohibited filesystem access, forbidden process/shell behaviour, or equivalent. |
| 7 | `CHANGE_SCOPE_VIOLATION` | Execution occurred but the candidate changed files/artifacts outside the work unit's permitted change scope. |
| 8 | `UNMET_PLANNED_DEPENDENCY` | The work itself is reasonable, but another requirement/work unit already present in the plan must reach trusted implementation first. |
| 9 | `MISSING_PLAN_PREREQUISITE` | Development reveals necessary prerequisite work that is absent from the current Behavior Plan/Contract. |
| 10 | `CONTRACT_OR_REQUIREMENT_AMBIGUITY` | The work cannot be judged reliably because the source requirement or Behavior Contract is contradictory, materially underspecified, or admits incompatible interpretations. |
| 11 | `TESTER_CANDIDATE_DEFECT` | After lower-level causes are ruled out, the Tester misunderstood the behaviour or produced a test that does not actually exercise/prove the requested behaviour. |
| 12 | `DEVELOPER_CANDIDATE_DEFECT` | A valid test/contract exists and the Developer's implementation does not satisfy it. |
| 13 | `EXPECTED_BEHAVIOR_RED` | The Tester candidate is valid, execution reaches the intended behaviour, and it fails specifically because that behaviour has not yet been implemented. This is successful RED progression, not a defect. |
| 14 | `ACCUMULATED_REGRESSION` | The current behaviour may pass, but previously accepted behaviour/tests now fail. The candidate has broken trusted functionality. |
| 15 | `SEMANTIC_INTEGRATION_FAILURE` | Work may function locally but conflicts with accepted components or produces incorrect integrated behaviour not represented by a simple local assertion. |
| 16 | `REVIEW_QUALITY_FAILURE` | Senior Review identifies maintainability, readability, unnecessary complexity, test gaming, poor design, or other requested quality failures after mechanical and behavioural validity have been established. |
| 17 | `ARCHITECTURE_CONSTRAINT_VIOLATION` | Behaviour works but the candidate violates an explicit architectural/component boundary or design constraint established above the Behavior Planner. |
| 18 | `SPECIFICATION_COVERAGE_GAP` | Final Gatekeeper reconciliation finds an original atomic obligation with no accepted unit test proving it. This is an explicit final observation, not automatically a repair instruction. |
| 19 | `UNCLASSIFIED_FAILURE` | Evidence shows a genuine failure but no defined class can be supported confidently. ATHBA must not guess; classification escalates instead. |

## Candidate handling invariant

For any dominant class other than accepted progression states, the current candidate remains evidence but does not become trusted project state.

ATHBA should prefer small packets of work:

- preserve evidence from the failed attempt;
- resolve one dominant issue;
- discard the unaccepted candidate as a progression base;
- rerun the bounded role/work unit from the last trusted revision;
- evaluate the new result independently.

Duplication is preferable to carrying multiple partially repaired obligations through the state machine.

## Planning feedback invariant

A downstream failure is allowed to reveal that the current plan is incomplete or sequenced incorrectly. The original Behavior Plan is therefore not immutable.

However, downstream agents do not alter scope or plan autonomously. Evidence must be routed to the appropriate planning/replanning authority. The planner may then decide to:

- reorder an existing planned dependency;
- defer the current work unit;
- add a justified prerequisite;
- revise a Behavior Contract;
- escalate ambiguity or architecture questions.

All plan mutations must be persisted with rationale and evidence references.

## Example: planned dependency

If REQ-002 tests behaviour on an object introduced by REQ-001, and REQ-002 is executed before REQ-001 exists, a module/import/compile failure is an observation. If inspection shows the candidate is consistent with REQ-002 and REQ-001 is already the planned prerequisite, the root classification is `UNMET_PLANNED_DEPENDENCY`.

The test is not rewritten merely to tolerate the missing foundation. The candidate is not promoted. ATHBA should defer REQ-002, complete/promote REQ-001, then regenerate/rerun the REQ-002 packet from the new trusted state.

## Scope of the next design step

This document freezes the classification names, meanings, and priority invariant only.

Before implementation, every classification must receive an explicit progression policy defining at minimum:

- evidence required for classification;
- authority allowed to classify/confirm it;
- candidate preservation/discard behaviour;
- work-unit state transition;
- next role/component invoked;
- whether plan mutation is permitted;
- retry/recovery rule;
- terminal/human escalation condition;
- persisted audit evidence.

The progression action must be determined by the classification contract, not improvised ad hoc by an LLM.
