import ast

import pytest

from core.development.microcycle_domain import (
    BoundaryClassificationRequest, BoundaryDiagnostic, DiagnosticFact,
    FinalTestMaterialisationRequest, FragmentationRequest, FrontierExecutionRequest,
    FrontierMaterialisationRequest, ScenarioFrontier, ScenarioParseRequest,
    SyntaxValidationRequest, TestScenarioDraft,
)
from core.development.python_pytest_adapter import PythonPytestAdapter


def source(body, module="import pytest"):
    return f"{module}\n\ndef test_widget():\n" + "\n".join(f"    {line}" for line in body.splitlines()) + "\n"


def prepared(body, module="import pytest"):
    adapter = PythonPytestAdapter()
    draft = TestScenarioDraft("generic-widget", "generic-behavior", "python", source(body, module), "tests/test_widget.py::test_widget", "tests/test_widget.py")
    model = adapter.parse_scenario(ScenarioParseRequest(draft))
    return adapter, model, adapter.fragment_scenario(FragmentationRequest(model))


def artifact(adapter, model, fragments, index):
    frontier = ScenarioFrontier(model.scenario_id, index, fragments[index].fragment_id, tuple(item.fragment_id for item in fragments[:index + 1]))
    return adapter.materialise_frontier(FrontierMaterialisationRequest(model, fragments, frontier, "base"))


def execute(adapter, tmp_path, model, value):
    return adapter.execute_frontier(FrontierExecutionRequest(value, str(tmp_path), model.test_path))


def classify(adapter, fragments, index, value, prior=None):
    return adapter.classify_boundary(BoundaryClassificationRequest(value, value_artifact(value), fragments[index], prior))


def value_artifact(value):
    return value._artifact


def diagnostic_with_artifact(adapter, tmp_path, model, value):
    diagnostic = execute(adapter, tmp_path, model, value)
    object.__setattr__(diagnostic, "_artifact", value)
    return diagnostic


def test_missing_import_at_active_frontier_is_valid_red(tmp_path):
    adapter, model, fragments = prepared("from absent_widget import Widget")
    value = artifact(adapter, model, fragments, 0)
    assessment = classify(adapter, fragments, 0, diagnostic_with_artifact(adapter, tmp_path, model, value))
    assert assessment.outcome == "valid_missing_capability_red"


def test_missing_constructor_and_member_are_valid_red(tmp_path):
    adapter, model, fragments = prepared("import widget_module\nwidget = widget_module.Widget()\nwidget.grow()")
    (tmp_path / "widget_module.py").write_text("class Present: pass\n")
    constructor = artifact(adapter, model, fragments, 1)
    constructor_result = classify(adapter, fragments, 1, diagnostic_with_artifact(adapter, tmp_path, model, constructor))
    assert constructor_result.outcome == "valid_missing_capability_red"
    (tmp_path / "widget_module.py").write_text("class Widget: pass\n")
    member = artifact(adapter, model, fragments, 2)
    member_result = classify(adapter, fragments, 2, diagnostic_with_artifact(adapter, tmp_path, model, member))
    assert member_result.outcome == "valid_missing_capability_red"


def test_assertion_red_green_and_structured_facts(tmp_path):
    adapter, model, fragments = prepared("import widget_module\nassert widget_module.value == 2")
    (tmp_path / "widget_module.py").write_text("value = 1\n")
    failed = artifact(adapter, model, fragments, 1)
    diagnostic = diagnostic_with_artifact(adapter, tmp_path, model, failed)
    assert {item.name for item in diagnostic.facts} >= {"collection_succeeded", "requested_node_found", "call_outcome", "source_line"}
    assert classify(adapter, fragments, 1, diagnostic).outcome == "valid_behavioral_red"
    (tmp_path / "widget_module.py").write_text("value = 2\n")
    green = diagnostic_with_artifact(adapter, tmp_path, model, failed)
    assert classify(adapter, fragments, 1, green).outcome == "green"


def test_bad_indentation_is_invalid_and_compound_forms_are_atomic():
    adapter = PythonPytestAdapter()
    bad = TestScenarioDraft("x", "b", "python", "def test_x():\n  if True:\n    pass\n   pass\n", "tests/x.py::test_x", "tests/x.py")
    with pytest.raises(ValueError, match="syntax"):
        adapter.parse_scenario(ScenarioParseRequest(bad))
    adapter, model, fragments = prepared("for item in [1]:\n    assert item == 1\nif True:\n    assert True\nwith pytest.raises(ValueError):\n    raise ValueError()")
    assert [item.kind for item in fragments] == ["loop_block", "if_block", "raises_block"]
    value = artifact(adapter, model, fragments, 0)
    compile(value.complete_source, "frontier", "exec")
    assert "if True" not in value.complete_source and "pytest.raises" not in value.complete_source


def test_prior_failure_is_rejected_and_later_fragments_hidden(tmp_path):
    adapter, model, fragments = prepared("from absent_widget import Widget\nwidget = Widget()")
    value = artifact(adapter, model, fragments, 1)
    assert "Widget()" in value.complete_source
    diagnostic = diagnostic_with_artifact(adapter, tmp_path, model, value)
    assert classify(adapter, fragments, 1, diagnostic, "green").outcome == "failure_before_frontier"
    first = artifact(adapter, model, fragments, 0)
    assert "Widget()" not in first.complete_source


def test_module_scope_import_collection_failure_is_narrowly_accepted(tmp_path):
    adapter, model, fragments = prepared("assert True", "import pytest\nfrom absent_widget import Widget")
    value = artifact(adapter, model, fragments, 0)
    diagnostic = diagnostic_with_artifact(adapter, tmp_path, model, value)
    assert diagnostic.kind == "collection_failure"
    assert classify(adapter, fragments, 0, diagnostic).outcome == "valid_missing_capability_red"


def test_dynamic_generation_fails_closed():
    adapter = PythonPytestAdapter()
    draft = TestScenarioDraft("x", "b", "python", "import pytest\n@pytest.mark.parametrize('x', [1])\ndef test_x(x):\n    assert x\n", "tests/x.py::test_x", "tests/x.py")
    with pytest.raises(ValueError, match="dynamic"):
        adapter.parse_scenario(ScenarioParseRequest(draft))


def test_final_artifact_matches_approved_scenario_intent():
    adapter, model, fragments = prepared("value = 1\nassert value == 1")
    final = adapter.materialise_final_test(FinalTestMaterialisationRequest(model, fragments, "base"))
    assert ast.dump(ast.parse(final.complete_source), include_attributes=False) == ast.dump(ast.parse(model.complete_source), include_attributes=False)
    assert all(item.source_span is not None for item in fragments)
