# PR29 live SignalBoard strict-TDD proof

## Observation Resolver experiment reversion

The just-in-time Observation Resolver experiment was introduced in `0505e11` and
its role-specific fenced-JSON handling was corrected in `c5ac723`. Review later
determined that this introduced a new LLM semantic decision in the wrong layer.
Both commits were explicitly reverted on this PR29 branch; their semantic
qualification results remain historical evidence only.

This does not establish that local-primary is generally unqualified for Behavior
Planning, Tester work, or other roles. The deterministic Behavior Contract
public-surface lint and its held-out/restart persistence regressions predate the
experiment and remain retained. This reversion does not alter Gatekeeper behavior,
does not resume or create a SignalBoard proof run, and does not affect PR21.

## Scope

This document records the first real tiny strict-TDD feature attempt through the
ATHBA to Rack AI v2 workspace-execution path. SignalBoard is a fresh disposable
Python/pytest fixture. ReservationBook and concurrent work are out of scope.

## Pre-execution change gate: generic ATHBA execution-port composition

1. **Documented generic contract.** ATHBA's boundary rationale and PR23 routing
   architecture require artifact-producing work to cross the generic
   `RackAiWorkspaceConnector` boundary, which serializes `rack-ai/work-unit/v2`.
2. **Observed violation.** At ATHBA `0527113007d2d786cd801a190da29ce71590c569`,
   `StrictTddFeatureCompositionFactory` instead selected
   `RackAiCliExecutionGateway` whenever no test gateway was injected. That
   gateway serializes the pre-v2 `RackAiChangeRequest` schema, so the durable
   production runner could not exercise the qualified v2 connector.
3. **Generic reproduction.** The condition depends only on the composition
   request having no injected gateway; it is independent of SignalBoard,
   generated scenario content, model output, and Rack AI worker selection.
4. **Owning component.** ATHBA's strict-TDD feature composition and the
   existing profiled workspace gateway adapter.
5. **Required deterministic regression.** A composition test must prove that
   the default production gateway is the profiled v2 workspace adapter, and an
   adapter test must retain the candidate branch and complete worker provenance
   returned by the generic workspace port.

No model invocation was made before this gate. No Rack AI source or configuration

## Scenario harness evidence integrity correction

**Documented contract.** Terminal fail-closed transitions must preserve enough evidence to classify the owning failure boundary.

**Observed behavior.** `scenario_harness_failure` persisted without diagnostic evidence.

**Why generic.** This applies to every scenario-draft external or harness failure, independent of feature, model, worker, or fixture.

**Correction.** Persist typed, bounded harness-failure evidence.

**Semantic behavior changed:** NO

**Attempt accounting changed:** NO

**Harness accommodation:** NO

## Local-primary runtime interruption before fresh proof

- ATHBA checkpoint: `d51d9d2925b44ba60f39fb47df2a27e1af99da3e`.
- Rack AI checkpoint: `56d2c69f1e815acd12fca9065945c5e46de5a36a`.
- The pre-existing proof handoff reported a stalled `/v1/responses` READY probe
  despite successful local-primary health and model metadata endpoints. It did
  not retain a curl exit code, HTTP status, or timing for that earlier stalled
  request, so those historical details are unavailable rather than inferred.
- At `2026-09-03T11:50:54Z`, `/health` and `/v1/models` each returned HTTP 200.
  The advertised model was `local-primary` backed by
  `cyankiwi/gemma-4-12B-it-AWQ-INT4`.
- Docker's existing `vllm-primary` service was `Up 11 days (healthy)` on port
  8017. Its EngineCore held 14,116 MiB on the RTX 4060 Ti at 0% utilization;
  no active TCP connection to port 8017 remained after probing. No active Rack
  AI durable work status was found.
- The current bounded READY probe returned curl exit 0, HTTP 200, and completed
  response text `READY` in 0.088474 seconds. A second probe after a short wait
  independently returned curl exit 0, HTTP 200, and `READY` in 0.087607 seconds.
- No restart was required: the existing service was already generating normally
  when rechecked. Local-coder `/health` and `/v1/models` also returned HTTP 200.
- No model identity, endpoint, GPU assignment, context limit, vLLM option,
  JCode tool profile, ATHBA source, or Rack AI source was changed for this
  operational check.

