"""Typed, approved application-toolchain selections and controlled setup plans."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ToolKind(str, Enum):
    PYTHON = "python"
    PYTEST = "pytest"
    RUSTC = "rustc"
    CARGO = "cargo"
    NODE = "node"
    NPM = "npm"
    TYPESCRIPT = "typescript"
    DOTNET = "dotnet"
    HTML_VALIDATOR = "html_validator"
    CSS_VALIDATOR = "css_validator"
    BROWSER = "browser"


class ProfileKind(str, Enum):
    PYTHON = "python"
    RUST = "rust"
    TYPESCRIPT = "typescript"
    DOTNET = "dotnet"
    JAVASCRIPT = "javascript"
    STATIC_WEB = "static_web"


@dataclass(frozen=True)
class ToolSelection:
    kind: ToolKind
    executable: str
    version: str


@dataclass(frozen=True)
class ProfileSelection:
    name: ProfileKind
    technologies: tuple[str, ...]
    tools: tuple[ToolSelection, ...]
    execution_context: str
    dependency_policy: str = "managed_read_only"
    framework: str | None = None
    project_language: str | None = None
    template: str | None = None


@dataclass(frozen=True)
class SetupFile:
    path: str
    content: str


@dataclass(frozen=True)
class ToolProbe:
    tool: ToolSelection
    argv: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedSetupProfile:
    id: str
    technologies: tuple[str, ...]
    tools: tuple[ToolProbe, ...]
    files: tuple[SetupFile, ...]
    build_command: tuple[str, ...]
    test_command: tuple[str, ...]
    execution_command: tuple[str, ...] | None
    smoke_commands: tuple[tuple[str, ...], ...]
    primary_runtime_path: str
    generated_paths: tuple[str, ...]
    bde_language_compatible: bool
    verification_limitation: str | None = None
