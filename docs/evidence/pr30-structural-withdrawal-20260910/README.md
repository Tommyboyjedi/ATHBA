# Historical record: withdrawn inter-behaviour experiment

The experimental inter-behaviour Structural Refactorer introduced in commit
1fc4debe76781d56661c532b79306459cd6aff68 was withdrawn. Behavioural development
already has bounded Tester repair/retry and Behaviour replan/split recovery.
ATHBA should use that existing decomposition mechanism rather than add another
small-model reasoning role. No replacement recovery logic was introduced.

The current PR30 lifecycle remains:
behavioural delivery -> final Specification Gatekeeper YES -> Naming
reconciliation -> post-behaviour Refactoring -> POST_BEHAVIOR_COMPLETE.

The large tracked proof and validation directory
`docs/evidence/pr30-structural-20260910/` belonged to the withdrawn
architecture and was deliberately pruned. Its original contents remain in
commit 80c5d2c9d4d4839f74598ea70a2b5df5ac191d46. Runtime historical state and
untracked evidence were not modified.

## Preserved Naming Assessor blocker

Run: `pr30-structural-20260910T194503Z`.
The two adjacent JSON files preserve the raw naming response and terminal
post-behaviour state byte for byte. Source paths and SHA256 values are recorded
in restoration-manifest.json.

The raw response was:

```text
YES
current_name: get_total
required_name: total.
```

The terminal diagnostic was
`ValueError: naming assessment must return NO or exactly one mapping`.
The state records BLOCKED, human_intervention_required, pending naming_assessor,
a passed entry Gatekeeper, and zero promoted post-behaviour refactor passes.
This is historical failure evidence for a subsequent task. Naming assessment,
parsing, prompts and retry behaviour have not been changed or rerun here.
No new live proof was performed.

The manifest lists every baseline-restored and removed file.

## Rollback validation

- Affected frontier/TDD/microcycle/revision/persistence/workspace suite: 147 passed.
- Specification/Gatekeeper/storage/provenance suite: 258 passed.
- Existing PR30 focused suite: 169 passed.
- Full ATHBA pytest: 1,194 passed (632.61 seconds).
- Coding-principles gate, configured mypy (57 source files), compileall,
  working-tree and staged whitespace checks: passed.
- Active repository audit: 486 files searched, no implementation symbol matches.
- The entire baseline tree is preserved; only this new historical record differs.

Exact commands, exit codes, elapsed times and raw-log hashes/locations are in
validation.json. The existing deprecation warnings remain visible in the raw
pytest logs. No existing test was weakened, and no live proof was run.
