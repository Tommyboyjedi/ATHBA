"""Regression reproductions for scoped Naming selection; no model execution."""
from core.development.python_parameter_naming import PythonParameterNaming
from dataclasses import replace
import pytest
from core.development.post_behavior_assessment import (
    IdentifierRename, NamingAssessmentInput, NamingAssessor, NamingDecision, NamingMaterial)
from core.development.post_behavior_slice import FocusedProductionSlice, ProductionSliceScope
from core.development.required_public_signature import RequiredPublicSignature
from core.development.specification_evidence_policy import RevisionFile

SOURCE = """class RunningTotal:
    def add(self, value):
        self._total += value
    def value(self):
        return self._total
    def total(self):
        return self._total
"""
SIGNATURES = (
    RequiredPublicSignature("RunningTotal", "add", ("amount",), "add(amount)"),
    RequiredPublicSignature("RunningTotal", "total", (), "total()"),
)

class NoModel:
    async def reason(self, request):
        raise AssertionError("A scoped declaration fact does not need concept inference")

def assessment(source=SOURCE, names=("RunningTotal", "add", "amount", "total")):
    return NamingAssessmentInput(
        NamingMaterial("\n".join(item.source_quote for item in SIGNATURES), names, SIGNATURES),
        FocusedProductionSlice("a"*40, (RevisionFile("running_total.py", source),),
            ProductionSliceScope("b"*40, "a"*40, ("running_total.py",))), parameter_naming=PythonParameterNaming())

@pytest.mark.asyncio
async def test_explicit_parameter_selected_despite_same_spelled_helper():
    decision = await NamingAssessor(NoModel()).reason(assessment())
    assert decision == NamingDecision(IdentifierRename("value", "amount", "RunningTotal", "add", 0))

@pytest.mark.asyncio
async def test_complete_scoped_names_do_not_rename_an_extra_alias():
    source = SOURCE.replace("add(self, value)", "add(self, amount)").replace("_total += value", "_total += amount")
    assert await NamingAssessor(NoModel()).reason(assessment(source)) == NamingDecision()

@pytest.mark.asyncio
async def test_same_parameter_pair_in_two_operations_selects_one_scoped_frontier():
    source = "class Counter:\n    def add(self, x):\n        return x\n    def subtract(self, x):\n        return x\n"
    signatures = tuple(RequiredPublicSignature("Counter", operation, ("amount",), operation+"(amount)") for operation in ("add","subtract"))
    request = assessment(source, ("Counter", "add", "subtract", "amount"))
    request = replace(request, material=replace(request.material, required_signatures=signatures))
    assert await NamingAssessor(NoModel()).reason(request) == NamingDecision(
        IdentifierRename("x", "amount", "Counter", "add", 0))

@pytest.mark.asyncio
async def test_parameter_selection_does_not_change_call_shape():
    with pytest.raises(ValueError, match="cannot change call shape"):
        await NamingAssessor(NoModel()).reason(assessment(
            SOURCE.replace("add(self, value)", "add(self, value=0)")))

@pytest.mark.asyncio
async def test_parameter_selection_requires_registered_language_adapter():
    request = assessment()
    request = replace(request, parameter_naming=None, production=replace(request.production,
        files=(RevisionFile("subject.js", "class RunningTotal {}"),)))
    with pytest.raises(ValueError, match="no configured language capability"):
        await NamingAssessor(NoModel()).reason(request)

class Model:
    def __init__(self, answer):
        self.answer = answer
        self.requests = []
    async def reason(self, request):
        from types import SimpleNamespace
        self.requests.append(request)
        return SimpleNamespace(text=self.answer)

@pytest.mark.asyncio
async def test_missing_operation_remains_a_bounded_model_comparison():
    source = SOURCE.replace("add(self, value)", "append(self, amount)").replace("_total += value", "_total += amount")
    model = Model("YES\ncurrent_name: append\nrequired_name: add")
    result = await NamingAssessor(model).reason(assessment(source))
    assert result == NamingDecision(IdentifierRename("append", "add"))
    assert len(model.requests) == 1

@pytest.mark.asyncio
async def test_additional_naming_authority_is_not_mechanically_declared_complete():
    source = SOURCE.replace("add(self, value)", "add(self, amount)").replace("_total += value", "_total += amount")
    model = Model("NO")
    request = assessment(source + "\nstatus = 0\n", ("RunningTotal", "add", "amount", "total", "status"))
    assert await NamingAssessor(model).reason(request) == NamingDecision()
    assert len(model.requests) == 1
    assert "status" in model.requests[0].prompt

@pytest.mark.asyncio
async def test_scoped_completion_rejects_duplicate_owning_declarations():
    source = "class RunningTotal:\n    def add(self, amount):\n        return amount\n\nclass RunningTotal:\n    def total(self):\n        return 0\n"
    with pytest.raises(ValueError, match="one owning declaration"):
        await NamingAssessor(NoModel()).reason(assessment(source))


@pytest.mark.asyncio
async def test_same_spelling_extra_field_authority_still_requires_model_comparison():
    source = SOURCE.replace("add(self, value)", "add(self, amount)").replace("_total += value", "_total += amount")
    request = assessment(source)
    request = replace(request, material=replace(request.material,
        text=request.material.text + "\nA field named amount is explicitly required."))
    model = Model("NO")
    assert await NamingAssessor(model).reason(request) == NamingDecision()
    assert len(model.requests) == 1