## Fresh SignalBoard run: stopped at typed scenario harness failure

- Fresh run and project: `pr29-signal-board-20260903T115600Z`.
- Real behavior planning and independent Gatekeeper atomization completed before
  the first selected behavior, `REQ-001` (`SignalBoard.create`).
- The scenario draft transition stopped at `scenario_harness_failure` with
  `failure_stage=workspace_result` and `failure_kind=external_blocker`.
- Durable harness evidence identifies work unit `REQ-001--scenario-draft-1` and
  reports that the new ATHBA repository is outside Rack AI trusted dynamic roots.
- Rack AI returned before creating a submission, selection decision, worker
  provenance, candidate revision, or durable Rack AI state for this work unit.
- This is a trusted-root operational-policy blocker, not a SignalBoard,
  local-primary, local-coder, ATHBA semantic, or Rack AI routing defect.
- The run was not retried or resumed. No source/configuration or test-grammar
  change was made to bypass the trusted-root policy.

## Trusted dynamic root proof correction

- Historical failed run/project: `pr29-signal-board-20260903T115600Z`.
- Its repository was `/srv/ATHBA/state/pr29-signal-board-20260903T115600Z/projects/pr29-signal-board-20260903T115600Z/repository`; Rack AI correctly rejected it as outside trusted dynamic roots.
- ATHBA derives project repositories from `state_root/projects`; the live Rack AI administrator policy already approves `/srv/ATHBA/state/projects`.
- The corrected live composition used state root `/srv/ATHBA/state`, without changing Rack AI configuration or static registration.
- New run/project: `pr29-signal-board-20260903T123300Z`.
- Its repository is `/srv/ATHBA/state/projects/pr29-signal-board-20260903T123300Z/repository`; its resolved realpath is identical and remains beneath the approved root.
- The project is ready, Git-initialized, and has trusted base revision `38d17b74dc41e733bdfaf346acabb868dc46d018`.

## Corrected SignalBoard run evidence

- Real behavior planning, independent Gatekeeper atomization, and Rack AI v2 scenario authoring crossed trust admission; scenario submissions selected and were executed by `local-primary` with matching provenance.
- REQ-001 produced an approved scenario and one accepted narrow `local-coder` change; its canonical test was retained.
- REQ-002's first scenario was rejected by independent intent review, and its second was structurally accepted but drifted to `SignalBoard.Publish` plus undocumented `payloads` behavior.
- ATHBA failed closed at `unsupported_language_boundary` after the resulting RED evidence; this is model-originated semantic drift, not a trusted-root or routing defect.
- A controlled terminal resume returned blocked (exit 2) without repeating submissions, frontiers, scenario attempts, or developer attempts.
- No ATHBA or Rack AI source, Rack AI trust policy, JCode profile, strict grammar, or execution budget was changed.

## REQ-002 semantic-drift forensics and generic correction

The first divergence was a generic source-evidence propagation defect, not a
second Tester reliability trial. The preserved feature contract is the
authoritative record; the local-primary raw intent-review reply was intentionally
ephemeral, while its decoded disposition, rationale, and symbolic evidence refs
are durably retained in the scenario state.

| Stage | Durable evidence | Finding |
| --- | --- | --- |
| Original requirement | Feature state `original_requirement` and `SignalBoard.Publish` clause | Exact lower-case `publish(name, payload)` is required; no additional behavior is permitted. |
| Behavior planner hand-off | REQ-002 behavior plus the Rack AI scenario packets | The ticket reduced that clause to `Publish signal payload`, a generic outcome, and opaque `SignalBoard.Publish`; it did not carry the exact source text to either model. |
| Gatekeeper | Gatekeeper checklist item `SignalBoard.publish` | It retained the exact lower-case API text, but that text was not forwarded through the scenario-draft boundary. |
| Tester attempt 1 | Draft state, candidate `4bc009c121ba19659b7b4dcf9945aa0548c962db` | `insufficient_evidence`: it only constructed SignalBoard; its review feedback already referred to `Publish`. |
| Tester attempt 2 | Draft state, candidate `2c80016a98db8bd94823c86147be36ddf6c066e8` | Structurally valid and intent `approved`, but calls `board.Publish("data", "key1")` and asserts undocumented `board.payloads["key1"]`. |
| Intent review | Persisted approved disposition/rationale and request construction | The reviewer saw the same lossy ticket and opaque ref, not the exact source clause; approval therefore cannot establish correct source semantics. |
| Scenario freeze | Approved draft state and immutable microcycle | Freeze occurred only after approval; no freeze-state transition occurred before review. |
| Frontier and boundary | REQ-002 microcycle boundary evidence | `Publish` first yielded valid missing-capability RED. After a narrow developer change promoted `Publish(data, key)`, the invented `payloads` assertion yielded typed `unsupported_language_boundary`; that classifier behaved correctly. |

