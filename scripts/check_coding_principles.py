"""AST gate for the coordinator and TDD progression refactors."""
from __future__ import annotations

import ast
from pathlib import Path

LIMIT = 100
TARGETS = [
    Path("core/development/behavior_contract_coordinator.py"),
    Path("core/development/contract_run_store.py"),
    Path("core/development/behavior_contract_domain.py"),
    Path("core/development/contract_run_domain.py"),
    Path("core/development/specification_domain.py"),
    Path("core/development/tdd_domain.py"),
    Path("core/development/tdd_progression.py"),
    Path("core/development/tdd_progression_validation.py"),
    Path("core/development/tdd_progression_values.py"),
    Path("core/development/failure_policy.py"),
    Path("core/development/failure_progression.py"),
    Path("core/development/failure_records.py"),
    Path("core/development/failure_state.py"),
    Path("core/development/failure_transitions.py"),
    Path("core/development/failure_values.py"),
    Path("core/development/specification_atomization.py"),
    Path("core/development/specification_assessment.py"),
    Path("core/development/specification_evidence.py"),
    Path("core/development/specification_gap_adapter.py"),
    Path("core/development/specification_gatekeeper.py"),
    Path("core/development/specification_reconciliation.py"),
    Path("core/development/test_evidence_reconciliation.py"),
]
ALLOWED_BASES = {"Enum", "Protocol", "str"}


def input_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    count = len(node.args.posonlyargs) + len(node.args.args) + len(node.args.kwonlyargs)
    if node.args.args and node.args.args[0].arg in {"self", "cls"}:
        count -= 1
    return count


def executable_line_count(node: ast.ClassDef) -> int:
    lines: set[int] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.stmt) and hasattr(child, "lineno"):
            if is_docstring(child):
                continue
            lines.add(child.lineno)
    return len(lines)


def is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ast.dump(node)


def main() -> int:
    failures: list[str] = []
    for path in TARGETS:
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            lines = executable_line_count(node)
            if lines > LIMIT:
                failures.append(f"{path}:{node.name} has {lines} executable lines")
            illegal_bases = [name for name in (base_name(base) for base in node.bases) if name not in ALLOWED_BASES]
            if illegal_bases:
                failures.append(f"{path}:{node.name} has forbidden bases {illegal_bases}")
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and input_count(method) > 2:
                    failures.append(f"{path}:{node.name}.{method.name} has {input_count(method)} inputs")
    print("\n".join(failures) or "coding principles gate passed")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
