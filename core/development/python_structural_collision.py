"""Python-only runtime proof of a direct production data/member call collision."""
from __future__ import annotations

import ast
import dis
import inspect
import sys
from pathlib import Path
from types import ModuleType

from core.development.python_missing_member import MissingMemberContext
from core.development.structural_refactor_domain import StructuralProblem


def structural_collision(error: BaseException, context: MissingMemberContext) -> StructuralProblem | None:
    if type(error) is not TypeError or context.production_path is None:
        return None
    trace = error.__traceback__
    if trace is None:
        return None
    while trace.tb_next is not None:
        trace = trace.tb_next
    if Path(trace.tb_frame.f_code.co_filename).resolve() != context.test_path:
        return None
    instruction = next((item for item in dis.get_instructions(trace.tb_frame.f_code)
                        if item.offset == trace.tb_lasti), None)
    if instruction is None or instruction.opname != "CALL":
        return None
    position = instruction.positions
    if position is None:
        return None
    module = ast.parse(context.test_path.read_text())
    calls = [node for node in ast.walk(module) if isinstance(node, ast.Call)
             and (node.lineno, node.end_lineno, node.col_offset, node.end_col_offset) ==
             (position.lineno, position.end_lineno, position.col_offset, position.end_col_offset)]
    if len(calls) != 1 or not isinstance(calls[0].func, ast.Attribute):
        return None
    member = calls[0].func
    if not isinstance(member.value, ast.Name):
        return None
    owner = trace.tb_frame.f_locals.get(member.value.id)
    owner_type = type(owner)
    production_module = sys.modules.get(owner_type.__module__)
    if type(production_module) is not ModuleType:
        return None
    module_path = vars(production_module).get("__file__")
    if not isinstance(module_path, str) or Path(module_path).resolve() != context.production_path:
        return None
    if not any(value is owner_type for value in vars(production_module).values()):
        return None
    sentinel = object()
    if inspect.getattr_static(owner_type, "__getattr__", sentinel) is not sentinel:
        return None
    if inspect.getattr_static(owner_type, "__getattribute__") is not object.__getattribute__:
        return None
    value = inspect.getattr_static(owner, member.attr, sentinel)
    if value is sentinel or callable(value) or hasattr(type(value), "__get__"):
        return None
    source = ast.parse(context.production_path.read_text())
    classes = [node for node in source.body if isinstance(node, ast.ClassDef)
               and node.name == owner_type.__name__]
    if len(classes) != 1 or classes[0].decorator_list or classes[0].bases:
        return None
    scope = classes[0]
    path = context.production_path.relative_to(Path.cwd()).as_posix()
    description = (
        f"{member.attr} currently resolves to a non-callable data attribute, so "
        f"the {member.attr}() call shape is blocked. Refactor that collision "
        "while preserving existing behaviour."
    )
    return StructuralProblem(description, path, scope.lineno, scope.end_lineno or scope.lineno, member.attr)