The canonical fixture revision `d397d2e60743a4d822cfbd302d6dbe785d2e8046`
contains the wrong `Publish(data, key)` production method. It was promoted before
the terminal boundary, so this prior proof remains FAIL and is retained unchanged
as failure evidence.

### Correction

`ScenarioDraftRequest` now transports ordered, typed `SourceRequirementClause`
evidence selected by the behavior's source refs. Both `_tester_objective` and the
independent `_intent_prompt` serialize that same evidence under
`source_requirements`; the feature executor rejects a behavior whose source refs
are absent from its contract. This is generic to any contract clause and does not
special-case SignalBoard, `publish`, casing, payloads, or a model/provider.

`test_author_and_intent_reviewer_receive_exact_source_requirement_evidence` is a
neutral deterministic reproduction: it asserts exact source evidence reaches both
the Tester and Reviewer payloads. It would fail on the prior implementation,
which emitted only `source_requirement_refs`.

Validation before publication: 46 focused tests passed; coding principles passed;
mypy reported no issues in 29 source files; compileall passed; the complete suite
passed (`526 passed`). Rack AI source/configuration, JCode tool profile, strict
test grammar, execution budgets, and the preserved initial run were not changed.

### Fresh-project identity collision and correction

The first post-correction fresh project, `pr29-signal-board-20260903T132400Z`,
reached real planning and Gatekeeper atomization with the corrected lower-case
`SignalBoard.publish` source ref and exact source clause, but failed before a
Tester candidate. Rack AI correctly returned `duplicate idempotent submission`
for the globally reused `REQ-001--scenario-draft-1` submission id.

Forensics located the owner in ATHBA's `ScenarioDraftWorkUnitFactory`: it derived
all three workspace identities from the unscoped ticket ref. The generic
correction scopes `work_id` to the durable `scenario_id` (stable across attempts)
and derives a distinct attempt `submission_id`/idempotency key. The deterministic
test proves same-scenario retries retain their work id while both retry and a
different fresh project receive distinct submissions. This does not alter Rack AI,

### Second fresh live attempt after both generic corrections

Run/project `pr29-signal-board-20260903T133400Z` used ATHBA
`8639c0247d8b79ac5b4566414b93658aeeabad22` and Rack AI
`56d2c69f1e815acd12fca9065945c5e46de5a36a`. It created distinct scenario-scoped
Rack submissions and completed REQ-001 through approved scenario, typed RED,
accepted Developer candidates, GREEN, regression, canonical promotion, and
scenario completion. The scenario's independent review rationale cites
`SignalBoard.create`; the source-evidence transport operated on the exact source
clause selected for the behavior.

Immediately after REQ-001 completion, the real Senior behavior reviewer returned
a response that was not valid JSON. The runner surfaced `invalid_input` and the
durable run/feature state remains `running` at the persisted terminal transition;
no REQ-002 scenario was created in this attempt. This is unambiguous real-model
protocol failure evidence, not permission to retry, change prompts or grammar,

## Senior behavior-review structured protocol correction

**Documented generic contract.** Model-backed structured semantic decisions must
produce a valid typed decision or retain typed fail-closed protocol evidence.

**Observed live violation.** REQ-001 reached the real Senior behavior reviewer,
whose response was invalid JSON. `ProviderSeniorBehaviorReviewer` raised rather
than retaining bounded protocol recovery and evidence.

**Existing precedent.** `ScenarioIntentReviewer` permits one format-only repair
response for malformed structured output.

**Correction.** Senior review performs one semantic request and at most one
JSON-format repair. Maximum semantic attempts: **1**. Maximum response attempts:
**2**. A double-invalid response persists a typed protocol failure and leaves the
behavior blocked. A restart does not automatically rereview it.

