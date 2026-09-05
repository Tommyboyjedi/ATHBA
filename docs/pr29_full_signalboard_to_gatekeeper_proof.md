# PR29 full SignalBoard-to-Gatekeeper proof

## Result

This proof is **incomplete**. The final fresh behavior-first run stopped fail-closed at `attempts_exhausted` while drafting the first Tester scenario for REQ-001. The Specification Gatekeeper was not invoked. No SignalBoard production code, tests, refactoring, naming correction, or post-stop retry was performed.

## Architectural cleanup

- Starting ATHBA head: `7727c5de27bee275bba7090bf375161da4a3804d`
- Behavior-first cleanup: `2f15db1` (`development: restore behavior-first development pipeline`)
- Durable-run recovery fixes discovered during setup: `5e01bda`, `e544fe0`
- Cleanup removes active TechnicalDecision/TechnicalBinding propagation, all resolver variants and qualification harnesses, and public-api name enforcement. Historical documentation remains explicitly marked historical. Observation Resolver remains absent.
- BPQ-V1, Rack AI, JCode, and PR21 were not changed.

Post-cleanup gates at `2f15db1`: focused 166 passed; full ATHBA suite 550 passed; coding-principles passed; mypy passed; compileall passed; `git diff --check` passed. The two generic durable-run fixes each had focused controller coverage; the first also had a 551-test full-suite pass.

## Canonical live input and readiness

- Fixture: BPQ-V1-B from the immutable BPQ-V1 loader.
- Corpus SHA-256: `523dc088007cdcd10484daa7cb272fdbdab4a37a306a5369bbeac1ff676d85cb`.
- Requirement SHA-256: `c46ce04d165b64d2459fdd821475289925496dc7541584230d60f4858ec9aa88`.
- A real `POST /v1/responses` generation on local-primary returned `READY` (`resp_94c47c88ed72961d`) before the run.

## Final run evidence

- Run/project: `pr29-full-signalboard-to-gatekeeper-20260904T232650Z`.
- Target repository: `/srv/ATHBA/state/projects/pr29-full-signalboard-to-gatekeeper-20260904T232650Z/repository`.
- Initial and final behavioral SHA: `88ec81761098cbe1ce58f0c4c5096aa9021d1e8e` (no accepted behavioral change).
- Evidence root: `/srv/ATHBA/evidence/pr29-full-signalboard-to-gatekeeper-20260904T232650Z`.
- Persisted planner contract: six requirements, `REQ-001` through `REQ-006`; planner `public_api` was advisory only (`publish`, `get_signal`) and did not reject any scenario.

| REQ | scenario | frontiers | RED/GREEN | regression | Senior Review | status |
| --- | --- | ---: | --- | --- | --- | --- |
| REQ-001 | not approved | 0 | not reached | not reached | not reached | attempts exhausted |
| REQ-002 to REQ-006 | not reached | 0 | not reached | not reached | not reached | blocked by REQ-001 |

REQ-001 attempt evidence: attempts 1 and 2 were real local-primary JCode worker timeouts after 300 seconds with no candidate. Attempt 3 produced a syntactically valid scenario but independent Intent Review returned `semantic_repair_required`: it asserted only that the module existed, not that a board started empty. Attempt 4, the bounded repair of that candidate, timed out after 300 seconds with no candidate. The persisted scenario state and Rack AI review packets retain exact paths and provenance.

The terminal state is `blocked`, reason `attempts_exhausted`; no Gatekeeper verdict exists. The Gatekeeper checklist was independently created before the block but no final assessment was invoked.


## Fresh corrected-boundary live run: 2026-09-05

This section records one new run at ATHBA `df164c339894bbb0b29f3505149fd1c30937b555`. Historical runs above are unchanged. The corrected pre-Intent boundary worked live: one mechanically valid scenario using an undeclared member reached Intent, was approved, frozen and fragmented. The end-to-end proof remains **incomplete**: REQ-001 stopped at assertion Frontier 2 with `unsupported_language_boundary`. No repair, resume, second proof, or harness correction was performed.

### Identity and readiness

- Run and project: `pr29-fresh-signalboard-20260905T105000Z`; actual controller start `2026-09-05T10:47:57.779736+00:00`.
- Branch: `pr29-live-tiny-strict-tdd-v2-proof`; expected starting head verified; tracked working tree clean. Existing untracked `evidence/` retained.
- Generated repository: `/srv/ATHBA/state/projects/pr29-fresh-signalboard-20260905T105000Z/repository`, resolved beneath the already-approved `/srv/ATHBA/state/projects` trusted dynamic root.
- Initial project SHA: `4d43e81184cd2ba7c23043a038c5843ec4e42269`.
- Final accepted project `main`: `20fa1eea109ffef49cb5cadbaf71a1fd009ef939`.
- Rack AI provenance version: `56d2c69f1e815acd12fca9065945c5e46de5a36a`.
- Evidence root (E below): `/srv/ATHBA/evidence/pr29-fresh-signalboard-20260905T105000Z`.
- Immutable BPQ-V1-B source used verbatim; canonical corpus hash `523dc088007cdcd10484daa7cb272fdbdab4a37a306a5369bbeac1ff676d85cb`; fixture file SHA256 `3b1c2deec2369d5edc7dba79af76b5c90ea3a9b7f70b895f78237c1184300352`; requirement SHA256 `c46ce04d165b64d2459fdd821475289925496dc7541584230d60f4858ec9aa88`.
- Both local health and model metadata endpoints returned HTTP 200. One bounded 60-second local-primary readiness request returned `READY` in 0.0994 seconds, response `resp_9d411af89435f756`. No services were restarted or configuration changed.
- Unmodified `scripts/run_pr23_strict_tdd_feature.py start` ran once with the above IDs, `E/requirement.txt`, Python/pytest, `signal_board.py`, `tests/test_signal_board.py`, state root `/srv/ATHBA/state`, and evidence root E. Runner exit was 2 after 19 application transitions.

### Real Behavior Planner and independent checklist

The real local Planner produced five requirements. Its full unedited contract is `E/behavior-contract.json`. Advisory `public_api` was `publish(name: str, payload: any)` and `get_signal(name: str) -> any`. No API names were supplied as a manual correction.

| REQ | Summary | Observable outcome | test_hint | Dependencies | Source refs |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | Initial state is empty | SignalBoard starts with no published signals | Verify board is empty upon instantiation | none | PR16-001 |
| REQ-002 | Publish and retrieve a signal | Payload is successfully published and retrievable | Publish a payload and verify retrieval matches | REQ-001 | PR16-002, PR16-006 |
| REQ-003 | Update existing signal | New payload replaces old payload for the same name | Publish twice to same name and verify the second value is returned | REQ-002 | PR16-003, PR16-004 |
| REQ-004 | Isolation of signal names | Publishing a new name does not affect existing names | Publish to name A, then name B, verify A remains unchanged | REQ-002 | PR16-005 |
| REQ-005 | Architectural constraints | Component adheres to mechanical and quality constraints | Verify no persistence, deletion, or subscription logic exists | none | PR16-007, PR16-008, PR16-009, PR16-010, PR16-011, PR16-012 |

The independent Specification Gatekeeper atomization used the original requirement and persisted its own checklist before scenario drafting. Existing composition kept this checklist out of Planner, Tester, Intent, Developer and Senior inputs. `E/gatekeeper-checklist-state.json` retains all twelve obligations. Final reconciliation was not invoked: every item below is **NOT_REACHED**, with no YES/NO judgment or implied coverage.

