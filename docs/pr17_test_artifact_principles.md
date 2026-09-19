# PR17 Test Artifact Principles

PR17 treats generated RED tests as autonomous candidate artifacts that ATHBA must validate before they can influence trusted progression.

## Scope

These principles apply to ATHBA-generated candidate RED tests.
They do not replace `coding_principles.MD` for ATHBA production code.

## Required validity checks

A candidate RED test must satisfy all of the following before ATHBA performs semantic RED verification:

- the test source parses successfully;
- the requested pytest node exists exactly;
- pytest runtime is available;
- collection succeeds without import/bootstrap corruption;
- the requested node is found and actually executes;
- the test remains inside the authorized test path;
- the test preserves inspectable stdout/stderr/traceback evidence;
- the test does not skip the requested behavior;
- the test does not rely on `xfail` or `xpass` semantics;
- the test does not fail in fixture/setup/bootstrap before the target behavior is exercised;
- the test does not swallow arbitrary exceptions through `except:` or `except Exception` style broad handlers;
- the test establishes the preconditions required to reach the claimed behavior;
- the test actually invokes or observes the claimed behavior;
- the test does not implement the production behavior itself.

## Autonomous RED definition

For PR17, the following are not valid RED evidence:

- syntax errors;
- collection failures;
- import-time/bootstrap failures;
- missing fixture/setup prerequisites;
- skipped tests;
- `xfail` or `xpass` outcomes;
- target nodes that never execute.

Only a `valid_executable_test` may proceed to semantic RED verification.

## Bootstrap and first-component rule

If a planned behavior cannot yet be exercised because the component or API does not exist, ATHBA must not treat the resulting collection or compiler failure as accepted RED.
ATHBA records the blocked evidence and routes it through the generic prerequisite mechanism rather than prescribing a concrete import or `getattr(...)` workaround.

## Evidence rule

ATHBA must preserve enough structured evidence to explain:

- what pytest collected;
- whether the requested node executed;
- where failure happened;
- what exception or assertion was observed;
- why the candidate was accepted or rejected for semantic RED analysis.
