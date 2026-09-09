# PR29 Behavior Planner technical-decision qualification (Phase 2B)

## Frozen identity

INITIAL_HEAD=44c74372639d76fb7637194014e389a41ed24cb4
QUALIFICATION_FROZEN_HEAD=14f31245a617c0dd218ad90dea80574fc2751cbc
PLANNER_CONTRACT_VERSION=technical-decisions-v1
PLANNER_SCHEMA_SIGNATURE=f601e38508a568ddbad10037a3f512120c3f17b87bd9fa9f4074b7a670ce016a
BPQ_CORPUS_SHA=523dc088007cdcd10484daa7cb272fdbdab4a37a306a5369bbeac1ff676d85cb
BPQ_A_SHA=6a88d231bc489d24507b0b9a7abbc61bd6e13e418a0d65567490da25c72eea36
BPQ_B_SHA=c46ce04d165b64d2459fdd821475289925496dc7541584230d60f4858ec9aa88
BPQ_C_SHA=65fe74ab5a04edd6b3e1cecd6a93da5b2b05ad45d973b131f712c8a4678d78bd
MODEL_READY=YES
RUN_ORDER=A1,B1,C1,A2,B2,C2,A3,B3,C3
SCHEDULED_RUNS=9
COMPLETED_RUNS=9
EVIDENCE_ROOT=evidence/pr29-phase2b-technical-decisions-20260904T175500Z
QUALIFICATION_HARNESS_COMMIT=14f31245a617c0dd218ad90dea80574fc2751cbc

The harness is qualification-only. It delegates unchanged requests through the
production BehaviorContractPlanner path: source-clause planning, Behavior
Contract planning, and its existing one bounded repair. It records exact rendered
prompts and raw UTF-8 provider strings. It does not alter prompts, responses,
timeouts, retries, provider, model, parser, or validation. It was the only
difference from the expected initial head before A1.

## Per-run mechanical result and semantic classification

Every run made the source-clause call, first Behavior Planner call, and the
existing production repair call. First output was JSON in every run but failed
full validation for uncovered source clauses. Each repair was then rejected by
the unchanged validator: technical decision source excerpt must be an exact
substring of requirement source. No final contract was accepted.

| Run | Fixture | Clauses | First JSON | First valid | Repair | Final | S1 S2 S3 S4 S5 S6 S7 |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| A1 | BPQ-V1-A | 17 | YES | NO | YES | NO | FAIL FAIL FAIL FAIL FAIL FAIL FAIL |
| B1 | BPQ-V1-B | 13 | YES | NO | YES | NO | FAIL FAIL FAIL FAIL FAIL FAIL FAIL |
| C1 | BPQ-V1-C | 16 | YES | NO | YES | NO | FAIL FAIL FAIL FAIL FAIL FAIL FAIL |
| A2 | BPQ-V1-A | 17 | YES | NO | YES | NO | FAIL FAIL FAIL FAIL FAIL FAIL FAIL |
| B2 | BPQ-V1-B | 13 | YES | NO | YES | NO | FAIL FAIL FAIL FAIL FAIL FAIL FAIL |
| C2 | BPQ-V1-C | 16 | YES | NO | YES | NO | FAIL FAIL FAIL FAIL FAIL FAIL FAIL |
| A3 | BPQ-V1-A | 17 | YES | NO | YES | NO | FAIL FAIL FAIL FAIL FAIL FAIL FAIL |
| B3 | BPQ-V1-B | 13 | YES | NO | YES | NO | FAIL FAIL FAIL FAIL FAIL FAIL FAIL |
| C3 | BPQ-V1-C | 16 | YES | NO | YES | NO | FAIL FAIL FAIL FAIL FAIL FAIL FAIL |

S1-S7 are FAIL because no accepted contract exists through the authoritative
validation boundary. This is not treating a rejected raw output as downstream
authority.

First validation errors were stable by fixture: A uncovered PR16-001 through
PR16-004; B uncovered PR16-007 through PR16-013; C uncovered PR16-001,
PR16-002, PR16-006, and PR16-015. The raw first and repair responses were
byte-identical across the three repetitions of each fixture. The detailed
prompts, responses, parsed clauses, timestamps, provenance, and exact errors
are in each evidence subdirectory.

