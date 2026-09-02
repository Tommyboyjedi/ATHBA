# PR23 Latch intent-review protocol forensics

## Scope and evidence

This review covers the terminal fresh Latch project
`pr23-live-latch-budget-20260902T133353Z`, run
`pr23-live-latch-budget-20260902T133353Z-run`. It reads the durable ATHBA
scenario state, proof report, and Rack AI Tester packet; it does not alter the
historical project or Rack AI.

## Attempt three

Attempt three had candidate SHA `b3f0fbc4d6fe4c98d8443223b67e11859e99bb9e`
and Rack AI branch
`rack/change-pr23-live-latch-budget-20260902T133353Z--REQ-001--scenario-draft-3--attempt-3`.
Its submitted source was:

```python
import pytest

from latch import Latch


def test_REQ_001():
    latch = Latch()
    assert latch is not None
```

The adapter's canonical identity is also `tests/test_latch.py::test_REQ_001`;
the canonicalised source is the same source above. The source directly imports
`Latch` from `latch.py`, and its static structural assessment passed: there were
no strict-grammar, substitute, mock, evasion, or production-reference issues.

The durable state then records `Expecting value: line 1 column 1 (char 0)` as
attempt three feedback. That is a constrained intent-review JSON parse error,
not a candidate-assessment result. The historical state did not retain either
the initial reviewer response or the one JSON-repair response. Therefore it
cannot truthfully classify either response as fenced JSON, JSON plus prose,
invalid schema, or another exact raw form, and it cannot establish whether the
repair response repeated the initial form. The only retained exact errors are
the escaped JSON parse feedback above and the same error embedded in attempt
four's no-op feedback.

Attempt four was sent the following purported Tester feedback:

> The repair produced no test-source change. The previous violations remain.
> Edit the existing candidate and resolve the listed issues. Expecting value:
> line 1 column 1 (char 0)

That feedback was reasoning-protocol failure incorrectly represented as a test
repair demand. The state records no raw reasoning content, provider credential,
or API value.

## Correction

Attempt three reached independent intent review only after structural acceptance.
It must therefore remain associated with its accepted candidate source, branch,
SHA, and assessment. Attempt four is not evidence of local-coder repair failure.
The current correction persists typed protocol facts separately, records bounded
response digests rather than raw provider text, performs exactly one repair call,
and blocks rather than creating another Tester attempt when both responses fail.