| Ref | Kind | Original checklist obligation |
| --- | --- | --- |
| initial_state | behavior | The SignalBoard must start with no published signals. |
| publish_signal | behavior | The system must allow users to publish a payload under a specific signal name. |
| replace_signal | behavior | Publishing a payload under an existing signal name must replace the previous value for that name. |
| isolate_signals | behavior | Publishing a payload for one signal name must not affect the values of other signal names. |
| get_latest_payload | behavior | The system must allow users to request the latest payload for a specific signal name. |
| return_latest_value | behavior | The system must return the most recently published value when a signal is requested. |
| in_memory_storage | constraint | The SignalBoard must be an in-memory component. |
| no_persistence | constraint | The system must not persist data to any external storage. |
| no_subscriptions | constraint | The system must not support subscriptions. |
| no_concurrency | constraint | The system does not need to handle concurrency. |
| no_validation | constraint | The system does not need to enforce validation rules. |
| small_and_direct | quality | The component must be small, direct, and dependency-free. |

### Tester attempt and Intent

REQ-001 had exactly one Tester submission, selected local-primary / `gemma4-12b-local-primary`, `generic-reasoning-worker`, JCode on `gpu-4060ti`. Its configured timeout remained 300 seconds and its only allowed/changed path was `tests/test_signal_board.py`. Rack AI returned `checks_passed`, acceptance `approved`, `last_error: null`; accepted candidate revision was `cc27dc68c2fcfcda676b85584c16ae226fbcd1eb`. The exact objective, requirements, routing and limits are retained in the original submitted v2 JSON under `E/execution-inputs/`; the packet preserves task, diff, commands, implementer output and selection/provenance. No timeout occurred.

The candidate, canonical and frozen complete scenario are identical:

```python
import pytest
from signal_board import SignalBoard

def test_REQ_001():
    board = SignalBoard()
    assert len(board.get_signals()) == 0
```

Mechanical assessment had valid syntax, a production reference and zero issues: undeclared `get_signals` did not block Intent. No repair feedback was needed or generated. Independent Intent approved with evidence `PR16-001` and rationale:

> The test correctly instantiates the SignalBoard and asserts that the length of the signals list is zero, directly verifying that the board starts with no published signals as required.

The scenario froze and produced three ordered fragments. It was not executed in full as the first RED.

| Frontier | Fragment | Evidence and result |
| --- | --- | --- |
| 0 | production import, source line 2 | Missing `SignalBoard` import admitted as `valid_missing_capability_red`; one production-only Developer submission; GREEN; regression clear; promoted. |
| 1 | constructor, source line 5 | Already GREEN after the preceding minimal class implementation; existing passing-frontier path ran regression and promoted without another Developer call. |
| 2 | assertion, source line 6 | Collection, exact-node discovery, setup and teardown passed. Call failed with `AttributeError: 'SignalBoard' object has no attribute 'get_signals'` at the active span. Classified `unsupported_language_boundary`; no accepted RED or Developer call for this Frontier. |

The single Developer submission selected local-coder / `eqaq-v2-local-coder`, `generic-coding-worker`, JCode `minimal` on `gpu-2060`, with unchanged 300-second timeout. Selection was `least_scarce_sufficient`. Only `signal_board.py` was allowed and changed. The objective contained the active import Frontier, not future complete-scenario assertions. The accepted candidate was `195f64a112670f677233972e77325527d6763d6a`; packet status `checks_passed`, acceptance `approved`, `last_error: null`. Worker tool errors (an attempted commit against sandbox read-only Git metadata and a missing `python` alias) were nonterminal; its subsequent `python3` test command passed. They are not the terminal blocker.

Trusted revision progression was initial `4d43e81184cd2ba7c23043a038c5843ec4e42269`, accepted import RED `e34a283f6e9bf7ade0d99a391525c822bbc6fbbb` on the isolated chain, validated Developer GREEN/CAS `195f64a112670f677233972e77325527d6763d6a`, then passing constructor/CAS `20fa1eea109ffef49cb5cadbaf71a1fd009ef939`. Two `regression_clear` transitions precede the promotions (lifecycle sequences 12 and 16). Current assertion regression remains pending, and there are no previously completed Behavior Requirements. Do not interpret these partial checks as full-scenario regression success. The failing assertion was not promoted. Revision lifecycle, feature canonical base and actual project main agree on the final accepted SHA; some intermediate lifecycle envelopes retain the initial canonical SHA, and the run summary's canonical fields are null.

REQ-001: approved/frozen scenario, 2/3 Frontiers complete, overall behavior pending/blocked, Senior Review not reached (zero attempts). REQ-002 through REQ-005 were not reached. REQ-006 was not planned in this run. Zero Behavior Requirements completed. Final Gatekeeper was not reached; its assessment history is empty.

### Terminal classification and contract gap

**ATHBA_HARNESS_DEFECT**, generic RED-classification coverage gap; runtime status `blocked`, reason `unsupported_language_boundary`.

Owning component: `PythonBoundaryClassifier.classify` in `core/development/python_pytest_adapter.py`, particularly the missing-capability and assertion branches around lines 632-642. Missing `AttributeError` capability is accepted only for production-import, constructor or call fragments. An assertion fragment accepts `AssertionError`/structured assertion-message shape, so this active assertion's missing member falls through to unsupported. The parser accepted and froze the same statement as an ordinary assertion.

The architectural contract is the corrected mechanical-only boundary followed by Intent approval, deterministic atomization and strict TDD. The existing implementation ledger (`docs/pr23_strict_tdd_implementation_ledger.md`, Sessions 3 and 5) permits ordinary assertions and states that within-scenario member capability failures remain valid RED. Here the production capability fails at the active approved assertion span with a GREEN prior Frontier, yet cannot enter the Developer RED path. This is a generic gap between accepted scenario grammar and RED support; the classifier contains no SignalBoard/name-specific condition. This classification does not establish that arbitrary AttributeErrors should all be accepted or prescribe a fix. It is not a public-api rejection, Tester mechanical failure, Intent rejection, Developer failure, or timeout. No source correction was made.

### Model accounting and retained evidence

Six top-level local invocations: readiness, Behavior Planner, independent checklist atomization, Tester workspace submission, Intent Review, and Developer workspace submission. Four direct successful generations plus 16 Tester and 6 Developer JCode token-response records give **26 observed generation records**. This is not a wire-level HTTP audit; unrecorded transport retries cannot be ruled out. Cloud/OpenRouter calls: zero. No subsequent model calls or rerun were made. `E/model-accounting.json` records the count and limitation.

Evidence locations relative to E:

- `identity.json`, `initial-project.json`, `requirement.txt`, `readiness-http.json`, `ready-request.json`, `ready-response.json`, `ready-summary.json`, plus both workers' health/metadata files.
- `behavior-contract.json`, `gatekeeper-checklist-state.json`, `REQ-001-scenario-snapshot.json`.
- `runner-start.log`, `runner-start.exit`, and `pr29-fresh-signalboard-20260905T105000Z/proof-report.json` / `proof-report.md` (persisted lifecycle, draft, microcycle and revision evidence).
- `execution-inputs/`: exact original v2 input JSON for the only Tester and Developer submissions, including literal objective/prompt and 300-second limits. A read-only observer copied these temporary inputs without wrapping or changing execution.
- `packet-index.json` and `rack-ai-packets/`: exact packet copies, including original source paths, implementer output, provenance, selection, changed paths, commands and candidate revisions.
- `terminal-snapshots/`: final run/feature/scenario/microcycle JSON, exact frozen scenario and accepted final project production/test source. Temporary pytest worktree paths in diagnostics are historical locations; persisted diagnostics are authoritative.

