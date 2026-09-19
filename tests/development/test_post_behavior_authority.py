"""Deterministic slice and mutation authority proofs using immutable source snapshots."""
from dataclasses import replace

import pytest

from core.development.post_behavior_assessment import IdentifierRename
from core.development.post_behavior_authority import (
    PythonPostBehaviorAuthority, RefactorAuthorityRequest, RenameAuthorityRequest,
)
from core.development.post_behavior_slice import PythonProductionSlice, SliceRequest
from core.development.specification_evidence_policy import RevisionFile, SpecificationSnapshot

BEFORE = "def unrelated():\n    return 'UNRELATED_SECRET'\n"
PRODUCTION = BEFORE + "\ndef draft_total(values):\n    result = sum(values)\n    return result\n"
TESTS = "from app import draft_total\n\ndef test_total():\n    assert draft_total([1, 2]) == 3\n"
AUTHORITY = PythonPostBehaviorAuthority()


def snapshot(revision, production=PRODUCTION, tests=TESTS, extra=()):
    return SpecificationSnapshot(revision, (
        RevisionFile("app.py", production), RevisionFile("tests/test_app.py", tests),
        RevisionFile("README.md", "DOCUMENTATION_SECRET"), *extra,
    ))


def focused(trusted=None):
    return PythonProductionSlice().derive(SliceRequest(snapshot("entry", BEFORE), trusted or snapshot("accepted")))


def rename(candidate, trusted=None, production=None):
    base = trusted or snapshot("accepted")
    return AUTHORITY.rename(RenameAuthorityRequest(
        base, candidate, production or focused(base), IdentifierRename("draft_total", "total"),
    ))


def refactor(candidate, trusted=None):
    base = trusted or snapshot("accepted")
    return AUTHORITY.refactor(RefactorAuthorityRequest(base, candidate, focused(base)))


def test_focused_context_excludes_tests_documents_and_unchanged_same_file_function():
    result = focused()
    assert result.files == (RevisionFile("app.py", "def draft_total(values):\n    result = sum(values)\n    return result\n"),)
    assert result.scope.entry_revision == "entry"
    assert result.scope.behaviorally_accepted_revision == "accepted"
    assert result.scope.production_paths == ("app.py",)
    assert result.regions[0].start_line == 4


def test_slice_includes_only_referenced_imports_and_changed_class_member():
    before = "import math\nimport secrets\n\nclass Calculator:\n    def unrelated(self):\n        return 'SECRET'\n\n    def total(self, x):\n        return x\n"
    after = before.replace("return x", "return math.floor(x)")
    result = PythonProductionSlice().derive(SliceRequest(snapshot("entry", before), snapshot("accepted", after)))
    assert result.files[0].source == "import math\nclass Calculator:\n    def total(self, x):\n        return math.floor(x)\n"
    assert "secrets" not in result.files[0].source
    assert "unrelated" not in result.files[0].source


def test_slice_regeneration_uses_new_accepted_code_and_keeps_baseline_identity():
    first = focused()
    changed = snapshot("renamed", PRODUCTION.replace("draft_total", "total"), TESTS.replace("draft_total", "total"))
    result = PythonProductionSlice().derive(SliceRequest(snapshot("entry", BEFORE), changed, first.scope))
    assert result.revision == "renamed"
    assert result.scope == first.scope
    assert result.identity != first.identity
    assert "def total(" in result.files[0].source
    assert "draft_total" not in result.files[0].source


def test_slice_rejects_mismatched_entry_and_missing_production_path():
    with pytest.raises(ValueError, match="entry revision mismatch"):
        PythonProductionSlice().derive(SliceRequest(snapshot("other", BEFORE), snapshot("accepted"), focused().scope))
    missing = replace(snapshot("accepted"), files=(RevisionFile("tests/test_app.py", TESTS),))
    with pytest.raises(ValueError, match="disappeared"):
        PythonProductionSlice().derive(SliceRequest(snapshot("entry", BEFORE), missing, focused().scope))


def test_exact_production_and_test_reference_rename_is_authorized():
    result = rename(snapshot("candidate", PRODUCTION.replace("draft_total", "total"), TESTS.replace("draft_total", "total")))
    assert result.passed, result.reason


