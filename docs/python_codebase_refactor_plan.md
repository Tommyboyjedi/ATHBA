# Python Codebase Refactor Plan

Date: 2026-08-30
Branch: `pr17-specification-gatekeeper`
Legacy snapshot: `8334f42a8865b9360972f5e0422a8f61d02dedb6`
Scope: application-owned Python under `athba/`, `core/`, and `llm_service/`

## Repository Audit

- Python files scanned: `193`
- Application-owned classes scanned: `283`
- Initial violation counts:
  - class-size: `1`
  - parameter-count: `60`
  - ATHBA-owned inheritance candidates before classification: `51`
  - major magic state/policy issues: repeated agent/tier/status strings and hard-coded retry/timeout/cooldown values across `core/services/`, `core/agents/`, and `core/llm/`
  - SQL/data-processing issues: `ProjectsService.list_active_projects` filtered active projects in Python instead of querying the repo directly

## Final Outcome Summary

- Repo-wide coding-principles gate expanded to scan application-owned code under `athba/`, `core/`, and `llm_service/`
- ATHBA-owned inheritance removed from agents, behaviors, providers, and touched endpoint schemas in this session scope
- Request/value objects introduced where touched services, repos, progression helpers, and provider boundaries previously exceeded the two-input rule
- `RdAgent` reduced below the class-size limit by extracting watchdog and protected-model helpers
- Active-project filtering moved into `ProjectRepo.list_active()` to eliminate the clear SQL-in-Python issue
- Provider and progression compatibility boundaries were repaired after full-suite validation exposed regressions

## Validation Evidence

- Initial baseline:
  - `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q`
  - Result: `197 passed, 20769 warnings in 11.25s`
- Focused regression/area coverage:
  - `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/services/test_git_service.py tests/test_spec_repo_normalize.py tests/test_foundation_contracts.py tests/development/test_tdd_coordinator.py tests/behaviors/test_analyze_spec_behavior.py tests/integration/test_spec_to_tickets_flow.py`
  - Result: `45 passed, 4551 warnings in 1.61s`
  - `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_coordinator.py tests/development/test_tdd_coordinator.py tests/test_spec_repo_normalize.py tests/integration/test_spec_to_tickets_flow.py tests/llm/test_openai_provider.py`
  - Result: `30 passed, 2865 warnings in 0.85s`
- Final required validations:
  - `./.venv/bin/python scripts/check_coding_principles.py`
  - Result: `coding principles gate passed`
  - `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q`
  - Result: `197 passed, 20769 warnings in 11.25s`
  - `./.venv/bin/python -m compileall athba core llm_service tests scripts`
  - Result: pass
  - `git diff --check`
  - Result: pass

## Checklist

- [x] Expand `scripts/check_coding_principles.py` into a repo-wide application-code gate.
  - Target responsibility: deterministic repo-wide class-size, parameter-count, inheritance, and exception enforcement.
  - Implementation evidence: gate now scans application-owned modules under `athba/`, `core/`, and `llm_service/`, and the final run returned `coding principles gate passed`.
  - Tests: `./.venv/bin/python scripts/check_coding_principles.py`
  - Commit SHA: `5465078`
- [x] Remove ATHBA-owned inheritance from agents, behaviors, providers, and endpoint schemas touched in Session 6.
  - Target responsibility: composition-only application layer.
  - Implementation evidence: agent and behavior abstractions now use protocols/composition, providers no longer rely on ATHBA-owned inheritance, and ticket schemas were flattened.
  - Tests: `tests/behaviors/test_analyze_spec_behavior.py`, `tests/integration/test_spec_to_tickets_flow.py`, `tests/development/test_behavior_contract_coordinator.py`, full suite.
  - Commit SHA: `5465078`
- [x] Replace remaining 3+ input application methods with typed request/context objects in touched session scope.
  - Target responsibility: two-input rule across services, repos, provider boundaries, and progression helpers.
  - Implementation evidence: request/value objects were added in `core/services/service_requests.py`, `core/datastore/repos/mongo_requests.py`, and `core/development/progression.py`; touched callers now pass explicit request objects.
  - Tests: `tests/services/test_git_service.py`, `tests/test_spec_repo_normalize.py`, `tests/development/test_coordinator.py`, `tests/development/test_tdd_coordinator.py`, `tests/llm/test_openai_provider.py`, full suite.
  - Commit SHA: `5465078`, `6289b86`
- [x] Decompose or reduce the only oversize changed class.
  - Target responsibility: no unapproved class-size violations.
  - Implementation evidence: `RdAgent` was reduced to `70` executable lines by moving watchdog-specific logic into helper functions.
  - Tests: repo-wide gate, full suite.
  - Commit SHA: `5465078`
- [x] Resolve clear SQL/data-processing violations in DB-backed code.
  - Target responsibility: push natural filtering into the repo/query layer.
  - Implementation evidence: `ProjectsService.list_active_projects()` now delegates to `ProjectRepo.list_active()` instead of filtering all projects in Python.
  - Tests: full suite baseline and final suite.
  - Commit SHA: `5465078`
- [x] Preserve behavior through focused reruns and final validation.
  - Target responsibility: no functional drift from the structural refactor.
  - Implementation evidence: provider compatibility and progression compatibility regressions were fixed after `--maxfail=1` full-suite reruns exposed them.
  - Tests: focused reruns above, final `197 passed`, compileall pass, `git diff --check` pass.
  - Commit SHA: `6289b86`
- [x] Record final session evidence in this ledger.
  - Target responsibility: durable execution evidence for Session 6.
  - Implementation evidence: this ledger captures the audit, validation results, and milestone SHAs.
  - Tests: N/A
  - Commit SHA: `0e00663`

INCOMPLETE_ITEMS = NONE
