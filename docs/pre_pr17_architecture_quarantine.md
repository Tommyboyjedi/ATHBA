# Pre-PR17 Architecture Quarantine

Date: 2026-08-30
Branch: `pr17-specification-gatekeeper`
Scope: `/srv/ATHBA`
Baseline HEAD before edits: `b9efd59344abbe4770e14b4ca69ec64c7afdd8f7`

## Authority

- Modern ATHBA owns product-development semantics: PM-led product interaction, specification meaning, architecture decomposition, Behavior Contracts, Gatekeeper obligations, development planning, Tester/Developer/Senior Reviewer semantics, project runtime meaning, and trusted revision progression.
- Rack AI owns physical execution control: worker and model selection, GPU and rack resource arbitration, model lifecycle, bounded process execution, path/network/resource policy, and accepted candidate materialization.
- Legacy ATHBA components may remain reachable for compatibility, but they must not redefine or compete with the modern ATHBA versus Rack AI ownership boundary.

## Component Classification

| component | active? | owner | disposition | evidence | action |
| --- | --- | --- | --- | --- | --- |
| `PR17 BehaviorContract lane` | yes | ATHBA | A. ACTIVE PRODUCT PATH | `scripts/run_pr17_independent_reservation_book.py` uses `BehaviorContractCoordinator`, `ProviderReasoningGateway`, `ProjectEnvironmentService`, `RackAiCliExecutionGateway`, `GitAcceptedTestCatalog`, and `TestEvidenceReconciler`; no imports of `llm_service`, `LlmExchange`, `GitService`, or `TestExecutionService`. | Keep authoritative for modern development orchestration and protect it with isolation tests. |
| `core/execution` Rack AI gateways | yes | ATHBA calling Rack AI | A. ACTIVE PRODUCT PATH | `scripts/run_pr17_independent_reservation_book.py` and `scripts/run_pr19_environment_proof.py` both use Rack AI execution seams and trusted project/runtime progression. | Keep as the only modern execution seam from ATHBA into physical execution. |
| `PmAgent` | yes | ATHBA | B. LEGACY BUT STILL REACHABLE | Active chat path is `core/endpoints/chat.py` -> `core/services/chat_service.py` -> `core/agents/agent_generator.py` -> `PmAgent`. | Retain as legacy chat compatibility and document that it is not the modern PR17 control plane. |
| `SpecBuilderAgent` | yes | ATHBA | B. LEGACY BUT STILL REACHABLE | `AgentGenerator` still routes `Spec`; active PM delegation and finalized-spec handoff still instantiate it. | Retain as legacy chat/spec compatibility and keep bounded smoke coverage. |
| `ArchitectAgent` | yes | ATHBA | B. LEGACY BUT STILL REACHABLE | `AgentGenerator` routes `Architect`; finalized spec flow still launches it. | Retain as legacy chat compatibility; keep cloud reasoning path isolated from Rack AI execution control. |
| `DeveloperAgent` | yes | ATHBA | B. LEGACY BUT STILL REACHABLE | `AgentGenerator` routes `Developer`; behavior set still drives `/tmp/athba_repos` branch/commit loop via `GitService`. | Quarantine as legacy development compatibility, not modern execution authority. |
| `TesterAgent` | yes | ATHBA | B. LEGACY BUT STILL REACHABLE | `AgentGenerator` routes `Tester`; behavior set still drives `GitService` plus `TestExecutionService` pytest loops. | Quarantine as legacy test/review compatibility, not modern execution authority. |
| `LlmExchange` | yes | ATHBA legacy adapter | B. LEGACY BUT STILL REACHABLE | PM/Spec/Developer/Tester call the local `/llm/infer` path; Architect intent analysis calls the cloud branch through the same helper. | Keep as a legacy reasoning transport helper and block new PR17+ orchestration from depending on it. |
| `GitService` | yes | ATHBA legacy adapter | B. LEGACY BUT STILL REACHABLE | `DeveloperAgent` and `TesterAgent` still instantiate it; old behaviors call `initialize_repo`, `create_branch`, `commit_files`, `checkout_branch`, and `get_branch_status`. | Keep for legacy chat compatibility only and mark it superseded by trusted project environment plus Rack AI execution. |
| `TestExecutionService` | yes | ATHBA legacy adapter | B. LEGACY BUT STILL REACHABLE | `TesterAgent` still instantiates it; `execute_tests_behavior.py` still runs repository-local pytest against `/tmp/athba_repos`. | Keep for legacy chat compatibility only and prevent modern orchestration from importing it. |
| `/tmp/athba_repos` workflow | yes | ATHBA legacy adapter | B. LEGACY BUT STILL REACHABLE | `GitService` default root is `/tmp/athba_repos`; `GenerateCodeBehavior` reads test context there; `TestExecutionService` runs pytest there. | Keep quarantined as the old dev/test execution lane until the UI migrates. |
| `llm_service` package | yes | ATHBA legacy adapter | B. LEGACY BUT STILL REACHABLE | `README.md`, `docs/SETUP.md`, `run scripts/llm_service_run.bat`, and `LlmExchange` still expose the local `llm_service.llm_server` runtime. | Mark explicitly legacy and superseded by provider-neutral reasoning plus Rack AI execution. |
| `ModelRegistry` | yes | legacy local model control | C. COMPATIBILITY-ONLY | Enumerates GGUF model files, per-agent threads, ctx windows, and Flow Judge paths for the local `llm_service` runtime. | Retain only as local legacy LLM-stack configuration; do not use in modern ATHBA control paths. |
| `LlmServerManagement` | yes | Rack AI domain historically, not modern ATHBA | C. COMPATIBILITY-ONLY | Contains watchdog, TTL eviction, protected model rules, and unload logic for the local `llm_service`. | Retain as quarantined legacy model-management code and document it as non-authoritative. |
| `core/agents/rd_agent.py` (`RdAgent`) | manually runnable only | Rack AI domain historically, not modern ATHBA | C. COMPATIBILITY-ONLY | No active imports from app entrypoints or `AgentGenerator`; only docs, enums, and its standalone `__main__` path reference it. | Mark as quarantined legacy resource-director code; keep out of active product routing. |

