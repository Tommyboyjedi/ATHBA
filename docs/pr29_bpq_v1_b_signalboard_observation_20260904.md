# PR29 BPQ-V1-B SignalBoard observation run

Date: 2026-09-04

This is one untouched production observation run at ATHBA `738e49ef5fe81525aa2933d341d205e6a7ed879e`. No ATHBA production code, test infrastructure, prompts, schemas, lint, frontier logic, Intent Review, retry budget, Rack AI, JCode, tool profile, timeout, BPQ corpus, ReservationBook, or Gatekeeper material was changed to influence the run.

## Canonical input and readiness

- BPQ corpus: `BPQ-V1`; fixture: `BPQ-V1-B` / `SignalBoard`.
- The runner loaded the requirement directly through `load_behavior_planner_qualification_v1`, not a copied or retyped requirement.
- Requirement SHA-256: `c46ce04d165b64d2459fdd821475289925496dc7541584230d60f4858ec9aa88`.
- Corpus SHA-256: `523dc088007cdcd10484daa7cb272fdbdab4a37a306a5369bbeac1ff676d85cb`.
- Both hashes were checked before the planner invocation and matched the frozen values.
- A real `POST /v1/responses` readiness generation using `local-primary` returned `READY` (`resp_a3ce73e5118af018`) before this run.
- The ordinary temporary environment used `OPENAI_API_BASE=http://127.0.0.1:8017/v1`, model `local-primary`, `CPU_ONLY=true`, and test Mongo/Django values; no credentials were persisted.

## Planner evidence and replay boundary

ATHBA created the fresh disposable project at `/srv/ATHBA/state/projects/pr29-bpq-v1-b-signalboard-20260904T115000Z/repository` and accepted the parsed planner result. The durable feature state and proof report preserve the canonical requirement, 13 parsed source clauses, and the accepted seven-requirement Behavior Contract. The contract has `public_api = ["publish", "get_latest"]`.

The unchanged production planner path did not persist its raw source-clause or raw Behavior Planner provider-response strings. Consequently, this observation has no fabricated replacement for those raw outputs. `BEHAVIOR_PLANNER_RAW_OUTPUT_SAVED=NO` is an evidence gap, not a planner failure.

The separate downstream replay artifact is `/srv/ATHBA/evidence/pr29-bpq-v1-b-signalboard-20260904T115000Z/behavior-planner-replays/BPQ-V1-B-accepted-contract.json`. It is the exact persisted accepted contract payload (SHA-256 `c9bae41cdb5fd9a5cbed6f3f8ba7ac3bba18ca4339fc6c5ec6ebaceb862e91a9`), is outside the BPQ corpus, and must not be read as a planner specification or qualification fixture. Its README states the source and the raw-output limitation.

## Stage progression

| Stage | Observation |
| --- | --- |
| BPQ INPUT | Reached; direct frozen BPQ-V1-B prose and both hashes verified. |
| SOURCE CLAUSES | Reached; 13 persisted accepted clauses (`PR16-001` through `PR16-013`). |
| BEHAVIOR CONTRACT | Reached; accepted SignalBoard contract, 7 observable requirements. |
| CONTRACT VALIDATION | Reached; deterministic parser accepted it and Gatekeeper checklist persisted. |
| TESTER ATTEMPTS | Reached; REQ-001 used all 4 bounded attempts. |
| STATIC VALIDATION/LINT | Reached; attempt 1 rejected deterministically. |
| INTENT | NOT_REACHED; all persisted `intent_review_response_attempts` are zero. |
| FRONTIERS | NOT_REACHED. |
| RED | NOT_REACHED. |
| GREEN | NOT_REACHED. |
| REGRESSION | NOT_REACHED. |
| SENIOR REVIEW | NOT_REACHED. |
| FINAL/TERMINAL STATE | Reached; blocked at `attempts_exhausted`. |

## First control rejection

The first control rejection was deterministic static product-surface lint on Tester attempt 1, candidate `3fd57333ba735ce5363da2416bb7006bd751a856`, work unit `REQ-001--scenario-draft-1`.

