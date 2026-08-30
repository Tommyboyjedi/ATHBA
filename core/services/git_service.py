"""
Git service for repository operations.

This module provides Git operations for the ATHBA project, including
repository initialization, branch management, and commit operations.
"""

import os
import shutil
from typing import Dict, List, Optional

from git import GitCommandError, Repo

from core.services.service_requests import (
    BranchCreateRequest,
    CommitFilesRequest,
    FileContentRequest,
)


class GitService:
    def __init__(self, repos_base_path: str = "/tmp/athba_repos"):
        self.repos_base_path = repos_base_path
        os.makedirs(self.repos_base_path, exist_ok=True)

    def _get_repo_path(self, project_id: str) -> str:
        return os.path.join(self.repos_base_path, project_id)

    def _require_repo_path(self, project_id: str) -> str:
        repo_path = self._get_repo_path(project_id)
        if not os.path.exists(repo_path):
            raise ValueError(f"Repository for project {project_id} does not exist")
        return repo_path

    async def initialize_repo(self, project_id: str, project_name: str) -> Dict[str, str]:
        repo_path = self._get_repo_path(project_id)
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path)
        os.makedirs(repo_path, exist_ok=True)
        repo = Repo.init(repo_path)
        readme_path = os.path.join(repo_path, "README.md")
        with open(readme_path, "w") as handle:
            handle.write(f"# {project_name}\n\n")
            handle.write("This project is managed by ATHBA - AI Development Team.\n")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")
        if repo.active_branch.name != "main":
            main_branch = repo.create_head("main")
            main_branch.checkout()
        return {"repo_path": repo_path, "initial_branch": "main", "status": "initialized"}

    def _branch_request(self, request_or_project_id, args) -> BranchCreateRequest:
        if isinstance(request_or_project_id, BranchCreateRequest):
            return request_or_project_id
        base_branch = args[1] if len(args) > 1 else "main"
        return BranchCreateRequest(
            project_id=request_or_project_id,
            branch_name=args[0],
            base_branch=base_branch,
        )

    async def create_branch(self, request_or_project_id, *args) -> Dict[str, str]:
        request = self._branch_request(request_or_project_id, args)
        repo = Repo(self._require_repo_path(request.project_id))
        base = repo.heads[request.base_branch]
        base.checkout()
        new_branch = repo.create_head(request.branch_name)
        new_branch.checkout()
        return {
            "branch_name": request.branch_name,
            "base_branch": request.base_branch,
            "status": "created",
        }

    def _commit_request(self, request_or_project_id, args) -> CommitFilesRequest:
        if isinstance(request_or_project_id, CommitFilesRequest):
            return request_or_project_id
        return CommitFilesRequest(
            project_id=request_or_project_id,
            files=args[0],
            commit_message=args[1],
        )

    async def commit_files(self, request_or_project_id, *args) -> Dict[str, object]:
        request = self._commit_request(request_or_project_id, args)
        repo_path = self._require_repo_path(request.project_id)
        repo = Repo(repo_path)
        committed_files: list[str] = []
        for file_path, content in request.files.items():
            full_path = os.path.join(repo_path, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as handle:
                handle.write(content)
            committed_files.append(file_path)
        repo.index.add(committed_files)
        commit = repo.index.commit(request.commit_message)
        return {
            "commit_sha": commit.hexsha,
            "files": committed_files,
            "message": request.commit_message,
            "branch": repo.active_branch.name,
            "status": "committed",
        }

    async def get_branch_status(self, project_id: str, branch_name: Optional[str] = None) -> Dict[str, object]:
        repo = Repo(self._require_repo_path(project_id))
        branch = repo.heads[branch_name] if branch_name else repo.active_branch
        commits: list[dict[str, str]] = []
        try:
            main_branch = repo.heads["main"]
            commits = [
                {
                    "sha": commit.hexsha[:7],
                    "message": commit.message.strip(),
                    "author": str(commit.author),
                    "date": commit.committed_datetime.isoformat(),
                }
                for commit in repo.iter_commits(f"{main_branch.name}..{branch.name}")
            ]
        except (GitCommandError, ValueError):
            pass
        modified_files = [item.a_path for item in repo.index.diff(None)]
        untracked_files = repo.untracked_files
        return {
            "branch_name": branch.name,
            "commits": commits,
            "commit_count": len(commits),
            "modified_files": modified_files,
            "untracked_files": untracked_files,
            "is_clean": len(modified_files) == 0 and len(untracked_files) == 0,
        }

    async def list_branches(self, project_id: str) -> List[str]:
        repo = Repo(self._require_repo_path(project_id))
        return [head.name for head in repo.heads]

    def _content_request(self, request_or_project_id, args) -> FileContentRequest:
        if isinstance(request_or_project_id, FileContentRequest):
            return request_or_project_id
        branch_name = args[1] if len(args) > 1 else None
        return FileContentRequest(project_id=request_or_project_id, file_path=args[0], branch_name=branch_name)

    async def get_file_content(self, request_or_project_id, *args) -> Optional[str]:
        request = self._content_request(request_or_project_id, args)
        repo_path = self._require_repo_path(request.project_id)
        full_path = os.path.join(repo_path, request.file_path)
        if not os.path.exists(full_path):
            return None
        with open(full_path, "r") as handle:
            return handle.read()

    async def checkout_branch(self, project_id: str, branch_name: str) -> Dict[str, str]:
        repo = Repo(self._require_repo_path(project_id))
        if branch_name not in [head.name for head in repo.heads]:
            raise ValueError(f"Branch {branch_name} does not exist")
        repo.heads[branch_name].checkout()
        return {"branch_name": branch_name, "status": "checked_out"}

    def repo_exists(self, project_id: str) -> bool:
        repo_path = self._get_repo_path(project_id)
        return os.path.exists(repo_path) and os.path.exists(os.path.join(repo_path, ".git"))