Original Rack AI packets:

- `/srv/rack-ai/state/changes/pr29-fresh-signalboard-20260905T105000Z--REQ-001--frontier-0--pr29-fresh-signalboard-20260905T105000Z--REQ-001--frontier-0--developer-1--submission-4928841240484814585/review-packet.json`
- `/srv/rack-ai/state/changes/pr29-fresh-signalboard-20260905T105000Z--REQ-001--scenario-draft--pr29-fresh-signalboard-20260905T105000Z--REQ-001--scenario-draft-1--submission-3869046333795984551/review-packet.json`

Authoritative scenario state: `/srv/ATHBA/state/scenario-drafts/pr29-fresh-signalboard-20260905T105000Z--REQ-001.json`; microcycle: `/srv/ATHBA/state/microcycles/pr29-fresh-signalboard-20260905T105000Z--REQ-001.json`; feature: `/srv/ATHBA/state/features/pr29-fresh-signalboard-20260905T105000Z.json`; run: `/srv/ATHBA/state/runs/pr29-fresh-signalboard-20260905T105000Z.json`. Original execution input filenames are `pr29-fresh-signalboard-20260905T105000Z--REQ-001--scenario-draft-1.json` and `pr29-fresh-signalboard-20260905T105000Z--REQ-001--frontier-0--developer-1.json` under E/execution-inputs.

### Scope and validation

ATHBA source code, prompts, adapter, grammar, Frontier machinery, Planner, Developer, Gatekeeper, accounting, timeouts, execution budgets and routing were unchanged. BPQ-V1, Rack AI, JCode and PR21 were unchanged; PR21 was not started. All existing TODOs, including test_hint and evidence_refs plumbing, remain intact. The real Developer changed production source **only in the generated project**, producing a minimal `SignalBoard` class; accepted final source is retained in E/terminal-snapshots. No production implementation was manually authored.

Only this documentation file is committed; generated state and runtime evidence remain outside the commit. Validation for the documentation change: `git diff --check`; no source-test suite was rerun for this documentation-only update. The live proof's partial test evidence and terminal outcome above are not a full end-to-end PASS.


## Deterministic assertion RED correction: 2026-09-05

This follow-up starts at ATHBA `5e75c1d567f28641367eca6d26d8a1891cc1c202`.
It corrects the generic harness defect; it does not resume, rerun, or amend the
historical live run `pr29-fresh-signalboard-20260905T105000Z` above. The original
failure evidence and persisted run/scenario/microcycle/feature state remain intact.
No model calls were made during this correction.

### Source and evidence trace

The current `strict_microcycle_advance._observe_frontier` materialises the active
prefix through `PythonFrontierMaterialiser`, then executes its exact pytest node
through `PythonPytestAdapter.execute_frontier` / `PytestStructuredExecutor` and
`python_pytest_probe`. Probe hooks record collection, node discovery/execution,
setup/call/teardown, exception and failure location. The executor converts these
into `BoundaryDiagnostic`; `PythonBoundaryClassifier` checks the prior frontier
and active emitted source span before classifying. `_observe_frontier` records
the assessment and only `_VALID_RED_OUTCOMES` can accept the RED revision and
select `SUBMIT_DEVELOPER`. Unsupported outcomes block instead. The synchronous
`StrictMicrocycleService._execute_frontier` route uses the same adapter/classifier.

The parser classifies `ast.Assert` as `assertion`; a bare expression call is
`call`. At the starting HEAD, the missing-capability exception branch admitted
imports, constructors and calls, but excluded assertions. The subsequent assertion
branch admitted behavioral assertion failures, so a missing member in an assertion
fell through to `unsupported_language_boundary`. There was also no runtime owner
check in the old call-span AttributeError branch.

Read-only inspection of the actual persisted microcycle confirms the active
`python-3-assertion`, line 6, `AttributeError` for the missing member, successful
collection/node discovery/setup/teardown, failed call and unsupported outcome.
Frontier 0 completed RED/GREEN/regression; Frontier 1 was already GREEN and
completed regression without a second Developer call.

### Reproduction and generic rule

Before changing production code, a parameterized real-pytest regression created
`widget_module.Widget` with no members, verified the constructor frontier GREEN,
and executed `widget.entries()` versus `assert len(widget.entries()) == 0`.
The actual exceptions were missing-member AttributeErrors. The call passed the
expected RED check, while the assertion failed it with the historical unsupported
classification: **1 passed, 1 failed**. This is retained in
`evidence/pr29-assertion-red-correction/before.log`.

A missing member is now accepted across supported fragment kinds only with
positive runtime ownership evidence: the innermost failure is a matching Python
`LOAD_ATTR` in the canonical test, the exception identifies the actual owner and
member, the owner module/type belongs to the declared production file (including
module type identity), and static lookup proves absence without invoking getters.
Custom attribute lookup, properties, substitutes and helper/production-internal
exceptions do not satisfy that proof. Collection, node execution, setup, call,
teardown, prior-frontier and active-span checks must also agree. Missing evidence
fails closed. Unknown fragment kinds remain unsupported.

The execution request gains an optional production-path diagnostic input, passed
from the existing strict-microcycle request into the probe. Existing persisted
state schemas are unchanged; the proof uses the existing extensible diagnostic
facts. Old diagnostics lacking ownership evidence cannot newly authorize an
AttributeError RED. No production name or fixture is special-cased.

Ordinary assertion mismatch remains the existing **valid_behavioral_red**, never
**valid_missing_capability_red**. Rejecting all behavioral assertion RED would
change strict-TDD semantics and is deliberately outside this correction.

Tests cover call/assertion equivalence, production module/class/instance members,
declarations and compound fragments, unknown fragment kinds, prior-frontier
failure, unrelated objects and exceptions, helpers, fixtures, properties, custom
lookup, mocks/substitutes, missing production-path evidence and invalid syntax.
The strict-microcycle transition regression checks accepted RED and pending
Developer action without making a Developer submission or advancing the frontier.

Tester, Intent Review, Behavior Planner, scenario grammar/freezing/fragmentation,
Frontier ordering, Developer mutation rules, GREEN validation, regression, CAS,
Senior Review, Gatekeeper, repair accounting and trusted-revision rules are
unchanged. Only production-path diagnostic plumbing changes in the microcycle
call sites. BPQ-V1, Rack AI, JCode, PR21, prompts, model configuration, routing,
execution budgets and timeouts are unchanged. Historical live proof remains
incomplete; deterministic correction is not a claim of live proof completion.

### Validation and preservation

All commands ran in `/srv/ATHBA` using `./.venv/bin/python`, `PYTHONPATH=.`,
CPU-only CI test settings, and `TMPDIR=/srv/ATHBA/evidence/pr29-assertion-red-correction`.
`PYTEST_ADDOPTS=--rootdir=.` kept nested disposable pytest projects rooted at their
own working directory while keeping all temporary files inside ATHBA.

- Focused adapter, strict-microcycle, RED-acceptance and domain tests: **66 passed**
  in 54.48s (`focused-final.log`).
