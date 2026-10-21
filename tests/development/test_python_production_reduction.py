"""Syntax reduction must preserve baseline bytes and leave semantics to acceptance."""
from __future__ import annotations
import ast

import pytest

from core.development.production_reduction_syntax import ReductionSource
from core.development.python_production_reduction import PythonProductionReductionAdapter


def plan(before: bytes | None, after: bytes | None):
    return PythonProductionReductionAdapter().plan(ReductionSource("module.py", before, after))


def replacements(before: bytes | None, after: bytes | None):
    return tuple(item.replacement for item in plan(before, after).opportunities)


def test_new_class_and_contents_are_independent_coarse_to_fine_opportunities():
    baseline = b'"""existing module"""\n'
    candidate = baseline + b"""
class Example:
    def __init__(self):
        self.values = []

    def add(self, value):
        self.values.append(value)
"""
    values = replacements(baseline, candidate)
    assert baseline + b"\n" in values
    assert any(value is not None and b"class Example:" in value and b"def __init__" not in value for value in values)
    assert any(value is not None and b"class Example:" in value and b"def add" not in value for value in values)
    assert any(value is not None and b"self.values = []" not in value and b"pass" in value for value in values)
    for value in values:
        ast.parse(value)


def test_empty_class_gets_only_syntax_scaffolding():
    baseline = b"# baseline\n"
    candidate = baseline + b"class Example:\n    value = 3\n"
    assert baseline + b"class Example:\n    pass\n" in replacements(baseline, candidate)


def test_unchanged_baseline_method_is_never_trimmed():
    baseline = b"class Existing:\n    def retained(self):\n        return 100\n"
    candidate = baseline + b"\n    def extra(self):\n        return 200\n"
    values = replacements(baseline, candidate)
    assert values
    assert all(value is not None and baseline in value for value in values)
    assert not any(value is not None and b"return 100" not in value for value in values)


def test_localized_modified_unit_restoration_preserves_unrelated_bytes():
    baseline = b"# unchanged formatting\r\nKEEP = '\xc3\xa9'  # stable\r\n\r\ndef value():\r\n    return 1\r\n"
    candidate = baseline.replace(b"return 1", b"return 999")
    assert baseline in replacements(baseline, candidate)
    assert all(value is not None and value.startswith(baseline[:baseline.index(b"def value")])
               for value in replacements(baseline, candidate))


def test_added_statement_can_be_removed_without_reverting_whole_function():
    baseline = b"def value():\n    return 1\n"
    candidate = b"def value():\n    unused = 2\n    return 1\n"
    values = replacements(baseline, candidate)
    assert baseline in values
    assert all(value is not None and b"return 1" in value for value in values)


def test_deleted_baseline_unit_is_restored_between_ordered_anchors():
    baseline = b"A = 1\nKEEP = 2\nZ = 3\n"
    candidate = b"A = 1\nZ = 3\n"
    assert baseline in replacements(baseline, candidate)


def test_deleted_baseline_file_is_restored_exactly():
    baseline = b"# original\nVALUE = 1\n"
    assert replacements(baseline, None) == (baseline,)


def test_added_import_is_a_whole_unit_deletion():
    baseline = b"VALUE = 1\n"
    candidate = b"from collections import (\n    deque,\n    Counter,\n)\n" + baseline
    assert baseline in replacements(baseline, candidate)


def test_multiline_decorated_declaration_removal_is_syntax_valid():
    baseline = b"def decorator(fn):\n    return fn\n"
    candidate = baseline + b"\n@decorator\ndef extra(\n    value,\n):\n    return value\n"
    values = replacements(baseline, candidate)
    assert any(value is not None and b"def extra" not in value and b"@decorator" not in value for value in values)
    for value in values:
        ast.parse(value)


def test_duplicate_declaration_correspondence_is_skipped_honestly():
    baseline = b"def same():\n    return 1\n\ndef same():\n    return 2\n"
    candidate = baseline + b"\nEXTRA = 3\n"
    result = plan(baseline, candidate)
    assert any("Ambiguous" in item for item in result.limitations)
    assert all(item.replacement is not None and baseline in item.replacement for item in result.opportunities)


def test_ambiguous_changed_gap_does_not_guess_unit_correspondence():
    baseline = b"one()\ntwo()\n"
    candidate = b"three()\nfour()\n"
    result = plan(baseline, candidate)
    assert not result.opportunities
    assert result.limitations


def test_statement_identity_does_not_change_when_unrelated_lines_shift():
    baseline = b""
    first = plan(baseline, b"class Example:\n    value = 1\n")
    second = plan(baseline, b"\n\nclass Example:\n    value = 1\n")
    assert [item.transformation_id for item in first.opportunities] == [
        item.transformation_id for item in second.opportunities]


@pytest.mark.parametrize("source", [b"def broken(:\n", b"\xef\xbb\xbfVALUE = 1\n", b"# coding: latin-1\nVALUE = '\xe9'\n"])
def test_unsupported_syntax_or_encoding_is_not_a_semantic_failure(source):
    result = plan(b"", source)
    assert result.opportunities == ()
    assert result.limitations


def test_inline_and_semicolon_packed_statements_are_skipped_without_reformatting():
    source = b"def example(): return 3\nA = 1; B = 2\n"
    result = plan(b"", source)
    assert result.limitations
    assert all(item.replacement is not None and b"A = 1; B = 2" in item.replacement
               for item in result.opportunities)


def test_no_change_has_no_opportunities_or_limitations():
    assert plan(b"VALUE = 1\n", b"VALUE = 1\n").opportunities == ()


def test_reordered_surviving_units_do_not_make_unknown_material_added():
    baseline = b"A = 1\nB = 2\n"
    candidate = b"B = 2\nA = 1\n"
    assert replacements(baseline, candidate) == ()


def test_added_parent_does_not_erase_preexisting_non_ast_material():
    baseline = b"# unchanged baseline comment\\n"
    candidate = b"class Added:\\n    pass\\n" + baseline + b"    value = 2\\n"
    result = plan(baseline, candidate)
    assert result.limitations
    assert all(item.replacement is not None and baseline in item.replacement
               for item in result.opportunities)
