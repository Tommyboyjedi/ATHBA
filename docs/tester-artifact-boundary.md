# Standalone Tester draft artifact

A fresh selected behavior is authored into one identity-owned .athba/scenario-drafts/<digest>/<filename> artifact. It is the only writable path, required artifact and syntax acceptance target for that authoring attempt. It is not the accumulated accepted test module.

The existing language adapter validates one scenario, freezes its canonical test identity, and materialises the accepted frontier into the canonical test module. Existing tests are merged by the trusted harness and remain regression acceptance authority. The draft candidate revision is never promoted as production authority.

Tester receives the selected source clause text and narrowly selected subject rather than a potentially whole-specification provenance quote. The original quote is preserved durably for independent Intent Review, Specification Gatekeeper, decomposition and restart. No Developer contract changes are made.

The draft path is persisted and immutable on resume. Historical requests without this field retain their existing authoring path and attempt accounting. Paths are derived from scenario identity and canonical filename, not arbitrary user/model selections.

This is an authoring/write boundary, not a filesystem read sandbox. Public workspace agents may inspect the pinned checkout; the prompt asks for public imports/interfaces and no production repair. No private RackAI data or new language-specific application analysis is introduced.
