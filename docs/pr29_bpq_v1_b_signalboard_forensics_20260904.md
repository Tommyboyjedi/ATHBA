# PR29 BPQ-V1-B SignalBoard forensics

Date: 2026-09-04

## Scope and evidence rule

This is an evidence-only reconstruction of completed run
`pr29-bpq-v1-b-signalboard-20260904T115000Z`. It does not rerun SignalBoard,
ReservationBook, or any model. It does not use Gatekeeper material to interpret
the development path. No raw provider strings are presented: the unchanged
planner path did not persist raw source-clause or Behavior Planner provider
responses. The accepted persisted/replay contract is the available evidence.

## Identity

| Item | Result |
| --- | --- |
| BPQ corpus / fixture | `BPQ-V1` / `BPQ-V1-B` |
| Requirement SHA-256 | `c46ce04d165b64d2459fdd821475289925496dc7541584230d60f4858ec9aa88` |
| Corpus SHA-256 | `523dc088007cdcd10484daa7cb272fdbdab4a37a306a5369bbeac1ff676d85cb` |
| Accepted contract replay SHA-256 | `c9bae41cdb5fd9a5cbed6f3f8ba7ac3bba18ca4339fc6c5ec6ebaceb862e91a9` |
| Replay artifact | `evidence/pr29-bpq-v1-b-signalboard-20260904T115000Z/behavior-planner-replays/BPQ-V1-B-accepted-contract.json` |
| Feature state | `state/features/pr29-bpq-v1-b-signalboard-20260904T115000Z.json` |
| REQ-001 state | `state/scenario-drafts/pr29-bpq-v1-b-signalboard-20260904T115000Z--REQ-001.json` |

All three supplied digests matched the retained artifacts/state.

## 1. Accepted Behavior Contract

The accepted replay contract has `component_name = SignalBoard`,
`capability = In-memory signal storage and retrieval`, status `tdd_ready`,
and `public_api = ["publish", "get_latest"]`.

* Invariants:
  * `The board is in-memory and dependency-free`
  * `No persistence, deletion, subscriptions, or validation rules are implemented`
  * `Only the most recent payload for any given name is stored`
* Error semantics:
  * `Return None or raise KeyError for non-existent signal names`
  * `Handle null payloads if allowed by type`
* Non-goals: `Persistence`, `Deletion`, `Subscriptions`, `Validation rules`,
  `Concurrency support`.
* Completion criteria:
  * `SignalBoard initializes empty`
  * `Payloads can be published under unique names`
  * `New payloads replace old ones for the same name`
  * `Retrieval returns the most recent payload`
  * `Operations on one signal name do not affect others`
* Production path: `signal_board.py`; test path:
  `tests/test_signal_board.py`.

| Ref | Source refs | Summary | Observable outcome | Test hint | Error expectation | Preserves state on failure | Depends on |
| --- | --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | PR16-003 | Initial state is empty | A new SignalBoard instance contains no signals | Verify that a fresh board returns no data for any key | null | true | none |
| REQ-002 | PR16-004 | Publish new signal | A payload is successfully stored under a new name | Publish a value and verify it can be retrieved | null | true | none |
| REQ-003 | PR16-005 | Update existing signal | The old payload is replaced by the new payload for the same name | Publish two different values to the same key and verify the second is returned | null | true | REQ-002 |
| REQ-004 | PR16-006 | Isolation of signal names | Values for other signal names remain unchanged after a publication | Publish to key A, then publish to key B, and verify key A is unchanged | null | true | REQ-002 |
| REQ-005 | PR16-007 | Retrieve latest payload | The latest payload is returned for a requested name | Retrieve a value that was previously published | Return None or raise KeyError | true | REQ-002 |
| REQ-006 | PR16-001, PR16-002, PR16-008 | Mechanical constraints | Component is dependency-free, in-memory, and small/direct | Verify no external imports are used and implementation is concise | null | true | none |
| REQ-007 | PR16-009, PR16-010, PR16-011, PR16-012, PR16-013 | Negative constraints | No persistence, deletion, subscriptions, or validation are present | Verify that methods for deletion or subscription do not exist | null | true | none |

