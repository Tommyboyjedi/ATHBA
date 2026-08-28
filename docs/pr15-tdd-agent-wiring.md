# PR15 — Wire a real RED → GREEN TDD cycle through Rack AI

## Goal

Wire ATHBA's first real TDD cycle onto the PR13 execution/progression layer and prove it by building one modest Python class through repeated RED -> GREEN steps using Rack AI/JCode/local models.

This PR deliberately **does not implement Architect planning or broad decomposition**. For this proof, ATHBA is force-fed the output we would expect from an Architect: a small class contract already decomposed into a fixed ordered list of behaviors. The purpose is to prove the next layer beneath architecture: can ATHBA turn one predefined behavior at a time into a Tester RED step, then a Developer GREEN step, preserve accepted revision progression, and repeat until the class exists?

PR14 remains the broader roadmap/idea holder and is not changed by this PR.

## Why this PR exists

PR13 proved that ATHBA can execute already-defined tiny work units through Rack AI and advance trusted repository state A -> B -> C. It did **not** prove the TDD agent/role wiring.

ATHBA already contains legacy concepts for an Architect, Tester and Developer, including Tester semantics around writing tests before implementation. Those older agents predate the new Rack AI boundary and must not simply regain direct Git/model/execution authority.

PR15 should preserve the useful semantic roles while routing all target-repository mutation and authoritative acceptance through the new `DevelopmentWorkUnit` -> `WorkUnitExecutionGateway` -> Rack AI path.

## Fixed proof target

Build a small Python `TaskQueue` class, expected to end up roughly 50-100 lines of production code, with a deliberately predefined behavior sequence.

The Architect output is **not generated in PR15**. Treat the following as force-fed architecture/behavior input:

1. `add_task(task_id, description)` adds a pending task.
2. adding a duplicate `task_id` raises a clear error and changes nothing.
3. `complete_task(task_id)` marks an existing task complete.
4. completing an unknown task raises a clear error.
5. `pending_tasks()` returns only incomplete tasks in insertion order.

The exact representation of a task may be chosen in the fixture, but keep the implementation small and dependency-free.

The finished class is the visible end product of PR15.

## TDD rule for this PR

Follow the classic Uncle Bob / three-laws shape strictly enough to prove the mechanism:

1. do not add production behavior until there is a failing test for it;
2. add only enough test to demonstrate the next missing behavior;
3. add only enough production code to make the current failing test pass;
4. after GREEN, existing tests must remain green before moving to the next behavior;
5. optional refactor may occur only while all tests are green and must not add new behavior.

Do not batch all five behaviors into one test-authoring step or one developer work unit.

## Intended flow

For each force-fed behavior:

```text
predefined behavior contract
        |
        v
ATHBA Tester/TDD role
        |
        v
RED work unit: add one focused failing test
        |
        v
Rack AI -> JCode/local worker
        |
        v
Rack AI proves the RED state using a deterministic RED-check command
        |
        v
accepted revision R1 containing the new failing test
        |
        v
ATHBA Developer/TDD role
        |
        v
GREEN work unit: implement only that behavior
        |
        v
Rack AI -> JCode/local worker
        |
        v
normal pytest acceptance must pass
        |
        v
accepted revision G1
        |
        v
next predefined behavior starts from G1
```

Repeat until the `TaskQueue` class satisfies the complete force-fed behavior list.

## Important: no Architect functionality in PR15

Do not ask ATHBA to invent the class, identify the five behaviors, recursively decompose a product concept, or decide architectural boundaries.

PR15 starts **after** those decisions have conceptually been made.

Represent that input explicitly, for example with a small provider-neutral structure such as `BehaviorSpec`, `TddBehavior`, `ArchitectHandoff`, or equivalent containing only what the TDD layer genuinely needs:

- stable behavior id;
- human-readable behavior/objective;
- target source path(s);
- target test path;
- dependency/order information where needed;
- deterministic RED verification command;
- deterministic GREEN acceptance command.

Do not turn this force-fed object into a general Architect API yet.

## Tester role

ATHBA already has a legacy `TesterAgent`, but it predates the new execution boundary. Reuse useful semantics where appropriate; do **not** blindly reconnect its old direct `GitService`, `TestExecutionService`, or direct local-model authority to the target repository.

