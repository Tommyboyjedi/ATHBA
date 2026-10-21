"""Byte spans for ordinary Python statements, without source re-emission."""
from __future__ import annotations
import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class StatementSpan:
    start: int
    end: int
    indent: bytes
    newline: bytes


@dataclass(frozen=True)
class PythonReductionBuffer:
    source: bytes

    def parse(self) -> ast.Module:
        if self.source.startswith(b"\xef\xbb\xbf"):
            raise ValueError("UTF-8 BOM source is unsupported by this bounded reducer")
        self.source.decode("utf-8")
        return ast.parse(self.source)

    def span(self, node: ast.stmt) -> StatementSpan:
        lines = self.source.splitlines(keepends=True)
        decorators = getattr(node, "decorator_list", ())
        start_line = min((node.lineno, *(item.lineno for item in decorators)))
        offsets = [0]
        for line in lines:
            offsets.append(offsets[-1] + len(line))
        first = lines[start_line - 1]
        indent = first[:len(first) - len(first.lstrip(b" \t"))]
        prefix = lines[node.lineno - 1][:node.col_offset]
        if prefix.strip():
            raise ValueError("inline or packed statement has no isolated byte span")
        finish_line = node.end_lineno or node.lineno
        last = lines[finish_line - 1]
        suffix = last[node.end_col_offset or 0:].strip()
        if suffix and not suffix.startswith(b"#"):
            raise ValueError("packed statement has no isolated byte span")
        newline = b"\r\n" if last.endswith(b"\r\n") else b"\n" if last.endswith(b"\n") else b""
        return StatementSpan(offsets[start_line - 1], offsets[finish_line], indent, newline)

    def fragment(self, node: ast.stmt) -> bytes:
        span = self.span(node)
        return self.source[span.start:span.end]

    def splice(self, span: StatementSpan, replacement: bytes) -> bytes:
        return self.source[:span.start] + replacement + self.source[span.end:]


def statement_key(node: ast.stmt) -> str:
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"{type(node).__name__}:{node.name}"
    if isinstance(node, ast.Assign):
        return "Assign:" + repr(tuple(ast.dump(target) for target in node.targets))
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        return type(node).__name__ + ":" + ast.dump(node.target)
    return type(node).__name__ + ":" + ast.dump(node, include_attributes=False)


def named_declaration(node: ast.stmt) -> bool:
    return isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))


def child_suites(node: ast.AST) -> tuple[tuple[str, list[ast.stmt]], ...]:
    result = []
    for field, value in ast.iter_fields(node):
        if isinstance(value, list) and value and all(isinstance(item, ast.stmt) for item in value):
            result.append((field, value))
    return tuple(result)
