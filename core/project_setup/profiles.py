"""Small controlled setup profiles; architecture text is never a command."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import PurePosixPath
import re

from core.project_setup.profile_domain import (
    ProfileKind, ProfileSelection, ResolvedSetupProfile, SetupFile,
    ToolKind, ToolProbe, ToolSelection,
)

MANAGED_READ_ONLY = "managed_read_only"
NODE_TEST_SMOKE = (
    "--input-type=module", "-e",
    "import test from 'node:test'; import assert from 'node:assert/strict'; "
    "test('setup runtime smoke', () => assert.equal(1, 1));",
)
DOTNET_TEST_HARNESS_LIMITATION = (
    ".NET scaffold build is configured, but no approved test harness/dependencies "
    "were selected; full test-environment verification is unsupported."
)
PINNED_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){2,3}(?:[-+][A-Za-z0-9.-]+)?")
PYTHON_BASENAME = re.compile(r"python(?:3(?:\.[0-9]+)?)?")
TOOL_BASENAMES = {
    ToolKind.RUSTC: {"rustc"}, ToolKind.CARGO: {"cargo"},
    ToolKind.NODE: {"node"}, ToolKind.NPM: {"npm"},
    ToolKind.TYPESCRIPT: {"tsc"}, ToolKind.DOTNET: {"dotnet"},
    ToolKind.HTML_VALIDATOR: {"html-validate"},
    ToolKind.CSS_VALIDATOR: {"stylelint"}, ToolKind.BROWSER: {"playwright"},
}
TECHNOLOGY_ALIASES = {".net": "dotnet", "c#": "csharp", "f#": "fsharp", "vb": "visual_basic"}


@dataclass(frozen=True)
class _Plan:
    tools: tuple[ToolProbe, ...]
    files: tuple[SetupFile, ...]
    build: tuple[str, ...]
    test: tuple[str, ...]
    primary: str
    generated: tuple[str, ...]
    smoke: tuple[tuple[str, ...], ...]
    execute: tuple[str, ...] | None = None
    compatible: bool = False
    limitation: str | None = None


class SetupProfileResolver:
    """Resolve approved choices without provisioning or executing any command."""

    def resolve(self, selection: ProfileSelection) -> ResolvedSetupProfile:
        _validate_selection(selection)
        resolvers = {
            ProfileKind.PYTHON: _python, ProfileKind.RUST: _rust,
            ProfileKind.TYPESCRIPT: _typescript, ProfileKind.DOTNET: _dotnet,
            ProfileKind.JAVASCRIPT: _javascript, ProfileKind.STATIC_WEB: _static_web,
        }
        if selection.name not in resolvers:
            raise ValueError("unsupported setup profile")
        plan = resolvers[selection.name](selection)
        return ResolvedSetupProfile(
            selection.name.value, _technologies(selection), plan.tools, plan.files,
            plan.build, plan.test, plan.execute, plan.smoke, plan.primary,
            plan.generated, plan.compatible, verification_limitation=plan.limitation,
        )


def _technologies(selection: ProfileSelection) -> tuple[str, ...]:
    return tuple(TECHNOLOGY_ALIASES.get(item.strip().lower(), item.strip().lower())
                 for item in selection.technologies)


def _validate_selection(selection: ProfileSelection) -> None:
    if selection.dependency_policy != MANAGED_READ_ONLY:
        raise ValueError("only preapproved managed_read_only dependencies are supported")
    technologies = _technologies(selection)
    if not technologies or any(not item for item in technologies) or len(set(technologies)) != len(technologies):
        raise ValueError("setup technologies must be explicit and unique")
    if not selection.execution_context or not selection.execution_context.strip():
        raise ValueError("setup execution context must be explicit")
    if len({tool.kind for tool in selection.tools}) != len(selection.tools):
        raise ValueError("setup tool selections must be unique")
    for tool in selection.tools:
        path = PurePosixPath(tool.executable)
        if (not path.is_absolute() or ".." in path.parts or str(path) != tool.executable
                or any(char.isspace() for char in tool.executable) or chr(0) in tool.executable):
            raise ValueError("setup tools require normalized absolute executable paths")
        basename = path.name
        if tool.kind in {ToolKind.PYTHON, ToolKind.PYTEST}:
            approved = PYTHON_BASENAME.fullmatch(basename) is not None
        else:
            approved = basename in TOOL_BASENAMES.get(tool.kind, set())
        if not approved:
            raise ValueError("executable is not an approved tool basename: " + tool.kind.value)
        if PINNED_VERSION.fullmatch(tool.version) is None:
            raise ValueError("setup tool version must be an exact approved version")


def _tools(selection: ProfileSelection, required: tuple[ToolKind, ...]) -> dict[ToolKind, ToolSelection]:
    tools = {item.kind: item for item in selection.tools}
    missing = set(required) - tools.keys()
    if missing:
        raise ValueError("missing approved tool selections: " + ", ".join(sorted(item.value for item in missing)))
    if tools.keys() - set(required):
        raise ValueError("profile contains unused tool selections")
    return tools


def _probes(tools: dict[ToolKind, ToolSelection]) -> tuple[ToolProbe, ...]:
    probes = []
    for kind, tool in tools.items():
        argv: tuple[str, ...]
        if kind == ToolKind.PYTEST:
            python = tools[ToolKind.PYTHON]
            if tool.executable != python.executable:
                raise ValueError("pytest selection must identify the approved Python environment")
            argv = (python.executable, "-B", "-c", "import pytest; print(pytest.__version__)")
        elif kind == ToolKind.DOTNET:
            argv = (tool.executable, "--list-sdks")
        else:
            argv = (tool.executable, "--version")
        probes.append(ToolProbe(tool, argv))
    return tuple(probes)


def _json_file(path: str, content: dict[str, object]) -> SetupFile:
    return SetupFile(path, json.dumps(content, indent=2, sort_keys=True) + "\n")


def _require_technologies(selection: ProfileSelection, allowed: set[str]) -> set[str]:
    chosen = set(_technologies(selection))
    if not chosen.issubset(allowed):
        raise ValueError("technology is incompatible with the approved setup profile")
    return chosen


def _python(selection: ProfileSelection) -> _Plan:
    if _require_technologies(selection, {"python"}) != {"python"}:
        raise ValueError("Python profile requires Python")
    if selection.execution_context not in {"library", "server", "console"}:
        raise ValueError("unsupported Python execution context")
    if selection.framework not in {None, "pytest"}:
        raise ValueError("Python profile uses the approved pytest test runtime")
    tools = _tools(selection, (ToolKind.PYTHON, ToolKind.PYTEST))
    python, pytest = tools[ToolKind.PYTHON], tools[ToolKind.PYTEST]
    files = (
        SetupFile("pyproject.toml", '[project]\nname = "application"\nversion = "0.1.0"\n'
                  f'requires-python = "=={python.version}"\n\n'
                  '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'),
        SetupFile("requirements-test.txt", f"pytest=={pytest.version}\n"),
        SetupFile(".gitignore", "__pycache__/\n.pytest_cache/\n.venv/\n"),
    )
    smoke = ((python.executable, "-B", "-c", "import pytest; print(pytest.__version__)"),)
    return _Plan(_probes(tools), files, (python.executable, "-B", "-m", "compileall", "-q", "."),
                 (python.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "."),
                 python.executable, ("__pycache__", ".pytest_cache", ".venv"), smoke, compatible=True)


def _rust(selection: ProfileSelection) -> _Plan:
    if _require_technologies(selection, {"rust"}) != {"rust"}:
        raise ValueError("Rust profile requires Rust")
    if selection.execution_context != "library" or selection.template not in {None, "lib"}:
        raise ValueError("controlled Rust profile is a Cargo library")
    if selection.framework not in {None, "cargo"}:
        raise ValueError("Rust profile uses the approved Cargo test/build configuration")
    tools = _tools(selection, (ToolKind.RUSTC, ToolKind.CARGO))
    cargo = tools[ToolKind.CARGO].executable
    files = (
        SetupFile("Cargo.toml", '[package]\nname = "application"\nversion = "0.1.0"\nedition = "2021"\n'),
        SetupFile("Cargo.lock", 'version = 4\n\n[[package]]\nname = "application"\nversion = "0.1.0"\n'),
        SetupFile("rust-toolchain.toml", f'[toolchain]\nchannel = "{tools[ToolKind.RUSTC].version}"\n'),
        SetupFile("src/lib.rs", "// Approved empty library scaffold.\n"),
        SetupFile(".gitignore", "target/\n"),
    )
    return _Plan(_probes(tools), files, (cargo, "build", "--locked", "--offline"),
                 (cargo, "test", "--locked", "--offline"), cargo, ("target",),
                 ((cargo, "build", "--locked", "--offline"),
                  (cargo, "test", "--locked", "--offline")))


def _web_requirements(selection: ProfileSelection, primary: tuple[ToolKind, ...]) -> tuple[ToolKind, ...]:
    chosen = set(_technologies(selection))
    required = list(primary)
    if "html" in chosen:
        required.append(ToolKind.HTML_VALIDATOR)
    if "css" in chosen:
        required.append(ToolKind.CSS_VALIDATOR)
    if selection.execution_context == "browser":
        required.append(ToolKind.BROWSER)
    return tuple(required)


def _web_files(selection: ProfileSelection) -> tuple[SetupFile, ...]:
    files = []
    chosen = set(_technologies(selection))
    if "html" in chosen:
        files.append(SetupFile("index.html", '<!doctype html>\n<html lang="en"><head>'
            '<meta charset="utf-8"><title>Application</title></head><body></body></html>\n'))
    if "css" in chosen:
        files.append(SetupFile("styles.css", "/* Approved empty application stylesheet. */\n"))
        files.append(_json_file(".stylelintrc.json", {"rules": {}}))
    if "html" in chosen:
        files.append(_json_file(".htmlvalidate.json", {"extends": ["html-validate:recommended"]}))
    return tuple(files)


def _web_smoke(selection: ProfileSelection, tools: dict[ToolKind, ToolSelection]) -> tuple[tuple[str, ...], ...]:
    commands: list[tuple[str, ...]] = []
    if "html" in _technologies(selection):
        commands.append((tools[ToolKind.HTML_VALIDATOR].executable, "index.html"))
    if "css" in _technologies(selection):
        commands.append((tools[ToolKind.CSS_VALIDATOR].executable, "styles.css"))
    if selection.execution_context == "browser":
        commands.append((tools[ToolKind.BROWSER].executable, "screenshot",
                         "--browser", "chromium", "about:blank", "/dev/null"))
    return tuple(commands)


def _node_files(tools: dict[ToolKind, ToolSelection]) -> tuple[SetupFile, ...]:
    return (_json_file("package.json", {
        "name": "application", "version": "0.1.0", "private": True, "type": "module",
        "engines": {"node": tools[ToolKind.NODE].version},
        "packageManager": "npm@" + tools[ToolKind.NPM].version,
    }), SetupFile(".gitignore", "node_modules/\ndist/\nplaywright-report/\ntest-results/\n"))


def _typescript(selection: ProfileSelection) -> _Plan:
    chosen = _require_technologies(selection, {"typescript", "javascript", "html", "css"})
    if "typescript" not in chosen or selection.execution_context not in {"node", "browser"}:
        raise ValueError("TypeScript requires an explicit Node/browser context")
    framework = "playwright" if selection.execution_context == "browser" else "node:test"
    if selection.framework not in {None, framework}:
        raise ValueError("TypeScript test framework conflicts with the controlled profile")
    required = _web_requirements(selection, (ToolKind.NODE, ToolKind.NPM, ToolKind.TYPESCRIPT))
    tools = _tools(selection, required)
    node, compiler = tools[ToolKind.NODE].executable, tools[ToolKind.TYPESCRIPT].executable
    files = (*_node_files(tools), *_web_files(selection),
             _json_file("tsconfig.json", {"compilerOptions": {"target": "ES2022", "module": "NodeNext",
                "moduleResolution": "NodeNext", "strict": True, "outDir": "dist"}, "include": ["src/**/*.ts", "tests/**/*.ts"]}),
             SetupFile("src/index.ts", "export {};\n"))
    test = ((tools[ToolKind.BROWSER].executable, "test") if selection.execution_context == "browser"
            else (node, "--test"))
    return _Plan(_probes(tools), files, (compiler, "--project", "tsconfig.json"), test, node,
                 ("node_modules", "dist", "playwright-report", "test-results"),
                 ((compiler, "--project", "tsconfig.json"), (node, *NODE_TEST_SMOKE),
                  *_web_smoke(selection, tools)))


def _javascript(selection: ProfileSelection) -> _Plan:
    chosen = _require_technologies(selection, {"javascript", "html", "css"})
    if "javascript" not in chosen or selection.execution_context not in {"node", "browser"}:
        raise ValueError("JavaScript execution context must explicitly be node or browser")
    framework = "playwright" if selection.execution_context == "browser" else "node:test"
    if selection.framework not in {None, framework}:
        raise ValueError("JavaScript test framework conflicts with the controlled profile")
    tools = _tools(selection, _web_requirements(selection, (ToolKind.NODE, ToolKind.NPM)))
    node = tools[ToolKind.NODE].executable
    files = (*_node_files(tools), *_web_files(selection), SetupFile("src/index.js", "export {};\n"))
    test = ((tools[ToolKind.BROWSER].executable, "test") if selection.execution_context == "browser"
            else (node, "--test"))
    return _Plan(_probes(tools), files, (node, "--check", "src/index.js"), test, node,
                 ("node_modules", "playwright-report", "test-results"),
                 ((node, "--check", "src/index.js"), (node, *NODE_TEST_SMOKE),
                  *_web_smoke(selection, tools)))


def _static_web(selection: ProfileSelection) -> _Plan:
    chosen = _require_technologies(selection, {"html", "css"})
    if selection.execution_context not in {"browser", "assets"}:
        raise ValueError("static web context must explicitly be browser or assets")
    if selection.framework not in {None, "playwright" if selection.execution_context == "browser" else "validators"}:
        raise ValueError("static-web framework conflicts with the controlled profile")
    tools = _tools(selection, _web_requirements(selection, ()))
    smoke = _web_smoke(selection, tools)
    if not chosen or not smoke:
        raise ValueError("static web requires selected HTML/CSS validation")
    test = ((tools[ToolKind.BROWSER].executable, "test") if selection.execution_context == "browser" else smoke[0])
    primary = tools[ToolKind.BROWSER].executable if selection.execution_context == "browser" else smoke[0][0]
    return _Plan(_probes(tools), _web_files(selection), smoke[0], test, primary,
                 ("playwright-report", "test-results"), smoke)


def _dotnet(selection: ProfileSelection) -> _Plan:
    _require_technologies(selection, {"dotnet", "csharp", "fsharp", "visual_basic"})
    if "dotnet" not in _technologies(selection):
        raise ValueError(".NET profile requires the .NET technology")
    choices = {"csharp": ("csproj", "cs"), "fsharp": ("fsproj", "fs"), "visual_basic": ("vbproj", "vb")}
    if selection.project_language not in choices or selection.template not in {"classlib", "console"}:
        raise ValueError(".NET requires an explicit supported language and template")
    if selection.framework is None or re.fullmatch(r"net[0-9]+\.[0-9]+", selection.framework) is None:
        raise ValueError(".NET requires an explicit target framework")
    if selection.execution_context != ("library" if selection.template == "classlib" else "console"):
        raise ValueError(".NET execution context conflicts with its approved template")
    declared_languages = set(_technologies(selection)) & set(choices)
    if declared_languages and declared_languages != {selection.project_language}:
        raise ValueError(".NET source technologies conflict with its explicit project language")
    tools = _tools(selection, (ToolKind.DOTNET,))
    dotnet = tools[ToolKind.DOTNET].executable
    project_extension, source_extension = choices[str(selection.project_language)]
    project = "Application." + project_extension
    output = "<OutputType>Exe</OutputType>" if selection.template == "console" else ""
    compile_item = '<ItemGroup><Compile Include="Application.fs" /></ItemGroup>' if selection.project_language == "fsharp" else ""
    source = _dotnet_source(selection)
    files = (
        _json_file("global.json", {"sdk": {"version": tools[ToolKind.DOTNET].version, "rollForward": "disable"}}),
        SetupFile(project, '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
                  f'<TargetFramework>{selection.framework}</TargetFramework>{output}'
                  '</PropertyGroup>' + compile_item + '</Project>\n'),
        SetupFile("Application." + source_extension, source),
        SetupFile("NuGet.Config", '<configuration><packageSources><clear /></packageSources></configuration>\n'),
        SetupFile(".gitignore", "bin/\nobj/\n"),
    )
    # A fresh project needs its local assets file. Cleared NuGet sources forbid downloads.
    return _Plan(_probes(tools), files, (dotnet, "build", project),
                 (dotnet, "test", project, "--no-restore"), dotnet, ("bin", "obj"),
                 ((dotnet, "build", project),),
                 (dotnet, "run", "--project", project, "--no-restore") if selection.template == "console" else None,
                 limitation=DOTNET_TEST_HARNESS_LIMITATION)


def _dotnet_source(selection: ProfileSelection) -> str:
    if selection.template == "classlib":
        return "namespace Application\n" if selection.project_language == "fsharp" else ""
    return {
        "csharp": "return;\n",
        "fsharp": "[<EntryPoint>]\nlet main _ = 0\n",
        "visual_basic": "Module Application\n    Sub Main()\n    End Sub\nEnd Module\n",
    }[str(selection.project_language)]
