# Bounded frontier production-change reduction

An ordinary frontier Developer candidate is reduced only after independent current
GREEN and the existing accumulated regression service both pass, and before canonical
promotion. Already-GREEN frontiers, Tester drafts, Naming, Refactoring, behavior repair
and regression repair do not enter this path. The Developer objective is unchanged.

## Authority

B is the trusted development base at frontier entry; R is the first recorded accepted
RED input for that frontier; I is this Developer submission's actual input; C is its
original RackAI candidate. All are exact immutable Git identities. Failed earlier
candidates remain part of the frontier's B-to-C delta, rather than becoming baseline.

The original DeveloperAttempt and RackAI response continue to identify C. A retained
reduction V is an ATHBA-authored descendant commit of C. Existing managed-working-ref
and canonical CAS promotion mechanisms alone grant V authority. Protected tests and
configuration are compared exactly with R. Required artifacts remain required.

## Small language capability

The generic reducer handles paths, opaque transformation IDs, bytes, revisions and
test results. ProductionReductionAdapter proposes localized complete syntax-unit
deletions/restorations. Its Python implementation uses AST positions without unparsing.
It can remove newly added files/declarations/functions/methods/imports/statements,
restore unambiguously changed or deleted baseline units, and insert only necessary
empty-suite pass syntax. Removing a necessary outer declaration does not suppress
independent opportunities inside it.

Unchanged baseline syntax and shared exact baseline byte-lines are conserved.
Ambiguous correspondence, unsupported encodings, packed/inline child edits and
untraversed exception-handler/match-case suites are recorded as limitations. This
capability performs no application-effect or product-semantics inference.

## Experiments and limits

The policy is at most 24 proposed trials and a 120-second persisted experiment
deadline per ordinary Developer candidate. Opportunities are deterministic,
coarse-to-fine and greedy. Both transformation and complete proposed production
content identities prevent repeated trials. Recompute after a retained change.

Every trial uses a fresh detached disposable workspace at V and applies only its
permitted production transformation. It preserves the exact test/configuration
tree, checks required artifacts, and uses the same regression commands: current
cumulative frontier, protected prior test nodes and configured accepted suite.
The existing runtime receives the smaller of its normal 60-second command bound
and the remaining experiment deadline. It cannot approve a partially executed suite.

Normal experiments reserve up to five seconds inside the bound for Git cleanup;
no experiment is admitted with less than five seconds available. Cleanup failure,
tracked test/runtime mutation, authority mismatch and infrastructure uncertainty
fail closed through existing integrity handling. Optional experiment rejection
does not consume a Developer/Tester attempt or call Planner.

The existing controller still observes stop requests between transitions.
An optional cancellation predicate can stop the deterministic search; no new
feature-level stop/recovery workflow is introduced. Mandatory immutable-authority
validation and abandoned-workspace reconciliation on restart have a separate
bounded safety-only allowance (20 seconds), and never launch further experiments
after the persisted experiment deadline.

## Durable evidence and restart

Atomic identity-bound checkpoints freeze B/R/I/C, adapter, policy and acceptance
conditions. The reducer locks one authority identity, saves a trial admission before
execution, and persists its workspace before Git creation. Per-trial source/patch,
commands/results, timing and retained/discarded decision remain available.

Only the checkpoint's last fully verified revision may be reused. A test-passing
but uncheckpointed or incompletely cleaned trial is not promoted on restart.
Interrupted registered workspaces are reconciled before reuse. The same model
submission is not replayed and ordinary budgets are not reset.

## Meaning of the result

The result is a smaller supported change that passed the current acceptance, or the
unchanged verified candidate when no reduction was retained. Trial exhaustion,
deadline, unsupported syntax and failed deletion are never proofs of minimality.
Joint removals may be missed. Future frontiers are not tested as acceptance, and
incidental future GREEN is permitted. No claim is made about untested correctness
or complete enforcement of the third law of TDD.