The raw provider strings that produced these parsed records were not persisted.
They are not reconstructed or fabricated here.

## 2. Accepted source clauses

| Ref | Exact text | Kind | Evidence kind |
| --- | --- | --- | --- |
| PR16-001 | The SignalBoard must be an in-memory component. | constraint | mechanical |
| PR16-002 | The component must be dependency-free. | constraint | mechanical |
| PR16-003 | A new SignalBoard must start with no published signals. | invariant | test |
| PR16-004 | The system must allow users to publish a payload under a specific signal name. | behavior | test |
| PR16-005 | Publishing a payload under an existing signal name must replace the previous value for that name. | behavior | test |
| PR16-006 | Publishing a payload for one signal name must not affect the values of other signal names. | invariant | test |
| PR16-007 | The system must provide a way to retrieve the latest payload for a specific signal name. | behavior | test |
| PR16-008 | The component must be small and direct. | quality | review |
| PR16-009 | The system must not provide persistence. | constraint | review |
| PR16-010 | The system must not provide deletion functionality. | constraint | review |
| PR16-011 | The system must not provide subscriptions. | constraint | review |
| PR16-012 | The system must not provide validation rules. | constraint | review |
| PR16-013 | The system must not provide concurrency support. | constraint | review |

REQ-001 maps only to PR16-003. Its parsed clause is a direct natural
decomposition of the sentence about a new board having no published signals;
the persisted REQ-001 fields do not introduce a method name or representation.

## 3. REQ-001 exactly

```json
{
  "ref": "REQ-001",
  "source_refs": ["PR16-003"],
  "summary": "Initial state is empty",
  "observable_outcome": "A new SignalBoard instance contains no signals",
  "test_hint": "Verify that a fresh board returns no data for any key",
  "error_expectation": null,
  "preserves_state_on_failure": true,
  "depends_on": []
}
```

It establishes the human behavior that a newly created board is empty.
REQ-001 does not require or mention `publish`, `get_latest`, or `signals`;
it does not specify a representation and it has no dependencies.

Its observability classification is:

* Directly observable from the ticket alone: the required initial-empty outcome.
* Observable only if Planner-generated API information were exposed: no such
  operation is named in REQ-001 itself; the retained Tester task did not expose
  that API information.
* Not determinable from the evidence: which concrete observation mechanism the
  component should offer to establish emptiness.

## 4. Tester information boundary

The exact attempt-1 task was a JSON object with this bounded semantic payload:

```text
role: Tester
task: Draft one complete behavioral scenario conforming to the supplied strict authoring contract.
ticket.id: REQ-001
ticket.behavior: Initial state is empty
ticket.expected_result: A new SignalBoard instance contains no signals
source_requirement_refs: [PR16-003]
source_requirements: [{ref: PR16-003, kind: invariant, evidence_kind: test,
  text: A new SignalBoard must start with no published signals.}]
repository_facts.production_excerpt: """ATHBA initial production module."""
repository_facts.test_excerpt: ""
repository_facts.visible_paths: [.gitignore, signal_board.py]
```

It also received the strict Python/pytest authoring envelope: only the allowed
test path could be edited; one syntactically valid ordinary test; direct
production reference; no production edit, substitute implementation, behavior
mock, skip/xfail, or frontier implementation. It did not receive any
Planner-produced `public_api` entry.

| Material | Given to attempt-1 Tester? | Basis |
| --- | --- | --- |
| Full canonical BPQ prose | NO | Absent from persisted task |
| Only REQ-001 ticket | YES | Ticket fields above |
| PR16-003 source clause text | YES | `source_requirements` |
| Summary / observable outcome | YES | Ticket behavior / expected_result |
| test_hint | NO | Absent from task |
| `public_api` | NO | Absent from task |
| `publish` / `get_latest` | NO | Absent from task |
| Other behavior requirements / future descriptions | NO | Only PR16-003 supplied |
| Repository source / test source | YES, bounded | Excerpts plus tool-visible workspace |
| Prior candidate | NO for attempt 1 | Fresh draft |
| Lint feedback | NO for attempt 1 | Produced after candidate |
| Gatekeeper information | NO | Absent from task |

