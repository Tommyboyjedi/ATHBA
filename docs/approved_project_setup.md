# Approved project setup and bounded handoff

This outer setup path uses the existing Mongo-backed ATHBA project and specification
records. It does not create another project database. An approved architecture
selects the toolchain; setup does not choose technology from unapproved preferences.
The source-controlled fixture is explicitly test-only, not a human approval.

The checked-in fixture contains the unchanged ProductCatalogue, ShoppingBasket and
OrderRegister sources with separate behavior identities and disjoint source/test
paths. The launcher requires an existing **test project** whose current specification
version and content hash match that fixture. It does not create the project, insert a
specification, provision Mongo, install dependencies or invent a successful delivery.

## Dry-run preflight

Run on gpurack, from the canonical checkout:

~~~bash
cd /srv/ATHBA
/srv/ATHBA/.venv/bin/python -B -m scripts.run_approved_project_campaign \
  --test-fixture \
  --project-id EXISTING_MONGO_TEST_PROJECT_ID \
  --state-root /srv/ATHBA/state/approved-project-setup \
  --evidence-root /srv/ATHBA/qualification-evidence/approved-project-preflight-UNIQUE_TIMESTAMP
~~~

Replace the project ID and evidence suffix. Mongo configuration must already be
available through ATHBA's normal environment. Do not put credentials in command
arguments. The --test-fixture flag is required; there is no production approval bypass.

Default operation validates the frozen fixture, looks up the real project and
checks its latest specification. It records a timestamped campaign-*.json; it
does not prepare an environment or invoke BDE. Each invocation retains its own
report. The database lookup is bounded without changing Mongo or model settings.

Mongo is currently unavailable/unprovisioned on the rack. Missing configuration,
connection failure or timeout is recorded as backend_unavailable before any
provisioning. This is an honest integration blocker. No alternative store, fake
project or Mongo installation is used. A missing project or mismatched
specification also blocks setup.

## Explicit preparation

Add --prepare to the same command only when the existing test project and exact
fixture specification are present. This calls the normal outer setup service. It
verifies the approved managed tool versions, creates/reuses one confined canonical
repository and runs bounded environment smoke checks. Repeating matching setup
reuses the existing environment and repository. A conflicting architecture,
unrelated repository content or changed trusted revision fails closed.

The fixture currently selects managed Python/pytest. Other setup profiles report
tool availability, environment verification and BDE compatibility separately.
A prepared non-Python environment does not imply a compatible behavioral adapter.

## Live handoff remains blocked

The --enable-live flag explicitly requests the same outer delivery boundary. It
cannot start models with this implementation. With ready setup, the normal
ProjectBehaviorDeliveries.dispatch uses FrozenSharedProjectBde, persists the
first delivery as blocked and stops. Without ready setup, no delivery is
dispatched. The report always distinguishes this capability gap from environment
readiness. No reservation or model interaction is created.

The frozen full-lifecycle factories bind feature state to project_id, derive
scenario identities from project plus REQ, and load accepted post-behavior
project/feature authority from one co-located state root. They lack the required
shared-project environment injection and independently scoped full-delivery
identity. Separate state directories alone do not provide this capability.
Changing project IDs, copying authority records, deleting prior state or adding
filesystem aliases is not an acceptable workaround.

Setup/delivery records are associated metadata beneath the existing user-facing
project identity. They do not replace that project or create a parallel project store.

Exit codes: 0 means dry-run preflight or requested setup succeeded; 2 means
backend/setup/handoff blocked; 1 means invalid authority or an unexpected failure.
Neither successful preflight nor successful setup means a full behavior was
delivered. Known frozen planning failures remain out of scope.


## Scope and verification limits

The six controlled profiles cover Python, Rust, TypeScript, .NET, JavaScript and
static HTML/CSS assets, including combined TypeScript/HTML/CSS. They accept exact
preapproved managed tool versions and never install packages or SDKs. Missing
tools block preparation. .NET currently resolves an explicit SDK/framework,
language and template, but remains blocked because an approved test-harness
selection is absent; a successful zero-test dotnet test is not treated as proof.

On this rack, Python/pytest tools and a disposable Git/runtime environment were
actually verified with controlled existing-project storage. Rust tools were found;
no Rust application environment was prepared. Other toolchains were not available.
Controlled storage/BDE tests are not proof of real frontend persistence or three
successful application builds. Mongo-backed setup remains unverified here because
the normal backend is not configured.

The additive ProjectsService(setup_root=STATE_ROOT / "projects") query
get_development_setup(project_id) returns associated setup, all full-behavior
sources/identities, revision and delivery results only after finding the existing
project. Existing service calls and project records are unchanged.

A later explicit handoff request uses the exact same path:

~~~bash
cd /srv/ATHBA
/srv/ATHBA/.venv/bin/python -B -m scripts.run_approved_project_campaign \
  --test-fixture --project-id EXISTING_MONGO_TEST_PROJECT_ID \
  --state-root /srv/ATHBA/state/approved-project-setup \
  --evidence-root /srv/ATHBA/qualification-evidence/approved-project-live-UNIQUE_TIMESTAMP \
  --prepare --enable-live
~~~

This command is intentionally blocked at the currently unsupported shared-BDE
boundary. It is not a runnable three-behavior model campaign and cannot export
interaction diagnostics, reserve resources, or claim model cleanup. Enabling
those operations requires a separately authorized compatible BDE seam. No
acceptance authority is copied or reconstructed to work around that limitation.
Interrupted outer records are retained for inspection, never blindly replayed;
automatic recovery of a partially progressed frozen BDE is not implemented here.
