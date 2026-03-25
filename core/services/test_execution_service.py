"""
Test Execution Service.

This module provides test execution capabilities using pytest, allowing
the Tester agent to run tests on ticket branches and capture results.
"""

import os
import subprocess
from typing import Dict, List, Optional
from pathlib import Path


class TestExecutionService:
    """
    Service for executing tests using pytest.
    
    Handles running pytest on specific branches, parsing results,
    and returning detailed test execution information.
    
    Attributes:
        repos_base_path: Base directory where project repositories are stored
    """
    
    def __init__(self, repos_base_path: str = "/tmp/athba_repos"):
        """
        Initialize the Test Execution Service.
        
        Args:
            repos_base_path: Base directory for project repositories
        """
        self.repos_base_path = repos_base_path
    
    def _get_repo_path(self, project_id: str) -> str:
        """
        Get the file system path for a project repository.
        
        Args:
            project_id: Unique identifier of the project
            
        Returns:
            Full path to the project repository directory
        """
        return os.path.join(self.repos_base_path, project_id)
    
    async def run_tests(
        self, 
        project_id: str, 
        test_files: Optional[List[str]] = None,
        verbose: bool = True
    ) -> Dict:
        """
        Execute tests using pytest.
        
        Args:
            project_id: Unique identifier of the project
            test_files: Optional list of specific test files to run.
                       If None, runs all tests
            verbose: Whether to capture verbose output
            
        Returns:
            Dictionary with test results:
            {
                "status": "success" | "failure" | "error",
                "passed": int,
                "failed": int,
                "errors": int,
                "skipped": int,
                "total": int,
                "pass_rate": float (0.0 to 1.0),
                "output": str (test output),
                "duration": float (seconds)
            }
        """
        repo_path = self._get_repo_path(project_id)
        
        # Check if repo exists
        if not os.path.exists(repo_path):
            return {
                "status": "error",
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "skipped": 0,
                "total": 0,
                "pass_rate": 0.0,
                "output": f"Repository not found: {repo_path}",
                "duration": 0.0
            }
        
        # Build pytest command
        cmd = ["pytest"]
        
        if test_files:
            # Run specific test files
            for test_file in test_files:
                test_path = os.path.join(repo_path, test_file)
                if os.path.exists(test_path):
                    cmd.append(test_path)
                else:
                    return {
                        "status": "error",
                        "passed": 0,
                        "failed": 0,
                        "errors": 1,
                        "skipped": 0,
                        "total": 0,
                        "pass_rate": 0.0,
                        "output": f"Test file not found: {test_file}",
                        "duration": 0.0
                    }
        else:
            # Run all tests in the repo
            cmd.append(repo_path)
        
        # Add pytest options
        cmd.extend([
            "-v" if verbose else "-q",  # Verbose or quiet
            "--tb=short",  # Short traceback format
            "--no-header",  # No pytest header
            "-ra"  # Show summary of all test outcomes
        ])
        
        # Execute pytest
        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            # Parse output
            return self._parse_pytest_output(
                result.stdout + result.stderr,
                result.returncode
            )
            
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "skipped": 0,
                "total": 0,
                "pass_rate": 0.0,
                "output": "Test execution timed out after 5 minutes",
                "duration": 300.0
            }
        except Exception as e:
            return {
                "status": "error",
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "skipped": 0,
                "total": 0,
                "pass_rate": 0.0,
                "output": f"Error executing tests: {str(e)}",
                "duration": 0.0
            }
    
    def _parse_pytest_output(self, output: str, return_code: int) -> Dict:
        """
        Parse pytest output to extract test results.
        
        Args:
            output: Combined stdout and stderr from pytest
            return_code: Pytest exit code (0 = all passed, 1 = some failed, etc.)
            
        Returns:
            Dictionary with parsed test results
        """
        # Initialize counters
        passed = 0
        failed = 0
        errors = 0
        skipped = 0
        duration = 0.0
        
        # Parse output for test counts
        # Pytest summary line format: "=== X passed, Y failed in Z.ZZs ==="
        lines = output.split('\n')
        
        for line in lines:
            # Look for summary line
            if ' passed' in line or ' failed' in line or ' error' in line:
                # Extract numbers
                import re
                
                passed_match = re.search(r'(\d+) passed', line)
                if passed_match:
                    passed = int(passed_match.group(1))
                
                failed_match = re.search(r'(\d+) failed', line)
                if failed_match:
                    failed = int(failed_match.group(1))
                
                error_match = re.search(r'(\d+) error', line)
                if error_match:
                    errors = int(error_match.group(1))
                
                skipped_match = re.search(r'(\d+) skipped', line)
                if skipped_match:
                    skipped = int(skipped_match.group(1))
                
                # Extract duration
                duration_match = re.search(r'in ([\d.]+)s', line)
                if duration_match:
                    duration = float(duration_match.group(1))
        
        # Calculate totals
        total = passed + failed + errors + skipped
        pass_rate = passed / total if total > 0 else 0.0
        
        # Determine status
        if return_code == 0:
            status = "success"
        elif errors > 0 or total == 0:
            status = "error"
        else:
            status = "failure"
        
        return {
            "status": status,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "total": total,
            "pass_rate": pass_rate,
            "output": output,
            "duration": duration
        }
    
    def get_test_files(self, project_id: str) -> List[str]:
        """
        Get list of all test files in the project repository.
        
        Args:
            project_id: Unique identifier of the project
            
        Returns:
            List of test file paths relative to repo root
        """
        repo_path = self._get_repo_path(project_id)
        test_files = []
        
        if not os.path.exists(repo_path):
            return test_files
        
        # Find all test files (test_*.py or *_test.py)
        for root, dirs, files in os.walk(repo_path):
            # Skip .git directory
            if '.git' in dirs:
                dirs.remove('.git')
            
            for file in files:
                if file.startswith('test_') and file.endswith('.py'):
                    # Get path relative to repo root
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, repo_path)
                    test_files.append(rel_path)
                elif file.endswith('_test.py'):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, repo_path)
                    test_files.append(rel_path)
        
        return test_files
