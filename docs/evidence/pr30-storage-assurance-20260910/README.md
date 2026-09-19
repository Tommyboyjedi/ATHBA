# PR30 Python storage decorator assurance

Reviewed starting head: a29071c538da2a7deb5f40ed9da8582eced89c95.

The preserved live run pr30-provenance-routing-20260910T133659Z completed all
four behaviors and passed bounded-omission provenance through final routing.
Its in-memory obligation then returned unsupported because the generated total
accessor used a property decorator (reported function line 15).

## Explicitly accepted assurance limit

The user authorized one Python policy change: function/method decorator opacity
is an assurance warning rather than a blocking unknown. This does not prove
arbitrary decorator semantics. No whitelist or recursive decorator analysis is
introduced.

python_specification_storage.py still walks the same full AST. Explicit open()
and storage/filesystem module detections still fail. Opaque calls, attributes,
operators/protocols, imports, dynamic runtime behavior, class effects and
unsupported configuration still block. This includes independent call/attribute
unknowns inside a decorator expression; they are not erased with the generic
function-decorator-opacity finding.

Each function/method decorator produces a finding with path, decorator line,
decorator expression and function name, ordered deterministically by source
location. The Python evidence adapter retains these findings on PASS, FAIL and
unsupported results reached by storage inspection. A decorated PASS says:

> Storage requirement passed by bounded static inspection; decorator effects were not statically verified.

Warnings use the existing findings field, survive JSON persistence and appear
in the final Gatekeeper/lifecycle evidence packet even when answer is YES.
No generic evidence, provenance, Gatekeeper acceptance or PR30 state transition
semantics were changed.

## Tests and evidence

The recorded live source is copied verbatim into a deterministic fixture with its
origin SHA and content hash; the historical repository is untouched. New tests
cover ordinary PASS, decorated PASS, the exact property case, every currently
recognized storage module plus open(), unrelated blocking unknowns, deterministic
multiple warnings, final routing, feature persistence and structured/Markdown
report packets. Existing tests remain intact.

Exact validation commands and results are recorded in validation.json and logs.
Fresh proof planning, invocation and terminal outcome will be retained alongside
the validation evidence. The original requirement is unchanged.

## Language boundary and debt

The core remains language agnostic; the current deterministic implementation is
primarily Python. See [the language adapter debt](../../specification_evidence_language_adapter_debt.md)
for the intended generic-policy -> language-adapter -> deterministic-tooling
boundary and the future Python, Rust, JavaScript, TypeScript, HTML, CSS, C#, Java
and PowerShell evidence capabilities. Those adapters are not implemented in PR30.

## Final validation

Implementation revision: fd4fcbb3e449b92ff0129dacc29cd593d95cf4f0.

| Check | Result |
| --- | --- |
| Focused storage/specification/Gatekeeper tests | 258 passed, 129.75 seconds |
| PR30 focused tests | 169 passed, 11.69 seconds |
| Full ATHBA pytest | 1,194 passed, 621.18 seconds |
| Coding-principles gate | PASS |
| Configured mypy | PASS, 57 source files |
| Compileall | PASS |
| Working/staged git diff checks | PASS |

The 29 new cases were added without weakening or deleting existing tests.
Configured mypy now explicitly covers both changed Python evidence modules.
Code and original requirement hashes remained unchanged through validation,
the recorded-item replay and the fresh live proof.

## Read-only replay of the original storage blocker

recorded-storage-replay.json retains the original NO and the new routed storage
result against the same immutable target revision:
0039443078c3b591be8108d386c2606f4fe8affe.

The old in-memory item now returns YES with:

> Storage requirement passed by bounded static inspection; decorator effects were not statically verified.

Its retained finding is:

> assurance_warning: running_total.py:14: @property on total; decorator effects were not statically verified

The old blocker reported the function definition at line 15; the new warning
points to the actual decorator at line 14. This replay made zero model calls
and did not change the old checklist, runtime state or target. It proves this
specific correction against the recorded artifact. It is not a resumed live
proof or a claim that the whole old run received new Gatekeeper approval.

## Fresh live outcome: a new behavioral blocker

Fresh identity: pr30-storage-assurance-20260910T151020Z.
Original requirement SHA256:
f94d99e83d826442c4d70d581dd46e91ebf1dc0e580eb3182f38a5c9d02e1f78.

The real local Responses probe returned READY. The original requirement was used
unchanged. Checklist creation accepted seven items in one attempt. Two behaviors
completed. The existing scenario repair/replan flow handled rejected drafts and
one worker timeout, then proceeded to the split child REQ_03-S001.

After 88 transitions the run terminated:

- status/reason: blocked / unsupported_language_boundary;
- scenario: pr30-storage-assurance-20260910T151020Z--REQ_03-S001;
- active fragment: python-4-assertion;
- generated assertion: assert rt.total() == 5;
- exception: TypeError: 'int' object is not callable;
- current production uses self.total = 0 and exposes a separate get() method;
- the existing Python frontier classifier did not treat this failure as supported
  RED, so the blocked fragment did not reach a Developer attempt.

This is a Python behavioral/API boundary failure, not a decorator-storage failure
or a missing non-Python evidence adapter. It remains outside this change. No
requirement, test, production file, checklist, target state, classifier, model
setting or harness was manually adapted after observing it.

The shell exited 2 after 1,035.833 seconds. Last canonical target SHA:
eafb172da6d834725b70e409ff7f756a194bc0e8.

Final Gatekeeper reconciliation was not reached or passed. Naming and refactoring
did not run; no assessor answer or POST_BEHAVIOR_COMPLETE is claimed. No final
storage assurance finding was produced by this fresh run because it stopped
earlier. The exact property warning is retained in the separate recorded-item
replay and deterministic packet tests.

## Retained state

live-result.json records the exact blocker and boundary evidence. live/ retains
the predeclaration and full structured/Markdown reports. runtime-state.tar.gz
preserves 30 runtime, referenced Rack packet, target file and index snapshots;
its manifest records original paths and verified content hashes.

The verified Git bundle preserves all target refs. The stopped target has a
generated staged frontier-test change in tests/test_running_total.py. It was
preserved, not cleaned/reset. target-working-state.json records the exact status,
index entries and staged/unstaged patches, alongside the archived file/index
snapshots. This preserves the failure beyond the committed target SHA.

The preceding failed run's recorded files still match their before/after hashes.
Neither old nor fresh terminal state was altered. The remaining live blocker is
reported for a later explicit task.
