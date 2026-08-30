"""AST gate for the coordinator refactor."""
from __future__ import annotations

import ast
from pathlib import Path

LIMIT = 100
TARGETS = [
    Path("core/development/behavior_contract_coordinator.py"),
    Path("core/development/contract_run_store.py"),
]


def input_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    return len(node.args.posonlyargs) + len(node.args.args) + len(node.args.kwonlyargs) - (1 if node.args.args and node.args.args[0].arg == "self" else 0)


def executable_line_count(node: ast.ClassDef) -> int:
    lines: set[int] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.stmt) and hasattr(child, "lineno"):
            if _is_docstring(child):
                continue
            lines.add(child.lineno)
    return len(lines)


def _is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def main() -> int:
    failures: list[str] = []
    for path in TARGETS:
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                lines = executable_line_count(node)
                if lines > LIMIT:
                    failures.append(f"{path}:{node.name} has {lines} executable lines")
                for method in node.body:
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and input_count(method) > 2:
                        failures.append(f"{path}:{node.name}.{method.name} has {input_count(method)} inputs")
    print("\n".join(failures) or "coding principles gate passed")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
