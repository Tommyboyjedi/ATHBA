"""Controlled setup-plan contracts; no builds, installations or model calls."""
from dataclasses import replace
import json
from pathlib import PurePosixPath

import pytest

from core.project_setup.profile_domain import (
    ProfileKind, ProfileSelection, ToolKind, ToolSelection,
)
from core.project_setup.profiles import SetupProfileResolver


def tool(kind, executable, version):
    return ToolSelection(kind, "/approved/" + executable, version)


PYTHON = (
    tool(ToolKind.PYTHON, "python3.14", "3.14.4"),
    tool(ToolKind.PYTEST, "python3.14", "8.4.2"),
)
NODE = (tool(ToolKind.NODE, "node", "22.14.0"), tool(ToolKind.NPM, "npm", "10.9.2"))
TYPESCRIPT = tool(ToolKind.TYPESCRIPT, "tsc", "5.8.2")
HTML = tool(ToolKind.HTML_VALIDATOR, "html-validate", "9.5.0")
CSS = tool(ToolKind.CSS_VALIDATOR, "stylelint", "16.16.0")
BROWSER = tool(ToolKind.BROWSER, "playwright", "1.51.0")
PYTHON_SELECTION = ProfileSelection(ProfileKind.PYTHON, ("python",), PYTHON, "library", framework="pytest")
DOTNET_SELECTION = ProfileSelection(
    ProfileKind.DOTNET, (".NET", "C#"), (tool(ToolKind.DOTNET, "dotnet", "10.0.100"),),
    "library", framework="net10.0", project_language="csharp", template="classlib",
)


