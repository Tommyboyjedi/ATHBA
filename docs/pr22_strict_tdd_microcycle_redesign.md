# PR22 — Strict TDD Microcycle Redesign

## Status

**Documentation-only architecture proposal.**

This PR does not implement the redesign. It records the decision, rollback boundary, language-agnostic contract, migration sequence, examples, and proof requirements before more PR17 code is changed.

The current PR17 branch remains preserved for comparison and forensic evidence. No PR17 history should be rewritten until this design is reviewed and explicitly approved.

---

## Executive decision

PR17 has accumulated a large amount of recovery, dependency, provisional-state, retry, review, and proof-harness machinery around a mistaken assumption:

> The complete behavioral test drafted by the Tester was treated as the next executable TDD test.

That assumption violates the second of Robert C. Martin's Three Laws of TDD:

1. Do not write production code unless it is required to make a failing unit test pass.
2. Do not write more of a unit test than is sufficient to fail; compilation failure counts as failure.
3. Do not write more production code than is sufficient to make the currently failing test pass.

A complete test for duplicate resource identifiers may require all of the following to exist before its final assertion can be exercised:

- the `ReservationBook` type;
- a working constructor;
- an `add_resource` operation;
- successful first-resource insertion;
- duplicate detection;
- the expected exception behavior.

If the type itself does not exist, strict TDD stops at that first missing capability. It does not continue treating the full duplicate-resource scenario as the immediate RED boundary.

The replacement architecture therefore treats the Tester's complete behavioral test as a **scenario draft**, not as the active test artifact. ATHBA progressively compiles that draft into the smallest syntactically complete test microstep that can reveal the next missing behavior.

The normal path becomes:

```text
Behavior ticket
  -> Tester drafts complete behavioral scenario
  -> independent scenario-intent validation
  -> language adapter parses scenario
  -> ATHBA materialises smallest syntactically complete frontier
  -> frontier fails at the expected active boundary
  -> Developer makes that frontier pass with minimum production code
  -> deterministic accumulated regression suite
  -> advance frontier within the same scenario
  -> repeat until complete scenario passes
  -> behavior-level semantic review
  -> repeat for next behavior
  -> feature-level review and independent Specification Gatekeeper reconciliation
```

This directly enforces the Three Laws instead of compensating after Law 2 has already been violated.

---

## Why the current design became stuck

The ReservationBook proof repeatedly selected a duplicate-resource behavior while `ReservationBook` itself was not defined. The Tester produced a complete duplicate-resource test. Pytest then failed during collection because the type could not be imported.

The two-layer RED validation correctly determined that the duplicate-resource behavior had not been exercised. However, the surrounding state machine then attempted to classify, defer, replan, synthesize prerequisites, preserve provisional semantics, generate new change identities, resume checkpoints, and retry the same oversized scenario.

The process eventually reached double-digit replans of the same behavioral test from effectively the same capability state.

The failure was not primarily caused by insufficient classification coverage. It was caused by presenting a later behavioral scenario as though it were the smallest current test increment.

Under strict TDD, the active RED boundary should have been the missing type or constructor, followed by the missing method, followed by the first successful operation, and only then the duplicate behavior.

---

## Core distinction: scenario draft versus active test

### Scenario draft

The Tester may generate a complete behavioral example because that is an understandable and bounded model task:

```python
def test_duplicate_resource_id():
    from reservation_book import ReservationBook

    book = ReservationBook()
    book.add_resource("A", capacity=10)

    with pytest.raises(ValueError):
        book.add_resource("A", capacity=10)
```

This draft expresses the intended final behavior. It is stored in ATHBA state as planning material. It is **not yet committed as the active executable test**.

The draft may be independently reviewed once to answer:

> Does this scenario actually demonstrate the behavior requested by the Behavior Planner ticket?

### Active test artifact

ATHBA's language adapter progressively materialises one syntactically complete prefix/frontier of that scenario into the target repository.

Only the active frontier is:

- executed;
- accepted as RED;
- supplied to Developer;
- committed as the current test state.

The final repository contains one canonical test, not a collection of duplicate microtests. Earlier forms exist only in Git history as previous revisions of the same test node.

---

## The strict microcycle

For one approved scenario:

