"""
Git service for repository operations.

This module provides Git operations for the ATHBA project, including
repository initialization, branch management, and commit operations.
"""

import os
import shutil
from typing import Optional, List, Dict
from pathlib import Path
import git
from git import Repo, GitCommandError


class GitService:
    """
    Service for managing Git repository operations.
    
    Handles repository initialization, branch creation, file commits,
    and other Git operations needed for the Developer agent workflow.
    
    Attributes:
        repos_base_path: Base directory where project repositories are stored
    """
    
    def __init__(self, repos_base_path: str = "/tmp/athba_repos"):
        """
        Initialize the Git service.
        
        Args:
            repos_base_path: Base directory for storing project repositories.
                           Defaults to /tmp/athba_repos
        """
        self.repos_base_path = repos_base_path
        os.makedirs(self.repos_base_path, exist_ok=True)
    
    def _get_repo_path(self, project_id: str) -> str:
        """
        Get the file system path for a project repository.
        
        Args:
            project_id: Unique identifier of the project
            
        Returns:
            Full path to the project repository directory
        """
        return os.path.join(self.repos_base_path, project_id)
    
    async def initialize_repo(self, project_id: str, project_name: str) -> Dict[str, str]:
        """
        Initialize a new Git repository for a project.
        
        Creates a new Git repository with a main branch and initial commit.
        
        Args:
            project_id: Unique identifier of the project
            project_name: Human-readable name of the project
            
        Returns:
            Dictionary with repo_path and initial_branch
            
        Raises:
            GitCommandError: If Git operations fail
        """
        repo_path = self._get_repo_path(project_id)
        
        # Remove existing repo if it exists
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path)
        
        # Create directory and initialize repo
        os.makedirs(repo_path, exist_ok=True)
        repo = Repo.init(repo_path)
        
        # Create initial README
        readme_path = os.path.join(repo_path, "README.md")
        with open(readme_path, "w") as f:
            f.write(f"# {project_name}\n\n")
            f.write("This project is managed by ATHBA - AI Development Team.\n")
        
        # Initial commit on main branch
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")
        
        # Ensure we're on main branch
        if repo.active_branch.name != "main":
            main_branch = repo.create_head("main")
            main_branch.checkout()
        
        return {
            "repo_path": repo_path,
            "initial_branch": "main",
            "status": "initialized"
        }
    
    async def create_branch(self, project_id: str, branch_name: str, 
                           base_branch: str = "main") -> Dict[str, str]:
        """
        Create a new branch for a ticket or feature.
        
        Args:
            project_id: Unique identifier of the project
            branch_name: Name of the new branch to create
            base_branch: Branch to create from (default: main)
            
        Returns:
            Dictionary with branch_name and status
            
        Raises:
            GitCommandError: If branch creation fails
            ValueError: If repository doesn't exist
        """
        repo_path = self._get_repo_path(project_id)
        
        if not os.path.exists(repo_path):
            raise ValueError(f"Repository for project {project_id} does not exist")
        
        repo = Repo(repo_path)
        
        # Ensure we're on base branch
        base = repo.heads[base_branch]
        base.checkout()
        
        # Create and checkout new branch
        new_branch = repo.create_head(branch_name)
        new_branch.checkout()
        
        return {
            "branch_name": branch_name,
            "base_branch": base_branch,
            "status": "created"
        }
    
    async def commit_files(self, project_id: str, files: Dict[str, str], 
                          commit_message: str) -> Dict[str, any]:
        """
        Write files to the repository and commit them.
        
        Args:
            project_id: Unique identifier of the project
            files: Dictionary mapping file paths to file contents
            commit_message: Commit message
            
        Returns:
            Dictionary with commit SHA, files committed, and status
            
        Raises:
            GitCommandError: If commit fails
            ValueError: If repository doesn't exist
        """
        repo_path = self._get_repo_path(project_id)
        
        if not os.path.exists(repo_path):
            raise ValueError(f"Repository for project {project_id} does not exist")
        
        repo = Repo(repo_path)
        
        # Write files to disk
        committed_files = []
        for file_path, content in files.items():
            full_path = os.path.join(repo_path, file_path)
            
            # Create directory if needed
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Write file
            with open(full_path, "w") as f:
                f.write(content)
            
            committed_files.append(file_path)
        
        # Stage files
        repo.index.add(committed_files)
        
        # Commit
        commit = repo.index.commit(commit_message)
        
        return {
            "commit_sha": commit.hexsha,
            "files": committed_files,
            "message": commit_message,
            "branch": repo.active_branch.name,
            "status": "committed"
        }
    
    async def get_branch_status(self, project_id: str, branch_name: Optional[str] = None) -> Dict[str, any]:
        """
        Get the status of a branch.
        
        Args:
            project_id: Unique identifier of the project
            branch_name: Name of branch to check (defaults to current branch)
            
        Returns:
            Dictionary with branch info, commits, and modified files
            
        Raises:
            ValueError: If repository doesn't exist
        """
        repo_path = self._get_repo_path(project_id)
        
        if not os.path.exists(repo_path):
            raise ValueError(f"Repository for project {project_id} does not exist")
        
        repo = Repo(repo_path)
        
        # Get branch
        if branch_name:
            branch = repo.heads[branch_name]
        else:
            branch = repo.active_branch
        
        # Get commits on this branch (compared to main)
        commits = []
        try:
            main_branch = repo.heads["main"]
            commit_list = list(repo.iter_commits(f"{main_branch.name}..{branch.name}"))
            commits = [
                {
                    "sha": c.hexsha[:7],
                    "message": c.message.strip(),
                    "author": str(c.author),
                    "date": c.committed_datetime.isoformat()
                }
                for c in commit_list
            ]
        except (GitCommandError, ValueError):
            # Branch might not exist yet or no commits
            pass
        
        # Get modified files
        modified_files = [item.a_path for item in repo.index.diff(None)]
        untracked_files = repo.untracked_files
        
        return {
            "branch_name": branch.name,
            "commits": commits,
            "commit_count": len(commits),
            "modified_files": modified_files,
            "untracked_files": untracked_files,
            "is_clean": len(modified_files) == 0 and len(untracked_files) == 0
        }
    
    async def list_branches(self, project_id: str) -> List[str]:
        """
        List all branches in the repository.
        
        Args:
            project_id: Unique identifier of the project
            
        Returns:
            List of branch names
            
        Raises:
            ValueError: If repository doesn't exist
        """
        repo_path = self._get_repo_path(project_id)
        
        if not os.path.exists(repo_path):
            raise ValueError(f"Repository for project {project_id} does not exist")
        
        repo = Repo(repo_path)
        return [head.name for head in repo.heads]
    
    async def get_file_content(self, project_id: str, file_path: str, 
                               branch_name: Optional[str] = None) -> Optional[str]:
        """
        Get the content of a file from the repository.
        
        Args:
            project_id: Unique identifier of the project
            file_path: Path to file relative to repo root
            branch_name: Branch to read from (defaults to current branch)
            
        Returns:
            File content as string, or None if file doesn't exist
            
        Raises:
            ValueError: If repository doesn't exist
        """
        repo_path = self._get_repo_path(project_id)
        
        if not os.path.exists(repo_path):
            raise ValueError(f"Repository for project {project_id} does not exist")
        
        full_path = os.path.join(repo_path, file_path)
        
        if not os.path.exists(full_path):
            return None
        
        with open(full_path, "r") as f:
            return f.read()
    
    async def checkout_branch(self, project_id: str, branch_name: str) -> Dict[str, str]:
        """
        Checkout an existing branch.
        
        Args:
            project_id: Unique identifier of the project
            branch_name: Name of branch to checkout
            
        Returns:
            Dictionary with branch_name and status
            
        Raises:
            GitCommandError: If checkout fails
            ValueError: If repository or branch doesn't exist
        """
        repo_path = self._get_repo_path(project_id)
        
        if not os.path.exists(repo_path):
            raise ValueError(f"Repository for project {project_id} does not exist")
        
        repo = Repo(repo_path)
        
        if branch_name not in [head.name for head in repo.heads]:
            raise ValueError(f"Branch {branch_name} does not exist")
        
        branch = repo.heads[branch_name]
        branch.checkout()
        
        return {
            "branch_name": branch_name,
            "status": "checked_out"
        }
    
    def repo_exists(self, project_id: str) -> bool:
        """
        Check if a repository exists for a project.
        
        Args:
            project_id: Unique identifier of the project
            
        Returns:
            True if repository exists, False otherwise
        """
        repo_path = self._get_repo_path(project_id)
        return os.path.exists(repo_path) and os.path.exists(os.path.join(repo_path, ".git"))
