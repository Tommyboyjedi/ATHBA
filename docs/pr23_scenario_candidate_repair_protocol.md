# PR23 scenario-candidate repair protocol

## Candidate chain

Attempt one is a `fresh_draft` from the canonical development base. Attempts two through four are `repair_previous_candidate` requests: each is bound to the immediately preceding accepted candidate ref and SHA, after ATHBA verifies that `git rev-parse <ref>` equals the persisted SHA. A missing source, ref, or mismatch fails closed. Candidate drafting never promotes the canonical development base.

## Typed contract and assessment

The Python/pytest adapter receives one typed authoring contract both when ATHBA constructs the Tester objective and when it validates a returned candidate. The contract permits imports, module data, and exactly one ordinary test. It rejects module docstrings, test-function docstrings, standalone string-expression statements, helpers, fixtures, classes, async/parameterized/dynamic tests, unsupported nodes, substitute implementations, behavior mocks, skips/xfails, and missing-capability evasion. Adapter-owned canonicalisation renames the accepted ordinary test; the original identity is retained as evidence.

Each attempt persists bounded source, candidate ref/SHA, parent attempt, repair mode/base, Rack evidence and typed worker provenance. A repair with an unchanged revision or unchanged source is typed as a consumed no-op attempt, with both source digests and its exact unchanged disposition retained. Its typed assessment records syntax, identities, structural facts, production references, substitutions, mocks, evasion markers, issue codes/spans, and actionable repair instructions. Older persisted attempts load without the new optional fields.

## Semantic review and cap

Structural rejection and `repair_required`, `wrong_behavior`, or `insufficient_evidence` semantic results all feed the next repair objective. The objective includes exact prior source, typed assessment, deterministic feedback, any intent feedback, ticket, strict contract, and requirement references; it never supplies replacement code. There are at most four attempts. The fourth candidate is structurally and semantically assessed before a later transition declares exhaustion. Escalation remains deferred; local-coder remains Tester and local-primary remains reviewer.

No live proof was run while this protocol was implemented.
