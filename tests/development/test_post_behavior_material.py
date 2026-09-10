"""Only explicit Behavior identifiers confer naming authority."""
from types import SimpleNamespace

import pytest

from core.development.post_behavior_adapters import focused_naming_material


@pytest.mark.parametrize("api,text,expected,kept", [
    (["Counter.total(values)"], "Store values in `SQLite`. ARCHITECTURE_SENTINEL", ("Counter", "total"), False),
    ([], "Expose method `total`. Do not provide ARCHITECTURE_SENTINEL.", ("total",), True),
    ([], "The function named total handles input.", ("total",), True),
    ([], "The method returns a value.", (), False),
    ([], "Create class Counter for numbers.", ("Counter",), True),
    (["total(values, default=0)"], "Gatekeeper NO test transcript SENTINEL.", ("total",), False),
])
def test_only_explicit_identifier_material_reaches_naming(api, text, expected, kept):
    delivery = SimpleNamespace(contract=SimpleNamespace(
        public_api=api, source_clauses=[SimpleNamespace(text=text)]))
    material = focused_naming_material(delivery)
    assert material.required_identifiers == expected
    assert "ARCHITECTURE_SENTINEL" not in material.text
    assert "transcript" not in material.text
    assert ("total" in material.text or "Counter" in material.text) == (bool(api) or kept)


def test_content_addressed_evidence_is_immutable_and_detects_corruption(tmp_path):
    from pathlib import Path
    from core.development.post_behavior_evidence import PostBehaviorEvidenceStore
    store = PostBehaviorEvidenceStore(tmp_path)
    reference = store.record("boundary", {"candidate": "a" * 40, "values": frozenset({"a", "b"})})
    original = Path(reference).read_bytes()
    assert store.record("boundary", {"candidate": "a" * 40, "values": frozenset({"b", "a"})}) == reference
    assert Path(reference).read_bytes() == original
    Path(reference).write_text("{}")
    with pytest.raises(ValueError, match="altered"):
        store.record("boundary", {"candidate": "a" * 40, "values": frozenset({"a", "b"})})
    assert Path(reference).read_text() == "{}"