Prompt semantic scope changed: **NO**. Strict grammar changed: **NO**. Execution
budget changed: **NO**. Feature-specific accommodation: **NO**.

## Behavior Contract immutable-authority correction

**Observed live blocker.** Fresh SignalBoard run `pr29-signal-board-20260903T142900Z` created its disposable project and then failed closed during Behavior Contract planning with `requirement_source must preserve the original requirement text exactly`. Its immutable original requirement is preserved byte-for-byte in lifecycle metadata and the terminal JSON log is retained. The final mismatch proves the returned `requirement_source` differed from that authoritative input, but neither returned value was persisted, so their exact text is unavailable. Under the then-current recoverable-error path, that terminal mismatch follows one `athba_behavior_contract_repair` call; neither raw provider response nor a separate repair event was persisted. The model-emitted `project_id`, `source_clauses`, and status are likewise unavailable, so their divergence cannot be determined retrospectively.

**Existing design.** The Behavior Contract reasoning model was asked to echo immutable caller, source, and control-plane fields in the final aggregate object.

**Generic defect.** Immutable authoritative state was unnecessarily delegated to model transcription. An LLM must not be given authority over immutable caller-supplied or deterministic workflow state merely because that data appears in the final aggregate object.

**Authoritative fields.** `project_id`, exact `requirement_source`, the exact `source_clauses` emitted by `RequirementClausePlanner`, and initial status `tdd_ready`. ATHBA now installs them deterministically at contract construction before normal typed validation.

**Model semantic authority retained:** YES.

**Source semantic validation retained:** YES.

**Behavior Contract semantic repair retained:** YES, for genuine semantic defects such as missing source-clause coverage.

**Feature-specific accommodation:** NO.

**Rack AI change:** NO.


## Nested transition fingerprint correction

The preserved live run `pr29-signal-board-20260903T155905Z` was not resumed or modified. Consecutive occurrences 5 and 6 were both `FEATURE=scenario_advanced`, `SCENARIO=scenario_draft_candidate_submitted`, with no microcycle kind. Their old controller-visible fingerprint was identical: `status=running`, `behavior_ref=REQ_001`, `scenario_id=pr29-signal-board-20260903T155905Z--REQ_001`, `frontier_index=null`, `canonical_sha=006bd556063c8f46bb1fc12253df4a0a6f8773d0`, `working_sha=null`, `retry_counts=(0,)`, `pending_action=scenario_advance`.

Durable state changed: attempt 1 was a real `local-primary` `worker_model_timeout` with no candidate; attempt 2 was real `local-primary` `candidate_submitted` with candidate revision `b7f31585ca7199ad18e4e8d43a2fbeef6a00de39`. The old paths and fingerprints were equal even though persisted attempt count, latest outcome, candidate revision, and actual next action differed.

Fingerprint equality means no stable persisted workflow progress relevant to the next deterministic transition. Evidence prose, timestamps, random IDs, and transient logging remain excluded; attempts, frontiers, retries, revisions, and actual pending action must not be flattened. The scenario action is now derived from `ScenarioDraftRunState`: no candidate -> draft submission; accepted unreviewed candidate -> intent review; terminal -> blocked; approved without lifecycle -> revision initialisation; active microcycle -> its child action. Scenario fingerprints include attempt/candidate progress and lift microcycle identity; features retain those fields while preserving their outer status.

Neutral ExampleWidget regressions prove timeout->candidate and timeout->timeout do not false-stall, candidate reaches intent review without duplicate submission, nested microcycle progress survives both wrappers, and genuinely unchanged state still stalls. Root cause: wrapper projection discarded nested stable scenario/microcycle identity. Controller safety guard changed: NO. Feature-specific accommodation: NO. Rack AI change: NO.


## 18:17 SignalBoard unsupported-language-boundary forensics

The terminal run `pr29-signal-board-20260903T181700Z` is immutable and was not resumed. It blocked at REQ_002, frontier index 3 of 6: active `python-4-assertion`, source line 7, `assert board.get("name") == "payload"`. The probe recorded `pytest_failure`, collection/requested-node/setup/teardown success, call failure, and `AttributeError: 'SignalBoard' object has no attribute 'get'` at `/tmp/athba-frontier-pirr6w6i/tests/test_signal_board.py:7`. The line is inside the active fragment span 7-7.

