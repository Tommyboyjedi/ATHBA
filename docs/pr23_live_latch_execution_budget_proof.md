# PR23 Latch execution-budget live proof

This is the terminal record for the fresh Latch proof after the execution-budget policy and its timeout-lineage correction.

## Revisions

- ATHBA budget policy: `d5c51f3`.
- ATHBA forensics/documentation: `05d1676`.
- ATHBA timeout-lineage correction: `22603bcbb2d5a55b1a16f128eba9e9507ca76dc0`.
- Rack AI execution provenance: `de6b8f441038e24120bca382135a1a84703611f9` on `pr-worker-execution-provenance`.
- Legacy remained `8334f42a8865b9360972f5e0422a8f61d02dedb6`.

## Historical interrupted run

- The historical external 700-second process bound was shorter than the inherited 900-second generic worker allowance.
- Its raw ATHBA state reads completed under ten seconds; no state-reader defect was reproduced.
- Attempts one and two wrote terminal Rack AI packets; attempt three had begun but had no terminal packet at external cutoff.
- Retained timestamps show planning about 50 seconds, attempt one about 111 seconds, and attempt two about 14 seconds.
- No retained monotonic JCode output or tool timestamp proves worker progress after the third attempt began.

## Persistent fresh process

- Project: `pr23-live-latch-budget-20260902T133353Z`.
- Run: `pr23-live-latch-budget-20260902T133353Z-run`.
- tmux session: `pr23-latch-budget-20260902T133353Z`.
- Durable log: `state/live-logs/pr23-latch-budget-20260902T133353Z.log`.
- First launch attempt with the generic change was contaminated before project creation because the detached environment lacked the required API-key variable.
- The fresh command file persisted the exact CLI invocation before launch and used no whole-proof timeout.

## Requirement and independent planning

> Build a small in-memory Latch. It can be instantiated, begins unlatched, and calling engage changes it to the engaged state.

The persisted lifecycle stream records `behavior_contract_completed` and `gatekeeper_completed` before Tester work. The production composition was pointed at real local-primary for reasoning and Rack AI selected real local-coder for all Tester work.

## External work units

| Attempt | Work kind | Budget | Workspace to packet | Result |
| --- | --- | ---: | ---: | --- |
| 1 | `scenario_draft` | 300 s | 70.478 s | Candidate invalid: module/test docstring and expression forms. |
| 2 | `scenario_repair` | 300 s | 48.289 s | Candidate invalid: unsupported top-level expression. |
| 3 | `scenario_repair` | 300 s | 24.551 s | Candidate invalid: constrained intent JSON parse failure. |
| 4 | `scenario_repair` | 300 s | 127.430 s | Candidate unchanged: same revision and source as attempt 3. |

Durations are Rack AI workspace creation to packet modification time. Every packet records `worker_id=local-coder`, `worker_role=implementer-tester`, `provider_profile=local-coder`, `model_id=eqaq-v2-local-coder`, and `resource_id=gpu-2060`.

## Candidate lineage and terminal outcome

1. Attempt one used the canonical `main` base and produced a candidate branch/SHA.
2. Attempt two repaired that immediate predecessor.
3. Attempt three repaired attempt two and produced a candidate branch/SHA.
4. Attempt four repaired attempt three; its returned branch had the same SHA and source, and deterministic no-op evidence was persisted.
5. No fifth attempt was created.

- Run status: `blocked`; reason: `attempts_exhausted`; clean CLI exit: 2.
- Canonical base remained `d73d0bf520e8d7c5dd96f1b2b74afc01b36b3af0`; no working revision or canonical promotion exists.
- No Developer, regression repair, behavior repair, frontier, checkpoint, resume, Senior Review, reconciliation, or final target pytest was reached.
- No work unit reached its configured wall-clock budget; no Rack AI timeout packet was required.
- This is fair local-coder candidate failure, not a terminalization, persistence, routing, or state-reader defect.

## Contaminated run and corrective restart

- `pr23-live-latch-budget-20260902T130352Z` terminated before project creation because tmux did not inherit `OPENAI_API_KEY`; it performed no proof work.
- `pr23-live-latch-budget-20260902T130649Z` exposed the generic missing-lineage controller defect after a correctly terminalized timeout; it is contaminated and was not used as proof.
- Commit `22603bc` adds a generic deterministic regression: a timeout without branch/SHA/source persists and ends the bounded drafting route without an invented repair parent.

## Classification

- Fresh terminal classification: `LOCAL_CODER_CANDIDATE_FAILURE`.
- The 700-second historical bound is `EXTERNAL_PROOF_TIMEOUT`, not local-coder exhaustion.
- `JCODE_PROGRESS_SIGNAL_AVAILABLE = NO`; no idle watchdog was implemented.
- Rack AI source/configuration was not changed, ReservationBook was not started, and no merge occurred.
