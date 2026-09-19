# PR17 Two-Layer RED Acceptance Architecture

## Old unsafe RED semantics

Before this change, ATHBA treated a mechanically accepted RED helper run as sufficient to advance to GREEN.
That was unsafe because a failing pytest process could still represent syntax, collection, bootstrap, skip, xfail, or wrong-behavior defects rather than trustworthy absent-behavior evidence.

## Autonomous RED definition

PR17 now distinguishes mechanical candidate materialization from ATHBA RED acceptance.
Rack AI may still materialize a candidate revision mechanically, but ATHBA promotes it to GREEN only after two independent layers succeed.

## Layer 1: Deterministic Test Artifact Validity

Layer 1 combines static AST inspection with a structured pytest probe.
It produces a bounded artifact disposition such as:

- `valid_executable_test`
- `syntax_invalid`
- `collection_failed`
- `target_test_missing`
- `skipped`
- `xfailed`
- `bootstrap_or_fixture_failure`
- `target_not_executed`
- `policy_invalid`
- `unsupported_or_unclassified`

Only `valid_executable_test` may proceed.

## Structured pytest probe

The RED helper now emits a structured probe packet instead of reducing pytest to a single exit code.
The probe preserves deterministic facts including runtime availability, collection success, node discovery, node execution, outcome, failure phase, exception type, failure message, traceback location, and raw stdout/stderr.

## Bootstrap handling

Collection, import, setup, or first-component bootstrap failures are rejected as RED evidence.
ATHBA preserves the evidence and routes the result through the existing dependency/prerequisite decision path where appropriate.

## Layer 2A: Behavior Evidence Analyzer

`BehaviorEvidenceAnalyzer` describes what the test actually did without deciding whether it was correct.
It records imports, calls, assertions, expected-exception scopes, target-operation candidates, runtime failure phase, runtime failure location, and explicitly unknown fields.

## Layer 2B: Independent RED Verifier

`RedBehaviorVerifier` is separate from the Tester and Senior Reviewer.
It receives the behavior contract, current TDD step, generated test source, artifact assessment, behavior evidence, and structured runtime evidence.
It returns one bounded disposition:

- `valid_red`
- `invalid_test`
- `wrong_behavior`
- `insufficient_evidence`

Only `valid_red` can start GREEN.

## Descriptive Tester repair

Rejected RED feedback remains descriptive.
ATHBA reports factual evidence such as skipped execution, setup failure, wrong operation, or insufficient execution evidence without prescribing replacement code.

## Model capability distinction

With the two-layer gate in place, bounded Tester retries can now exhaust truthfully.
When Layer 1, the analyzer, and the verifier all work, ATHBA can distinguish a Tester-model capability blocker from an ATHBA architecture defect.

## Persistence and resume

`ContractCycleRecord.red_analysis` now persists the candidate change id, candidate revision, trusted base, artifact assessment, behavior evidence, and verifier result.
Resume therefore preserves why a RED candidate was accepted or rejected and avoids promoting rejected RED candidates to GREEN.

## Boundaries

This change preserves the PR17 role boundaries:

- Tester proposes candidate tests.
- Test Artifact Gate validates executable legitimacy.
- Behavior Evidence Analyzer describes actual behavior.
- RED Verifier decides whether the failure is trustworthy RED.
- Developer works only from accepted `valid_red` bases.
- Senior Reviewer remains responsible for GREEN implementation semantics.
- Specification Gatekeeper remains independent and reconciles final accepted tests against original obligations.
- Rack AI remains untouched as the generic execution substrate.
- PR21 refactoring work remains out of scope.
