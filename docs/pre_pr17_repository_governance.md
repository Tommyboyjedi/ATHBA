# Pre-PR17 Repository Governance

Date: 2026-08-30
Branch: `pr17-specification-gatekeeper`
Scope: `/srv/ATHBA`
Baseline HEAD before edits: `973f5f8aad84531398b11d3df96193e7b6e46248`
Implementation commit: `9671f84f7e901fb0b7e079917f310b0c1e3ee2dd`

## Checklist

- [x] Mandatory governance inputs reviewed.
  Target responsibility: derive governance and CI changes from the current repository state rather than stale notes.
  Implementation evidence: re-read `AGENTS.md`, `agent.MD`, `coding_principles.MD`, current PR17 description, `docs/pr17-specification-gatekeeper.md`, current workflow state, `pyproject.toml`, top-level docs, and the Jobs 1-3 ledgers before editing.
  Tests: N/A.
  Commit SHA: `9671f84f7e901fb0b7e079917f310b0c1e3ee2dd`

- [x] Coding-principles gate hardened.
  Target responsibility: count variadics as real inputs and enforce the repo-wide application-owned class audit without broad exemptions.
  Implementation evidence: updated `scripts/check_coding_principles.py` so `*args` and `**kwargs` count as real inputs, then fixed the exposed `TddCoordinator` constructor violation instead of suppressing it.
  Tests: `./.venv/bin/python scripts/check_coding_principles.py` -> `coding principles gate passed`.
  Commit SHA: `9671f84f7e901fb0b7e079917f310b0c1e3ee2dd`

- [x] Static type gate added.
  Target responsibility: add a real type checker over the modern typed PR17 surfaces and provider boundary.
  Implementation evidence: added `mypy` to the committed Poetry dev dependency set, configured a scoped `mypy` gate in `pyproject.toml`, tightened the provider contract to `ProviderRequest`, and aligned the Gatekeeper evidence/checklist union types with that typed boundary.
  Tests: `./.venv/bin/python -m mypy` -> `Success: no issues found in 13 source files`.
  Commit SHA: `9671f84f7e901fb0b7e079917f310b0c1e3ee2dd`

- [x] CI gate expanded.
  Target responsibility: make CI enforce the same required repo gates from the committed lockfile.
  Implementation evidence: updated `.github/workflows/python.yml` to install Poetry `2.4.1`, sync from `poetry.lock`, and run coding gate, `mypy`, `compileall`, and `pytest -q` in CPU-only mode.
  Tests: `./.venv/bin/python - <<'PY' ... yaml.safe_load(...)` -> `workflow yaml ok`.
  Commit SHA: `9671f84f7e901fb0b7e079917f310b0c1e3ee2dd`

- [x] Reproducibility state recorded.
  Target responsibility: keep dependency resolution committed and consistent with Python `^3.14`.
  Implementation evidence: preserved Python `^3.14`, kept the committed `poetry.lock`, and intentionally updated it only for the new `mypy` dev dependency.
  Tests: `./.venv/bin/python -m poetry check` -> warnings only about Poetry 2.4.1 metadata deprecations for `[tool.poetry]`; no lock or dependency integrity errors.
  Commit SHA: `9671f84f7e901fb0b7e079917f310b0c1e3ee2dd`

- [x] Warning reduction performed without broad suppression.
  Target responsibility: remove clear ATHBA-owned warning sources in touched active code and classify the remaining warning sources.
  Implementation evidence: replaced ATHBA-owned `datetime.utcnow()` usage across `core/` with timezone-aware UTC, added `__test__ = False` to `TestRunRequest` and `TestExecutionService`, and updated the most visible test fixtures to stop emitting ATHBA-owned deprecation warnings.
  Tests: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q` -> `239 passed`; remaining warnings are third-party Python 3.14 deprecations from `pytest_asyncio` and Django.
  Commit SHA: `9671f84f7e901fb0b7e079917f310b0c1e3ee2dd`

- [x] PR17 contract document synchronized.
  Target responsibility: align the source-controlled PR17 contract with the authoritative current PR body, especially independence and final `YES` or `NO` reconciliation semantics.
  Implementation evidence: rewrote `docs/pr17-specification-gatekeeper.md` around the current PR17 contract and its final accepted-test reconciliation rule.
  Tests: N/A.
  Commit SHA: `9671f84f7e901fb0b7e079917f310b0c1e3ee2dd`

- [x] Repository documentation updated.
  Target responsibility: make operator docs describe the real modern repository state instead of the retired local-stack-first story.
  Implementation evidence: updated `README.md`, `PROJECT_STATE.md`, `DIVERGENCE.md`, `docs/SETUP.md`, and `docs/TESTING.md` to reflect the `/srv/ATHBA` PR17 path, the ATHBA versus Rack AI boundary, and the actual validation workflow.
  Tests: N/A.
  Commit SHA: `9671f84f7e901fb0b7e079917f310b0c1e3ee2dd`

- [x] Mongo configuration contract made consistent.
  Target responsibility: align settings and docs with the actual authenticated `MONGO_*` runtime contract.
  Implementation evidence: updated `athba/settings.py` and `.env.example` to expose the `MONGO_HOST`, `MONGO_PORT`, `MONGO_DB_NAME`, `MONGO_USER`, and `MONGO_PASS` contract used by `core.infra.mongo`.
  Tests: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q tests/api/test_projects_active.py` -> included in focused pass, `42 passed` total focused suite.
  Commit SHA: `9671f84f7e901fb0b7e079917f310b0c1e3ee2dd`

## Validation

- Focused governance suite: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q tests/llm/test_openai_provider.py tests/development/test_tdd_coordinator.py tests/development/test_specification_gatekeeper.py tests/development/test_test_evidence_reconciliation.py tests/api/test_projects_active.py` -> `42 passed, 3784 warnings in 0.93s` before test-fixture warning cleanup.
- Coding gate: `./.venv/bin/python scripts/check_coding_principles.py` -> `coding principles gate passed`.
- Static type gate: `./.venv/bin/python -m mypy` -> `Success: no issues found in 13 source files`.
- Full suite: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q` -> `239 passed, 25281 warnings in 11.78s`.
- Compileall: `./.venv/bin/python -m compileall athba core llm_service tests scripts` -> passed.
- Workflow syntax: `./.venv/bin/python - <<'PY' ... yaml.safe_load(...)` -> `workflow yaml ok`.
- Diff check: `git diff --check` -> passed.

MANUAL_GITHUB_ACTION_REQUIRED = PRESENT
Manual action detail: configure the repository's required status checks in GitHub branch protection to include the updated workflow gate after this branch lands.
INCOMPLETE_ITEMS = NONE