## Notes

- Resource ownership conflict resolved by classification: physical model loading, model eviction, and host pressure management are legacy-local concerns and are no longer part of the modern ATHBA control plane.
- Two development execution lanes still coexist in source, but only one is authoritative for new work: PR17+ BehaviorContract orchestration over Rack AI. The old Developer/Tester `/tmp/athba_repos` loop is retained only as a quarantined compatibility path.
- README and setup guidance now point readers at this document and `docs/ATHBA_RACK_AI_ARCHITECTURE.md` before using the legacy local LLM stack.

## Checklist

- [x] Read the authoritative architecture and active entrypoints before editing.
  Target responsibility: classify current runtime ownership with direct evidence.
  Implementation evidence: audited `core/api.py`, `core/endpoints/chat.py`, `core/services/chat_service.py`, `core/agents/agent_generator.py`, `scripts/run_pr17_independent_reservation_book.py`, and `scripts/run_pr19_environment_proof.py`.
  Tests: documented by `tests/development/test_architecture_quarantine.py`.
  Commit SHA: `b8ea7e4e50f275a936e0204667441adaab7eebe1`
- [x] Classify the old local LLM/resource control plane.
  Target responsibility: quarantine physical model and resource management away from the modern ATHBA control plane.
  Implementation evidence: documented `llm_service`, `ModelRegistry`, `LlmServerManagement`, `RdAgent`, and `LlmExchange` as legacy or compatibility-only, and added source warnings to the legacy stack entrypoints.
  Tests: documented by `tests/development/test_architecture_quarantine.py`.
  Commit SHA: `b8ea7e4e50f275a936e0204667441adaab7eebe1`
- [x] Classify the old Developer/Tester execution stack.
  Target responsibility: distinguish the old `/tmp/athba_repos` Git/pytest lane from the modern Rack AI execution lane.
  Implementation evidence: documented `GitService`, `TestExecutionService`, and the old Developer/Tester behavior loop as legacy but reachable.
  Tests: documented by `tests/development/test_architecture_quarantine.py` and `tests/agents/test_legacy_agent_smoke.py`.
  Commit SHA: `b8ea7e4e50f275a936e0204667441adaab7eebe1`
- [x] Repair still-active legacy PM delegation behavior.
  Target responsibility: ensure reachable compatibility behaviors execute without undefined-name failures.
  Implementation evidence: fixed `core/agents/behaviors/pm/delegate_to_spec_builder_behavior.py` to use `BehaviorExecution` inputs instead of undefined names.
  Tests: `tests/agents/test_legacy_agent_smoke.py`.
  Commit SHA: `b8ea7e4e50f275a936e0204667441adaab7eebe1`
- [x] Add bounded active-path smoke coverage.
  Target responsibility: prove still-reachable PM/Spec/Architect/Developer/Tester behavior paths execute with fakes and no live LLM or Mongo requirement.
  Implementation evidence: added `tests/agents/test_legacy_agent_smoke.py` covering representative active intents across all five agent families.
  Tests: `tests/agents/test_legacy_agent_smoke.py`.
  Commit SHA: `b8ea7e4e50f275a936e0204667441adaab7eebe1`
- [x] Update top-level operator guidance.
  Target responsibility: prevent readers from treating the legacy local LLM stack as the modern authoritative architecture.
  Implementation evidence: updated `README.md` and `docs/SETUP.md` to point to the quarantine and ATHBA/Rack AI authority documents.
  Tests: N/A.
  Commit SHA: `b8ea7e4e50f275a936e0204667441adaab7eebe1`

INCOMPLETE_ITEMS = NONE


## Validation

- Focused smoke and quarantine suite: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/agents/test_legacy_agent_smoke.py tests/development/test_architecture_quarantine.py` -> `8 passed`.
- Coding gate: `./.venv/bin/python scripts/check_coding_principles.py` -> `coding principles gate passed`.
- Full suite: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q` -> `239 passed`.
- Compileall: `./.venv/bin/python -m compileall athba core llm_service tests scripts` -> passed.
- Diff check: `git diff --check` -> passed.
- Branch state after validation: `git status --short --branch` -> `## pr17-specification-gatekeeper...origin/pr17-specification-gatekeeper [ahead 1]`.
