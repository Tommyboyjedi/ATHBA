# PR23 Revision Lifecycle

## Terms

Each active strict-TDD scenario has two distinct persisted revision concepts.

- **Canonical development base** is the SHA currently resolved by the project canonical ref. It moves only after deterministic accumulated regression clears.
- **Managed microcycle working ref** is a deterministic ATHBA-owned ref under refs/heads/athba/microcycles/. It may be ahead of the canonical base while a frontier or Developer/repair candidate is being assessed.

The scenario id is restricted to letters, digits, underscore, and hyphen; its SHA-256 key names both the persisted record and managed ref. The full working ref is persisted in MicrocycleRevisionState, never reconstructed by a coordinator.

## Lifecycle

1. Initialisation verifies the supplied canonical ref resolves to the supplied canonical base SHA, CAS-creates the working ref at that SHA, then persists state. A persistence failure deletes the new ref.
2. Scenario drafting is planning material and mutates neither ref.
3. A valid deterministic RED frontier, accepted Developer candidate, or accepted regression-repair candidate must be a descendant of the current working SHA. CAS advances only the working ref.
4. Invalid, rejected, unavailable, or non-fast-forward candidates mutate neither authoritative ref.
5. Regression clearance requires the tested candidate to equal the current working SHA and to descend from the canonical base. CAS then advances the canonical ref and persists the same SHA as canonical_development_base. A persistence failure CAS-rolls back the canonical ref.
6. During accumulated regression, the canonical base remains unchanged; bounded repair may advance only the working ref. Only a subsequent clear can promote.
7. The next frontier starts from the aligned regression-cleared canonical/working SHA.

## Rack AI binding invariant

RackAiRevisionBindingFactory loads and recovery-validates persisted active state and produces the RepositoryBinding from the working ref and working SHA. It verifies locally that git rev-parse of binding.base_ref equals binding.base_sha.

A mismatch fails before a Rack AI gateway can be invoked. This adds no Rack AI request fields and does not choose an executor backend.

## Recovery and completion

Recovery fails closed if the canonical ref changed outside ATHBA, the working ref points at an unexpected SHA, or the persisted working SHA is not descended from the canonical base. A missing active working ref is recreated only at the persisted safe SHA after lineage validation.

The completion policy is deletion: after canonical and working SHA align, ATHBA CAS-deletes the active working ref, persists behavior_complete, and retains commits plus transition evidence. Recovery will clean a leftover aligned completed ref but never creates an active ref for a completed scenario.