@pytest.mark.parametrize("production,tests", [
    (PRODUCTION.replace("draft_total", "total").replace("sum(values)", "len(values)"), TESTS.replace("draft_total", "total")),
    (PRODUCTION.replace("draft_total", "total").replace("return result", "return 9"), TESTS.replace("draft_total", "total")),
    (PRODUCTION.replace("draft_total", "total"), TESTS.replace("draft_total", "total").replace("== 3", "== 9")),
    (PRODUCTION.replace("draft_total", "total"), TESTS.replace("draft_total", "total").replace("[1, 2]", "[3]")),
    (PRODUCTION.replace("draft_total", "total"), TESTS.replace("draft_total", "total") + "\ndef test_new():\n    assert True\n"),
    (PRODUCTION.replace("draft_total", "total").replace("result", "value"), TESTS.replace("draft_total", "total")),
    (PRODUCTION.replace("draft_total", "total").replace("UNRELATED_SECRET", "CHANGED"), TESTS.replace("draft_total", "total")),
    (PRODUCTION.replace("draft_total", "total"), TESTS),
    (PRODUCTION.replace("draft_total", "total").replace("values):", "values=()):"), TESTS.replace("draft_total", "total")),
])
def test_rename_rejects_non_reference_edits_and_missing_reference_update(production, tests):
    result = rename(snapshot("candidate", production, tests))
    assert not result.passed
    assert "non-authorized" in result.reason


def test_rename_preserves_import_alias_local_shadow_and_string_values():
    tests = ("from app import draft_total as calculate\n"
             "def test_total():\n    draft_total = 'draft_total'\n"
             "    assert calculate([1, 2]) == 3\n    assert draft_total == 'draft_total'\n")
    base = snapshot("accepted", tests=tests)
    candidate = snapshot("candidate", PRODUCTION.replace("draft_total", "total"),
                         tests.replace("import draft_total", "import total"))
    result = rename(candidate, base)
    assert result.passed, result.reason
    assert not rename(snapshot("bad", candidate.files[0].source, tests.replace("draft_total", "total")), base).passed


def test_method_rename_updates_only_resolved_receiver_not_unrelated_same_name():
    before = "class Other:\n    def old(self):\n        return 0\n"
    source = before + "\nclass Counter:\n    def old(self):\n        return 3\n"
    tests = "from app import Counter, Other\ndef test_value():\n    item = Counter()\n    other = Other()\n    assert item.old() == 3\n    assert other.old() == 0\n"
    base = snapshot("accepted", source, tests)
    production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", before, tests), base))
    candidate = snapshot("candidate", source.replace("def old(self):\n        return 3", "def count(self):\n        return 3"),
                         tests.replace("item.old()", "item.count()"))
    request = RenameAuthorityRequest(base, candidate, production, IdentifierRename("old", "count"))
    assert AUTHORITY.rename(request).passed
    overbroad = snapshot("bad", source.replace("old", "count"), tests.replace("old", "count"))
    assert not AUTHORITY.rename(replace(request, candidate=overbroad)).passed


def test_ambiguous_focused_same_named_declarations_fail_closed():
    source = "class One:\n    def old(self):\n        return 1\nclass Two:\n    def old(self):\n        return 2\n"
    base = snapshot("accepted", source)
    production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", ""), base))
    candidate = snapshot("candidate", source.replace("old", "new"))
    result = AUTHORITY.rename(RenameAuthorityRequest(base, candidate, production, IdentifierRename("old", "new")))
    assert not result.passed
    assert "one focused declaration" in result.reason


def test_module_qualified_reference_is_authorized():
    tests = "import app as product\ndef test_value():\n    assert product.draft_total([1, 2]) == 3\n"
    base = snapshot("accepted", tests=tests)
    result = rename(snapshot("candidate", PRODUCTION.replace("draft_total", "total"), tests.replace("draft_total", "total")), base)
    assert result.passed, result.reason


def test_refactor_can_change_internal_names_and_control_structure_with_unchanged_tests():
    candidate = snapshot("candidate", BEFORE + "\ndef draft_total(values):\n    return sum(values)\n")
    result = refactor(candidate)
    assert result.passed, result.reason