```text
DID_REQ001_TESTER_KNOW_GET_LATEST_EXISTS=NO
DID_REQ001_TESTER_RECEIVE_FULL_PUBLIC_API=NO
DID_REQ001_TESTER_RECEIVE_OTHER_BEHAVIORS=NO
```

Attempts 2--4 carried the same REQ-001 ticket and PR16-003 clause. Attempt 2
also received the first candidate and the deterministic undeclared-`signals`
feedback. Later repair prompts retained that prior candidate/assessment plus the
previous timeout feedback. None of those persisted tasks contain the full
public API or `get_latest`.

## 5. Attempt 1

Candidate revision `3fd57333ba735ce5363da2416bb7006bd751a856`,
work unit `REQ-001--scenario-draft-1`, was:

```python
from signal_board import SignalBoard

def test_REQ_001():
    board = SignalBoard()
    assert len(board.signals) == 0
```

The candidate assessment says syntax valid `true`, direct production reference
`signal_board.py`, one actual identity
`tests/test_signal_board.py::test_REQ_001`, and no mocks, substitute
definitions, evasion markers, helpers, fixtures, classes, parameterization, or
unsupported nodes. Its sole issue was:

```text
code: undeclared_product_member
member: signals
usage role: attribute read on the SignalBoard instance in len(board.signals)
line: 5
feedback: Candidate references undeclared product member `signals` at line 5.
Product interactions must remain inside the declared product contract. Repair
the candidate without introducing undeclared product surface.
```

The test is recognizably aimed at REQ-001's initial-empty behavior. It inspects
state through `signals`. That member is not private by the lint's name
convention: it has no leading underscore. It is rejected as *undeclared* because
it is absent from the compiled `public_api` member set. The retained assessment
records no other invalidity.

Control flow is decisive here: a candidate whose assessment is accepted becomes
`intent_review_pending` and then invokes Intent Review; a failed assessment
becomes `candidate_invalid`. Therefore:

```text
ATTEMPT1_ONLY_BLOCKER_BEFORE_INTENT=undeclared_product_member
ATTEMPT1_WOULD_ROUTE_TO_INTENT_IF_LINT_CLEAN=YES
```

This is a route statement, not a counterfactual execution or claim that Intent
would approve the candidate.

## 6. Current authority of public_api

The contract compiler turns parseable entries in `contract.public_api` into a
`DeclaredProductSurface`; for this contract it is the member set
`{publish, get_latest}`.

| Source location | Input | Rule | Failure classification | Pipeline point |
| --- | --- | --- | --- | --- |
| `core/development/strict_tdd_feature_execution_advance.py` | Behavior Contract | Compiles `DeclaredProductSurface` and passes it to scenario drafting | none itself | Before Tester submission and Intent Review |
| `core/development/python_pytest_adapter.py` plus `behavior_contract_surface.py` | Tester candidate, component name, production path, compiled surface | Any attribute on a recognized component instance that is private or absent from the surface is an issue | `private_product_member` or `undeclared_product_member`; candidate invalid | Static candidate assessment before Intent Review |
| `core/development/strict_microcycle.py` | Accepted Developer candidate source and compiled surface | Named class methods/attributes not private and absent from surface are violations | `production_contract_lint_rejected` | After Developer result, before working revision advancement |
| `core/development/behavior_contract_coordinator.py` and domain validation | Contract field | Requires `public_api` to be an array of strings | contract validation error for malformed field | Contract parsing/validation |

No distinct TDD-frontier validation rule using `public_api` was found. The
frontier/developer path receives the compiled surface and enforces it only at
the Developer-candidate check shown above. In this run that stage was
not reached.

The current authority is therefore
`PUBLIC_API_CURRENT_AUTHORITY=AUTHORITATIVE_WHITELIST`, not merely metadata or
Tester guidance. The exact static test lint and Developer lint were introduced
by commit `464ad01f7bacd49a00aa55d6d7c10b96d9c762fc`
(`Add deterministic behavior-contract surface lint`): its parent contains
neither `DeclaredProductSurface` nor `undeclared_product_member`.