For PR15, the Tester role means:

- receive exactly one predefined behavior;
- formulate a tiny test-authoring work unit for that behavior;
- constrain writes to the test file/path only;
- require deterministic proof that the new test is RED before production implementation begins;
- record the accepted revision containing that failing test;
- never write production code in the RED step.

The test authoring itself should be executed through Rack AI as a bounded work unit so Rack AI retains physical worker/model/Git authority. ATHBA describes the Tester semantic task; Rack AI chooses how it runs.

Do not hard-code `local-coder`, `local-primary`, a GPU id, a model id or endpoint into ATHBA.

## RED verification without changing Rack AI's acceptance semantics

Rack AI `work-unit/v1` currently treats successful acceptance commands in the normal way; do not redesign Rack AI just to represent an expected failing pytest exit code.

For this controlled proof fixture, include a small deterministic test harness in the seed repository, for example:

`scripts/assert_test_fails.py`

The harness should:

- execute one named pytest test;
- return exit code 0 only when that specific test fails as expected;
- return nonzero if the test unexpectedly passes, cannot be collected, crashes for unrelated reasons, or the result is otherwise not a trustworthy RED state;
- provide useful stdout/stderr evidence.

Then a RED work unit can use a normal Rack AI acceptance command such as conceptually:

`python scripts/assert_test_fails.py tests/test_task_queue.py::test_add_task`

This keeps Rack AI's existing acceptance contract unchanged while proving a genuine RED state.

The harness is test infrastructure for this proof, not a TaskQueue-specific Rack AI feature.

## GREEN verification

The corresponding Developer work unit must start from the accepted RED revision.

It may write only the production path required for that behavior, for example `task_queue.py`.

Acceptance should run the focused test plus, where useful, the existing accumulated test suite. By the end of each GREEN step all tests written so far must pass.

The Developer work unit must not modify the test file to make the test easier.

Path policy should enforce this separation:

- RED unit: test path writable, production path not writable;
- GREEN unit: production path writable, test path not writable.

A GREEN attempt that edits the test should be rejected by Rack AI path policy.

## TDD coordinator/wiring

Build the smallest new ATHBA application-layer component needed to orchestrate this sequence on top of PR13. Name it according to existing conventions (`TddCoordinator`, `TddCycle`, etc.).

It should:

- accept the force-fed ordered behavior specs and initial repository binding;
- create/submit one RED work unit;
- require an accepted trusted RED revision before GREEN;
- create/submit one GREEN work unit from that exact revision;
- require GREEN acceptance before the next behavior;
- use each returned `accepted_revision` as the next trusted base;
- persist phase, behavior id, attempts and trusted revision sufficiently for inspection/resume;
- stop/fail closed on rejection, transport failure or accepted-without-revision;
- never advance to GREEN if RED was not proven;
- never advance to the next behavior if GREEN did not pass.

Reuse PR13's progression/state concepts rather than creating a second unrelated campaign engine.

## State model

Keep it modest. We need visibility into the loop even without a UI.

Persist enough to answer:

- current behavior id;
- current phase (`red`, `green`, optionally `refactor`);
- RED work-unit id and base revision;
- RED accepted revision;
- GREEN work-unit id and base revision;
- GREEN accepted revision;
- Rack AI evidence/packet locations;
- blocked/failure reason;
- completed behaviors.

A rich front end is **not** required in PR15. Structured persisted state and a clear CLI/test report are enough for this proof.

## Legacy agent compatibility

Inspect existing:

- `core/agents/architect_agent.py`
- `core/agents/tester_agent.py`
- `core/agents/developer_agent.py`
- their behaviors/services

Identify useful domain ideas, but do not restore old execution ownership that conflicts with the new architecture.

The desired direction is that `Tester` and `Developer` become semantic ATHBA roles above `WorkUnitExecutionGateway`, not direct owners of target Git execution or concrete local models.

PR15 may introduce clean new application-layer abstractions rather than forcing old classes into the new path if that is safer and simpler. Document what legacy behavior is reused versus deliberately bypassed.

## Proof fixture

Use a disposable Python repository dedicated to this PR15 qualification.

Suggested initial shape:

```text
repo/
  task_queue.py
  tests/
    test_task_queue.py
  scripts/
    assert_test_fails.py
  pyproject.toml or minimal pytest config
```

