# PR23 Latch timeout forensics

## Classification

The former 700-second whole-process bound was shorter than the inherited
900-second work-unit allowance. It was therefore an **EXTERNAL_PROOF_TIMEOUT**
and could not establish whether an in-flight work unit would terminalize at its
configured deadline. It is not evidence of local-coder exhaustion.

The repository state reader is healthy: bounded raw JSON reads of both retained
state files completed with `RAW_STATE_EXIT=0`. There is no **STATE_READER_FAILURE**.

## Evidence timeline (UTC)

| Time | Evidence | Finding |
| --- | --- | --- |
| 10:49:54 | Project Git seed | Latch project created. |
| 10:50:42 | Feature state | Planning/Gatekeeper phase had completed sufficiently to start Tester work. |
| 10:50:44 | Attempt 1 workspace | First Tester work unit began. |
| 10:51:57 | Attempt 1 test write | Observable JCode tool activity. |
| 10:52:35 | Attempt 1 packet | Terminal `checks_passed` / Rack acceptance `approved`; ATHBA later rejected its module docstring. |
| 10:52:36 | Attempt 2 workspace | Repair Tester work unit began. |
| 10:52:44 | Attempt 2 test write | Observable JCode tool activity. |
| 10:52:50 | Attempt 2 packet | Terminal `checks_passed` / Rack acceptance `approved`; ATHBA persisted candidate parsing failure. |
| 10:52:57 | ATHBA state | Attempt 2 was durably recorded and lifecycle occurrence 8 delivered. |
| 10:52:58 | Attempt 3 workspace | Third repair work unit began. No packet, test write, commit, or retained trace followed. |
| about 11:01:34 | External stop | Approximately 700 seconds after start; no proof-specific process later remained. |

Attempt 1 took about 111 seconds from workspace creation to packet. Attempt 2
took about 14 seconds. Planning before the first workspace took about 50 seconds.

## Packets and active cutoff operation

Both retained packets contain `worker_id=local-coder`,
`worker_role=implementer-tester`, `provider_profile=local-coder`,
`model_id=eqaq-v2-local-coder`, and `resource_id=gpu-2060`. Both are terminal
Rack AI packets, not timeout packets. No packet exists for attempt 3.

At cutoff, ATHBA had started the third Tester repair request. The workspace
exists but has no generated-test mutation. Retained evidence cannot distinguish
JCode generation, a tool wait, an idle process, or Rack AI waiting after an
unrecorded child exit; it does prove ATHBA was not waiting after a terminal third
packet. Whether Rack AI would have emitted its own timeout packet is unavailable.