- Full `python -m pytest -q`: **618 passed** in 174.23s, exit 0 (`full.log`, `full.exit`).
- `scripts/check_coding_principles.py`: PASS (`principles-final.log`).
- Configured `python -m mypy`: PASS, 29 source files (`mypy-final.log`).
- Explicit mypy for adapter, probe and missing-member helper: PASS, 3 source files.
- `python -m compileall -q athba core llm_service tests scripts`: PASS (`compileall.log`).
- `git diff --check`: PASS.
- SHA-256 comparison: all 38 historical evidence/state files unchanged
  (`historical-hashes.json`). Evidence logs remain untracked and outside the commit.

Log paths above are relative to `evidence/pr29-assertion-red-correction/`.


## Fresh assertion-correction qualification: pr29-fresh-signalboard-20260905T162901Z

This new run is **incomplete**, stopped at the first typed terminal blocker before any Tester model attempt was recorded. It does not exercise the corrected assertion RED classifier. Historical sections above and historical runtime state are unchanged. No resume, post-terminal retry, alternate fresh run, architecture fix, or PR21 work was performed.

### Identity and readiness

- Run ID and project ID: `pr29-fresh-signalboard-20260905T162901Z`.
- ATHBA branch: `pr29-live-tiny-strict-tdd-v2-proof`; starting head: `a4ff78e268fcc3a12f38da88d939724dfac5be7c`. GitHub PR29 had that same head.
- Tracked working tree was clean. `git status --short` also showed pre-existing untracked `evidence/`, preserved and left unstaged; the entire tree was therefore not literally empty of untracked files.
- Generated project repository: `/srv/ATHBA/state/projects/pr29-fresh-signalboard-20260905T162901Z/repository`. Its new, previously nonexistent path was resolved beneath the already-approved `/srv/ATHBA/state/projects` dynamic root. The returned Rack AI packet confirms the same registered root and successful worktree preparation before executor failure.
- Initial and final accepted project SHA: `084f592b0a6796fcc68c38fbd3d296c2f6ce2278`. Project `main`, metadata, feature canonical base, and retained packet base/head agree. Final project status is clean; initial-to-final Git diff is empty.
- Rack AI head and controller provenance: `56d2c69f1e815acd12fca9065945c5e46de5a36a`.
- Evidence root (E below): `/srv/ATHBA/evidence/pr29-fresh-signalboard-20260905T162901Z`.
- Immutable fixture: BPQ-V1-B. Corpus SHA256 `523dc088007cdcd10484daa7cb272fdbdab4a37a306a5369bbeac1ff676d85cb`; fixture file SHA256 `3b1c2deec2369d5edc7dba79af76b5c90ea3a9b7f70b895f78237c1184300352`; original requirement SHA256 `c46ce04d165b64d2459fdd821475289925496dc7541584230d60f4858ec9aa88`. The loader output was written verbatim to `E/requirement.txt`.
- Both workers' `/health` and `/v1/models` returned HTTP 200. One local-primary `POST /v1/responses`, bounded to 60 seconds, returned exactly `READY` in 0.087381 seconds, response `resp_aaa52f42afdffe60`. Raw readiness request/response and endpoint metadata are retained. No service restart occurred.

The first CLI process failed during provider construction because the fresh SSH shell lacked `OPENAI_API_KEY`; it created no run or project and made zero proof model calls. Its error/exit are preserved in `E/preflight-launch-error.log` and `.exit`. The documented local invocation environment was then supplied: `OPENAI_API_BASE=http://127.0.0.1:8017/v1` and the documented non-secret local-primary bearer label. No configuration file was edited. The same unused identity was started, not resumed.

The evidence setup also set `TMPDIR=/srv/ATHBA/evidence/pr29-fresh-signalboard-20260905T162901Z/tmp` (63 bytes) to confine temporary files to ATHBA. This was a task-created process-environment choice and is explicitly disclosed: it may have contributed to the subsequent socket-path failure. It must not be described as an identical execution environment to the historical proof. No attempt was made to shorten it and retry after the terminal failure.

The unchanged `scripts/run_pr23_strict_tdd_feature.py start` used the above IDs, original requirement file, `--language python --test-framework pytest --production-path signal_board.py --test-path tests/test_signal_board.py --state-root /srv/ATHBA/state --evidence-root E`, with no checkpoint or budget override. Controller start was `2026-09-05T16:30:17.945163+00:00`; it stopped at `2026-09-05T16:31:35.121883+00:00`, exit 2, after six application transitions. A passive observer copied temporary v2 submission inputs; it did not wrap or alter a gateway.

### Real Behavior Contract

The real configured local-primary source-clause planner and Behavior Planner ran. The accepted, unedited contract contains **exactly seven Behavior Requirements**, not six. Full contract and source clauses are retained in `E/behavior-contract.json`. Advisory API names are `publish` and `get_signal`; no model-selected API was renamed or manually corrected. Planner output is recorded as evidence without endorsing its extra error semantics or interpreting it as final source conformance.

| Ref | Source refs | Summary | Observable outcome | test_hint | Dependencies |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | PR16-001 | Initial state is empty | The board starts with no published signals. | Verify that a new SignalBoard instance returns no values for any query. | none |
| REQ-002 | PR16-002 | Publishing a signal | A payload can be published under a specific name. | Publish a value and verify it can be retrieved by name. | REQ-001 |
| REQ-003 | PR16-003, PR16-004 | Update existing signal | Publishing to an existing name replaces the previous value. | Publish a value, then publish a different value for the same name and verify the second value is returned. | REQ-002 |
| REQ-004 | PR16-005 | Isolation of signal updates | Publishing to one name does not affect other names. | Publish values for two different names and verify that updating one does not change the other. | REQ-002 |
| REQ-005 | PR16-006 | Retrieve latest payload | The latest payload for a given name is retrieved. | Verify that the retrieval mechanism returns the correct payload for a known name. | REQ-002 |
| REQ-006 | PR16-007 | Architectural constraints | The component is small, direct, and dependency-free. | Verify the source code has no external dependencies and is concise. | none |
| REQ-007 | PR16-008 | In-memory constraint | The component is in-memory with no persistence. | Verify that data is lost when the SignalBoard instance is destroyed. | none |

### Independent Gatekeeper checklist

The configured checklist planner independently used the original requirement, not the Behavior Requirement list, and persisted twelve items before scenario submission. The composition's `SpecificationGatekeeper.ensure_state` supplies only project ID and original requirement text to checklist creation. Checklist state is not passed into Planner, scenario execution, Intent, Developer, or Senior Review; the captured Tester objective confirms its absence. `E/gatekeeper-checklist-state.json` preserves the complete state.

Final reconciliation was **not invoked**. `latest_assessment` is null and `assessment_history` and feature `final_reconciliation` are empty. All item results are NOT_REACHED; no YES/NO coverage judgment exists. The lifecycle event named `gatekeeper_completed` at sequence 3 denotes checklist creation only, not final Gatekeeper success.

