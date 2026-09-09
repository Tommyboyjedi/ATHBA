# ATHBA Testing

Date: 2026-08-30

## Standard validation sequence

Use the same gates locally and in CI:

```bash
poetry run python scripts/check_coding_principles.py
poetry run mypy
poetry run python -m compileall athba core llm_service tests scripts
poetry run pytest -q
```

Recommended CPU-only environment for repeatable verification:

```bash
export DJANGO_SECRET_KEY=athba-test-secret
export CPU_ONLY=true
export MONGO_USER=test
export MONGO_PASS=test
```

## Focused PR17 suites

Examples of focused validation surfaces used during the pre-PR17 remediation work:
- `tests/development/test_behavior_contract_coordinator.py`
- `tests/development/test_specification_gatekeeper.py`
- `tests/development/test_test_evidence_reconciliation.py`
- `tests/development/test_state_store_safety.py`
- `tests/development/test_architecture_quarantine.py`
- `tests/execution/test_rack_ai_cli_gateway.py`

## Warning policy

- Fix ATHBA-owned deprecations when touching active code.
- Keep third-party warning filters narrow and documented.
- Do not use broad warning suppression to make the suite look healthy.