Keep dependencies minimal; pytest is sufficient.

Register the fixture with Rack AI normally. Do not target ATHBA or Rack AI themselves.

## Required live sequence

The final live qualification should show approximately:

```text
Initial SHA X

Behavior 1: add task
  RED unit -> accepted failing test -> R1
  GREEN unit base R1 -> accepted implementation -> G1

Behavior 2: duplicate id
  RED unit base G1 -> R2
  GREEN unit base R2 -> G2

Behavior 3: complete task
  RED -> R3
  GREEN -> G3

Behavior 4: unknown completion
  RED -> R4
  GREEN -> G4

Behavior 5: pending insertion order
  RED -> R5
  GREEN -> G5

Final G5:
  complete TaskQueue implementation exists
  complete test suite passes
```

The exact number of revisions may vary only if there is a clearly justified refactor phase; do not collapse multiple behaviors merely to shorten the run.

## Tests for ATHBA

Add deterministic unit/integration tests proving at least:

1. GREEN cannot run before RED is accepted.
2. next behavior cannot run before current GREEN is accepted.
3. GREEN uses the exact RED `accepted_revision` as its base.
4. next RED uses the previous GREEN accepted revision as its base.
5. rejected RED stops the cycle.
6. RED accepted without revision fails closed.
7. rejected GREEN stops the cycle.
8. GREEN accepted without revision fails closed.
9. persisted state records behavior + phase + revision progression.
10. resume does not rerun already completed RED/GREEN phases.
11. Tester RED work unit allows only test paths.
12. Developer GREEN work unit allows only production paths.
13. no GPU/model/worker selection appears in outbound ATHBA requests.

Keep existing PR11-PR13 tests green.

## Live acceptance proof

Run the full real path on `gpurack`:

ATHBA PR15 TDD coordinator
-> Rack AI work-unit interface
-> Rack AI resource selection
-> JCode
-> local model
-> isolated target worktree
-> RED verification / GREEN verification
-> trusted accepted revision
-> next phase

No cloud model is required for this proof.

Do not manually write the final `TaskQueue` production implementation between phases. The local Rack AI execution path must produce it.

The force-fed behavior specification is allowed because architecture/decomposition is explicitly outside PR15 scope.

## Success criteria

PR15 is a PASS when:

- the fixed five-behavior input is provided to ATHBA;
- each behavior goes through an observable RED then GREEN cycle;
- the RED test is genuinely failing before production code for that behavior is introduced;
- GREEN makes that test and all accumulated tests pass;
- trusted repository revisions chain correctly across every phase;
- Rack AI retains Git/model/worker authority;
- final accepted revision contains a working `TaskQueue` class and its tests;
- final pytest suite passes;
- persisted ATHBA state reconstructs the TDD history;
- no manual target-code intervention is needed.

Report final result explicitly as:

`PR15_TDD_LOOP = PASS`

or

`PR15_TDD_LOOP = FAIL`

## Non-goals

Do NOT add in PR15:

- automatic Architect decomposition;
- broad concept -> story generation;
- recursive ticket splitting;
- OpenRouter/cloud planning;
- PM/UI redesign;
- rich TDD dashboard;
- automatic application architecture;
- parallel DAG scheduling;
- Rack AI scheduler changes unless a real runtime bug is exposed;
- direct model/GPU selection from ATHBA;
- full Tiny Ticket build.

## Definition of done

1. PR15 branch is based on current ATHBA `master` including merged PR13.
2. force-fed behavior contract is explicit and durable.
3. Tester RED and Developer GREEN semantics are wired to the new work-unit execution path.
4. RED is deterministically proven before GREEN.
5. path policy separates test-writing from production-writing authority.
6. accepted revisions progress across RED -> GREEN -> next RED.
7. TDD state is persisted sufficiently for resume/inspection.
8. Python 3.14 full ATHBA suite and compile gate pass.
9. real `gpurack` live run completes the five behavior cycles.
10. final TaskQueue class is roughly the intended modest size and fully covered by the accumulated tests.
11. no Architect/decomposition functionality is smuggled into this PR.
12. PR14 remains untouched.

Do not merge PR15 automatically when implementation is complete; return it for review with full live evidence.
