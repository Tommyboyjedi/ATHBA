"""
Tests for Git Service.

This module tests the GitService class functionality including repository
initialization, branch management, and commit operations.
"""

import pytest
import os
import shutil
import tempfile
from core.services.git_service import GitService


class TestGitService:
    """Test suite for GitService."""
    
    @pytest.fixture
    def temp_repos_path(self):
        """Create a temporary directory for test repositories."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup after tests
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def git_service(self, temp_repos_path):
        """Create a GitService instance with temporary path."""
        return GitService(repos_base_path=temp_repos_path)
    
    @pytest.mark.asyncio
    async def test_initialize_repo(self, git_service):
        """Test repository initialization."""
        project_id = "test_project_001"
        project_name = "Test Project"
        
        result = await git_service.initialize_repo(project_id, project_name)
        
        assert result["status"] == "initialized"
        assert result["initial_branch"] == "main"
        assert "repo_path" in result
        assert git_service.repo_exists(project_id)
        
        # Verify README was created
        readme_content = await git_service.get_file_content(project_id, "README.md")
        assert project_name in readme_content
        assert "ATHBA" in readme_content
    
    @pytest.mark.asyncio
    async def test_create_branch(self, git_service):
        """Test branch creation."""
        project_id = "test_project_002"
        await git_service.initialize_repo(project_id, "Test Project")
        
        branch_name = "feature/test-branch"
        result = await git_service.create_branch(project_id, branch_name)
        
        assert result["status"] == "created"
        assert result["branch_name"] == branch_name
        assert result["base_branch"] == "main"
        
        # Verify branch exists
        branches = await git_service.list_branches(project_id)
        assert branch_name in branches
        assert "main" in branches
    
    @pytest.mark.asyncio
    async def test_create_branch_no_repo(self, git_service):
        """Test branch creation fails when repository doesn't exist."""
        with pytest.raises(ValueError, match="does not exist"):
            await git_service.create_branch("nonexistent_project", "test-branch")
    
    @pytest.mark.asyncio
    async def test_commit_files(self, git_service):
        """Test committing files to repository."""
        project_id = "test_project_003"
        await git_service.initialize_repo(project_id, "Test Project")
        await git_service.create_branch(project_id, "feature/add-files")
        
        files = {
            "src/main.py": "print('Hello, World!')",
            "src/utils.py": "def helper():\n    return True",
            "tests/test_main.py": "def test_main():\n    assert True"
        }
        
        commit_message = "Add initial Python files"
        result = await git_service.commit_files(project_id, files, commit_message)
        
        assert result["status"] == "committed"
        assert "commit_sha" in result
        assert len(result["commit_sha"]) == 40  # Full SHA is 40 chars
        assert result["message"] == commit_message
        assert result["branch"] == "feature/add-files"
        assert set(result["files"]) == set(files.keys())
        
        # Verify files were written
        for file_path, expected_content in files.items():
            content = await git_service.get_file_content(project_id, file_path)
            assert content == expected_content
    
    @pytest.mark.asyncio
    async def test_get_branch_status(self, git_service):
        """Test getting branch status."""
        project_id = "test_project_004"
        await git_service.initialize_repo(project_id, "Test Project")
        await git_service.create_branch(project_id, "feature/status-test")
        
        # Commit some files
        files = {"test.txt": "test content"}
        await git_service.commit_files(project_id, files, "Test commit")
        
        status = await git_service.get_branch_status(project_id, "feature/status-test")
        
        assert status["branch_name"] == "feature/status-test"
        assert status["commit_count"] >= 1
        assert len(status["commits"]) >= 1
        assert status["is_clean"] is True
        assert status["commits"][0]["message"] == "Test commit"
    
    @pytest.mark.asyncio
    async def test_list_branches(self, git_service):
        """Test listing all branches."""
        project_id = "test_project_005"
        await git_service.initialize_repo(project_id, "Test Project")
        
        # Create multiple branches
        await git_service.create_branch(project_id, "feature/branch1")
        await git_service.checkout_branch(project_id, "main")
        await git_service.create_branch(project_id, "feature/branch2")
        await git_service.checkout_branch(project_id, "main")
        await git_service.create_branch(project_id, "bugfix/issue123")
        
        branches = await git_service.list_branches(project_id)
        
        # Should have at least 4 branches (may have main and/or master depending on Git version)
        assert len(branches) >= 4
        assert "feature/branch1" in branches
        assert "feature/branch2" in branches
        assert "bugfix/issue123" in branches
        assert "main" in branches or "master" in branches
    
    @pytest.mark.asyncio
    async def test_checkout_branch(self, git_service):
        """Test checking out a branch."""
        project_id = "test_project_006"
        await git_service.initialize_repo(project_id, "Test Project")
        await git_service.create_branch(project_id, "feature/test")
        
        # Checkout main
        result = await git_service.checkout_branch(project_id, "main")
        assert result["status"] == "checked_out"
        assert result["branch_name"] == "main"
        
        # Checkout feature branch
        result = await git_service.checkout_branch(project_id, "feature/test")
        assert result["status"] == "checked_out"
        assert result["branch_name"] == "feature/test"
    
    @pytest.mark.asyncio
    async def test_checkout_nonexistent_branch(self, git_service):
        """Test checkout fails for nonexistent branch."""
        project_id = "test_project_007"
        await git_service.initialize_repo(project_id, "Test Project")
        
        with pytest.raises(ValueError, match="does not exist"):
            await git_service.checkout_branch(project_id, "nonexistent-branch")
    
    @pytest.mark.asyncio
    async def test_get_file_content(self, git_service):
        """Test getting file content from repository."""
        project_id = "test_project_008"
        await git_service.initialize_repo(project_id, "Test Project")
        
        # Write a file
        files = {"config.json": '{"setting": "value"}'}
        await git_service.commit_files(project_id, files, "Add config")
        
        content = await git_service.get_file_content(project_id, "config.json")
        assert content == '{"setting": "value"}'
        
        # Test nonexistent file
        content = await git_service.get_file_content(project_id, "nonexistent.txt")
        assert content is None
    
    @pytest.mark.asyncio
    async def test_repo_exists(self, git_service):
        """Test checking if repository exists."""
        project_id = "test_project_009"
        
        assert git_service.repo_exists(project_id) is False
        
        await git_service.initialize_repo(project_id, "Test Project")
        
        assert git_service.repo_exists(project_id) is True
    
    @pytest.mark.asyncio
    async def test_reinitialize_repo(self, git_service):
        """Test reinitializing a repository removes old content."""
        project_id = "test_project_010"
        
        # Initialize repo and add a file
        await git_service.initialize_repo(project_id, "Test Project v1")
        await git_service.commit_files(
            project_id,
            {"old_file.txt": "old content"},
            "Add old file"
        )
        
        # Reinitialize
        await git_service.initialize_repo(project_id, "Test Project v2")
        
        # Old file should not exist
        content = await git_service.get_file_content(project_id, "old_file.txt")
        assert content is None
        
        # New README should exist
        readme = await git_service.get_file_content(project_id, "README.md")
        assert "Test Project v2" in readme
    
    @pytest.mark.asyncio
    async def test_multiple_commits_on_branch(self, git_service):
        """Test multiple commits on a single branch."""
        project_id = "test_project_011"
        await git_service.initialize_repo(project_id, "Test Project")
        await git_service.create_branch(project_id, "feature/multi-commit")
        
        # First commit
        await git_service.commit_files(
            project_id,
            {"file1.txt": "content 1"},
            "First commit"
        )
        
        # Second commit
        await git_service.commit_files(
            project_id,
            {"file2.txt": "content 2"},
            "Second commit"
        )
        
        # Third commit
        await git_service.commit_files(
            project_id,
            {"file3.txt": "content 3"},
            "Third commit"
        )
        
        status = await git_service.get_branch_status(project_id)
        assert status["commit_count"] == 3
        assert len(status["commits"]) == 3