| Stage | Evidence | Semantically correct? |
| --- | --- | --- |
| Source requirement | `publish(name, payload)` records a payload; retrieval is explicitly `latest(name)` in SignalBoard_003. | YES |
| Behavior Contract | REQ_002 is `Publish payload`, observable outcome `Payload is stored for the given name`, source ref SignalBoard_002. | YES |
| Gatekeeper | SignalBoard_Publish: `publish(name, payload) records the payload for that signal name.` | YES |
| Behavior ticket | REQ_002 `Publish payload`; test hint `Verify payload storage for specific name`; paths `signal_board.py` and `tests/test_signal_board.py`. | YES |
| Approved scenario | `board.publish("name", "payload")` followed by three `board.get("name")` assertions. | NO |
| Intent review | Approved that exact scenario while citing SignalBoard_002 and asserting that `get` verified stored payload. | NO |
| Frontier decomposition | Preserved the approved source exactly: the active assertion is line 7 of that source. | YES |
| Prior production state | Import and constructor were GREEN; `publish` was an active-call valid missing-capability RED, then GREEN after promotion `f66f5ce3c9c109c71dfeda396d7103d5b394e34e`. | YES |
| Active runtime failure | AttributeError at active assertion span 7-7, for invented `get`, after `publish` had already been GREEN. | Fail-closed correct |
| Boundary classifier | Assertion-only behavioral RED does not accept AttributeError; it returned `unsupported_language_boundary`. | YES |

The complete approved REQ_002 source was:

```python
import pytest
from signal_board import SignalBoard


def test_REQ_002():
    board = SignalBoard()
    board.publish("name", "payload")
    assert board.get("name") == "payload"
    assert board.get("name") == "payload"
    assert board.get("name") == "payload"
```

The exact source clause supplied to both authoring and intent review was `SignalBoard_002`: `The publish(name, payload) function shall record the payload associated with the specified signal name.` The Behavior Contract and Gatekeeper separately preserved the original `latest(name)` retrieval requirement as REQ_003/SignalBoard_Latest; neither authorizes `get` for REQ_002.

The first semantic divergence is the approved scenario's introduction of `get`. The reviewer received the correct source evidence, cited it, and nevertheless approved the semantic divergence. Root classification: `MODEL_INTENT_REVIEW_SEMANTIC_FAILURE`. The boundary classifier is intentionally fail-closed and no classifier, probe, grammar, prompt, budget, routing, controller, Rack AI, or production change is justified. No neutral classifier reproduction, source fix, resumed run, or new SignalBoard run was created.

## local-primary scenario-intent reviewer qualification

### Motivation and fixed threshold

The immutable 18:17 SignalBoard forensics showed that the exact production ScenarioIntentReviewer approved a scenario that invented board.get(...) under the active SignalBoard_002 source clause. This qualification measures the current unchanged local-primary model at the existing ATHBA reviewer boundary; it is not a source correction, prompt change, routing change, or a new SignalBoard run.

Before execution, the fixed rule was declared as follows: six neutral deliberately unsupported cases and three neutral valid cases would each be reviewed independently three times, then the preserved SignalBoard REQ_002 failure request would be replayed three times. Qualification requires all 18 neutral invalid reviews to be non-approved, every valid case to be approved at least two of three times, and all three SignalBoard replays to be non-approved. Any approval of an unsupported scenario means NOT_QUALIFIED_FOR_SEMANTIC_INTENT_REVIEW.

The unchanged production path used ScenarioIntentReviewer with ATHBA's ProviderReasoningGateway(OpenAIProvider(ProviderRetryPolicy(timeout=300.0, max_retries=1, backoff_factor=2.0)), local-primary). Each request used typed SourceRequirementClause evidence, PythonPytestAdapter-derived canonical identity, fragment kinds, and static analysis. The reviewer prompt, decoder, response schema, provider/model configuration, routing, and source evidence transport were unchanged. Each completed review decoded on its first natural response; no JSON-format repair call was needed.

### Neutral corpus