```text
scenario frontier N
  -> materialise a complete test artifact
  -> parse/compile/collect
  -> execute if the language/runtime permits
  -> classify the first failure boundary
```

Possible outcomes:

### Valid RED at the active frontier

Examples:

- the referenced type does not exist;
- the constructor does not exist;
- the requested method does not exist;
- the operation executes but returns the wrong value;
- the expected exception is not raised.

The failure must correspond to the exact capability introduced by the active frontier.

### Invalid generated test artifact

Examples:

- incomplete syntax;
- malformed indentation;
- an unclosed block;
- a missing test terminator;
- a failure before the active frontier caused by unrelated setup;
- invalid framework usage introduced by Tester or adapter.

This is not RED. It is a Tester/adapter artifact defect.

### Infrastructure failure

Examples:

- compiler unavailable;
- runtime unavailable;
- executor transport failure;
- corrupted execution packet.

This is not RED and does not consume Developer attempts.

### GREEN

The active frontier passes. ATHBA runs the deterministic accumulated regression suite. If all tests pass, the frontier becomes the new development base and the next scenario fragment is exposed.

---

## Retry limits

During this redesign and proof phase, no unchanged task should be retried more than four times.

Default maximums:

- Tester scenario drafting: 4 attempts;
- scenario-intent repair: 1 constrained repair after initial response;
- Developer for one active frontier: 4 attempts;
- regression repair: 4 attempts;
- identical frontier re-execution from an unchanged development base: 4 attempts maximum;
- repeated replanning of the same full scenario from the same base: prohibited.

A new frontier after a successful GREEN is progress, not a retry.

The retry count must be persisted and must not reset after process restart.

---

## Language-agnostic design

### Not literal line-by-line execution

The microcycle engine must never expose source by raw line number.

A physical source line is not a language-independent semantic unit. A line may be:

- an incomplete `for` header;
- the opening line of an `if` block;
- one part of a multiline expression;
- a VBA `If` whose required `End If` appears much later;
- a C# expression whose braces and terminator are elsewhere;
- a continuation line in Python, JavaScript, SQL, or shell syntax.

The unit of progression is a **syntactically complete scenario fragment**, derived through a language adapter from an AST, CST, compiler service, or equivalent parser representation.

### Required adapter contract

The orchestration layer remains language agnostic. Each supported language/test framework provides an adapter implementing responsibilities equivalent to:

```text
parse_scenario(draft_source, test_metadata) -> ScenarioModel
validate_scenario_syntax(model) -> SyntaxAssessment
validate_scenario_intent(model, behavior_ticket) -> IntentEvidence
fragment_scenario(model) -> ordered ScenarioFragments
materialise_frontier(model, frontier_index) -> CompleteTestArtifact
execute_frontier(artifact, project_runtime) -> StructuredDiagnostic
classify_boundary(diagnostic, active_fragment) -> BoundaryAssessment
materialise_final_test(model) -> CompleteTestArtifact
```

The adapter must guarantee that every materialised frontier is a complete source artifact for the target language and test framework.

### Scenario fragment examples

A fragment may be:

- one import/reference operation;
- one complete declaration;
- one constructor invocation;
- one setup call;
- one target action;
- one assertion;
- one expected-exception block;
- one complete control-flow block;
- one complete query/statement;
- one complete asynchronous operation.

A fragment is not necessarily one line.

### Syntax completeness versus missing capability

The engine must distinguish:

1. **Syntactic incompleteness** — invalid Tester/adapter artifact.
2. **Semantic compilation/link failure at the active frontier** — valid RED when the active frontier requests that missing capability.
3. **Runtime behavioral failure at the active frontier** — valid RED.
4. **Failure before the active frontier** — invalid ordering or scenario decomposition.
5. **Failure after the active frontier** — later scenario content must not yet have been materialised.

This distinction is what makes compiler errors usable without accepting arbitrary malformed source as RED.

---

## Cross-language examples

### Python / pytest

Approved scenario draft:

```python
def test_duplicate_resource_id():
    from reservation_book import ReservationBook

    book = ReservationBook()
    book.add_resource("A", capacity=10)

    with pytest.raises(ValueError):
        book.add_resource("A", capacity=10)
```

Possible fragments:

