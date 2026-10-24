# Retrying setup-owned unfinished scaffolds

Approved project preparation records setup-progress.json outside the application
repository before Git initialization or scaffold writes. It pins the project,
approved setup/architecture/specification, profile/runtime, confined repository
location, expected file hashes, original Git identity and refs. This is operational
ownership only: it does not grant READY or accepted behavioral authority.

Retry setup.prepare(handoff) with the same approved handoff. Under the existing
project lock, preparation verifies recorded files, index, refs and Git identity,
completes missing authorized setup files, reruns unchanged readiness checks, and
publishes the verified scaffold/environment through the existing path. Successful
preparation remains idempotent. Failed setup records are retained in setup-failures.
Unexpected files, edits, modes, refs or ownership mismatches are preserved and
refused. An unknown repository still requires the original approved-repository
authority; matching scaffold contents alone grant no permission.

For a retained failure predating the progress record, setup.recover(handoff,
HistoricalSetupEvidence(...)) is an explicit service operation. Supply absolute,
SHA256-pinned paths to the original failed setup record, approved failed-run
record and pre-existing repository snapshot. Recovery correlates the pinned
backend/architecture authority, failed readiness evidence, exact original seed,
index, refs, recorded file inventory and current files under the setup lock.
It atomically records only verified in-progress ownership with those evidence
references, then calls normal preparation. It never inserts READY authority.
It supports only a recorded, undelivered, newly initialized scaffold; unsupported
or ambiguous histories fail closed.

There is no automatic adoption, reset, cleanup, dependency installation, model
execution or delivery dispatch. An interruption during Git initialization before
a seed checkpoint remains ambiguous and requires separate evidence review.
An unchanged successful smoke check does not establish pytest/configuration
isolation; that question remains separate.
