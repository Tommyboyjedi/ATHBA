"""ATHBA-owned Python and pytest commands for bounded development targets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PythonPytestRuntime:
    """Describe the runtime ATHBA supplies to a Python development target."""

    python_executable: str = "python3"

    def __post_init__(self) -> None:
        if not self.python_executable.strip():
            raise ValueError("python executable must be non-empty")

    def red_command(
        self,
        test_name: str,
        expected_exception_type: str | None = None,
    ) -> list[str]:
        command = [
            self.python_executable,
            "-B",
            "scripts/assert_test_fails.py",
            test_name,
        ]
        if expected_exception_type:
            command.append(expected_exception_type)
        return command

    def pytest_command(self, target: str) -> list[str]:
        return [
            self.python_executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            target,
        ]