## 7. Source behavior versus identifiers

The canonical BPQ prose says that people can “publish a payload” and that it
must be possible to “ask for the latest payload.” It does not literally contain
the identifier `publish` or the identifier `get_latest`. It does mandate the
underlying publish/store/replace and latest-retrieval behaviors. A conforming
public implementation could plausibly use other identifiers without
contradicting that prose. Thus `publish` and `get_latest` are
Planner-chosen identifiers in this accepted contract, not source-mandated
identifiers.

## 8. Attempts 2--4: separate operational record

Every later attempt selected the same persisted worker provenance:
`backend=jcode`, `worker_id=local-primary`,
`model_id=gemma4-12b-local-primary`, `provider_profile=local-primary`, and
`resource_id=gpu-4060ti`. Each retained Rack AI review packet includes
non-empty `implementer_output` with model tool activity/token counters, so a
model session actually began. No candidate source, candidate revision, changed
path, or accepted command was produced by these attempts.

| Attempt | Work unit / submission | Base lineage | Result | Timeout | Partial output / evidence | Localization |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | `REQ-001--scenario-draft-2` / `...submission-12104124362205439256` | repair parent 1; base branch/revision attempt 1 / `3fd57333...` | `worker_model_timeout` | 300 s | Model tool transcript retained in its review packet | JCode wall-clock wait after session began; provider inference versus another in-session wait is not localized |
| 3 | `REQ-001--scenario-draft-3` / `...submission-12104125461717067467` | repair parent 2; retained base branch attempt 1; no new base SHA | `worker_model_timeout` | 300 s | Model tool transcript retained in its review packet | Same JCode wall-clock classification; lower layer not localized |
| 4 | `REQ-001--scenario-draft-4` / `...submission-12104130959275208522` | repair parent 3; retained base branch attempt 1; no new base SHA | `worker_model_timeout` | 300 s | Model tool transcript retained in its review packet | Same JCode wall-clock classification; lower layer not localized |

The review packets are the Rack AI evidence locations recorded in scenario
state, under
`/srv/rack-ai/state/changes/pr29-bpq-v1-b-signalboard-20260904T115000Z--REQ-001--scenario-draft--...`.
No separate JCode log artifact was found in the retained run locations; the
packet `implementer_output` is the available JCode evidence. The exact shared
error is `jcode wall-clock timeout exceeded for worker local-primary after 300 seconds`.

```text
MODEL_READINESS_HAD_PREVIOUSLY_PASSED=YES
TESTER_TIMEOUTS_IDENTICAL_FAILURE_MODE=YES
```

These timeouts are operational/JCode-wall-clock failures. They do not classify
the attempt-1 semantic or static-lint question.

## 9. Reached route

```text
BPQ prose
-> source clause planning
-> accepted Behavior Contract
-> deterministic contract validation
-> REQ-001 selection
-> Tester attempt 1
-> static validation
-> lint rejection (undeclared_product_member: signals)
-> repair attempt 2
-> JCode wall-clock timeout
-> attempt 3
-> JCode wall-clock timeout
-> attempt 4
-> JCode wall-clock timeout
-> attempts exhausted
```

NOT_REACHED: Intent Review, TDD frontier, RED classification/execution, Developer,
GREEN, regression, Senior Review, and final behavior completion.

## 10. Findings

| Hypothesis | Classification | Evidence-bound reason |
| --- | --- | --- |
| H1: real Behavior Planner successfully decomposed the prose into an accepted contract | PROVEN | Accepted replay has 13 clauses and 7 requirements; feature state is blocked only downstream |
| H2: source mandates identifiers `publish` and `get_latest` | DISPROVEN | Neither identifier occurs literally in the canonical prose |
| H3: schema causes Planner to choose implementation-facing API identifiers | PROVEN | Schema requests `public_api`; accepted output supplies identifiers absent from source prose |
| H4: static lint treats Planner-chosen identifiers as authoritative whitelist | PROVEN | Compiled surface rejects `signals` solely because absent from `{publish,get_latest}` |