| Ref | Kind | Independently generated obligation | Final result |
| --- | --- | --- | --- |
| initial_state | behavior | The SignalBoard must start with no published signals. | NOT_REACHED |
| publish_signal | behavior | The system must allow users to publish a payload under a specific signal name. | NOT_REACHED |
| replace_signal | behavior | Publishing a payload under an existing signal name must replace the previous payload for that name. | NOT_REACHED |
| isolate_signals | behavior | Publishing a payload for one signal name must not affect the values of other signal names. | NOT_REACHED |
| get_latest_payload | behavior | The system must allow users to request the latest payload for a specific signal name. | NOT_REACHED |
| return_latest_value | behavior | The system must return the most recently published value when a signal is requested. | NOT_REACHED |
| in_memory_storage | constraint | The SignalBoard must be an in-memory data structure. | NOT_REACHED |
| no_persistence | constraint | The system must not persist data to any external storage. | NOT_REACHED |
| no_subscriptions | constraint | The system must not support subscriptions. | NOT_REACHED |
| no_validation | constraint | The system must not implement validation rules. | NOT_REACHED |
| no_concurrency | constraint | The system must not handle concurrency. | NOT_REACHED |
| small_and_direct | quality | The component must be small, direct, and dependency-free. | NOT_REACHED |

### Behavior Requirement execution and revision progression

| Ref | Status | Counted Tester attempts | Intent | Frozen fragments | Frontiers completed | RED | GREEN | Regression | Senior Review | Canonical revision |
| --- | --- | ---: | --- | ---: | ---: | --- | --- | --- | --- | --- |
| REQ-001 | blocked: scenario_harness_failure | 0 | NOT_REACHED | 0 | 0 | NOT_REACHED | NOT_REACHED | NOT_REACHED | NOT_REACHED (0 attempts) | initial SHA unchanged |
| REQ-002 | NOT_REACHED | 0 | NOT_REACHED | 0 | 0 | NOT_REACHED | NOT_REACHED | NOT_REACHED | NOT_REACHED (0 attempts) | no progression |
| REQ-003 | NOT_REACHED | 0 | NOT_REACHED | 0 | 0 | NOT_REACHED | NOT_REACHED | NOT_REACHED | NOT_REACHED (0 attempts) | no progression |
| REQ-004 | NOT_REACHED | 0 | NOT_REACHED | 0 | 0 | NOT_REACHED | NOT_REACHED | NOT_REACHED | NOT_REACHED (0 attempts) | no progression |
| REQ-005 | NOT_REACHED | 0 | NOT_REACHED | 0 | 0 | NOT_REACHED | NOT_REACHED | NOT_REACHED | NOT_REACHED (0 attempts) | no progression |
| REQ-006 | NOT_REACHED | 0 | NOT_REACHED | 0 | 0 | NOT_REACHED | NOT_REACHED | NOT_REACHED | NOT_REACHED (0 attempts) | no progression |
| REQ-007 | NOT_REACHED | 0 | NOT_REACHED | 0 | 0 | NOT_REACHED | NOT_REACHED | NOT_REACHED | NOT_REACHED (0 attempts) | no progression |

REQ-001 reached a generic Rack AI submission but returned an external launch failure. Durable `attempts` is empty, `approved_microcycle` is null, and there is no candidate source or revision. Mechanical validation, independent Intent, freeze, deterministic fragment creation, RED, Developer, GREEN, regression, CAS promotion and Senior Review were not reached. Neither corrected boundary was live-qualified. No Behavior Requirement completed; execution stopped instead of selecting another independent requirement after the blocker. No microcycle or revision-lifecycle state was created.

### Submission, worker and packet evidence

Exactly one Rack AI workspace submission exists:

- Logical work ID: `pr29-fresh-signalboard-20260905T162901Z--REQ-001--scenario-draft`.
- Submission/idempotency ID: `pr29-fresh-signalboard-20260905T162901Z--REQ-001--scenario-draft-1`.
- Selection decision ID: `selection-pr29-fresh-signalboard-20260905T162901Z--REQ-001--scenario-draft-1`.
- Physical change identity: `pr29-fresh-signalboard-20260905T162901Z--REQ-001--scenario-draft--pr29-fresh-signalboard-20260905T162901Z--REQ-001--scenario-draft-1--submission-8484878532335806390`.
- ATHBA work-unit ID: `REQ-001--scenario-draft-1`.
- Selected worker: `local-primary`; model: `gemma4-12b-local-primary`; provider profile: `local-primary`; backend/worker kind: `jcode`; worker role: `generic-reasoning-worker`; resource: `gpu-4060ti`. Selection and returned provenance agree. This is selected execution identity, not proof that a model generation happened.
- Selection: `only_eligible`; required capabilities reasoning and coding; medium complexity/priority; no large-context request. local-coder was ineligible for this request (`capability_unsupported`).
- Allowed path: `tests/test_signal_board.py`; immutable 300-second timeout, one backend implementation attempt, network disabled. No limits or routing were changed.
- Packet status `failed`; acceptance `rejected`; `last_error: path must be shorter than SUN_LEN`. ATHBA records `failure_kind=external_blocker`, `failure_stage=workspace_result`, `backend_status=rejected`.
- Candidate revision/source: **none**. Packet `head_sha` equals the initial base and must not be reported as a generated candidate. `changed_paths`, `commands`, diff and implementer output are empty.
- Original Rack AI packet: `/srv/rack-ai/state/changes/pr29-fresh-signalboard-20260905T162901Z--REQ-001--scenario-draft--pr29-fresh-signalboard-20260905T162901Z--REQ-001--scenario-draft-1--submission-8484878532335806390/review-packet.json`.
- Exact retained copy: `/srv/ATHBA/evidence/pr29-fresh-signalboard-20260905T162901Z/rack-ai-packets/pr29-fresh-signalboard-20260905T162901Z--REQ-001--scenario-draft--pr29-fresh-signalboard-20260905T162901Z--REQ-001--scenario-draft-1--submission-8484878532335806390.json`.
- Complete objective, generic routing envelope and acceptance constraints: `E/execution-inputs/pr29-fresh-signalboard-20260905T162901Z--REQ-001--scenario-draft-1.json`. The packet also retains the objective under `task`. It contains only the focused REQ-001 ticket, source clause, strict mechanical authoring rules and initial repository facts; no Gatekeeper checklist or complete Behavior Contract was exposed.

All direct reasoning stages used the unchanged live composition's `ProviderReasoningGateway`, configured model `local-primary`, at the loopback endpoint. Metadata identifies `cyankiwi/gemma-4-12B-it-AWQ-INT4`. These direct stages do not have Rack AI submission IDs or packet paths: source-clause planning, Behavior Contract planning and independent checklist creation retain accepted structured output but not raw request/response IDs. Their prompt builders are unchanged source at the starting SHA. Raw historical prompts were not reconstructed and misrepresented as captured wire evidence. Intent, Developer, Senior Review and final Gatekeeper have no submissions.

### First terminal blocker and qualification limit

**EXTERNAL_BLOCKER**: executor launch failed with `path must be shorter than SUN_LEN`; outer run status `blocked`, typed scenario reason `scenario_harness_failure`.

The retained evidence establishes a socket-path-length execution failure, not a model timeout, malformed model reply, bad scenario, semantic rejection or RED-classifier defect. The task-specific temporary directory is a plausible contributor introduced during this task; the offending socket pathname and executor stack are not retained, so a causal attribution to that variable or to a particular Rack AI/JCode source line is not proven. No external source inspection or modification was performed to resolve that uncertainty. The owning boundary is local execution-environment/socket initialization behind the Rack AI/JCode execution path; exact component attribution remains unavailable.