def test_refactor_may_introduce_adjacent_private_helper():
    candidate = snapshot("candidate", BEFORE + "\ndef draft_total(values):\n    return _sum(values)\n\ndef _sum(items):\n    return sum(items)\n")
    result = refactor(candidate)
    assert result.passed, result.reason


@pytest.mark.parametrize("source", [
    PRODUCTION.replace("draft_total", "total"),
    PRODUCTION.replace("values):", "values, initial=0):"),
    PRODUCTION.replace("UNRELATED_SECRET", "CHANGED"),
    PRODUCTION + "\ndef unrelated_public():\n    return 1\n",
])
def test_refactor_rejects_public_signature_or_outside_slice_edits(source):
    assert not refactor(snapshot("candidate", source)).passed


def test_refactor_tests_are_byte_for_byte_read_only():
    result = refactor(snapshot("candidate", PRODUCTION.replace("return result", "return sum(values)"), TESTS + "\n"))
    assert not result.passed
    assert "cannot write: tests/test_app.py" in result.reason


def test_refactor_cannot_modify_existing_private_helper_outside_slice():
    before = "def _helper():\n    return 1\n"
    source = before + "\ndef draft_total(values):\n    return sum(values)\n"
    base = snapshot("accepted", source)
    production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", before), base))
    candidate = snapshot("candidate", source.replace("return 1", "return 2"))
    result = AUTHORITY.refactor(RefactorAuthorityRequest(base, candidate, production))
    assert not result.passed


def test_refactor_preserves_public_fields_and_constructor_signature():
    source = "class Counter:\n    def __init__(self, value=1):\n        self.value = value\n    def count(self):\n        return self.value\n"
    base = snapshot("accepted", source)
    production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", ""), base))
    for changed in (source.replace("self.value", "self.other"), source.replace("value=1", "value=2")):
        result = AUTHORITY.refactor(RefactorAuthorityRequest(base, snapshot("candidate", changed), production))
        assert not result.passed


def test_write_authority_rejects_incomplete_stale_and_changed_file_sets():
    assert not rename(replace(snapshot("candidate"), complete=False)).passed
    assert not rename(snapshot("candidate"), production=replace(focused(), revision="rejected")).passed
    assert not refactor(snapshot("candidate", extra=(RevisionFile("new.py", "pass\n"),))).passed


def test_rename_and_refactor_cannot_edit_non_source_files():
    changed = replace(snapshot("candidate"), files=tuple(
        replace(file, source="CHANGED") if file.path == "README.md" else file for file in snapshot("accepted").files
    ))
    assert not rename(changed).passed
    assert not refactor(changed).passed


def test_imported_name_shadowed_by_unrelated_function_keeps_its_references():
    tests = "from app import draft_total\ndef draft_total():\n    return 7\ndef test_shadow():\n    assert draft_total() == 7\n"
    base = snapshot("accepted", tests=tests)
    expected = tests.replace("import draft_total", "import total")
    candidate = snapshot("candidate", PRODUCTION.replace("draft_total", "total"), expected)
    assert rename(candidate, base).passed
    wrong = expected.replace("assert draft_total()", "assert total()")
    assert not rename(snapshot("bad", candidate.files[0].source, wrong), base).passed


def test_unrelated_local_import_cannot_be_mistaken_for_product_identifier():
    tests = "from app import draft_total\ndef test_shadow():\n    from elsewhere import draft_total\n    assert draft_total() == 7\n"
    base = snapshot("accepted", tests=tests)
    expected = tests.replace("from app import draft_total", "from app import total")
    candidate = snapshot("candidate", PRODUCTION.replace("draft_total", "total"), expected)
    assert rename(candidate, base).passed
    assert not rename(snapshot("bad", candidate.files[0].source, expected.replace("assert draft_total()", "assert total()")), base).passed


def test_unsupported_production_language_fails_closed():
    entry = snapshot("entry", BEFORE)
    accepted = snapshot("accepted", BEFORE, extra=(RevisionFile("product.js", "export const value = 1;"),))
    with pytest.raises(ValueError, match="unsupported production language"):
        PythonProductionSlice().derive(SliceRequest(entry, accepted))


def test_required_identifier_collision_in_same_scope_fails_closed():
    source = PRODUCTION + "\ndef total(values):\n    return len(values)\n"
    base = snapshot("accepted", source)
    candidate = snapshot("candidate", source.replace("def draft_total", "def total"), TESTS.replace("draft_total", "total"))
    result = rename(candidate, base)
    assert not result.passed
    assert "already exists" in result.reason


