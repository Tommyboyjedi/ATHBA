"""Deterministic private product-surface policy derived from Behavior Contracts."""
from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.development.behavior_contract_domain import BehaviorContract
from core.development.microcycle_domain import SourceSpan


_MEMBER = re.compile(r"^(?:(?P<owner>[A-Za-z_][A-Za-z0-9_]*)\.)?(?P<member>[A-Za-z_][A-Za-z0-9_]*)(?:\([^\n]*\))?$")


@dataclass(frozen=True)
class DeclaredProductSurface:
    """Machine-usable contract declarations; no Gatekeeper state is accepted."""

    component_name: str
    members: frozenset[str]
    unsupported_public_api_entries: tuple[str, ...] = ()
    canonical_members: tuple[str, ...] = ()

    @classmethod
    def compile(cls, contract: BehaviorContract) -> "DeclaredProductSurface":
        members: set[str] = set()
        canonical_members: list[str] = []
        unsupported: list[str] = []
        for entry in contract.public_api:
            match = _MEMBER.fullmatch(entry.strip())
            if match is None:
                unsupported.append(entry)
                continue
            owner, member = match.group("owner"), match.group("member")
            if owner is not None and owner != contract.component_name:
                unsupported.append(entry)
            elif owner is None and member == contract.component_name:
                continue
            else:
                members.add(member)
                canonical_members.append(entry.strip())
        return cls(
            contract.component_name,
            frozenset(members),
            tuple(unsupported),
            tuple(canonical_members),
        )

    @property
    def machine_usable(self) -> bool:
        return bool(self.component_name and self.members)

    def allows(self, member: str) -> bool:
        return member in self.members

    def allows_canonical(self, member: str) -> bool:
        return member in self.canonical_members


@dataclass(frozen=True)
class ProductSurfaceViolation:
    member: str
    detail: str
    span: SourceSpan
    usage_role: str = "unknown"


def lint_test_candidate_violations(source: str, surface: DeclaredProductSurface, production_path: str) -> tuple[ProductSurfaceViolation, ...]:
    module = ast.parse(source)
    aliases = _production_class_aliases(module, surface.component_name, production_path)
    instances = _production_instances(module, aliases, surface.component_name)
    violations: list[ProductSurfaceViolation] = []
    parents = _parents(module)
    for node in ast.walk(module):
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name) or node.value.id not in instances:
            continue
        span = SourceSpan(node.lineno, node.end_lineno or node.lineno)
        if node.attr.startswith("_"):
            detail = f"Candidate directly references private product member `{node.attr}` at line {node.lineno}. Product interactions must remain inside the declared product contract."
        elif not surface.machine_usable:
            detail = f"Candidate references product member `{node.attr}` at line {node.lineno}, but the Behavior Contract has no machine-usable product surface. Repair the candidate without introducing undeclared product surface."
        elif not surface.allows(node.attr):
            detail = f"Candidate references undeclared product member `{node.attr}` at line {node.lineno}. Product interactions must remain inside the declared product contract. Repair the candidate without introducing undeclared product surface."
        else:
            continue
        violations.append(
            ProductSurfaceViolation(node.attr, detail, span, _usage_role(node, parents))
        )
    return _unique(violations)


def production_candidate_violations(source: str, surface: DeclaredProductSurface) -> tuple[ProductSurfaceViolation, ...]:
    module = ast.parse(source)
    classes = [item for item in module.body if isinstance(item, ast.ClassDef) and item.name == surface.component_name]
    violations: list[ProductSurfaceViolation] = []
    for class_node in classes:
        for node in class_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _append_production_violation(violations, node.name, node, surface)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                for name in _assigned_names(node):
                    _append_production_violation(violations, name, node, surface)
        for descendant in ast.walk(class_node):
            if isinstance(descendant, ast.Assign):
                for target in descendant.targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                        _append_production_violation(violations, target.attr, descendant, surface)
    return _unique(violations)


def production_candidate_source(repository_root: Path, revision: str, production_path: str) -> str:
    result = subprocess.run(["git", "show", f"{revision}:{production_path}"], cwd=repository_root, text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"production candidate source is unavailable: {(result.stderr or result.stdout).strip()}")
    return result.stdout


def _production_class_aliases(module: ast.Module, component_name: str, production_path: str) -> set[str]:
    production_module = Path(production_path).with_suffix("").as_posix().replace("/", ".")
    aliases: set[str] = set()
    for node in module.body:
        if isinstance(node, ast.ImportFrom) and node.module == production_module:
            aliases.update(item.asname or item.name for item in node.names if item.name == component_name)
        elif isinstance(node, ast.Import):
            aliases.update(item.asname or item.name.split(".")[0] for item in node.names if item.name == production_module)
    return aliases


def _production_instances(module: ast.Module, aliases: set[str], component_name: str) -> set[str]:
    instances: set[str] = set()
    for node in ast.walk(module):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value, targets = node.value, _assigned_names(node)
        if isinstance(value, ast.Call) and _is_constructor(value.func, aliases, component_name):
            instances.update(targets)
        elif isinstance(value, ast.Name) and value.id in instances:
            instances.update(targets)
    return instances


def _is_constructor(node: ast.expr, aliases: set[str], component_name: str) -> bool:
    if isinstance(node, ast.Name):
        return node.id in aliases
    return isinstance(node, ast.Attribute) and node.attr == component_name and isinstance(node.value, ast.Name) and node.value.id in aliases

def _assigned_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
    targets: tuple[ast.expr, ...] = tuple(node.targets) if isinstance(node, ast.Assign) else (node.target,)
    return tuple(target.id for target in targets if isinstance(target, ast.Name))


def _append_production_violation(violations: list[ProductSurfaceViolation], name: str, node: ast.AST, surface: DeclaredProductSurface) -> None:
    if name.startswith("_") or name in surface.members:
        return
    line = getattr(node, "lineno", 0)
    end_line = getattr(node, "end_lineno", line) or line
    violations.append(ProductSurfaceViolation(name, f"Production candidate defines undeclared public product member `{name}` at line {line}.", SourceSpan(line, end_line)))

def _unique(violations: list[ProductSurfaceViolation]) -> tuple[ProductSurfaceViolation, ...]:
    values: dict[tuple[str, int], ProductSurfaceViolation] = {}
    for item in violations:
        values[(item.member, item.span.start_line)] = item
    return tuple(values.values())

def _parents(module: ast.Module) -> dict[int, ast.AST]:
    return {
        id(child): parent
        for parent in ast.walk(module)
        for child in ast.iter_child_nodes(parent)
    }


def _usage_role(node: ast.Attribute, parents: dict[int, ast.AST]) -> str:
    """Classify only direct strict-grammar contexts; ambiguous flow stays unknown."""
    current: ast.AST = node
    while (parent := parents.get(id(current))) is not None:
        if isinstance(parent, ast.Assert):
            return "observation"
        if isinstance(parent, ast.Expr):
            return "action"
        if isinstance(parent, (ast.Assign, ast.AnnAssign)):
            return "unknown"
        if isinstance(parent, ast.FunctionDef):
            break
        current = parent
    return "unknown"
