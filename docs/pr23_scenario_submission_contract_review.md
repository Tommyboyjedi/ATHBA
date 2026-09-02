# PR23 scenario submission contract review

Date: 2026-09-01
Session: 8C1
Status: corrective architectural review; no new live proof was run.

## Decision

A Tester submits ordinary framework-valid scenario source. ATHBA, not the source
file, owns provenance. The authoritative source requirement references remain in
ScenarioDraftRequest and ScenarioDraftRunState. The independent
ScenarioIntentReviewer supplies the rationale and semantic evidence only after
approval.

The selected canonical-identity policy is adapter-owned deterministic
normalisation. For Python/pytest, the adapter accepts exactly one supported test
and renames that one test to the Behavior Planner's planned canonical identity
before ATHBA freezes the TestScenarioDraft. The original identity is retained
in ScenarioSourceCandidate.actual_test_identity, so the source submission and
the stable frontier/Gatekeeper identity remain traceable without requiring the
model to reproduce a spelling convention.

## Preserved live-proof candidate review

The records below are forensic findings, not a rewritten result for the
historical four-attempt proof. Rack AI's py_compile acceptance established
syntax only; it did not establish pytest collection, production-path integrity,
or behavior intent.

| Attempt | Syntax | Actual pytest identity | Production path | Substitute or mock | Ticket representation | Deterministic rejection finding |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Valid | tests/test_toggle_switch.py::TestToggleSwitch::test_REQ_001_toggle_switch_instantiation | Imports ToggleSwitch from toggle_switch | None | The method attempts the requested instantiation | ATHBA metadata encoding: the markers were inside a docstring, not source comments. The submitted identity also differed from the planned top-level identity. |
| 2 | Valid | No collected pytest test: the lower-case class test_REQ_001 contains only a docstring method | Imports ToggleSwitch from toggle_switch | None | No executable behavioral assertion was present | ATHBA metadata encoding and canonical-name shape were both invalid, and the scenario was semantically incomplete. |
| 3 | Valid | tests/test_toggle_switch.py::test_REQ_001 | Imports inside a guarded try block | None | It describes instantiation but converts a missing production capability into assert True and return | Semantic scenario defect: missing-capability evasion; the canonical function name itself matched. |
| 4 | Valid | tests/test_toggle_switch.py::test_REQ_001 | Does not import or reference toggle_switch | MockToggleSwitch, MockToggleSwitchState, and _get_mock_instance substitute a local type | No: it proves a locally manufactured object, not the declared production behavior | Production substitution/evasion. Its metadata was also only docstring content, but substitution is independently disqualifying. |

The candidates therefore must not be described collectively as model
incapability. Attempts one and two were partly rejected by ATHBA-owned envelope
and identity requirements. Attempts three and four contain separate,
deterministic scenario defects that remain disqualifying after this correction.

## Contract boundaries

- ScenarioSourceCandidate retains model-authored source, Rack AI candidate
  revision/evidence, and the adapter-discovered actual identity.
- ScenarioStaticAnalysis is produced by the language adapter. It records
  production-path references, local substitute definitions, behavior mocks, and
  skip/xfail or missing-capability evasions.
- ScenarioDraftAttempt persists both records, while old attempt state without
  them remains readable.
- The frozen TestScenarioDraft receives source requirement refs from request
  state and the approved intent rationale from ScenarioIntentResult.
- Comments that happen to use old ATHBA-SCENARIO-* text are ordinary source
  comments. They are neither parsed nor trusted as provenance.
- Python policy permits one ordinary module-level data helper and does not ban
  ordinary helpers globally. It fails closed only for focused, declared
  production-path substitution or behavior mocking.

## Validation scope

The corrective tests use catalog and profile scenarios only. They cover plain
source approval, non-authoritative legacy comments, adapter canonicalisation,
static production references, no/multiple/syntax-invalid test rejection,
substitute and mock rejection, missing-capability evasion rejection, legitimate
helper acceptance, bounded attempts, and persisted resume behavior.

No live endpoint, Rack AI execution, ToggleSwitch rerun, ReservationBook, PR21,
merge, or Rack AI source/configuration change was performed in this session.
