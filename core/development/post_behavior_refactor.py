"""Public Python surface and exact out-of-slice source protection."""
from __future__ import annotations

import ast
from dataclasses import dataclass

from core.development.post_behavior_slice import FocusedProductionSlice, end_line, node_key, start_line
from core.development.specification_evidence_policy import RevisionFile

PUBLIC_INTERFACE_METADATA = frozenset({"__all__", "__slots__"})


@dataclass(frozen=True)
class PublicIdentifier:
    owner: tuple[str, ...]
    name: str
    signature: str


def public_surface(source: str) -> tuple[PublicIdentifier, ...]:
    return _public_body(ast.parse(source).body, ())


def _public_body(body: list[ast.stmt], owner: tuple[str, ...]) -> tuple[PublicIdentifier, ...]:
    result = []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_") or node.name.startswith("__") and node.name.endswith("__"):
                signature = repr((type(node).__name__, ast.dump(node.args),
                                  ast.dump(node.returns) if node.returns else None,
                                  tuple(ast.dump(item) for item in node.decorator_list),
                                  tuple(ast.dump(item) for item in getattr(node, "type_params", ()))))
                result.append(PublicIdentifier(owner, node.name, signature))
            if owner:
                fields = {item.attr for item in ast.walk(node) if isinstance(item, ast.Attribute)
                          and isinstance(item.ctx, ast.Store) and isinstance(item.value, ast.Name)
                          and item.value.id in {"self", "cls"} and not item.attr.startswith("_")}
                result.extend(PublicIdentifier(owner, name, "attribute") for name in sorted(fields))
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                signature = repr((tuple(ast.dump(item) for item in node.bases),
                                  tuple(ast.dump(item) for item in node.keywords),
                                  tuple(ast.dump(item) for item in node.decorator_list)))
                result.append(PublicIdentifier(owner, node.name, signature))
                result.extend(_public_body(node.body, (*owner, node.name)))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    if target.id in PUBLIC_INTERFACE_METADATA:
                        result.append(PublicIdentifier(owner, target.id, ast.dump(node)))
                    elif not target.id.startswith("_"):
                        field_signature = ("field", ast.dump(node.annotation), node.simple) if isinstance(node, ast.AnnAssign) else ("field",)
                        result.append(PublicIdentifier(owner, target.id, repr(field_signature)))
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            if node.target.id in PUBLIC_INTERFACE_METADATA:
                result.append(PublicIdentifier(owner, node.target.id, ast.dump(node)))
    return tuple(sorted(set(result), key=repr))


@dataclass(frozen=True)
class RefactorSourcePair:
    before: RevisionFile
    after: RevisionFile
    production: FocusedProductionSlice


@dataclass(frozen=True)
class PrivateSourceSlot:
    prefix: tuple[str, ...]
    position: int
    identity: tuple[str, ...]


@dataclass(frozen=True)
class SourceProtection:
    selected: frozenset[tuple[str, ...]]
    original: frozenset[tuple[str, ...]]
    private_slots: tuple[PrivateSourceSlot, ...]


def frozen_sources_match(request: RefactorSourcePair) -> bool:
    selected = frozenset(region.identity for region in request.production.regions
                         if region.path == request.before.path)
    original = frozenset(_identities(ast.parse(request.before.source).body, ()))
    slots = _private_slots(ast.parse(request.before.source).body, ())
    protection = SourceProtection(selected, original, tuple(slot for slot in slots if slot.identity in selected))
    return _frozen(request.before.source, protection) == _frozen(request.after.source, protection)


def _identities(body: list[ast.stmt], prefix: tuple[str, ...]) -> list[tuple[str, ...]]:
    result = []
    for index, node in enumerate(body):
        identity = (*prefix, node_key(node, index))
        result.append(identity)
        if isinstance(node, ast.ClassDef):
            result.extend(_identities(node.body, identity))
    return result


def _private_slots(body: list[ast.stmt], prefix: tuple[str, ...]) -> list[PrivateSourceSlot]:
    result = []
    for index, node in enumerate(body):
        identity = (*prefix, node_key(node, index))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("_"):
            result.append(PrivateSourceSlot(prefix, index, identity))
        if isinstance(node, ast.ClassDef):
            result.extend(_private_slots(node.body, identity))
    return result


def _frozen(source: str, protection: SourceProtection) -> str:
    ranges = _editable_ranges(ast.parse(source).body, ((), protection))
    lines = source.splitlines(keepends=True)
    for start, end, marker in sorted(ranges, reverse=True):
        lines[start - 1:end] = [marker]
    return "".join(lines)


def _editable_ranges(body: list[ast.stmt],
                     context: tuple[tuple[str, ...], SourceProtection]) -> list[tuple[int, int, str]]:
    prefix, protection = context
    result, cluster = [], []
    present = {(*prefix, node_key(node, index)) for index, node in enumerate(body)}
    for index, node in enumerate(body):
        identity = (*prefix, node_key(node, index))
        selected = identity in protection.selected
        helper = (identity not in protection.original and
                  isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("_"))
        if helper:
            prior = next((slot for slot in protection.private_slots if slot.prefix == prefix
                          and slot.position == index and slot.identity not in present), None)
            if prior is not None:
                identity, selected = prior.identity, True
        if selected or helper:
            cluster.append((node, identity, selected))
            continue
        result.extend(_cluster_ranges(cluster))
        cluster = []
        if isinstance(node, ast.ClassDef):
            result.extend(_editable_ranges(node.body, (identity, protection)))
    result.extend(_cluster_ranges(cluster))
    return result


def _cluster_ranges(cluster: list[tuple[ast.stmt, tuple[str, ...], bool]]) -> list[tuple[int, int, str]]:
    if not cluster or not any(selected for _, _, selected in cluster):
        return []
    marker = "".join(f"<focused:{identity!r}>\n" for _, identity, selected in cluster if selected)
    return [(start_line(cluster[0][0]), end_line(cluster[-1][0]), marker)]
