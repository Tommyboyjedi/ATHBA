"""
Test Execution Service.

This module provides test execution capabilities using pytest, allowing
the Tester agent to run tests on ticket branches and capture results.
"""

import os
import re
import subprocess
from typing import Dict, List

from core.services.service_requests import TestRunRequest


TEST_TIMEOUT_SECONDS = 300


class TestExecutionService:
    def __init__(self, repos_base_path: str = "/tmp/athba_repos"):
        self.repos_base_path = repos_base_path

    def _get_repo_path(self, project_id: str) -> str:
        return os.path.join(self.repos_base_path, project_id)

    def _missing_repo_result(self, repo_path: str) -> Dict:
        return {
            "status": "error",
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "skipped": 0,
            "total": 0,
            "pass_rate": 0.0,
            "output": f"Repository not found: {repo_path}",
            "duration": 0.0,
        }

    def _missing_test_file_result(self, test_file: str) -> Dict:
        return {
            "status": "error",
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "skipped": 0,
            "total": 0,
            "pass_rate": 0.0,
            "output": f"Test file not found: {test_file}",
            "duration": 0.0,
        }

    def _timeout_result(self) -> Dict:
        return {
            "status": "error",
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "skipped": 0,
            "total": 0,
            "pass_rate": 0.0,
            "output": "Test execution timed out after 5 minutes",
            "duration": float(TEST_TIMEOUT_SECONDS),
        }

    def _execution_error_result(self, error: Exception) -> Dict:
        return {
            "status": "error",
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "skipped": 0,
            "total": 0,
            "pass_rate": 0.0,
            "output": f"Error executing tests: {error}",
            "duration": 0.0,
        }

    def _build_command(self, request: TestRunRequest, repo_path: str) -> Dict | list[str]:
        cmd = ["pytest"]
        if request.test_files:
            for test_file in request.test_files:
                test_path = os.path.join(repo_path, test_file)
                if not os.path.exists(test_path):
                    return self._missing_test_file_result(test_file)
                cmd.append(test_path)
        else:
            cmd.append(repo_path)
        cmd.extend(["-v" if request.verbose else "-q", "--tb=short", "--no-header", "-ra"])
        return cmd

    async def run_tests(self, request: TestRunRequest) -> Dict:
        repo_path = self._get_repo_path(request.project_id)
        if not os.path.exists(repo_path):
            return self._missing_repo_result(repo_path)
        cmd = self._build_command(request, repo_path)
        if isinstance(cmd, dict):
            return cmd
        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=TEST_TIMEOUT_SECONDS,
            )
            return self._parse_pytest_output(result.stdout + result.stderr, result.returncode)
        except subprocess.TimeoutExpired:
            return self._timeout_result()
        except Exception as error:
            return self._execution_error_result(error)

    def _parse_pytest_output(self, output: str, return_code: int) -> Dict:
        passed = failed = errors = skipped = 0
        duration = 0.0
        for line in output.split("\n"):
            if " passed" not in line and " failed" not in line and " error" not in line:
                continue
            passed_match = re.search(r"(\d+) passed", line)
            failed_match = re.search(r"(\d+) failed", line)
            error_match = re.search(r"(\d+) error", line)
            skipped_match = re.search(r"(\d+) skipped", line)
            duration_match = re.search(r"in ([\d.]+)s", line)
            if passed_match:
                passed = int(passed_match.group(1))
            if failed_match:
                failed = int(failed_match.group(1))
            if error_match:
                errors = int(error_match.group(1))
            if skipped_match:
                skipped = int(skipped_match.group(1))
            if duration_match:
                duration = float(duration_match.group(1))
        total = passed + failed + errors + skipped
        status = "success" if return_code == 0 else "error" if errors > 0 or total == 0 else "failure"
        return {
            "status": status,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "total": total,
            "pass_rate": passed / total if total > 0 else 0.0,
            "output": output,
            "duration": duration,
        }

    def get_test_files(self, project_id: str) -> List[str]:
        repo_path = self._get_repo_path(project_id)
        test_files: list[str] = []
        if not os.path.exists(repo_path):
            return test_files
        for root, dirs, files in os.walk(repo_path):
            if ".git" in dirs:
                dirs.remove(".git")
            for file_name in files:
                if file_name.startswith("test_") and file_name.endswith(".py"):
                    full_path = os.path.join(root, file_name)
                    test_files.append(os.path.relpath(full_path, repo_path))
                elif file_name.endswith("_test.py"):
                    full_path = os.path.join(root, file_name)
                    test_files.append(os.path.relpath(full_path, repo_path))
        return sorted(test_files)
