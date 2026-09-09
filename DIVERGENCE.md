# Divergence and Quarantine

Date: 2026-08-30

This repository intentionally contains both the modern PR17 development-semantics path and older compatibility stacks. The important distinction is ownership, not mere file presence.

## Modern authoritative path

The authoritative ATHBA path is the PR17 lane built around:
- `core/development/behavior_contract_coordinator.py`
- the Session 1-3 domain modules under `core/development/`
- `core/execution/` Rack AI gateway adapters
- `scripts/run_pr17_independent_reservation_book.py`

This path owns Behavior Contracts, failure progression, Gatekeeper state, targeted gaps, accepted-test reconciliation, and trusted revision progression.

## Quarantined compatibility path

The following remain reachable but non-authoritative for modern PR17 work:
- `llm_service/` local LLM runtime
- `core/agents/` legacy PM/Spec/Architect/Developer/Tester chat flows
- `core/services/git_service.py` and `core/services/test_execution_service.py` legacy `/tmp/athba_repos` loop
- `core/agents/helpers/llm_exchange.py` compatibility provider bridge

These paths stay in the repo for compatibility and smoke coverage. They must not redefine the ATHBA versus Rack AI boundary.

## Operational rule

When updating documentation, CI, or validation policy, treat the modern PR17 path as authoritative and describe the legacy surfaces explicitly as quarantined compatibility code.
