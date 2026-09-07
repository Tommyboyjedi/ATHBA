"""Python runtime import and packaging declarations, inspected without execution."""
from __future__ import annotations

import ast
import configparser
import sys
import tomllib
from pathlib import PurePosixPath

from core.development.specification_evidence_policy import SpecificationSnapshot
from core.development.specification_revision_snapshot import production_python

DYNAMIC_IMPORT_NAMES = frozenset({"__import__", "eval", "exec", "compile", "import_module", "__builtins__", "getattr", "setattr", "globals", "locals", "vars", "__dict__"})


def dependency_findings(snapshot: SpecificationSnapshot) -> tuple[tuple[str, ...], tuple[str, ...]]:
    external: list[str] = []
    unsupported: list[str] = []
    local: set[str] = set()
    for file in snapshot.files:
        if not production_python(file):
            continue
        parts = PurePosixPath(file.path).parts
        if parts[0] == "src":
            parts = parts[1:]
        if len(parts) == 1:
            local.add(PurePosixPath(parts[0]).stem)
        elif parts[-1] == "__init__.py":
            local.add(parts[0])
    for file in snapshot.files:
        if production_python(file):
            for node in ast.walk(ast.parse(file.source)):
                roots = import_roots(node)
                external.extend(f"{file.path}:{getattr(node, "lineno", 0)}: external import {root}" for root in roots
                                if root not in sys.stdlib_module_names and root not in local)
                if dynamic_reference(node):
                    unsupported.append(f"{file.path}:{getattr(node, "lineno", 0)}: dynamic code/import reference")
        declared, unknown = metadata_dependencies(file.path, file.source)
        external.extend(declared)
        unsupported.extend(unknown)
    return tuple(external), tuple(unsupported)


def import_roots(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name.split(".")[0] for alias in node.names)
    if isinstance(node, ast.ImportFrom) and not node.level:
        return ((node.module or "").split(".")[0],)
    return ()


OPAQUE_IMPORT_MODULES = frozenset({"importlib", "runpy", "pkgutil", "builtins", "sys", "ctypes", "subprocess", "os", "pickle", "marshal"})


def dynamic_reference(node: ast.AST) -> bool:
    return (isinstance(node, ast.Name) and node.id in DYNAMIC_IMPORT_NAMES) or (
        isinstance(node, ast.Attribute) and node.attr in DYNAMIC_IMPORT_NAMES
    ) or bool(OPAQUE_IMPORT_MODULES.intersection(import_roots(node)))


def metadata_dependencies(path: str, source: str) -> tuple[list[str], list[str]]:
    name = PurePosixPath(path).name
    declared: list[str] = []
    unknown: list[str] = []
    try:
        if name == "pyproject.toml":
            data = tomllib.loads(source)
            project = data.get("project", {})
            declared.extend(project.get("dependencies", []))
            for group in project.get("optional-dependencies", {}).values():
                declared.extend(group)
            if "dependencies" in project.get("dynamic", []) or "optional-dependencies" in project.get("dynamic", []):
                unknown.append(f"{path}: dynamic dependency metadata")
            poetry = data.get("tool", {}).get("poetry", {})
            declared.extend(key for key in poetry.get("dependencies", {}) if key != "python")
        elif name.startswith("requirements") and name.endswith(".txt"):
            for line in source.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    if line.startswith("-"):
                        unknown.append(f"{path}: indirect/option dependency declaration {line}")
                    else:
                        declared.append(line)
        elif name == "setup.cfg":
            config = configparser.ConfigParser(interpolation=None)
            config.read_string(source)
            declared.extend(config.get("options", "install_requires", fallback="").split())
            if config.has_section("options.extras_require"):
                for value in config["options.extras_require"].values():
                    declared.extend(value.split())
        elif name == "setup.py":
            unknown.append(f"{path}: executable dependency metadata is unsupported")
        elif name in {"Pipfile", "Pipfile.lock", "environment.yml", "environment.yaml", "package.json", "Cargo.toml"}:
            unknown.append(f"{path}: unsupported dependency declaration format")
    except (ValueError, TypeError, AttributeError, configparser.Error):
        unknown.append(f"{path}: invalid dependency metadata")
    return [f"{path}: declared external dependency {value}" for value in declared], unknown