@pytest.mark.parametrize("production,tests,renamed_production,renamed_tests", [
    (
        "class Counter:\n    def __init__(self):\n        self.old = 3\n    def read(self):\n        return self.old\n",
        "from app import Counter\ndef test_value():\n    item = Counter()\n    assert item.old == item.read() == 3\n",
        "class Counter:\n    def __init__(self):\n        self.value = 3\n    def read(self):\n        return self.value\n",
        "from app import Counter\ndef test_value():\n    item = Counter()\n    assert item.value == item.read() == 3\n",
    ),
    (
        "class Counter:\n    old = 3\n    def read(self):\n        return self.old\n",
        "from app import Counter\ndef test_value():\n    assert Counter.old == Counter().old == 3\n",
        "class Counter:\n    value = 3\n    def read(self):\n        return self.value\n",
        "from app import Counter\ndef test_value():\n    assert Counter.value == Counter().value == 3\n",
    ),
    (
        "old = 3\ndef read():\n    return old\n",
        "from app import old\ndef test_value():\n    assert old == 3\n",
        "value = 3\ndef read():\n    return value\n",
        "from app import value\ndef test_value():\n    assert value == 3\n",
    ),
])
def test_explicit_fields_are_renamed_with_exact_references(production, tests, renamed_production, renamed_tests):
    base = snapshot("accepted", production, tests)
    focused_production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", ""), base))
    candidate = snapshot("candidate", renamed_production, renamed_tests)
    request = RenameAuthorityRequest(base, candidate, focused_production, IdentifierRename("old", "value"))
    result = AUTHORITY.rename(request)
    assert result.passed, result.reason
    changed_value = snapshot("bad", renamed_production.replace("3", "9"), renamed_tests.replace("3", "9"))
    assert not AUTHORITY.rename(replace(request, candidate=changed_value)).passed


def test_field_rename_does_not_touch_local_same_name_variable_or_other_class_field():
    source = "class Counter:\n    def __init__(self):\n        self.old = 3\n    def read(self):\n        old = 9\n        return self.old + old\n\nclass Other:\n    old = 7\n"
    base = snapshot("accepted", source)
    focused_production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", "class Other:\n    old = 7\n"), base))
    candidate = snapshot("candidate", source.replace("self.old", "self.value"))
    request = RenameAuthorityRequest(base, candidate, focused_production, IdentifierRename("old", "value"))
    result = AUTHORITY.rename(request)
    assert result.passed, result.reason
    assert not AUTHORITY.rename(replace(request, candidate=snapshot("bad", source.replace("old", "value")))).passed


def test_class_field_does_not_rebind_unqualified_global_in_method():
    source = "old = 7\n\nclass Counter:\n    old = 3\n    def read(self):\n        return self.old + old\n"
    base = snapshot("accepted", source)
    production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", "old = 7\n"), base))
    candidate_source = source.replace("    old = 3", "    value = 3").replace("self.old", "self.value")
    request = RenameAuthorityRequest(base, snapshot("candidate", candidate_source), production, IdentifierRename("old", "value"))
    assert AUTHORITY.rename(request).passed
    assert not AUTHORITY.rename(replace(request, candidate=snapshot("bad", candidate_source.replace("+ old", "+ value")))).passed


def test_read_only_property_name_is_an_explicit_declaration():
    source = "class Counter:\n    @property\n    def old(self):\n        return 3\n"
    tests = "from app import Counter\ndef test_value():\n    assert Counter().old == 3\n"
    base = snapshot("accepted", source, tests)
    production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", ""), base))
    candidate = snapshot("candidate", source.replace("def old", "def value"), tests.replace(".old", ".value"))
    result = AUTHORITY.rename(RenameAuthorityRequest(base, candidate, production, IdentifierRename("old", "value")))
    assert result.passed, result.reason


def test_refactor_may_rename_focused_private_helper_and_its_internal_parameters():
    source = "def _sum(values):\n    return sum(values)\n\ndef total(values):\n    return _sum(values)\n"
    base = snapshot("accepted", source)
    production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", ""), base))
    candidate = snapshot("candidate", source.replace("_sum", "_add").replace("def _add(values):\n    return sum(values)", "def _add(items):\n    return sum(items)"))
    result = AUTHORITY.refactor(RefactorAuthorityRequest(base, candidate, production))
    assert result.passed, result.reason