## Raw terminal technical decisions and bindings

These are rejected repair artifacts, recorded for forensics rather than accepted
contracts. All repetitions of the stated fixture have the same artifact.

- A1, A2, A3: TD-001 ReservationBook, class, source_requirement, invalid
  paraphrased excerpt; TD-002 create_reservation, TD-003 cancel_reservation,
  TD-004 get_availability, all behavior_planner methods. Bindings: REQ-001
  TD-001/action; REQ-002--003 TD-001/error; REQ-004 TD-002/action; REQ-005--008
  TD-002/error; REQ-009 TD-003/action; REQ-010 TD-003/error; REQ-011
  TD-003/state; REQ-012 TD-004/observation; REQ-013 TD-001, TD-002, TD-003/state;
  REQ-014--017 TD-001/state.
- B1, B2, B3: TD-001 SignalBoard, variable, source_requirement, invalid
  invented/paraphrased excerpt; TD-002 publish and TD-003 get_signal,
  behavior_planner methods. Bindings: REQ-001 TD-001/state; REQ-002--004
  TD-002/action; REQ-005 TD-003/action. The component identifier is not a class
  decision and the query uses action rather than observation.
- C1, C2, C3: TD-001 ParcelLocker, class, source_requirement, invalid paraphrased
  excerpt; TD-002 place_parcel, TD-003 collect_parcel, TD-004 is_available,
  behavior_planner methods. Bindings: REQ-001--002 TD-001/action; REQ-003--005
  TD-002/action; REQ-006--007 TD-003/action; REQ-008 TD-002/action; REQ-009
  TD-004/action.

## Predeclared gate result

FIRST_RESPONSE_VALID_COUNT=0
REPAIR_USED_COUNT=9
FINAL_ACCEPTED_COUNT=0
SOURCE_IDENTIFIER_CORRUPTIONS=9 (all rejected; invalid source excerpts)
FABRICATED_SOURCE_PROVENANCE_ACCEPTED=0
MATERIAL_IRRELEVANT_BINDINGS_ACCEPTED=0
MATERIAL_ROLE_ERRORS_ACCEPTED=0
S1_PASS_COUNT=0
S2_PASS_COUNT=0
S3_PASS_COUNT=0
S4_PASS_COUNT=0
S5_PASS_COUNT=0
S6_PASS_COUNT=0
S7_PASS_COUNT=0
MECHANICAL_QUALIFICATION=FAIL
SEMANTIC_QUALIFICATION=FAIL
RELIABILITY_QUALIFICATION=FAIL
BEHAVIOR_PLANNER_TECHNICAL_DECISION_QUALIFIED=NO

Mechanical qualification fails at 0/9. Semantic qualification fails because all
nine terminal raw artifacts claimed source_requirement provenance with an
inexact source excerpt. Reliability fails at 0/9 PASS for every criterion. This
does not authorize model, prompt, schema, corpus, retry, provider, or downstream
changes.

## Boundaries

RAW_SOURCE_CLAUSE_OUTPUTS_CAPTURED=YES
RAW_BEHAVIOR_PLANNER_OUTPUTS_CAPTURED=YES
PRODUCTION_SOURCE_CHANGED_AFTER_A1=NO
PROMPT_CHANGED_AFTER_A1=NO
SCHEMA_CHANGED_AFTER_A1=NO
BPQ_CHANGED=NO
TESTER_INVOKED=NO
DEVELOPER_INVOKED=NO
SIGNALBOARD_APPLICATION_RUN=NO
RESERVATIONBOOK_APPLICATION_RUN=NO
PARCELLOCKER_APPLICATION_RUN=NO
RACK_AI_CHANGED=NO
JCODE_CHANGED=NO
PR21_CHANGED=NO
TESTER_TECHNICAL_FIELDS_EXPOSED=NO
DEVELOPER_TECHNICAL_FIELDS_EXPOSED=NO

The static model-payload boundary remains intact: BehaviorContract.to_model_dict
removes technical_decisions, and each observable requirement model dictionary
removes technical_bindings. Evidence remains untracked and unstaged; this
document is the only post-run tracked change.
