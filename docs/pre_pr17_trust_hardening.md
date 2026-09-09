# Pre-PR17 Trust Hardening

Date: 2026-08-30
Branch: `pr17-specification-gatekeeper`
Scope: `/srv/ATHBA`
Code milestone: `1a1538b`

## Baseline

- [x] Confirmed working branch and protected legacy snapshot.
  Evidence: `git rev-parse legacy` = `8334f42a8865b9360972f5e0422a8f61d02dedb6`; `git rev-parse HEAD` before edits = `2504256956fcd47970c7314f7e5525beacc6936f`.
  Tests: N/A.
  Commit SHA: `1a1538b`
- [x] Read mandatory guidance and architecture/state constraints before editing.
  Evidence: reviewed `AGENTS.md`, `agent.MD`, `coding_principles.MD`, PR17 description, `docs/pr17-specification-gatekeeper.md`, `docs/pre_pr17_correctness_remediation.md`, `docs/ATHBA_RACK_AI_ARCHITECTURE.md`, `docs/pr19-environment-management.md`.
  Tests: N/A.
  Commit SHA: `1a1538b`
- [x] Identified the active trust and durability surfaces.
  Evidence: audited `core/datastore/repos/tdd_state_repo.py`, `core/datastore/repos/work_unit_state_repo.py`, `core/development/project_environment_store.py`, `core/development/project_environment_lifecycle.py`, `core/services/git_service.py`, `core/services/test_execution_service.py`, `core/execution/rack_ai_cli_transport.py`, `core/execution/rack_ai_result.py`, `core/execution/rack_ai_cli_gateway.py`, `core/development/specification_reconciliation.py`, and `core/agents/behaviors/developer/generate_code_behavior.py`.
  Tests: focused suite selected from `tests/services/test_git_service.py`, `tests/services/test_test_execution_service.py`, `tests/development/test_state_store_safety.py`, `tests/development/test_project_environment.py`, `tests/execution/test_rack_ai_cli_gateway.py`, `tests/development/test_test_evidence_reconciliation.py`, `tests/development/test_specification_gatekeeper.py`.
  Commit SHA: `1a1538b`

## Responsibility Map

- [x] Project/state persistence confinement.
  Target responsibility: reject unsafe filesystem identifiers and keep state roots confined.
  Implementation evidence: added `core/filesystem_policy.py`; updated `core/development/project_environment_store.py`, `core/datastore/repos/tdd_state_repo.py`, `core/datastore/repos/work_unit_state_repo.py`, and `core/development/project_environment_lifecycle.py`.
  Tests: `tests/development/test_state_store_safety.py`, `tests/development/test_project_environment.py`.
  Commit SHA: `1a1538b`
- [x] Atomic durable JSON state writes.
  Target responsibility: write authoritative JSON via same-directory temp file, fsync, replace, cleanup.
  Implementation evidence: added `core/atomic_json_file.py`; moved file-backed authoritative stores onto `write_json_atomically(...)`.
  Tests: `tests/development/test_state_store_safety.py::test_atomic_json_write_preserves_existing_file_on_replace_failure`.
  Commit SHA: `1a1538b`
- [x] Legacy Git/file access confinement.
  Target responsibility: reject unsafe project identifiers and repository-relative file paths before repository mutation/read.
  Implementation evidence: updated `core/services/git_service.py` and the direct test-context file read in `core/agents/behaviors/developer/generate_code_behavior.py`.
  Tests: `tests/services/test_git_service.py`.
  Commit SHA: `1a1538b`
- [x] Test-file traversal confinement.
  Target responsibility: reject unsafe project identifiers and unsafe requested test file paths; keep discovery inside repository root.
  Implementation evidence: updated `core/services/test_execution_service.py` to use identifier/path confinement and repository-bounded discovery.
  Tests: `tests/services/test_test_execution_service.py`.
  Commit SHA: `1a1538b`
- [x] Rack AI packet trust and request identity verification.
  Target responsibility: confine packet loading under configured state root and verify returned packet identity against submitted request identity before mapping.
  Implementation evidence: updated `core/execution/rack_ai_cli_transport.py`, `core/execution/rack_ai_result.py`, and `core/execution/rack_ai_cli_gateway.py`.
  Tests: `tests/execution/test_rack_ai_cli_gateway.py`.
  Commit SHA: `1a1538b`
- [x] Final accepted-test evidence continuity.
  Target responsibility: require the accepted test body from semantic acceptance to still exist unchanged at the final trusted revision before returning YES.
  Implementation evidence: updated `core/development/specification_reconciliation.py` to compare accepted and final test-body digests by pytest node id.
  Tests: `tests/development/test_test_evidence_reconciliation.py`, `tests/development/test_specification_gatekeeper.py`.
  Commit SHA: `1a1538b`

## Validation

- [x] Focused trust/persistence suite passed.
  Evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/services/test_git_service.py tests/services/test_test_execution_service.py tests/development/test_state_store_safety.py tests/development/test_project_environment.py tests/execution/test_rack_ai_cli_gateway.py tests/development/test_test_evidence_reconciliation.py tests/development/test_specification_gatekeeper.py`
  Tests: `75 passed in 9.20s`.
  Commit SHA: `1a1538b`
- [x] Coding principles gate passed.
  Evidence: `./.venv/bin/python scripts/check_coding_principles.py`
  Tests: `coding principles gate passed`.
  Commit SHA: `1a1538b`
- [x] Full test suite passed.
  Evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q`
  Tests: `231 passed, 23993 warnings in 11.67s`.
  Commit SHA: `1a1538b`
- [x] Compileall passed.
  Evidence: `./.venv/bin/python -m compileall athba core llm_service tests scripts`
  Tests: completed without compile errors.
  Commit SHA: `1a1538b`
- [x] `git diff --check` passed.
  Evidence: `git diff --check`
  Tests: completed without diff errors.
  Commit SHA: `1a1538b`
- [x] Branch state and boundary were recorded.
  Evidence: `git status --short --branch` after validation showed only this ledger file pending on `pr17-specification-gatekeeper`; `git rev-parse legacy` remained `8334f42a8865b9360972f5e0422a8f61d02dedb6` throughout the job.
  Tests: `git status --short --branch`; `git rev-parse legacy`.
  Commit SHA: `1a1538b`

INCOMPLETE_ITEMS = NONE
