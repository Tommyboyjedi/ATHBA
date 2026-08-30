# Project Execution Boundary Refactor Plan

Date: 2026-08-30
Branch: `pr17-specification-gatekeeper`
Legacy snapshot: `8334f42a8865b9360972f5e0422a8f61d02dedb6`
Target modules:
- `core/development/project_environment.py`
- `core/execution/rack_ai_contract.py`
- `core/execution/rack_ai_cli_gateway.py`

## Session checklist

- [x] Verify branch and protected historical snapshot.
  Target responsibility: branch safety and historical boundary preservation.
  Implementation evidence: `git rev-parse --abbrev-ref HEAD` returned `pr17-specification-gatekeeper`; `git rev-parse legacy` returned `8334f42a8865b9360972f5e0422a8f61d02dedb6`.
  Tests: N/A.
  Commit SHA: `WORKTREE`
- [x] Read mandatory inputs before editing.
  Target responsibility: architectural and coding-principle compliance.
  Implementation evidence: reviewed `AGENTS.md`, `agent.MD`, `coding_principles.MD`, the PR17 description, `docs/pr17-specification-gatekeeper.md`, `scripts/check_coding_principles.py`, all completed Session 1-4 ledgers, target modules, focused tests, and direct callers.
  Tests: N/A.
  Commit SHA: `WORKTREE`
- [x] Inventory current module sizes, classes/functions, call graph, persistence surfaces, wire fields, and boundary responsibilities before refactor.
  Target responsibility: exact pre-refactor boundary map.
  Implementation evidence: recorded current module sizes, class list, caller/import surface, persisted `state/projects/.../project.json` shape, and Rack AI request/result fields below.
  Tests: N/A.
  Commit SHA: `WORKTREE`
- [x] Run focused baseline tests before refactor.
  Target responsibility: establish current project lifecycle, trusted revision, Rack AI contract, and gateway behavior.
  Implementation evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_project_environment.py tests/execution/test_rack_ai_work_unit_contract.py tests/execution/test_rack_ai_cli_gateway.py tests/development/test_behavior_contract_coordinator.py` passed with `89 passed`.
  Tests: `tests/development/test_project_environment.py`, `tests/execution/test_rack_ai_work_unit_contract.py`, `tests/execution/test_rack_ai_cli_gateway.py`, `tests/development/test_behavior_contract_coordinator.py`.
  Commit SHA: `WORKTREE`
- [x] Decompose project lifecycle, runtime state, persistence, and retirement into cohesive objects while preserving `core.development.project_environment` import compatibility.
  Target responsibility: typed ATHBA-owned project state and lifecycle services.
  Implementation evidence: introduced `core/development/project_environment_state.py`, `core/development/project_environment_store.py`, `core/development/project_environment_git.py`, and `core/development/project_environment_lifecycle.py`; reduced `core/development/project_environment.py` to a compatibility facade.
  Tests: `tests/development/test_project_environment.py`, `tests/development/test_behavior_contract_coordinator.py`.
  Commit SHA: `WORKTREE`
- [x] Isolate trusted revision promotion and Git-side verification into focused collaborators while preserving fast-forward and rollback guarantees.
  Target responsibility: explicit trusted revision promotion boundary.
  Implementation evidence: `TrustedRevisionPromoter` now owns canonical ref verification, fast-forward validation, compare-and-swap promotion, and rollback-on-save-failure using `GitProjectClient` request objects.
  Tests: `tests/development/test_project_environment.py`, `tests/development/test_behavior_contract_coordinator.py`.
  Commit SHA: `WORKTREE`
- [x] Separate Rack AI domain contract, wire serialization, CLI process transport, and result/error mapping while preserving current request/response shape.
  Target responsibility: explicit ATHBA to Rack AI boundary.
  Implementation evidence: introduced `core/execution/rack_ai_request.py`, `core/execution/rack_ai_result.py`, and `core/execution/rack_ai_cli_transport.py`; reduced `core/execution/rack_ai_cli_gateway.py` to request-build, transport, and result-map composition; reduced `core/execution/rack_ai_contract.py` to compatibility re-exports.
  Tests: `tests/execution/test_rack_ai_work_unit_contract.py`, `tests/execution/test_rack_ai_cli_gateway.py`, `tests/development/test_project_environment.py`.
  Commit SHA: `WORKTREE`
- [x] Extend `scripts/check_coding_principles.py` to cover all Session 5 changed/new application classes without broad exemptions.
  Target responsibility: machine enforcement for the Session 5 scope.
  Implementation evidence: added the Session 5 project-environment and Rack AI boundary modules to `TARGETS` without weakening earlier session coverage.
  Tests: `./.venv/bin/python scripts/check_coding_principles.py`.
  Commit SHA: `WORKTREE`
- [x] Add or update compatibility tests where persistence or wire compatibility coverage is weak.
  Target responsibility: preserved readable state and Rack AI wire shape.
  Implementation evidence: added a legacy project-state compatibility test proving old payloads missing `runtime.environment_resources` still reload; updated gateway monkeypatch coverage for the extracted transport module.
  Tests: `tests/development/test_project_environment.py`, `tests/execution/test_rack_ai_cli_gateway.py`.
  Commit SHA: `WORKTREE`
- [x] Run post-refactor focused tests.
  Target responsibility: local behavior preservation.
  Implementation evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_project_environment.py tests/execution/test_rack_ai_work_unit_contract.py tests/execution/test_rack_ai_cli_gateway.py tests/development/test_behavior_contract_coordinator.py` passed with `90 passed`.
  Tests: `tests/development/test_project_environment.py`, `tests/execution/test_rack_ai_work_unit_contract.py`, `tests/execution/test_rack_ai_cli_gateway.py`, `tests/development/test_behavior_contract_coordinator.py`.
  Commit SHA: `WORKTREE`
