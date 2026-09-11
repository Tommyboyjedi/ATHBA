"""Only focused affected syntax crosses the bounded identifier-change boundary."""
from __future__ import annotations

import ast
from copy import copy
from dataclasses import dataclass

from core.development.post_behavior_rename import PythonRenameReferences, RenameTarget
from core.development.post_behavior_slice import end_line, start_line
from core.development.specification_evidence_policy import RevisionFile


@dataclass(frozen=True)
class RenameReferenceContext:
    target: RenameTarget
    files: tuple[RevisionFile, ...]


def affected_reference_sources(request: RenameReferenceContext) -> tuple[RevisionFile, ...]:
    result = []
    for file in request.files:
        references = {row for row, _column in PythonRenameReferences(request.target, file).positions()}
        rows = frozenset(references)
        if rows:
            body = ast.parse(file.source).body
            selected = _include_dependencies(body, _selected_nodes(body, rows))
            source = "\n\n".join(_render_node(file.source, node, rows) for node in selected) + "\n"
            result.append(RevisionFile(file.path, source))
    return tuple(result)


def _selected_nodes(body: list[ast.stmt], rows: frozenset[int]) -> list[ast.stmt]:
    selected: list[ast.stmt] = []
    for node in body:
        if not any(start_line(node) <= row <= end_line(node) for row in rows):
            continue
        if isinstance(node, ast.ClassDef) and not any(start_line(node) <= row < start_line(node.body[0]) for row in rows):
            focused = copy(node)
            focused.body = _include_dependencies(node.body, _selected_nodes(node.body, rows))
            setattr(focused, "_original_body_start", start_line(node.body[0]))
            selected.append(focused)
        else:
            selected.append(node)
    return selected


def _include_dependencies(body: list[ast.stmt], selected: list[ast.stmt]) -> list[ast.stmt]:
    result = list(selected)
    while True:
        needed = {node.id for item in result for node in ast.walk(item)
                  if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
        additions = [node for node in body if node not in result and _bound_names(node) & needed]
        if not additions:
            return sorted(result, key=start_line)
        result.extend(additions)


def _bound_names(node: ast.stmt) -> set[str]:
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {alias.asname or alias.name.split(".")[0] for alias in node.names}
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return {item.id for target in targets for item in ast.walk(target) if isinstance(item, ast.Name)}
    return set()


def _render_node(source: str, node: ast.stmt, rows: frozenset[int]) -> str:
    lines = source.splitlines(keepends=True)
    if isinstance(node, ast.ClassDef) and not any(start_line(node) <= row < start_line(node.body[0]) for row in rows):
        body_start = getattr(node, "_original_body_start", start_line(node.body[0]))
        header = "".join(lines[start_line(node) - 1:body_start - 1]).rstrip()
        return header + "\n" + "\n\n".join(_render_node(source, item, rows) for item in node.body)
    return "".join(lines[start_line(node) - 1:end_line(node)]).rstrip()