@pytest.mark.parametrize("selection,expected_technologies", [
    pytest.param(PYTHON_SELECTION, ("python",), id="python-managed"),
    pytest.param(ProfileSelection(ProfileKind.RUST, ("rust",), (
        tool(ToolKind.RUSTC, "rustc", "1.98.0"), tool(ToolKind.CARGO, "cargo", "1.98.0"),
    ), "library", framework="cargo"), ("rust",), id="rust-cargo"),
    pytest.param(ProfileSelection(ProfileKind.TYPESCRIPT, ("typescript",),
        (*NODE, TYPESCRIPT), "node", framework="node:test"),
        ("typescript",), id="typescript-node"),
    pytest.param(DOTNET_SELECTION, ("dotnet", "csharp"), id="dotnet-explicit-csharp"),
    pytest.param(ProfileSelection(ProfileKind.JAVASCRIPT, ("javascript",),
        NODE, "node", framework="node:test"), ("javascript",), id="javascript-node"),
    pytest.param(ProfileSelection(ProfileKind.STATIC_WEB, ("html", "css"),
        (HTML, CSS), "assets", framework="validators"), ("html", "css"), id="html-css-assets"),
    pytest.param(ProfileSelection(ProfileKind.TYPESCRIPT, ("typescript", "html", "css"),
        (*NODE, TYPESCRIPT, HTML, CSS, BROWSER), "browser", framework="playwright"),
        ("typescript", "html", "css"), id="combined-typescript-html-css"),
])
def test_profiles_are_controlled_plans_without_execution(selection, expected_technologies, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("profile resolution must not execute a tool or installer")

    monkeypatch.setattr("subprocess.run", forbidden)
    profile = SetupProfileResolver().resolve(selection)

    assert profile.id == selection.name.value
    assert profile.technologies == expected_technologies
    assert profile.bde_language_compatible is (selection.name == ProfileKind.PYTHON)
    approved = {item.executable for item in selection.tools}
    assert profile.primary_runtime_path in approved
    commands = [profile.build_command, profile.test_command,
                *profile.smoke_commands, *(probe.argv for probe in profile.tools)]
    if profile.execution_command:
        commands.append(profile.execution_command)
    assert all(isinstance(command, tuple) and command and command[0] in approved for command in commands)
    assert all("install" not in command and "ci" not in command for command in commands)
    assert all(command[0] not in {"bash", "sh", "sudo", "npx"} for command in commands)
    assert profile.files
    for scaffold in profile.files:
        path = PurePosixPath(scaffold.path)
        assert not path.is_absolute() and ".." not in path.parts
        assert "ATHBA initial production module" not in scaffold.content
    if selection.name != ProfileKind.PYTHON:
        assert not any(item.path.endswith(".py") for item in profile.files)
        assert not any("pytest" in argument for command in commands for argument in command)
    if "html" in expected_technologies:
        assert any(item.path == "index.html" for item in profile.files)
    if "css" in expected_technologies:
        assert any(item.path == "styles.css" for item in profile.files)
    if selection.name == ProfileKind.RUST:
        assert profile.build_command in profile.smoke_commands
        assert profile.test_command in profile.smoke_commands
        assert "--offline" in profile.build_command and "--locked" in profile.test_command
    if selection.name == ProfileKind.TYPESCRIPT:
        assert profile.build_command[0] == TYPESCRIPT.executable
        assert "tsconfig.json" in profile.build_command
        assert profile.build_command in profile.smoke_commands
    if selection.name in {ProfileKind.TYPESCRIPT, ProfileKind.JAVASCRIPT}:
        assert any("node:test" in argument for command in profile.smoke_commands for argument in command)
    if selection.execution_context == "browser":
        assert any(command[1:] == ("screenshot", "--browser", "chromium", "about:blank", "/dev/null")
                   for command in profile.smoke_commands)
    if selection.name != ProfileKind.DOTNET:
        assert profile.verification_limitation is None
    if selection.name == ProfileKind.PYTHON:
        pytest_probe = next(probe for probe in profile.tools if probe.tool.kind == ToolKind.PYTEST)
        assert pytest_probe.argv[0] == PYTHON[0].executable
        assert pytest_probe.argv[-1] == "import pytest; print(pytest.__version__)"
        assert all("-m" not in command for command in profile.smoke_commands)


def test_dotnet_requires_approved_sdk_framework_language_and_template():
    resolver = SetupProfileResolver()
    for omitted in ("framework", "project_language", "template"):
        with pytest.raises(ValueError, match=r"\.NET"):
            resolver.resolve(replace(DOTNET_SELECTION, **{omitted: None}))
    with pytest.raises(ValueError, match="conflict"):
        resolver.resolve(replace(DOTNET_SELECTION, project_language="fsharp"))
    fsharp = resolver.resolve(replace(
        DOTNET_SELECTION, technologies=("dotnet", "fsharp"), project_language="fsharp",
    ))
    files = {item.path: item.content for item in fsharp.files}
    assert "Application.fsproj" in files and "Application.fs" in files
    assert "Application.csproj" not in files
    assert "<TargetFramework>net10.0</TargetFramework>" in files["Application.fsproj"]
    assert json.loads(files["global.json"])["sdk"] == {"version": "10.0.100", "rollForward": "disable"}
    assert "<clear />" in files["NuGet.Config"]
    assert fsharp.build_command == ("/approved/dotnet", "build", "Application.fsproj")
    assert not fsharp.bde_language_compatible
    assert fsharp.build_command in fsharp.smoke_commands
    assert "approved test harness" in fsharp.verification_limitation


def test_missing_or_conflicting_choices_never_fall_back_to_python():
    resolver = SetupProfileResolver()
    invalid = (
        replace(PYTHON_SELECTION, tools=PYTHON[:1]),
        ProfileSelection(ProfileKind.JAVASCRIPT, ("javascript",), NODE, ""),
        ProfileSelection(ProfileKind.JAVASCRIPT, ("javascript",), NODE, "guessed"),
        ProfileSelection(ProfileKind.TYPESCRIPT, ("python",), (*NODE, TYPESCRIPT), "node"),
        ProfileSelection(ProfileKind.TYPESCRIPT, ("typescript",), (*NODE, TYPESCRIPT),
                         "node", framework="unapproved-runner"),
    )
    for selection in invalid:
        with pytest.raises(ValueError):
            resolver.resolve(selection)


def test_read_only_pins_and_executable_allowlist_are_enforced():
    resolver = SetupProfileResolver()
    with pytest.raises(ValueError, match="managed_read_only"):
        resolver.resolve(replace(PYTHON_SELECTION, dependency_policy="install_latest"))
    unsafe_tools = (
        replace(PYTHON[0], executable="python3.14"),
        replace(PYTHON[0], executable="/approved/../python3.14"),
        replace(PYTHON[0], executable="/approved/bash"),
        replace(PYTHON[0], executable="/approved/python3.14;touch"),
        replace(PYTHON[0], version="latest"),
        replace(PYTHON[0], version="^3.14.4"),
        replace(PYTHON[0], version="3.14"),
    )
    for unsafe in unsafe_tools:
        with pytest.raises(ValueError):
            resolver.resolve(replace(PYTHON_SELECTION, tools=(unsafe, PYTHON[1])))


def test_exact_probe_does_not_confuse_prerelease_or_other_installed_sdk(tmp_path, monkeypatch):
    from core.project_setup.commands import CommandResult, SetupCommandRunner
    from core.project_setup.profile_domain import ToolProbe
    runner = SetupCommandRunner()
    monkeypatch.setattr(runner, "run", lambda request: CommandResult(
        request.argv, 0, "Python 3.14.4rc1", ""))
    python = ToolSelection(ToolKind.PYTHON, "/managed/python", "3.14.4")
    assert not runner.inspect((ToolProbe(python, (python.executable, "--version")), tmp_path)).available
    monkeypatch.setattr(runner, "run", lambda request: CommandResult(
        request.argv, 0, "8.0.100 [/managed/sdk]\n9.0.100 [/managed/sdk]\n", ""))
    sdk = ToolSelection(ToolKind.DOTNET, "/managed/dotnet", "9.0.100")
    observed = runner.inspect((ToolProbe(sdk, (sdk.executable, "--list-sdks")), tmp_path))
    assert observed.available and observed.actual_version == "9.0.100"