The generic execution contract failed before producing a candidate: an admitted bounded workspace request selected a worker but could not initialize execution. ATHBA preserved the backend failure and correctly kept counted model attempts at zero. This is environment/path-sensitive, with no evidence that SignalBoard behavior or an API name caused it. No new ATHBA source defect is established. Because the task added a temporary-directory environment setting, this run cannot establish that the unchanged historical execution environment would fail. It provides **no conclusion** about the corrected architecture's ability to complete behavioral development and no model-incapability conclusion. No recovery or second proof followed.

### Model-call accounting

`MODEL_CALLS_MADE=AT_LEAST_4`: one retained READY generation plus at least one generation each for source-clause planning, Behavior Contract planning and checklist creation. There were three completed direct proof reasoning stages. A Behavior Contract format-repair call and low-level provider retries are not individually persisted by this path, so the exact wire-level count is unavailable; four is a lower bound, not an exact audit. The one Rack AI submission is separately counted and is **not** added as a confirmed model generation: zero Tester model attempts, zero worker model-output records. Cloud/OpenRouter calls: **0**. No post-terminal model calls were made.

### Evidence, preservation and validation

Authoritative state paths:

- Run: `/srv/ATHBA/state/runs/pr29-fresh-signalboard-20260905T162901Z.json`.
- Feature: `/srv/ATHBA/state/features/pr29-fresh-signalboard-20260905T162901Z.json`.
- Scenario: `/srv/ATHBA/state/scenario-drafts/pr29-fresh-signalboard-20260905T162901Z--REQ-001.json`.
- Microcycle/revision state: absent (not reached).
- Generated project metadata: `/srv/ATHBA/state/projects/pr29-fresh-signalboard-20260905T162901Z/project.json`.

E also contains `identity.json`, `initial-project.json`, immutable `requirement.txt`, health/model metadata, readiness request/response/summary, `execution-environment.json`, startup logs/exits, `capture.log`, `packet-index.json`, the full contract/checklist, and `terminal-snapshots/` of run, feature, scenario, lifecycle and final initial-only production source. Controller JSON/Markdown reports are `E/pr29-fresh-signalboard-20260905T162901Z/proof-report.json` and `proof-report.md`. `model-accounting.json` records the lower bound and uncertainty. `evidence-manifest.json` hashes retained files. Historical evidence/state was not resumed or edited; the previous documentation bytes are an exact prefix of this file.

ATHBA source, Tester/Intent prompts, Planner, Python adapter, scenario grammar, RED classifier, Frontier machinery, Developer, Senior Review, Gatekeeper, attempt/execution budgets, timeout values, worker routing, BPQ-V1, Rack AI, JCode and PR21 are unchanged. No TODO was addressed. No persistent configuration or service was changed. The process environment setup is disclosed above, including the temporary-directory deviation. The generated project's initial production placeholder was created by the ordinary environment service; no generated production or test candidate modified it thereafter.

Only this documentation file is staged and committed with `docs: record fresh SignalBoard end-to-end proof`; evidence remains untracked. Validation: `git diff --check` and documentation-prefix/source-scope checks. No source test suite is needed for this documentation-only change, and no target tests ran in this blocked proof. Push remains on PR29; no merge.


## Fresh proof after Rack AI hotfix: pr29-fresh-signalboard-20260905T172413Z

This separately authorized fresh run is **incomplete**. Rack AI's previous socket-path blocker did not recur: three real Tester submissions ran, and the third scenario passed mechanical validation and independent Intent Review. It froze into three fragments. The first Frontier's probe then failed before any RED assessment, and the adapter raised an uncaught `IndexError`. No post-stop resume, model retry, harness correction, or PR21 work occurred. All previous sections and evidence remain historical and unchanged.

### Identity, readiness and invocation

- Run/project: `pr29-fresh-signalboard-20260905T172413Z`; repository `/srv/ATHBA/state/projects/pr29-fresh-signalboard-20260905T172413Z/repository`.
- Initial and final accepted project SHA: `a738a8f433ee2224cb5349a4a7cd209bc9145410`. Canonical `main` remains clean and initial-to-final diff is empty. No trusted revision advanced.
- ATHBA starting branch/head: `pr29-live-tiny-strict-tdd-v2-proof` / `f1f34f37b1d8ff738ba83f2cbc95aad3c92e9c40`. This head differs from `a4ff78e268fcc3a12f38da88d939724dfac5be7c` only by the previous proof-documentation commit; architecture source is unchanged.
- Rack AI hotfix head and controller provenance: `469dc13c4d669266de21c629cc449f889364b7e2`. The user applied it before this task; this task made no Rack AI or JCode change.
- Tracked ATHBA files were clean; pre-existing untracked `evidence/` was preserved. Generated project/run identity did not exist before launch and resolved beneath `/srv/ATHBA/state/projects`, the already-approved trusted dynamic root. Returned packets confirm the same registered root.
- Evidence root (E below): `/srv/ATHBA/evidence/pr29-fresh-signalboard-20260905T172413Z`.
- BPQ-V1-B was loaded verbatim. Canonical corpus SHA256 `523dc088007cdcd10484daa7cb272fdbdab4a37a306a5369bbeac1ff676d85cb`; fixture file SHA256 `3b1c2deec2369d5edc7dba79af76b5c90ea3a9b7f70b895f78237c1184300352`; requirement SHA256 `c46ce04d165b64d2459fdd821475289925496dc7541584230d60f4858ec9aa88`.
- local-primary and local-coder health and metadata endpoints all returned HTTP 200. One bounded 60-second local-primary READY generation returned exactly `READY`, response `resp_ac1734c1a4a28e02`, in 0.088942 seconds. No healthy service was restarted.
- Local invocation used `OPENAI_API_BASE=http://127.0.0.1:8017/v1` and the documented non-secret local-primary bearer label. As disclosed before launch, `TMPDIR=/srv/ATHBA/evidence/pr29-fresh-signalboard-20260905T172413Z/tmp` retained the previous run's directory pattern to exercise the hotfix. No persistent configuration file was changed.

**Launch-environment omission:** the task did not supply the Django test environment, including `DJANGO_SECRET_KEY`. Endpoint readiness did not exercise pytest startup. The isolated reproduction below identifies that omission as the first underlying execution blocker; it must not be attributed to local-model incapability or hidden as a successful architecture qualification.

The unchanged full runner used `start`, fresh run/project IDs, `E/requirement.txt`, Python/pytest, production path `signal_board.py`, test path `tests/test_signal_board.py`, `/srv/ATHBA/state`, and E, with no checkpoint or budget override. Controller start was `2026-09-05T17:24:34.701377+00:00`; the last delivered transition was `state_initialised` at `2026-09-05T17:33:20.472503+00:00`. It then exited 1. A passive evidence observer copied temporary workspace inputs without modifying gateway behavior.

### Real Behavior Planner and full contract

The configured local source-clause planner and Behavior Planner produced **exactly five Behavior Requirements**. Their unedited accepted output is in `E/behavior-contract.json`, including every source clause and advisory API declaration. No Planner output, API name, dependency, or test_hint was manually edited.