1. Import/reference `ReservationBook` inside the test body.
2. Construct `ReservationBook()`.
3. Call `add_resource("A", capacity=10)` successfully.
4. Execute the duplicate call inside the complete `pytest.raises` context.

ATHBA always emits a complete Python function. It never emits a dangling `with`, incomplete indentation, or half an expression.

If fragment 1 fails with `ImportError` inside the active test, that is valid RED for making the type available.

If the generated Python file has bad indentation, that is not RED; it is an invalid test artifact.

### C# / xUnit

Approved scenario draft:

```csharp
[Fact]
public void DuplicateResourceIdIsRejected()
{
    var book = new ReservationBook();
    book.AddResource("A", 10);

    Assert.Throws<ArgumentException>(
        () => book.AddResource("A", 10));
}
```

Possible fragments:

1. Complete test method containing `new ReservationBook()`.
2. Add the complete first `AddResource` statement.
3. Add the complete `Assert.Throws` expression.

The adapter always emits the closing method/class braces. It never emits a half method or half lambda.

A compiler diagnostic saying `ReservationBook` cannot be found is valid RED for fragment 1. A missing closing brace generated by the adapter is an adapter defect, not RED.

### JavaScript / TypeScript

Approved scenario draft:

```typescript
test("duplicate resource id is rejected", () => {
    const book = new ReservationBook();
    book.addResource("A", 10);

    expect(() => book.addResource("A", 10)).toThrow();
});
```

Fragments are complete statements or complete expression blocks. The adapter preserves the enclosing callback and test terminators at every frontier.

### VBA

Approved scenario draft:

```vb
Public Sub TestDuplicateResourceId()
    Dim book As ReservationBook
    Set book = New ReservationBook

    book.AddResource "A", 10

    On Error Resume Next
    book.AddResource "A", 10
    If Err.Number = 0 Then
        Err.Raise vbObjectError + 1, , "Expected duplicate rejection"
    End If
End Sub
```

The adapter does not expose raw lines. Examples of complete VBA fragments are:

1. The complete `Dim` declaration.
2. The complete `Set ... = New ...` statement.
3. The first complete method call.
4. The complete error-observation sequence, including the entire `If ... End If` block.

A lone `If ... Then` line is never a frontier. `If ... End If`, `For ... Next`, `With ... End With`, and `Select Case ... End Select` are complete block nodes.

### `for` / loop example

For any language, this is invalid microstep slicing:

```text
for each item in items
```

without a syntactically complete body and terminator where required.

The first implementation treats a loop as one atomic fragment containing:

- the loop declaration;
- its current complete body;
- its closing token or block boundary.

A future adapter may support nested frontiers inside a loop, but only by materialising a complete loop with a complete prefix of child statements and all required closure syntax. It must never emit a raw partial line.

---

## Suggested internal representation

The system should introduce language-neutral orchestration records such as:

```text
TestScenarioDraft
ScenarioModel
ScenarioFragment
ScenarioFrontier
MaterialisedTestArtifact
BoundaryDiagnostic
BoundaryAssessment
MicrocycleState
```

Illustrative fields:

### `ScenarioFragment`

- fragment id;
- fragment kind;
- source span or AST/CST identity;
- declared capability;
- required prior fragment ids;
- expected boundary kind;
- language-adapter metadata.

### `ScenarioFrontier`

- scenario id;
- current fragment index;
- materialised test node;
- development base revision;
- current RED revision;
- retry count;
- boundary evidence;
- status.

### `BoundaryAssessment`

- `valid_missing_capability_red`;
- `valid_behavioral_red`;
- `green`;
- `invalid_test_syntax`;
- `failure_before_frontier`;
- `infrastructure_failure`;
- `unsupported_language_boundary`.

These values are illustrative. The implementation should select clear typed names and stable persistence values.

---

## Developer contract

The Developer receives only:

- the current materialised frontier test;
- the exact structured failure diagnostic;
- the allowed production path;
- the current development base.

The Developer's responsibility is:

> Make the active frontier pass with the smallest production change required.

It must not receive the unexposed remainder of the scenario where that would encourage speculative implementation.

It must not be asked to perform feature-level design, final semantic reconciliation, or coding-principles refactoring.

Maximum Developer attempts per unchanged frontier: four.

---

## Regression contract

