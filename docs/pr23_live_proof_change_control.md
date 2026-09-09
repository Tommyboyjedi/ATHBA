# PR23 live-proof change control

## Enforceable decision gate

Any further harness change must demonstrate that it restores the original generic contract rather than merely allowing the process to move one step forward for the purpose of testing.

Model output that violates an existing documented contract is not, by itself, evidence that the harness must change.

A change is permitted only when a documented generic contract exists, the owning component demonstrably violates it, the defect reproduces without feature-specific logic, and a deterministic generic regression proves the correction. It must preserve safety and existing tests, remain valid across feature/language/worker changes, and cannot be justified by one extra live-proof transition. The model's latest syntax, name, structure, strategy, or tool choice is not automatically a requirement; ordinary model failure is not an orchestration subsystem.

| Evidence | Decision |
| --- | --- |
| Documented contract violated | Generic correction permitted |
| Model violates documented contract | Count or repair model attempt; harness unchanged |
| Evidence insufficient | Audit and fail closed; no change |
| Fixture-specific obstacle | No harness change |
| Worker capability exhausted under valid contract | Routing/escalation design, not accommodation |

Prohibited: granting a tool because it was attempted; accepting an unsupported test form; raising attempt/timeout bounds; requirement-specific prompt recipes; misattributing another component's failure; and repeatedly extending the harness instead of bounded worker escalation.

## Freeze

Strict scenario grammar, deterministic frontiers, four Tester submissions, typed execution budgets, and worker provenance remain frozen. Model escalation and worker-pool scheduling are deferred. No live feature proof may justify incremental fixture-specific accommodation.