| Ref | Source refs | Summary | Observable outcome | test_hint | Dependencies |
| --- | --- | --- | --- | --- | --- |
| REQ-001 | PR16-001 | Initial state is empty | SignalBoard starts with no published signals | Verify that a new instance returns no values for any query | none |
| REQ-002 | PR16-002, PR16-006 | Basic publish and retrieve | Payload can be published and retrieved | Publish a value and assert that the same value is returned | REQ-001 |
| REQ-003 | PR16-003, PR16-004 | Overwrite behavior | New payload replaces old payload for same name | Publish value A, then value B for same name, verify B is returned | REQ-002 |
| REQ-004 | PR16-005 | Isolation of signal names | New signal name does not affect existing signals | Publish value A for name X, then value B for name Y, verify X is still A | REQ-002 |
| REQ-005 | PR16-007, PR16-008 | Architectural constraints | Component is in-memory and dependency-free | Verify no external dependencies or persistence layers are initialized | none |

REQ-006 was not planned in this run. The source-clause and contract results are recorded as model output, not as proof of final source conformance. Existing test_hint handoff TODOs were not addressed.

### Independent Specification Gatekeeper checklist

Checklist creation completed before Tester submission using the original requirement. Ten independent items are retained in `E/gatekeeper-checklist-state.json`. The composition keeps this checklist out of Planner, Tester, Intent, Developer and Senior inputs; retained Tester objectives confirm no checklist exposure. No checklist item was added, corrected, or manually adjudicated.

Final Gatekeeper reconciliation was **not invoked**: latest assessment is null, assessment history is empty, and feature final reconciliation is empty. Every result below is NOT_REACHED; no accepted final-revision test evidence exists for a YES/NO judgment. The lifecycle `gatekeeper_completed` marker denotes checklist creation only.

| Ref | Kind | Independently created obligation | Final result |
| --- | --- | --- | --- |
| initial_state | invariant | A new board starts with no published signals. | NOT_REACHED |
| publish_signal | behavior | People can publish a payload under a signal name. | NOT_REACHED |
| replace_signal | behavior | Publishing a payload under an existing signal name replaces the previous current value for that name. | NOT_REACHED |
| isolation_of_signals | invariant | Publishing a payload under one signal name must not affect other signal names. | NOT_REACHED |
| get_latest_payload | behavior | The system must allow asking for the latest payload for a signal and return the most recently published value. | NOT_REACHED |
| no_persistence | constraint | The component must not provide persistence. | NOT_REACHED |
| no_deletion | constraint | The component must not provide deletion functionality. | NOT_REACHED |
| no_subscriptions | constraint | The component must not provide subscriptions. | NOT_REACHED |
| no_concurrency | constraint | The component must not provide concurrency support. | NOT_REACHED |
| small_and_direct | quality | The component must be small, direct, and dependency-free. | NOT_REACHED |

### REQ-001 Tester attempts and Intent

All three submissions selected `local-primary`, `generic-reasoning-worker`, backend/worker kind `jcode`, model `gemma4-12b-local-primary`, profile `local-primary`, resource `gpu-4060ti`. Every returned selection agrees with execution provenance. Capability routing remained reasoning plus coding, medium complexity/priority, no large context, selection `only_eligible`; local-coder was ineligible for that request with `capability_unsupported`. Each Tester envelope allowed only `tests/test_signal_board.py`, network disabled, unchanged 300-second timeout and one backend implementation attempt.

| Attempt | Submission identity | Rack status | Rack acceptance | Candidate revision | Retained worker generation records |
| --- | --- | --- | --- | --- | ---: |
| 1 | pr29-fresh-signalboard-20260905T172413Z--REQ-001--scenario-draft-1 | checks_passed | approved | 1f89a02cf98902d52058775f1870d4726a25b31d | 22 |
| 2 | pr29-fresh-signalboard-20260905T172413Z--REQ-001--scenario-draft-2 | failed | rejected | NONE | 9 |
| 3 | pr29-fresh-signalboard-20260905T172413Z--REQ-001--scenario-draft-3 | checks_passed | approved | ebd7dc39932d54b99c3efcea82b9ad81761b5185 | 17 |

1. Fresh draft: the worker created an empty test file and repeatedly reported that the production placeholder lacked code to exercise. Rack AI's syntax/artifact checks passed, but ATHBA mechanically rejected `no_test` and `missing_production_reference`. No Intent call occurred. The empty candidate source and revision are retained; the worker transcript explains the outcome without establishing general incapability.
2. Repair of candidate `1f89a02cf98902d52058775f1870d4726a25b31d`: JCode timed out after 300 seconds, with no new candidate. Persisted outcome is `worker_model_timeout`. Its packet head is the repair base, not a new candidate. The existing bounded policy continued; timeout was not a terminal semantic verdict.
3. `retry_repair_from_existing_candidate`, still bound to the retained attempt-1 candidate: returned `ebd7dc39932d54b99c3efcea82b9ad81761b5185`. Mechanical validation accepted it with no issues. Independent Intent approved in one response, evidence `PR16-001`. No fourth attempt was submitted.

The exact third candidate and frozen scenario are identical:

```python
from signal_board import SignalBoard

def test_REQ_001():
    sb = SignalBoard()
    assert len(sb.signals) == 0
```

Intent rationale: The test correctly instantiates the SignalBoard and asserts that the length of the signals list is zero, directly verifying that the board starts with no published signals as required.

This confirms that a mechanically valid scenario using `signals` reached independent Intent Review. The full Behavior Contract and checklist were not exposed to the Tester. The approved scenario was frozen by the application, not manually authored or edited.

### Fragments, Frontiers and requirement outcomes

Deterministic atomization produced:

| Index | Fragment | Source line | State |
| --- | --- | ---: | --- |
| 0 | `from signal_board import SignalBoard` | 1 | Active; materialized; probe startup failed before RED classification |
| 1 | `sb = SignalBoard()` | 4 | Frozen fragment only; no active Frontier execution |
| 2 | `assert len(sb.signals) == 0` | 5 | Frozen fragment only; no active Frontier execution |

Only Frontier 0 was activated. No complete-scenario RED shortcut was used. Boundary evidence is empty, accepted RED is null, Developer attempts are empty, regression and Senior Review remain pending, and zero Frontiers completed. The corrected missing-capability assertion classifier was **not reached**.

| Ref | Status | Tester attempts | Intent | Fragments | Frontiers completed | RED | GREEN | Regression | Senior Review |
| --- | --- | ---: | --- | ---: | ---: | --- | --- | --- | --- |
| REQ-001 | blocked by process crash; behavior incomplete | 3 | APPROVED | 3 | 0 | ERROR_BEFORE_CLASSIFICATION | NOT_REACHED | NOT_REACHED | NOT_REACHED (0 attempts) |
| REQ-002 | NOT_REACHED | 0 | NOT_REACHED | 0 | 0 | NOT_REACHED | NOT_REACHED | NOT_REACHED | NOT_REACHED |
| REQ-003 | NOT_REACHED | 0 | NOT_REACHED | 0 | 0 | NOT_REACHED | NOT_REACHED | NOT_REACHED | NOT_REACHED |
| REQ-004 | NOT_REACHED | 0 | NOT_REACHED | 0 | 0 | NOT_REACHED | NOT_REACHED | NOT_REACHED | NOT_REACHED |
| REQ-005 | NOT_REACHED | 0 | NOT_REACHED | 0 | 0 | NOT_REACHED | NOT_REACHED | NOT_REACHED | NOT_REACHED |

Zero Behavior Requirements completed. No dependency-ready requirement was selected after the crash. Canonical revision stayed `a738a8f433ee2224cb5349a4a7cd209bc9145410`. A managed working ref was initialized at that same SHA; no RED/GREEN/regression/CAS promotion occurred. Tester candidate branches contain test-only changes but are not trusted project progression. Generated production source remains the initial placeholder; no Developer was invoked.