After each frontier becomes GREEN, ATHBA runs the accumulated suite deterministically through the project runtime/executor.

The regression check must not invoke an LLM merely to run tests.

Possible outcomes:

- all tests pass — advance development base and expose next frontier;
- previously GREEN tests fail — create a bounded regression-repair packet containing the current frontier plus only the newly failing prior tests;
- test infrastructure fails — classify as infrastructure/environment failure;
- repair budget exhausted — fail closed.

The full suite runs again after regression repair.

---

## Semantic review placement

Senior semantic review should not occur after every import, constructor, or individual microstep.

The preferred review levels are:

1. **Scenario-intent review before execution** — confirms the complete scenario represents the behavior ticket.
2. **Behavior review after the complete scenario is GREEN** — confirms the behavior was implemented coherently.
3. **Feature-level review after all behavior scenarios complete** — optional but recommended before final Gatekeeper reconciliation.

The Specification Gatekeeper remains independent and performs final accepted-test reconciliation against the original requirement checklist.

---

## Parallelism

Strict TDD is sequential within one scenario dependency chain.

Parallelism remains possible across:

- independent components;
- independent feature requirements;
- behavior scenarios whose shared foundation is already GREEN;
- isolated branches with later regression and integration reconciliation.

ATHBA must not parallelise two scenario frontiers that both require an unresolved shared capability.

The first PR22 implementation proof should be sequential. Parallel execution should be added only after the microcycle state machine is proven.

---

## Commit rollback and retention plan

Current remote PR17 head at the time of this design:

```text
fe2af8f0ae519cc8a506bf0d3ac79e4d4cbea4b8
```

The following plan is explicit so implementation does not preserve obsolete complexity merely because it already exists.

### Commits to revert from the active PR17 implementation path

#### `fe2af8f0ae519cc8a506bf0d3ac79e4d4cbea4b8`
`Add PR17 green regression gate progression`

Revert as a whole before rebuilding. Useful ideas are reimplemented cleanly:

- retain the narrow single-frontier Developer contract;
- retain accumulated regression authority;
- replace the agent-driven supervisory regression work unit with deterministic test execution;
- replace cycle semantics tied to the old full-test RED model.

#### `0f7e833a13bcc058fa0076d6a8ea233ad49f7522`
`Add provisional semantic progression ledger`

Revert completely from the normal TDD path. Provisional semantic progression was introduced to preserve useful work after oversized tests exposed unresolved prerequisites. The strict microcycle removes that need inside a behavior scenario.

If future feature-level provisional integration is still required, it must be redesigned outside the inner TDD microcycle after strict TDD is proven.

#### `07bee72b7e99c66c4fab1806320be4d63568fc85`
`development: scope replanned red attempts for rack ai`

Revert. It supports repeated replanning of the same oversized RED scenario. Strict microcycles advance a frontier after GREEN rather than repeatedly resubmitting the same full behavior.

Normal retry-scoped change identities remain valid for genuine bounded retries.

#### `92ec6259d6a2365d38495829210911f6c5d2cff6`
`development: defer proof trust promotion until semantic approval`

Revert. In the replacement model, each GREEN frontier plus regression clearance advances the development base. Behavior-level semantic review occurs after the complete scenario, not after every microstep.

The system must still prevent invalid REDs and failed GREENs from advancing the development base.

### Historical documentation to retain but mark superseded

#### `5665151`
`docs: record pr17 reservation book proof 3 status`

Keep as historical evidence. Update the document header to state that its progression model was superseded by PR22. Do not treat it as the current architecture contract.

### Commits to retain but rework

#### `d0ec87b8ba66d24538daee6a64056c8977779a78`
`docs: add PR17 test artifact principles`

Retain the concept of test-artifact principles, but replace the global rule that compile/import/bootstrap failure is never RED.

New rule:

> A compile/import/missing-capability failure is valid RED only when it occurs at the exact active scenario frontier and the materialised test artifact is syntactically complete.

#### `2354476d6a5eb95764f9ff18e7acbfd04478495d`
`development: add structured PR17 red analysis services`

Retain structured evidence, static analysis, and boundary reporting. Replace the full-scenario `valid_red` decision with frontier-aware boundary assessment.

#### `9e4f9e52b5eadc9a2bd08cdf40d9dfaae6507ed4`
`development: gate green on verified PR17 valid red`

