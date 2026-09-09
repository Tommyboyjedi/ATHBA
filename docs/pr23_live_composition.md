# PR23 Live Composition

## Scope

Session 8B2 provides a reusable, typed application composition for the strict-TDD feature path. It does not contact a live model, run the tiny live feature, run ReservationBook, change Rack AI, or change the immutable legacy commit.

## Composition

\`StrictTddFeatureCompositionFactory\` supplies the feature application service and its collaborators:

1. project environment lifecycle and durable feature state;
2. independently invoked behavior-contract planning and Gatekeeper checklist atomization;
3. scenario drafting with intent review;
4. lifecycle initialization, working-ref Rack binding, strict microcycles, deterministic regression, Senior review, and persisted behavior repair/replan routes;
5. accepted completed-microcycle evidence and final checklist reconciliation against the canonical Git revision.

The feature coordinator owns only feature checkpoints. Scenario drafting retains its own durable state; strict microcycles retain their own durable state; revision lifecycle retains the canonical/working-ref state.

## Revision invariant

Before strict work begins, a behavior creates an active revision lifecycle record at the feature's canonical SHA. Strict RED, Developer, regression-repair, and behavior-repair execution obtain a binding from the managed working ref. Accepted candidates advance that working ref; only regression clearance promotes the canonical ref. On behavior completion the managed ref is deleted.

After lifecycle promotion, \`TrustedProjectRevisionSynchronizer\` verifies that canonical ref already equals the lifecycle SHA and updates only the project metadata. It never performs a second ref promotion. Therefore the next selected behavior receives the previous behavior's promoted canonical SHA.

## Resume and reconciliation

Feature state stores the normalized contract, Gatekeeper state, completed behavior references, canonical/working state, evidence references, block reason, and final reconciliation. A matching restarted request reuses that state and does not repeat completed behavior execution or final reconciliation.

\`CompletedFeatureReconciler\` loads only completed, Senior-approved strict microcycle state. It passes that accepted evidence through \`GitAcceptedTestCatalog\` at the final canonical SHA; pending, blocked, repair, or uncompleted scenarios cannot be counted as evidence.

## No-live proof

The acceptance test creates a real temporary Git project and real persisted project, scenario, microcycle, revision, and feature stores. A deterministic fake reasoning gateway provides intent/Senior/reconciliation decisions; a deterministic fake Rack gateway makes real Git commits. It proves managed working-ref binding, canonical promotion, working-ref deletion after behavior completion, final accepted-evidence reconciliation, and restart without duplicate planning. No endpoint or Rack AI process is contacted.
