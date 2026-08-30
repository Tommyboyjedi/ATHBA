# Pre-PR17 Correctness Remediation

- [x] Scope and mandatory inputs reviewed.
  Evidence: Re-read AGENTS.md, agent.MD, coding_principles.MD, PR17 description, gatekeeper docs/ledgers, and machine gate before editing on 2026-08-30.
  Commit SHA: PENDING
- [x] Baseline defect audit captured.
  Evidence: Confirmed dependency reasoning boundary bug, tester stale `run_tests` call, broken Spec behavior active paths, and duplicated `RepositoryBinding` persistence boundary.
  Commit SHA: PENDING
- [ ] Dependency prerequisite reasoning boundary repaired.
  Target responsibility: `DependencyPrerequisitePlanner` must send `ReasoningRequest` to the reasoning gateway.
  Implementation evidence: PENDING
  Tests: PENDING
  Commit SHA: PENDING
- [ ] Tester execution service boundary repaired.
  Target responsibility: active tester behavior must call `TestExecutionService.run_tests()` with canonical `TestRunRequest`.
  Implementation evidence: PENDING
  Tests: PENDING
  Commit SHA: PENDING
- [ ] Spec behavior call chain repaired.
  Target responsibility: active Spec behaviors must run through `BehaviorExecution`, return `ChatMessage`, and use canonical repo request objects.
  Implementation evidence: PENDING
  Tests: PENDING
  Commit SHA: PENDING
- [ ] Repository binding persistence repaired.
  Target responsibility: `RepositoryBinding` owns its persistence boundary; snapshots preserve optional fields and `environment_resources` without breaking legacy loads.
  Implementation evidence: PENDING
  Tests: PENDING
  Commit SHA: PENDING
- [ ] Session 6 caller compatibility audit completed.
  Target responsibility: changed production boundaries have no remaining confirmed stale callers in audited scope.
  Implementation evidence: PENDING
  Tests: PENDING
  Commit SHA: PENDING
- [ ] Focused baseline and post-fix tests recorded.
  Target responsibility: targeted regressions prove repaired boundaries and compatibility.
  Implementation evidence: PENDING
  Tests: PENDING
  Commit SHA: PENDING
- [ ] Final validation suite recorded.
  Target responsibility: coding-principles gate, full pytest, compileall, diff check, and status all pass.
  Implementation evidence: PENDING
  Tests: PENDING
  Commit SHA: PENDING

INCOMPLETE_ITEMS = PRESENT