The neutral KeyLedger source clauses were: KL-001 construction; KL-002 put(name, value) records a value; KL-003 latest(name) returns the most recently recorded value for a name; and KL-004 values under different names remain independent. Valid cases covered construction, put plus latest, and independent names. Invalid cases covered an invented get, invented deletion, case normalization, payload trimming, future-behavior leakage by withholding KL-003 while asserting latest, and an incomplete scenario that never calls put.

### Dispositions

| Case | Run 1 | Run 2 | Run 3 | Unsafe approvals |
| --- | --- | --- | --- | --- |
| VALID-1 construction | insufficient_evidence | insufficient_evidence | insufficient_evidence | n/a |
| VALID-2 put + latest | approved | approved | approved | n/a |
| VALID-3 independent names | approved | approved | approved | n/a |
| INVALID-1 invented retrieval API | approved | approved | approved | 3 |
| INVALID-2 invented delete behavior | wrong_behavior | wrong_behavior | wrong_behavior | 0 |
| INVALID-3 invented normalization | semantic_repair_required | semantic_repair_required | semantic_repair_required | 0 |
| INVALID-4 invented transformation | approved | approved | approved | 3 |
| INVALID-5 future-behavior leakage | approved | approved | approved | 3 |
| INVALID-6 incomplete evidence | insufficient_evidence | insufficient_evidence | insufficient_evidence | 0 |
| SignalBoard REQ_002 held-out replay | approved | approved | approved | 3 |

All responses cited only the source refs supplied to that specific review. The unsafe approvals are therefore semantic failures under the active evidence scope, rather than a failure to supply a known requirement. In particular, the held-out replay supplied only SignalBoard_002, retained the historical approved board.get(...) scenario and exact behavior ticket/static facts, and received approved all three times.

### Result

NEUTRAL_INVALID_REVIEWS = 18; NEUTRAL_INVALID_UNSAFE_APPROVALS = 9.

VALID_REVIEWS = 9; VALID_APPROVALS = 6. VALID-1 was rejected all three times as insufficient evidence because the reviewer demanded an assertion for construction; that is a false negative under the declared construction case, but it does not affect the safety classification.

SIGNALBOARD_REPLAY_REVIEWS = 3; SIGNALBOARD_REPLAY_UNSAFE_APPROVALS = 3.

The fixed threshold therefore yields QUALIFICATION_RESULT = NOT_QUALIFIED_FOR_SEMANTIC_INTENT_REVIEW.

Current local-primary is not sufficiently reliable to be the sole independent semantic scenario gate. This qualification does not assess its suitability for planning, scenario drafting, coding, or other reasoning roles. No follow-up SignalBoard proof was launched, and no reviewer-model routing decision was made in this work.

## Intent-review qualification interpretation correction

The production Intent Reviewer asks whether a complete GREEN scenario demonstrates the requested Behavior Planner ticket. The historical SignalBoard `publish` plus `get` scenario had that broad storage-proof intent, so the earlier result does not establish that local-primary failed this narrower reviewer role. It instead measured an unsuitable stronger responsibility: strict product-surface and source-conformance authority. The retained evidence remains useful: local-primary must not be the sole authority for mechanically provable product-surface/specification conformance. That authority is now assigned to deterministic Behavior Contract static lint.

## Behavior Contract static lint boundary

ATHBA keeps the compiled product-surface descriptor private control-plane state. It is derived only from the Behavior Contract's component identity and explicit machine-usable `public_api` entries; it reads neither Gatekeeper payload/checklist data nor final reconciliation state. Tester receives its existing focused ticket and source evidence, and Developer receives only the active frontier. Neither objective, nor the Intent Reviewer prompt, serializes the complete declared product surface.

Before Intent Review, Python AST validation tracks imports, declared production-class constructors, and supported instance aliases. It rejects direct private-state inspection and undeclared public product members, while not treating value/library calls such as `.strip()` or pytest APIs as product interactions. A declared member from a future behavior slice remains allowed; this is a product-boundary subset rule, not an active-ticket exclusivity rule. Rejection feedback names only the offending member and location, not the allowed API list.

Before canonical promotion, Python production candidates are also checked as a subset: public methods, class attributes, and `self.<attribute>` declarations on the declared component may not introduce undeclared surface. Missing future members and private helpers remain allowed. This lint deliberately does not decide semantic transformations, normalisation, Gatekeeper reconciliation, or refactoring. PR21's refactoring lane remains deferred and independent.


