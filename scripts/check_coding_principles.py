"""Repo-wide AST gate for ATHBA application-owned Python code."""
from __future__ import annotations

import ast
from pathlib import Path

LIMIT = 100
APPLICATION_ROOTS = (Path("athba"), Path("core"), Path("llm_service"))
ALLOWED_BASES = {"Enum", "Protocol", "str"}
FRAMEWORK_BASES = {
    "ABC",
    "APIView",
    "APIRouter",
    "AppConfig",
    "BaseModel",
    "Enum",
    "Exception",
    "JsonResponse",
    "Protocol",
    "Schema",
    "object",
    "str",
}
DISALLOWED_EXCEPTION_MARKERS = (
    "ATHBA_CODING_PRINCIPLES_EXCEPTION",
    "CODING_PRINCIPLES_EXCEPTION",
)


def application_files() -> list[Path]:
    files: list[Path] = []
    for root in APPLICATION_ROOTS:
        files.extend(sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts))
    return files


def input_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    count = len(node.args.posonlyargs) + len(node.args.args) + len(node.args.kwonlyargs)
    if node.args.args and node.args.args[0].arg in {"self", "cls"}:
        count -= 1
    if node.args.vararg is not None:
        count += 1
    if node.args.kwarg is not None:
        count += 1
    return count


def is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def executable_line_count(node: ast.ClassDef) -> int:
    lines: set[int] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.stmt) and hasattr(child, "lineno"):
            if is_docstring(child):
                continue
            lines.add(child.lineno)
    return len(lines)


def base_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def scan_exception_markers(path: Path, failures: list[str]) -> None:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for marker in DISALLOWED_EXCEPTION_MARKERS:
            if marker in line:
                failures.append(f"{path}:{line_number} contains unapproved exception marker {marker}")


def scan_class(path: Path, node: ast.ClassDef, failures: list[str]) -> None:
    lines = executable_line_count(node)
    if lines > LIMIT:
        failures.append(f"{path}:{node.name} has {lines} executable lines")
    illegal_bases: list[str] = []
    for base in node.bases:
        name = base_name(base)
        if name and name not in ALLOWED_BASES and name not in FRAMEWORK_BASES:
            illegal_bases.append(name)
    if illegal_bases:
        failures.append(f"{path}:{node.name} has forbidden bases {illegal_bases}")
    for method in node.body:
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            count = input_count(method)
            if count > 2:
                failures.append(f"{path}:{node.name}.{method.name} has {count} inputs")


def main() -> int:
    failures: list[str] = []
    for path in application_files():
        source = path.read_text(encoding="utf-8")
        scan_exception_markers(path, failures)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                scan_class(path, node, failures)
    print("\n".join(failures) or "coding principles gate passed")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