### First blocker, generic defect and isolated reproduction

Primary classification: **EXTERNAL_BLOCKER**, pytest startup environment incomplete. The one post-stop reproduction, using the same interpreter/environment and an isolated copy of the deterministic first Frontier under E, returned exit 1, zero stdout bytes, and stderr ending in:

```text
ImportError: Set the DJANGO_SECRET_KEY environment variable
pytest-django found a Django project in /srv/ATHBA (it contains manage.py)
```

The launch omitted that test environment. The reproduction used the production probe command with a 30-second bound; it did not invoke models, resume the controller, change live state or generate a new Rack AI submission. Before/after hashes of run, feature, scenario and microcycle state were identical. Its inputs, stdout, stderr and hashes are retained in `E/probe-reproduction.json`, `.stdout`, `.stderr` and `E/probe-reproduction/`. The original disposable Frontier worktree was removed by existing cleanup; the original probe's stderr was not persisted, so this is clearly labeled reproduction evidence, not recovered original stderr.

A secondary **generic ATHBA_HARNESS_DEFECT** is directly established by the original traceback and source: `PytestStructuredExecutor.execute` in `core/development/python_pytest_adapter.py:582` evaluates `completed.stdout.splitlines()[-1]` and catches only `json.JSONDecodeError`. Empty stdout raises `IndexError`, losing subprocess exit/stderr facts instead of returning the typed infrastructure diagnostic expected by the adapter boundary. Any probe startup failure with empty stdout can trigger it; no SignalBoard name or scenario-specific condition is involved. The owner is the Python adapter's subprocess-output handling. Probe startup/settings discovery owns the underlying environment dependency. No fix was made to either.

Actual terminal process status is **CRASHED_EXIT_1**, not a fabricated typed `blocked` result. Persisted run and feature statuses remain `running`; run reason is `application_transition_exception_before_receipt`, with eleven delivered application transitions, no pending receipt and no in-flight marker. Microcycle pending action remains `observe_frontier`. The controller exception path saves that reason and re-raises; it produced no final JSON/Markdown proof report. Snapshot documentation does not alter those statuses or attempt recovery.

The first empty Tester candidate and subsequent timeout were handled by the normal bounded path and were not the terminal blocker. Neither model incapability nor assertion-RED failure is inferred. The hotfix enabled actual workspace execution; this run still does not establish end-to-end architectural completion. No post-terminal environment fix, retry or new proof followed.

### Model accounting and every submission's evidence

There were **eight top-level model-backed invocations/submissions**: READY, source-clause planning, Behavior Planner, independent checklist creation, three Tester workspace submissions and one Intent Review. Retained JCode transcripts contain 22 + 9 + 17 = **48 worker generation records**. Adding five completed direct generations gives **at least 53 observed/required generation records**. Exact HTTP-call count is not persisted: a contract format-repair call, transport retries or an in-flight generation at timeout may not be individually visible. These limits are recorded in `E/model-accounting.json`; 53 must not be presented as an exact wire audit. Cloud/OpenRouter calls: **0**.

All direct stages used configured local-primary at the loopback Responses endpoint; metadata identifies the serving model in `E/local-primary-models.json`. Direct stages have no Rack AI packet or submission ID. Accepted source clauses/contract/checklist/Intent are persisted, while their raw request/response IDs are not; READY has a retained raw response. Prompt builders are unchanged at the starting ATHBA SHA. No raw prompt was reconstructed and mislabeled as captured evidence. Developer, Senior and final Gatekeeper have no invocations.

Each workspace submission's logical work ID is `pr29-fresh-signalboard-20260905T172413Z--REQ-001--scenario-draft`; submission IDs are the distinct `...--scenario-draft-1`, `-2`, and `-3` values above. `E/submission-summary.json` includes complete selection decisions, physical change IDs, provenance, candidate/head distinctions, result classifications, command evidence and generation-record counts. `E/execution-inputs/` retains all three original generic envelopes with exact objective, repair lineage, immutable context, allowed paths and budgets. Candidate source is retained in authoritative scenario state. `E/packet-index.json` links original packets to exact copies in `E/rack-ai-packets/`.

Original packet paths:

- `/srv/rack-ai/state/changes/pr29-fresh-signalboard-20260905T172413Z--REQ-001--scenario-draft--pr29-fresh-signalboard-20260905T172413Z--REQ-001--scenario-draft-1--submission-14418578062428706533/review-packet.json`
- `/srv/rack-ai/state/changes/pr29-fresh-signalboard-20260905T172413Z--REQ-001--scenario-draft--pr29-fresh-signalboard-20260905T172413Z--REQ-001--scenario-draft-2--submission-14418574763893821900/review-packet.json`
- `/srv/rack-ai/state/changes/pr29-fresh-signalboard-20260905T172413Z--REQ-001--scenario-draft--pr29-fresh-signalboard-20260905T172413Z--REQ-001--scenario-draft-3--submission-14418575863405450111/review-packet.json`

### State, preservation, scope and validation

- Scenario state: `/srv/ATHBA/state/scenario-drafts/pr29-fresh-signalboard-20260905T172413Z--REQ-001.json`.
- Microcycle state: `/srv/ATHBA/state/microcycles/pr29-fresh-signalboard-20260905T172413Z--REQ-001.json`.
- Run and feature: `/srv/ATHBA/state/runs/pr29-fresh-signalboard-20260905T172413Z.json` and `/srv/ATHBA/state/features/pr29-fresh-signalboard-20260905T172413Z.json`.
- Revision lifecycle: `/srv/ATHBA/state/revisions/microcycle-revisions/2b0690f73bb158c2edfa0f0ae64e690fe21de4628cf89ba989fff0aebf21dcd4.json` (initialized only).
- Lifecycle events: `/srv/ATHBA/state/lifecycle-events/lifecycle-runs/6a8306c06261099ef83d2fa38a11fee544a317fde3e94924c7657f6314703630/events.jsonl`.

E retains identity, initial project metadata, immutable requirement, readiness request/response and both workers' endpoint evidence, execution-environment record, runner log/exit, observer and original inputs, complete contract/checklist, packet copies/index/summary, model accounting, diagnostic reproduction, and terminal snapshots including frozen scenario and initial-only production source. A separate `terminal-summary.json` records the process crash without changing live state. `evidence-manifest.json` hashes retained artifacts. Historical runs were neither resumed nor edited; prior document bytes remain an exact prefix.

No ATHBA source, Tester/Intent prompt, Behavior Planner, Python adapter, grammar, RED classifier, Frontier machinery, Developer, Senior Review, Gatekeeper, attempt budget, execution budget, timeout, routing, BPQ-V1, Rack AI, JCode or PR21 was changed during this task. No TODO was addressed, no persistent configuration changed and no service restarted. Only proof documentation is committed. Generated test candidates exist solely as retained noncanonical Tester work; canonical project production and tests did not advance.

Validation for this documentation-only update: `git diff --check`, exact historical-prefix preservation, unchanged source scope, immutable fixture hash and unchanged Rack AI head. No source suite was run; the isolated probe diagnostic is not a behavioral test PASS. Commit message: `docs: record fresh SignalBoard end-to-end proof`. Push targets PR29; no merge.
