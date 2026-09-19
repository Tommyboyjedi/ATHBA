"""Fail-closed runtime evidence for a missing member on the production surface."""
from __future__ import annotations

import dis
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


@dataclass(frozen=True)
class MissingMemberContext:
    test_path: Path
    production_path: Path | None


def missing_production_member(error: BaseException, context: MissingMemberContext) -> bool:
    """Require a direct failed attribute load, a real production owner, and absence.

    Do not execute getters, infer ownership from exception wording, or accept
    exceptions raised inside production methods, fixtures, or test helpers.
    """
    if type(error) is not AttributeError or not error.name or context.production_path is None:
        return False
    trace = error.__traceback__
    if trace is None:
        return False
    while trace.tb_next is not None:
        trace = trace.tb_next
    if Path(trace.tb_frame.f_code.co_filename).resolve() != context.test_path:
        return False
    instruction = next((item for item in dis.get_instructions(trace.tb_frame.f_code)
                        if item.offset == trace.tb_lasti), None)
    if instruction is None or instruction.opname != "LOAD_ATTR" or instruction.argval != error.name:
        return False
    owner = error.obj
    owner_type = owner if isinstance(owner, type) else type(owner)
    module = owner if type(owner) is ModuleType else sys.modules.get(owner_type.__module__)
    if not isinstance(module, ModuleType):
        return False
    module_path = vars(module).get("__file__")
    if not isinstance(module_path, str) or Path(module_path).resolve() != context.production_path:
        return False
    if owner is not module and not any(value is owner_type for value in vars(module).values()):
        return False
    sentinel = object()
    if inspect.getattr_static(owner, error.name, sentinel) is not sentinel:
        return False
    lookup_type = type(owner)
    if inspect.getattr_static(lookup_type, "__getattr__", sentinel) is not sentinel:
        return False
    if inspect.getattr_static(lookup_type, "__getattribute__") not in (
        object.__getattribute__, type.__getattribute__, ModuleType.__getattribute__,
    ):
        return False
    return True