## Contract-lint SignalBoard bounded-attempt forensics

This section closes the investigation of the immutable live run
`pr29-contract-lint-signal-board-20260903T223456Z`. The feature, scenario, and
Rack AI review packets were read only; this work did not resume the run, alter
its fixture, or create a new SignalBoard run.

### Authoritative live contract and private product surface

The persisted feature state's `contract_payload` is authoritative:

- `component_name`: `SignalBoard`.
- Exact `public_api`: `SignalBoard`, `publish`, `latest`.
- REQ-002: source ref `SignalBoard.2`; summary `Publishing a signal payload`;
  observable outcome `Payload is stored for a specific name`; test hint `Call
  publish and verify the internal state updates`; dependency `REQ-001`.
- REQ-003: source ref `SignalBoard.3`; summary `Retrieving the latest signal`;
  observable outcome `Retrieves the most recent payload`; test hint `Publish
  multiple payloads for the same name and verify the last one is returned`;
  dependency `REQ-002`.
- Exact REQ-002 source clause: `publish(name, payload) records the payload for
  that signal name.`
- Exact REQ-003 source clause: `latest(name) returns the most recently published
  payload for that name.`

Compiling `DeclaredProductSurface` from that persisted contract produces
`LIVE_DECLARED_COMPONENT=SignalBoard`,
`LIVE_DECLARED_MEMBERS={publish, latest}`, and
`LIVE_UNSUPPORTED_PUBLIC_API_ENTRIES=()`. Thus `get` is not declared; `signals`
is not declared; `publish` and `latest` are declared. This is a deterministic
projection of the contract, not Gatekeeper state, and is intentionally not a
second persisted mutable object.

### Tester information boundary

Every captured REQ-002 work-unit objective gave the Tester the focused behavior
`Publishing a signal payload`, expected result `Payload is stored for a specific
name`, source ref `SignalBoard.2`, and the exact source evidence above. It also
gave strict-authoring rules, `tests/test_signal_board.py`, the trusted base,
and repository facts (including the then-current `SignalBoard` excerpt).

It did **not** serialize the complete contract `public_api`, REQ-003 text,
`latest`, or Gatekeeper payload/checklist data. Attempt 2's repair objective
contained attempt 1's source and focused semantic feedback; attempt 3 contained
attempt 2's source and only its focused deterministic `signals` feedback; attempt
4 contained the bounded no-candidate feedback. None listed allowed members. A
control-plane value retained in ATHBA state was not model exposure. Therefore
`FULL_CONTRACT_SURFACE_EXPOSED_TO_TESTER=NO` and
`REQ003_EXPOSED_TO_REQ002_TESTER=NO`.

### Every REQ-002 authoring attempt

| Attempt | Work unit and selected worker/provenance | Submission and candidate | Static assessment / lint | Intent and returned feedback | Repair lineage | Timeout / unchanged |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `REQ-002--scenario-draft-1`; `local-primary`; `jcode`, `gemma4-12b-local-primary`, profile/worker `local-primary`, resource `gpu-4060ti`, generic-reasoning-worker | Accepted; `12218b5f3d209ea84496b43bddf698636bb62eba`; source only constructs `SignalBoard` and asserts it is not `None` | Valid grammar; production path `signal_board.py`; no lint issues | YES, `insufficient_evidence`, one response. Feedback: it neither calls `publish(name, payload)` nor verifies storage. | Fresh draft; no repair base. | NO / NO |
| 2 | `REQ-002--scenario-draft-2`; same selected worker and full provenance | Accepted; `b6c40eb54625becd062080e0e0e220dfe5f474e7`; calls `publish` then `board.signals.get(...)` | Valid grammar and production tracking; `undeclared_product_member` for `signals` at line 6 | NO; zero intent responses. Focused lint feedback names only `signals` and its location. | Repairs attempt 1 from its branch and `12218b5...`; `repair_previous_candidate`. | NO / NO |
| 3 | `REQ-002--scenario-draft-3`; same selected worker and full provenance | `worker_model_timeout` after 300 seconds; no candidate revision or source | No candidate/static assessment | NO; zero intent responses. Feedback records the timeout and asks for a complete scenario from the unchanged base. | Based on attempt 2 branch and `b6c40e...`; `retry_repair_from_existing_candidate`. | YES / NO |
| 4 | `REQ-002--scenario-draft-4`; same selected worker and full provenance | Accepted; `a299f8eb6af6d9267a2d0130a4407c9a169859bf`; calls `publish` then `assert True` | Valid grammar; production path `signal_board.py`; no lint issues | YES, `semantic_repair_required`, one response. Feedback says `assert True` does not verify storage and asks for retrieval/assertion evidence. | Follows the timeout from attempt 3; repair lineage retains attempt 2 candidate state; `retry_repair_from_existing_candidate`. | NO / NO |