```text
Candidate references undeclared product member `signals` at line 5. Product interactions must remain inside the declared product contract. Repair the candidate without introducing undeclared product surface.
```

The candidate was model-authored by the real Tester worker (`jcode`, `gemma4-12b-local-primary`, provider/worker `local-primary`, `gpu-4060ti`), but the rejection was deterministic and no LLM reviewed or decided it. ATHBA did automatically continue with its existing bounded repair route, but did not recover to an accepted scenario: attempts 2, 3, and 4 each ended `worker_model_timeout` after their unchanged 300-second worker limit and produced no candidate source or revision.

## Terminal stop

The last successful stage was contract validation/Gatekeeper checklist persistence. The terminal state is `blocked`, reason/classification `attempts_exhausted`, at REQ-001 Tester scenario drafting. No scenario passed static validation, so no Intent calls, frontiers, RED/GREEN cycles, Developer calls, regressions, or Senior Reviews occurred. No post-stop repair or resumption was performed.

## Durable evidence

- Run report: `/srv/ATHBA/evidence/pr29-bpq-v1-b-signalboard-20260904T115000Z/proof-report.json` and `.md`.
- Feature state: `/srv/ATHBA/state/features/pr29-bpq-v1-b-signalboard-20260904T115000Z.json`.
- Scenario state: `/srv/ATHBA/state/scenario-drafts/pr29-bpq-v1-b-signalboard-20260904T115000Z--REQ-001.json`.
- Rack AI review packets are retained at the per-attempt `evidence_location` fields in that scenario state.

## Required result markers

```text
STARTING_HEAD=738e49ef5fe81525aa2933d341d205e6a7ed879e
BPQ_CORPUS=BPQ-V1
BPQ_FIXTURE=BPQ-V1-B
REQUIREMENT_SHA256=c46ce04d165b64d2459fdd821475289925496dc7541584230d60f4858ec9aa88
CORPUS_SHA256=523dc088007cdcd10484daa7cb272fdbdab4a37a306a5369bbeac1ff676d85cb
CANONICAL_INPUT_USED_DIRECTLY=YES
MODEL_READY_V1_RESPONSES=YES
BEHAVIOR_PLANNER_INVOKED=YES
BEHAVIOR_PLANNER_RAW_OUTPUT_SAVED=NO
BEHAVIOR_PLANNER_OUTPUT_ACCEPTED=YES
BEHAVIOR_PLANNER_REPLAY_ARTIFACT_SAVED=YES
SOURCE_CLAUSE_COUNT=13
BEHAVIOR_REQUIREMENT_COUNT=7
PUBLIC_API_OUTPUT=publish,get_latest
FIRST_CONTROL_REJECTION_STAGE=STATIC_VALIDATION/LINT
FIRST_CONTROL_REJECTION_CLASSIFICATION=undeclared_product_member
FIRST_CONTROL_REJECTION_LLM_INVOLVED=NO
FIRST_CONTROL_REJECTION_AUTOMATICALLY_RECOVERED=NO
LAST_SUCCESSFUL_STAGE=CONTRACT_VALIDATION
TERMINAL_RESULT=BLOCKED
TERMINAL_STOP_STAGE=TESTER_ATTEMPTS
TERMINAL_STOP_CLASSIFICATION=attempts_exhausted
TESTER_ATTEMPTS=4
INTENT_CALLS=0
FRONTIERS_REACHED=0
DEVELOPER_CALLS=0
GREEN_FRONTIERS=0
REGRESSIONS_RUN=0
SENIOR_REVIEWS=0
PRODUCTION_SOURCE_CHANGED_BY_CODEX=NO
PROMPTS_CHANGED=NO
PLANNER_SCHEMA_CHANGED=NO
STATIC_LINT_CHANGED=NO
TDD_FRONTIER_LOGIC_CHANGED=NO
RACK_AI_CHANGED=NO
PR21_CHANGED=NO
BPQ_CORPUS_CHANGED=NO
RESERVATIONBOOK_RUN=NO
```