Retain the invariant that Developer never receives an unaccepted RED. Change the accepted unit from a complete behavior test to the active scenario frontier.

#### `466fcff16faae4cb4102f0c2255ce1786b1ae80c`
`scripts: seed structured PR17 red probe helper`

Retain the evidence protocol, but move language-specific probing behind the language/test adapter contract.

#### `97024172993ad43d7c549dfafe2034ddeb61fb58`
`development: harden structured pytest red probe`

Retain pytest hooks and structured phase evidence. Extend classification so a missing capability at the active frontier can be valid RED while malformed syntax remains invalid.

#### `5488083682b8f87032d80efcb25560b6c9bd01d4`
`development: repair dependency decision recovery`

Retain for genuine cross-scenario or external dependencies. Remove missing types, constructors, methods, and earlier statements within one scenario from the normal dependency-planner route; those are handled by frontier progression.

### Local interrupted commits explicitly excluded

The following local commits are preserved only on:

```text
backup/model-switch-proof4-20260831
```

They must not be cherry-picked into PR17 or the redesign without separate review:

- `0ee5c3b` — `Repair non-actionable tester step proposals`
- `6e69665` — `Resume PR17 proof harness to terminal state`
- `69d3804` — `Persist accepted proof revisions before next phase`
- `d76c65a` — `Sync proof project baseline before each phase`

They were produced during an interrupted proof/model-switch session against the obsolete progression model. They are forensic evidence, not approved architecture.

---

## Controlled implementation sequence

### Phase 0 — Freeze and preserve

1. Keep PR17 head and the local backup branch immutable for comparison.
2. Preserve failed proof state/workspaces until the redesign is proven.
3. Do not run another ReservationBook proof against the old loop.
4. Cap existing retries at four before any further live proof.

### Phase 1 — Create implementation branch

Create a new implementation branch from the PR17 state after `5488083`, or create a branch from current PR17 and apply the explicit reverts above.

Preferred review-friendly approach:

1. branch from current PR17 head;
2. revert `fe2af8f`;
3. revert `0f7e833`;
4. revert `07bee72`;
5. revert `92ec625`;
6. mark proof-3 documentation superseded;
7. commit the rollback separately before new implementation.

### Phase 2 — Domain model

Add typed persistent records for:

- scenario draft;
- scenario intent result;
- scenario fragments;
- active frontier;
- language adapter identity/version;
- materialised test artifact;
- boundary assessment;
- microcycle retry state;
- final scenario completion.

### Phase 3 — Language adapter contract

Define the language-agnostic adapter protocol.

Implement Python/pytest first, but do not claim language independence until at least one structurally different adapter or conformance fake proves the interface can represent compiled/block-structured languages.

Add conformance tests for:

- Python indentation and context-manager blocks;
- C#/Java-style braces and compile diagnostics;
- VBA `If...End If` and `For...Next` block completeness.

### Phase 4 — Scenario drafting and intent validation

1. Tester receives one Behavior Planner ticket.
2. Tester returns one complete scenario draft and exact test identity.
3. Independent scenario-intent reviewer validates that the draft expresses the requested behavior.
4. Invalid scenario drafts receive descriptive repair, maximum four Tester attempts.
5. Approved scenario is frozen for microcycle progression.

### Phase 5 — Scenario fragmentation

1. Adapter parses approved scenario into AST/CST/model.
2. Adapter emits ordered syntactically complete fragments.
3. Engine persists frontier index zero.
4. Engine materialises only the first frontier as a complete test artifact.
5. No raw line slicing is permitted.

### Phase 6 — Strict RED boundary

1. Parse/compile/collect the materialised frontier.
2. Confirm artifact syntax is valid.
3. Confirm the first failure occurs at the active frontier.
4. Classify missing type/member/capability or behavioral assertion as valid RED when it matches the frontier.
5. Reject unrelated syntax, setup, infrastructure, or earlier-boundary failure.
6. Persist accepted RED evidence and exact development base.

### Phase 7 — Narrow GREEN

1. Developer receives only the active frontier and structured diagnostic.
2. Developer writes minimum production code.
3. Maximum four attempts.
4. Active frontier must pass.
5. Failed candidate never advances the development base.