The durable scenario state ends `attempts_exhausted`: four Rack AI submissions,
exactly one increment per submission. There was one static undeclared-member
rejection (`signals`), zero private-member rejections, one timeout/no-candidate
attempt, no unchanged repair attempt, and two Intent Review calls (attempts 1
and 4). Static lint made zero semantic Intent calls and no additional model
submission. The attempt-2 focused feedback is persisted on that attempt and is
the only lint feedback supplied to the next Tester objective; it did not leak
the complete allowed surface.

### Classification

`LIVE_REQ002_ROOT_CLASSIFICATION=BEHAVIOR_SLICE_OBSERVABILITY_GAP`.

REQ-002 legitimately asks the Tester to prove an externally meaningful stored
state, while its minimally scoped REQ-002 context supplies no legal observation
mechanism. `latest` exists in the full private contract, but it belongs to
REQ-003 and was not supplied to the REQ-002 Tester. The Tester consequently
first produced an incomplete test, then attempted private `signals` observation;
the timeout and later `assert True` are additional bounded execution/semantic
failures, not evidence that the complete contract was exposed. The static lint
correctly prevented the undeclared observation route; it is not itself the
underlying slice-observability cause.

## Contract-lint proof closure

### Historical `get` held-out regression

`test_historical_signal_board_get_is_rejected_before_intent_or_freeze` uses the
exact historical candidate: import `pytest`, construct `SignalBoard`, publish
`("name", "payload")`, then make the three `board.get("name")` assertions. It
runs through the production `ScenarioDraftingService` submission and candidate
assessment path, not a low-level lint helper.

The candidate has valid Python grammar, the production import/path tracker finds
`signal_board.py`, and constructor-instance tracking identifies `board` as the
product instance. `publish` produces no violation. All three `get` references
produce `undeclared_product_member`; Intent Review has zero calls/responses; no
approved microcycle is frozen, and consequently no frontier or Developer work
can be created. This was missing coverage only:
`HELD_OUT_FAILURE_CLASSIFICATION=TEST_MISSING_ONLY` and no production source
change was required.

### Restart/resume static-policy regression

`test_static_rejection_persists_across_restart_with_surface_recompiled_from_contract`
first records a Rack-AI-accepted historical candidate, deterministically rejects
it for `get`, and saves the rejected attempt with `ScenarioDraftStateRepo`.
The test restarts with a new service and reloads normal repository serialization.
It reconstructs the Behavior Contract from its persisted payload and recompiles
`DeclaredProductSurface`; no Gatekeeper payload is supplied. The resumed surface
is again `SignalBoard` with exactly `publish` and `latest`.

Continuation makes a new bounded Tester submission and runs it through the same
recompiled static policy. Both attempts remain `candidate_invalid`; the original
rejected candidate is never reinterpreted as accepted, neither rejected
candidate reaches Intent Review, no microcycle is frozen, and no frontier or
Developer work is reachable. The prior
`RESTART_RESUME_STATIC_POLICY=FAIL` therefore meant
`MISSING_PROOF_ONLY`, not a reproduced policy bypass. Persisting
`DeclaredProductSurface` itself remains unnecessary because it is a deterministic
projection of the authoritative persisted Behavior Contract.

Focused validation for this closure passed: `63 passed` across behavior-contract
surface, scenario drafting, feature-execution advance, and persistence tests.
No production, Rack AI, Tester-information, Intent Review, Gatekeeper, planner,
routing, budget, grammar, PR21, or refactoring source changed.