- [x] Run full suite.
  Target responsibility: repository-wide compatibility.
  Implementation evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q` passed with `197 passed`.
  Tests: repository test suite.
  Commit SHA: `WORKTREE`
- [x] Run compileall.
  Target responsibility: import and syntax integrity.
  Implementation evidence: `./.venv/bin/python -m compileall athba core llm_service tests scripts` completed successfully.
  Tests: `compileall`.
  Commit SHA: `WORKTREE`
- [x] Run `git diff --check`.
  Target responsibility: patch hygiene.
  Implementation evidence: `git diff --check` returned no output.
  Tests: `git diff --check`.
  Commit SHA: `WORKTREE`
- [ ] Confirm `legacy` remains unchanged and push all Session 5 commits to PR17.
  Target responsibility: branch integrity and publication.
  Implementation evidence: pending commit/push step.
  Tests: `git rev-parse legacy`, `git push`.
  Commit SHA: `PENDING`
- [x] Finalize this ledger with `INCOMPLETE_ITEMS = NONE` only after every mandatory item is complete.
  Target responsibility: authoritative Session 5 record.
  Implementation evidence: this ledger now records the completed decomposition, compatibility evidence, and validation results; publication evidence will be updated after push.
  Tests: N/A.
  Commit SHA: `WORKTREE`

## Before refactor

- `core/development/project_environment.py`
  - Size: `10153` bytes
  - Lines: `216`
  - Classes: `ProjectRuntime`, `DevelopmentProject`, `ProjectEnvironmentRepo`, `ProjectEnvironmentService`
  - Helpers/constants: `LIFECYCLE_STATES`, `ENVIRONMENT_LIFETIMES`
- `core/execution/rack_ai_contract.py`
  - Size: `6351` bytes
  - Lines: `179`
  - Classes: `RepositoryBinding`
  - Helpers/constants: `SUPPORTED_ACCEPTANCE_VERDICTS`, `FORBIDDEN_RESOURCE_SELECTION_KEYS`, `to_rack_ai_request`, `parse_rack_ai_result`, payload walkers, string validators
- `core/execution/rack_ai_cli_gateway.py`
  - Size: `5461` bytes
  - Lines: `138`
  - Classes: `RackAiCliTransportError`, `RackAiCliConfig`, `RackAiCliExecutionGateway`
  - Helpers: summary parsing, packet loading, error formatting, CLI argv assembly

## Persistence surfaces to preserve

- `state/projects/<project_id>/project.json`
  - `project_id`
  - `repository_root`
  - `default_ref`
  - `trusted_base_sha`
  - `runtime.kind`
  - `runtime.version`
  - `runtime.environment_path`
  - `runtime.test_command`
  - `runtime.build_command`
  - `runtime.lifetime`
  - optional `runtime.environment_resources`
  - `generated_paths`
  - `status`
  - `workspace_lifetime`
- Compatibility detail
  - older payloads omit `runtime.environment_resources`
  - newer payloads include `runtime.environment_resources: ["/srv/ATHBA/.venv"]`
- Rack AI request shape
  - `change_id`
  - `repository.id`
  - `repository.base_ref`
  - optional `repository.base_sha`
  - optional `repository.root`
  - `task`
  - `allowed_paths`
  - `acceptance.commands`
  - `acceptance.required_artifacts`
  - `limits.max_implementation_attempts`
  - `limits.timeout_seconds`
  - `limits.network`
  - optional `environment_resources`
- Rack AI result fields consumed
  - `work_unit_id`
  - `change_id`
  - `status`
  - `acceptance_verdict`
  - optional `accepted_head_sha`
  - optional `accepted_revision`
  - optional `head_sha`
  - optional `selected_worker_id`
  - optional `placement`
  - optional `branch`
  - optional `packet_path`
  - optional `worktree_path`
  - optional `worktree`
  - optional `last_error`

## Public callers and focused tests

- Callers/importers
  - `scripts/run_pr19_environment_proof.py`
  - `scripts/run_pr17_independent_reservation_book.py`
  - `core/execution/work_unit_gateway.py`
  - `core/development/progression.py`
  - `core/development/contract_run_domain.py`
  - tests in `tests/development` and `tests/execution`
- Focused baseline tests
  - `tests/development/test_project_environment.py`
  - `tests/execution/test_rack_ai_work_unit_contract.py`
  - `tests/execution/test_rack_ai_cli_gateway.py`
  - `tests/development/test_behavior_contract_coordinator.py`

## Resulting modules and responsibilities

- `core/development/project_environment_state.py`
  - project lifecycle enums, runtime/environment value objects, persisted project state, compatibility decoding
- `core/development/project_environment_store.py`
  - file-backed project persistence
- `core/development/project_environment_git.py`
  - repository initialization, commit lookup, canonical ref lookup, ancestry checks, ref promotion
- `core/development/project_environment_lifecycle.py`
  - runtime factory, readiness verifier, bootstrapper, trusted revision promoter, retire flow, composed service entrypoint
- `core/development/project_environment.py`
  - compatibility facade and re-exports
- `core/execution/rack_ai_request.py`
  - repository binding, typed Rack AI request records, explicit wire serialization
- `core/execution/rack_ai_result.py`
  - accepted/rejected result parsing, execution-result mapping, forbidden resource-key scanning
- `core/execution/rack_ai_cli_transport.py`
  - CLI argv assembly, temp spec writing, stdout summary parsing, packet loading, transport error creation
- `core/execution/rack_ai_cli_gateway.py`
  - thin composition gateway
- `core/execution/rack_ai_contract.py`
  - compatibility re-exports for public import stability

INCOMPLETE_ITEMS = PRESENT