def test_refactor_cannot_rename_unfocused_private_helper():
    before = "def _sum(values):\n    return sum(values)\n"
    source = before + "\ndef total(values):\n    return _sum(values)\n"
    base = snapshot("accepted", source)
    production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", before), base))
    candidate = snapshot("candidate", source.replace("_sum", "_add"))
    assert not AUTHORITY.refactor(RefactorAuthorityRequest(base, candidate, production)).passed


def test_full_and_focused_target_selection_agree_for_repeated_field_assignments():
    from core.development.post_behavior_rename import (
        FocusedRenameSelection, RenameSelection, select_focused_target, select_target,
    )

    source = "class Counter:\n    def __init__(self):\n        self.old = 3\n    def reset(self):\n        self.old = 0\n"
    base = snapshot("accepted", source)
    production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", ""), base))
    whole = select_target(RenameSelection(base, production, "old", "value"))
    projected = select_focused_target(FocusedRenameSelection(production.files, "old", "value"))
    assert (whole.path, whole.owner, whole.name, whole.kind) == (
        projected.path, projected.owner, projected.name, projected.kind,
    )
    assert projected.owner == "Counter"


@pytest.mark.parametrize("source,error", [
    ("class Counter:\n    old = 1\n    value = 2\n", "already exists"),
    ("class One:\n    old = 1\nclass Two:\n    old = 2\n", "one focused declaration"),
    ("def old():\n    return 1\ndef old():\n    return 2\n", "one focused declaration"),
])
def test_focused_target_selection_preserves_collision_and_ambiguity_guards(source, error):
    from core.development.post_behavior_rename import FocusedRenameSelection, select_focused_target

    with pytest.raises(ValueError, match=error):
        select_focused_target(FocusedRenameSelection((RevisionFile("app.py", source),), "old", "value"))


def test_focused_decorated_target_uses_definition_line_for_reference_identity():
    from core.development.post_behavior_rename import FocusedRenameSelection, select_focused_target

    source = "class Counter:\n    @property\n    def old(self):\n        return 3\n"
    result = select_focused_target(FocusedRenameSelection((RevisionFile("app.py", source),), "old", "value"))
    assert result.declaration_line == 3


@pytest.mark.parametrize("source,changed", [
    ("class Counter:\n    value: int = 1\n", "class Counter:\n    value: str = 1\n"),
    ("value: int = 1\n", "value: str = 1\n"),
    ("value: int = 1\n", "value = 1\n"),
    ("__all__ = ['Counter']\nclass Counter:\n    pass\n", "__all__ = []\nclass Counter:\n    pass\n"),
    ("class Counter:\n    __slots__ = ('value',)\n", "class Counter:\n    __slots__ = ('other',)\n"),
    ("class Counter:\n    __slots__: tuple[str, ...] = ('value',)\n", "class Counter:\n    __slots__: tuple[str, ...] = ()\n"),
    ("__all__ = []\n__all__ += ['Counter']\nclass Counter:\n    pass\n", "__all__ = []\n__all__ += []\nclass Counter:\n    pass\n"),
])
def test_refactor_preserves_public_field_annotations_and_explicit_interface_metadata(source, changed):
    base = snapshot("accepted", source)
    production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", ""), base))
    candidate = snapshot("candidate", changed)
    result = AUTHORITY.refactor(RefactorAuthorityRequest(base, candidate, production))
    assert not result.passed
    assert "public interface changed" in result.reason


def test_refactor_can_change_private_annotation_without_changing_public_metadata():
    source = "__all__ = ['Counter']\nclass Counter:\n    __slots__ = ('value',)\n    value: int = 1\n    _cache: list = []\n"
    base = snapshot("accepted", source)
    production = PythonProductionSlice().derive(SliceRequest(snapshot("entry", ""), base))
    candidate = snapshot("candidate", source.replace("_cache: list = []", "_cache: dict = {}"))
    result = AUTHORITY.refactor(RefactorAuthorityRequest(base, candidate, production))
    assert result.passed, result.reason
