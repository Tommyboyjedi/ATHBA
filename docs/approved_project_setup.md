# Approved project setup and team delivery

Setup uses the existing ATHBA project/specification backend and a pinned upstream
architecture approval. It does not issue human approval, create another project
database, provision Mongo, install SDKs or write business implementations.

One approved project owns one application repository and its configured canonical
branch. Each full behavior has a stable branch, linked worktree, trusted revision,
BDE state namespace and evidence. Display order does not create dependencies.
A declared dependency becomes ready only after its prerequisite is integrated
into accepted application main.

## Fixture launcher

The unchanged ProductCatalogue, ShoppingBasket and OrderRegister fixture remains
explicitly test-only. It requires an existing test project whose persisted
specification version/content hash matches the fixture. No project/specification
is inserted by this script.

From an approved ATHBA checkout on gpurack:

~~~bash
/srv/ATHBA/.venv/bin/python -B -m scripts.run_approved_project_campaign \
  --test-fixture --project-id EXISTING_MONGO_TEST_PROJECT_ID \
  --state-root /srv/ATHBA/state/approved-project-setup \
  --evidence-root /srv/ATHBA/qualification-evidence/project-preflight-UNIQUE_TIMESTAMP
~~~

Default operation checks approval, the existing backend project and specification,
then writes one timestamped report. It does not prepare environments/branches or
dispatch work. Add `--prepare` to prepare/reuse the approved environment and
dependency-ready delivery branches, without model execution. Each blocked
dependency is reported independently.

Only an explicit `--enable-live` requests `dispatch_ready` through the standard
service path. It can be combined with `--prepare`. Independent deliveries are
offered together under the configured dispatch concurrency; one failed branch
does not stop another. This command is **not executed by implementation/tests**.
It does not submit or promote any branch into application main, and does not
automatically integrate prerequisites or repeatedly retry waiting work.

Exit codes: 0 means the requested preflight/preparation succeeded or all requested
branches completed; 2 means prerequisites/waiting/blocking; 1 means invalid
authority, a branch failure or an unexpected failure. A completed branch is not an
integrated application. The report leaves interaction count unavailable after
live dispatch rather than claiming zero.

## Standard service operations

`compose_project_setup(ProjectSetupCompositionRequest(...))` exposes:
`setup`, `deliveries: TeamDeliveryService`, `records`, and `management: TeamServices`.
Supply the existing ProjectsService and pinned approval; the fixture loader is
not a production approval mechanism.

The following is a service API outline, not an automatically executed campaign:

~~~python
from core.delivery_management.domain import ManagementRequest, MergeKind, MergeStatus
from core.delivery_management.store import RecordIdentity
from core.project_setup.delivery import DeliveryRequest

await services.setup.prepare(handoff)
requests = tuple(DeliveryRequest(handoff, b.id) for b in handoff.decision.behaviors)

# Preparation does not invoke BDE. Independent ready branches may be prepared
# in any display order; an unintegrated declared prerequisite reports waiting.
branch = await services.deliveries.prepare(requests[0])

# Explicit execution: existing inner REQ/frontier TDD, Gatekeeper, late Naming
# and Refactoring all use the delivery worktree/branch, never application main.
results = await services.deliveries.dispatch_ready(requests)
historical = await services.deliveries.dispatch(requests[0])
resumed = await services.deliveries.resume(requests[0])

request = ManagementRequest(project_id, delivery_id, actor_reference)
sync = services.deliveries.synchronize(request)
operation = services.deliveries.submit(request)
# submit first synchronizes accepted main, then prepares/validates integration.
# A deferred/failed sync returns that outcome instead of an integration.

if operation.kind == MergeKind.INTEGRATION and operation.status == MergeStatus.VALIDATED:
    key = RecordIdentity(project_id, operation.id)
    approval = services.management.merges.approve(key, actor_reference)
    published = services.management.merges.promote(key, approval)

view = services.deliveries.inspect(project_id)
~~~

`dispatch` returns recorded completed results without replay. `resume` is an
explicit bounded continuation under the same identities/attempt history; it does
not reinterpret legacy sequential shared-checkout authority. Legacy PR73 records
with `active_delivery`/sequential delivery results require explicit compatibility
review. Existing single-behavior callers keep their default composition.

`synchronize` pins main and delivery revisions and validates a separate ordinary
merge candidate. While active work owns the branch, it records a deferred request.
The BDE processes it at a quiescent accepted-REQ checkpoint, without resetting
attempts or changing historical acceptance. Unsafe/incomplete evidence blocks
synchronization rather than importing changes under an active frontier.

Integration is separate management authority. Approval names exact main,
delivery and candidate SHAs plus evidence. Main advancing invalidates that
candidate/approval. Conflicts, failing combined regression and missing/changed
accepted tests leave main unchanged. No ours/theirs resolution or semantic merge
agent is used.

Inspect `view` and `services.management.records.merge(RecordIdentity(project_id,
operation_id))` for exact candidate, conflicts and history. A later explicitly
supplied resolution commit is revalidated through
`services.management.merges.validate_resolution(key, exact_resolution_sha)`;
passing validation still requires exact approval/promotion. Interrupted
publication is inspected/reconciled with `services.management.merges.recover(key)`.
A delivery promotion can be reconciled through
`services.deliveries.recover_delivery(RecordIdentity(project_id, delivery_id))`.
Recovery refuses newer authority and does not roll it back.

The existing `ProjectsService(setup_root=STATE_ROOT / "projects")` method
`get_development_setup(project_id)` exposes associated setup plus
`delivery_management` only after resolving the existing frontend project.
No parallel dashboard or authentication product is introduced.

## Evidence and limits

Completed contributions retain original source identities, accepted test
origins, active supersessions, post-Naming test hashes and unresolved assurance.
Synchronization uses explicitly qualified completed-REQ checkpoint evidence;
it does not manufacture final Gatekeeper or post-behavior completion. Merge
validation preserves accepted identities/hashes from both sides, runs configured
build/full regression and verifies required test nodes actually execute.

Toolchain preparation remains controlled and read-only: Python, Rust, TypeScript,
JavaScript, HTML/CSS and .NET profiles retain their existing supported/blocked
capabilities. This change adds no language engine. Python is the existing concrete
BDE composition. Linked worktrees isolate Git indexes/working files; they are not
an operating-system security sandbox.

Mongo remains unconfigured on the rack. Real frontend-backed verification is
therefore blocked before provisioning; controlled injected-storage tests do not
prove Mongo persistence. The public RackAI linked-worktree runtime path has not
been exercised by a live reservation/model run in this assignment. Disposable-Git
and controlled existing-gateway proofs are identified separately from live
qualification. No deployment, automatic integration, live campaign or infrastructure
provisioning is implied.