### Phase 8 — Deterministic regression

1. Run current frontier test.
2. Run accumulated completed scenario tests.
3. Do not invoke an LLM to run tests.
4. On regression, create bounded conflict repair using current frontier plus failing prior tests.
5. Rerun full suite.
6. Advance development base only after regression clearance.

### Phase 9 — Advance frontier

1. Increment persisted scenario frontier.
2. Materialise the next complete test artifact for the same canonical test node.
3. Execute immediately.
4. If already GREEN, continue advancing until the next genuine RED or scenario completion.
5. Do not invoke Developer for passing frontiers.

### Phase 10 — Scenario completion and review

1. Final materialised test equals the approved full scenario.
2. Full scenario and accumulated suite pass.
3. Run one behavior-level Senior Review.
4. Mark the behavior requirement complete only after review.
5. Select the next Behavior Planner ticket.

### Phase 11 — Feature completion

1. All behavior scenarios complete.
2. Full regression suite passes.
3. Optional whole-feature semantic review.
4. Independent Specification Gatekeeper reconciliation.
5. Future PR21 engineering-quality/refactoring process begins only after behavior approval.

### Phase 12 — Persistence and resume proof

Prove restart at each boundary:

- after scenario approval;
- after accepted RED;
- after Developer GREEN;
- after regression clearance;
- between two frontiers;
- before behavior-level review.

Resume must not:

- expose later fragments early;
- repeat completed frontiers;
- lose retry counts;
- reuse stale Rack AI packets;
- regress development base.

### Phase 13 — Proof order

1. Unit tests for fragment construction and diagnostics.
2. Adapter conformance tests.
3. Generic toy scenario with missing type, method, operation, and assertion.
4. Persistence/resume proof.
5. Live tiny feature proof.
6. Brand-new ReservationBook proof only after all previous gates pass.

---

## Required generic test matrix

At minimum:

1. Missing type at frontier is valid RED.
2. Missing method at frontier is valid RED.
3. Behavioral assertion failure at frontier is valid RED.
4. Incomplete syntax is invalid test artifact.
5. Failure before frontier is rejected.
6. Later scenario fragments are invisible to Developer.
7. Passing frontier advances automatically without Developer.
8. Regression blocks development-base promotion.
9. Regression repair remains bounded.
10. Same canonical test grows without duplicate final tests.
11. Retry budget stops at four.
12. Resume continues at exact frontier.
13. Complete `If`/loop/block fragments are never sliced by line.
14. Unsupported language adapter fails closed.
15. Final Gatekeeper sees only completed accepted tests.

---

## Definition of done

PR22 implementation is complete only when:

- the active test unit is a language-adapter frontier, not a complete future scenario;
- every frontier artifact is syntactically complete;
- missing capabilities at the frontier can be valid RED;
- arbitrary syntax/collection failures are not accepted;
- Developer sees only one frontier;
- Developer writes only enough production code to make that frontier pass;
- accumulated tests remain GREEN after each frontier;
- regression execution is deterministic;
- one canonical test grows to the complete approved scenario;
- no normal-path prerequisite deferral is used for missing type/member/earlier scenario statements;
- provisional semantic progression is absent from the inner microcycle;
- Senior Review occurs at behavior or feature level, not every tiny frontier;
- retries are capped at four;
- persistence/resume is proven;
- Python and block-structured/compiled-language conformance are demonstrated;
- one fresh ReservationBook proof completes from an empty implementation;
- no ReservationBook-specific logic exists in orchestration.

---

## Final architectural summary

```text
Original requirement
  -> independent Gatekeeper checklist
  -> Behavior Contract
  -> next behavior ticket
  -> Tester full scenario draft
  -> scenario-intent approval
  -> language adapter fragments scenario
  -> active syntactically complete frontier
  -> strict RED at active frontier
  -> narrow Developer GREEN
  -> deterministic regression
  -> next frontier
  -> complete scenario GREEN
  -> behavior-level semantic review
  -> next behavior
  -> complete feature regression
  -> final Gatekeeper reconciliation
  -> future PR21 quality/refactoring lane
```

This design is intentionally smaller than the current PR17 inner loop. It accepts that strict TDD is sequential within one scenario and preserves parallelism only across genuinely independent GREEN boundaries.