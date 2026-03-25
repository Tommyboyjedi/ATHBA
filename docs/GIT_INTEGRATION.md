# Git Integration Documentation

## Overview

ATHBA integrates Git version control to manage code for all projects. Each project gets its own isolated Git repository where the Developer agent creates branches, commits code, and tracks changes.

**Key Features**:
- 📁 Isolated repositories per project
- 🌿 Automatic branch creation for tickets
- 💾 Commit tracking with ticket association
- 📊 Branch status monitoring
- 🔄 Clean GitOps workflow

## Architecture

### Repository Structure

```
/tmp/athba_repos/                    # Base directory for all repos
├── project_001/                     # Project-specific repository
│   ├── .git/                        # Git metadata
│   ├── README.md                    # Auto-generated project README
│   ├── src/                         # Source code
│   │   ├── auth/
│   │   ├── api/
│   │   └── utils/
│   ├── tests/                       # Test files
│   └── docs/                        # Documentation
├── project_002/                     # Another project
│   └── ...
└── project_003/
    └── ...
```

### Branch Strategy

ATHBA follows a simplified GitFlow model:

```
main (protected)
├── ticket/123-feature-a            # Feature branch
├── ticket/124-feature-b            # Feature branch  
├── ticket/125-bugfix-c             # Bugfix branch
└── ticket/126-enhancement-d        # Enhancement branch
```

**Branch Naming Convention**:
```
ticket/<ticket_id>-<sanitized-title>

Examples:
- ticket/65abc123-implement-user-auth
- ticket/65abc456-fix-validation-bug
- ticket/65abc789-add-logging-feature
```

## GitService API

The `GitService` class provides all Git operations needed by the Developer agent.

### Initialization

```python
from core.services.git_service import GitService

# Use default path (/tmp/athba_repos)
git_service = GitService()

# Or specify custom path
git_service = GitService(repos_base_path="/custom/path")
```

### Repository Management

#### Initialize Repository

Creates a new Git repository with initial commit:

```python
result = await git_service.initialize_repo(
    project_id="project_001",
    project_name="Customer Portal"
)

# Returns:
{
    "repo_path": "/tmp/athba_repos/project_001",
    "initial_branch": "main",
    "status": "initialized"
}
```

**What Happens**:
1. Creates directory at `<base_path>/<project_id>`
2. Initializes Git repository (`git init`)
3. Creates README.md with project info
4. Makes initial commit on `main` branch

#### Check Repository Exists

```python
exists = git_service.repo_exists("project_001")
# Returns: True or False
```

### Branch Operations

#### Create Branch

Creates a new branch from `main` (or specified base):

```python
result = await git_service.create_branch(
    project_id="project_001",
    branch_name="ticket/123-new-feature"
)

# Returns:
{
    "branch_name": "ticket/123-new-feature",
    "base_branch": "main",
    "status": "created"
}
```

#### List Branches

```python
branches = await git_service.list_branches("project_001")
# Returns: ["main", "ticket/123-feature-a", "ticket/124-feature-b"]
```

#### Checkout Branch

```python
result = await git_service.checkout_branch(
    project_id="project_001",
    branch_name="ticket/123-new-feature"
)

# Returns:
{
    "branch_name": "ticket/123-new-feature",
    "status": "checked_out"
}
```

#### Get Branch Status

```python
status = await git_service.get_branch_status(
    project_id="project_001",
    branch_name="ticket/123-new-feature"  # Optional, defaults to current
)

# Returns:
{
    "branch_name": "ticket/123-new-feature",
    "commits": [
        {
            "sha": "a7f3b92",
            "message": "Implement new feature",
            "author": "Developer Agent",
            "date": "2026-03-25T12:00:00"
        }
    ],
    "commit_count": 1,
    "modified_files": [],
    "untracked_files": [],
    "is_clean": True
}
```

### File Operations

#### Commit Files

Writes files to repository and creates a commit:

```python
files = {
    "src/auth/jwt_service.py": "# JWT Service implementation\n...",
    "tests/test_jwt.py": "# JWT tests\n...",
    "docs/auth.md": "# Authentication\n..."
}

result = await git_service.commit_files(
    project_id="project_001",
    files=files,
    commit_message="Implement JWT authentication"
)

# Returns:
{
    "commit_sha": "a7f3b9234f567890abcdef1234567890abcdef12",
    "files": ["src/auth/jwt_service.py", "tests/test_jwt.py", "docs/auth.md"],
    "message": "Implement JWT authentication",
    "branch": "ticket/123-jwt-auth",
    "status": "committed"
}
```

**What Happens**:
1. Creates directories if needed
2. Writes each file to disk
3. Stages files (`git add`)
4. Creates commit (`git commit`)
5. Returns commit SHA

#### Get File Content

```python
content = await git_service.get_file_content(
    project_id="project_001",
    file_path="src/auth/jwt_service.py",
    branch_name="ticket/123-jwt-auth"  # Optional
)

# Returns: String content of file, or None if not found
```

## Integration with Developer Agent

The Developer agent uses GitService throughout its workflow:

### 1. Claim Ticket
```
User: "Claim a ticket"
├── Developer: Queries tickets from Backlog
└── Returns: Ticket assigned to Developer
```

### 2. Create Branch
```
User: "Create a branch"
├── Developer: Checks if repo exists
├── GitService: initialize_repo() if needed
├── GitService: create_branch("ticket/123-...")
├── Developer: Updates ticket.branch_name
└── Returns: Branch created successfully
```

### 3. Generate Code
```
User: "Generate code"
├── Developer: Uses LLM to generate code
├── Stores code in session.pending_code
└── Returns: Code preview
```

### 4. Commit Code
```
User: "Commit the code"
├── Developer: Gets code from session.pending_code
├── GitService: commit_files(project_id, files, message)
├── Developer: Updates ticket.commits list
├── Developer: Clears session.pending_code
└── Returns: Commit successful with SHA
```

### 5. Request Review
```
User: "Request code review"
├── Developer: Verifies commits exist
├── GitService: get_branch_status() for commit summary
├── Developer: Moves ticket to Review column
├── Developer: Assigns Tester agent
└── Returns: Review requested
```

## Ticket-Git Relationship

Tickets track their associated Git artifacts:

```python
{
    "id": "65abc123",
    "title": "Implement JWT authentication",
    "branch_name": "ticket/65abc123-implement-jwt-auth",
    "commits": [
        "a7f3b9234f567890abcdef1234567890abcdef12",
        "b8c4d15234f567890abcdef1234567890abcdef23"
    ],
    "column": "Review",
    "agents": ["Developer", "Tester"]
}
```

**Tracking**:
- `branch_name`: Git branch for this ticket
- `commits`: List of commit SHAs
- History entries track branch creation and commits

## Workflow Scenarios

### Scenario 1: New Feature Implementation

```
1. Architect generates ticket: "Implement user login"
   ├── Ticket created in Backlog
   └── No Git artifacts yet

2. Developer claims ticket
   ├── Ticket → "To Do"
   └── Assigned to Developer

3. Developer creates branch
   ├── Repo initialized (if first time)
   ├── Branch: ticket/123-implement-user-login
   ├── Ticket.branch_name updated
   └── Ticket → "In Progress"

4. Developer generates code
   ├── LLM generates login code
   ├── Code stored in session
   └── Preview shown to user

5. Developer commits code
   ├── Files written to repo
   ├── Commit created: a7f3b92
   ├── Ticket.commits updated
   └── Code visible in Git

6. Developer requests review
   ├── Ticket → "Review"
   ├── Tester assigned
   └── Ready for testing
```

### Scenario 2: Multiple Commits on One Ticket

```
1. Developer creates branch
   └── Branch: ticket/456-complex-feature

2. Developer commits Part 1
   ├── Files: src/part1.py
   ├── Commit: a1b2c3d
   └── Ticket.commits = ["a1b2c3d"]

3. Developer commits Part 2
   ├── Files: src/part2.py
   ├── Commit: e4f5g6h
   └── Ticket.commits = ["a1b2c3d", "e4f5g6h"]

4. Developer commits Tests
   ├── Files: tests/test_feature.py
   ├── Commit: i7j8k9l
   └── Ticket.commits = ["a1b2c3d", "e4f5g6h", "i7j8k9l"]

5. Branch status shows full history
   └── 3 commits ahead of main
```

### Scenario 3: Multiple Tickets in Parallel

```
Project has 3 active tickets:

ticket/001-feature-a (Developer, In Progress)
├── Branch: ticket/001-feature-a
└── Commits: 2

ticket/002-feature-b (Developer, In Progress)  
├── Branch: ticket/002-feature-b
└── Commits: 1

ticket/003-bugfix-c (Developer, In Progress)
├── Branch: ticket/003-bugfix-c
└── Commits: 3

All branches coexist independently.
Developer can switch between them.
```

## Error Handling

GitService includes comprehensive error handling:

### Repository Doesn't Exist

```python
try:
    await git_service.create_branch("nonexistent_project", "feature")
except ValueError as e:
    print(f"Error: {e}")
    # Error: Repository for project nonexistent_project does not exist
```

### Branch Already Exists

```python
# Git will raise GitCommandError
# Developer agent checks for existing branch_name before creating
```

### Invalid Branch Name

```python
# Sanitization happens in Developer agent:
title = "Fix bug #123!"
sanitized = "fix-bug-123"  # Special chars removed
branch_name = f"ticket/{id}-{sanitized}"
```

### Commit Without Changes

```python
# If no files provided or no changes:
result = await git_service.commit_files(
    project_id="proj",
    files={},  # Empty
    commit_message="Empty commit"
)
# Git will handle gracefully or skip if no changes
```

## File Organization

### Auto-Generated Structure

When Developer commits code, files are organized by the LLM's suggested structure:

```
project_001/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── jwt_service.py
│   │   └── middleware.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
├── tests/
│   ├── __init__.py
│   ├── test_auth.py
│   └── test_api.py
├── docs/
│   ├── API.md
│   └── AUTH.md
└── README.md
```

### Directory Creation

GitService automatically creates nested directories:

```python
files = {
    "src/deeply/nested/module.py": "content",
    "tests/integration/api/test_endpoints.py": "content"
}

await git_service.commit_files(project_id, files, "Add modules")
# Creates: src/deeply/nested/ and tests/integration/api/
```

## Testing

### Git Service Test Suite

Location: `tests/services/test_git_service.py`

**12 Tests** (all passing):
1. `test_initialize_repo` - Repository creation
2. `test_create_branch` - Branch creation
3. `test_create_branch_no_repo` - Error handling
4. `test_commit_files` - File commits
5. `test_get_branch_status` - Branch status
6. `test_list_branches` - Branch listing
7. `test_checkout_branch` - Branch checkout
8. `test_checkout_nonexistent_branch` - Error handling
9. `test_get_file_content` - File retrieval
10. `test_repo_exists` - Repository checking
11. `test_reinitialize_repo` - Repository reset
12. `test_multiple_commits_on_branch` - Multiple commits

Run tests:
```bash
pytest tests/services/test_git_service.py -v
```

### Test Coverage

- ✅ Repository lifecycle (init, exists, reinit)
- ✅ Branch operations (create, list, checkout, status)
- ✅ File operations (commit, retrieve)
- ✅ Error scenarios (missing repo, invalid branch)
- ✅ Multiple commits on same branch
- ✅ Temporary directory cleanup

## Configuration

### Custom Repository Path

```python
# In Developer agent initialization:
class DeveloperAgent(IAgent):
    def __init__(self, session: Projses):
        self.git_service = GitService(
            repos_base_path="/opt/athba/repos"  # Custom path
        )
```

### Git Configuration

GitService uses system Git installation:

```bash
# Verify Git is installed
git --version

# Configure Git identity (optional, for commit attribution)
git config --global user.name "ATHBA Developer"
git config --global user.email "developer@athba.local"
```

## Performance Considerations

### Repository Size
- Each project has isolated repository
- Keeps repos small and fast
- No shared history between projects

### Commit Frequency
- Developer commits per user request
- Not automatic after every code generation
- User controls when to commit

### Branch Cleanup
- Branches persist until manually deleted
- Future enhancement: Auto-delete merged branches
- Current: All branches kept for history

## Security Considerations

### Local Only
- All repositories stored locally
- No remote push by default
- No GitHub/GitLab integration yet

### Access Control
- Files written with current user permissions
- No additional access restrictions
- Suitable for single-user or trusted environment

### Code Review
- All code reviewed by Tester before merge
- No direct commits to main
- Branch-based workflow enforced

## Future Enhancements

### Planned Features
1. **Remote Integration**: Push to GitHub/GitLab
2. **Pull Requests**: Auto-create PRs for review
3. **Merge Operations**: Merge approved branches to main
4. **Conflict Resolution**: Handle merge conflicts
5. **Branch Cleanup**: Delete merged branches
6. **Git Hooks**: Pre-commit linting, tests
7. **Tags**: Version tagging for releases
8. **Stash**: Temporary code storage

### Advanced Features
1. **Rebase**: Keep history clean
2. **Cherry-Pick**: Move commits between branches
3. **Bisect**: Find bug-introducing commits
4. **Submodules**: Manage dependencies
5. **Worktrees**: Multiple working directories

## Troubleshooting

### Git Not Installed
```
Error: git: command not found

Solution: Install Git
sudo apt-get install git  # Ubuntu/Debian
brew install git          # macOS
```

### Permission Denied
```
Error: Permission denied: /tmp/athba_repos

Solution: Check permissions
sudo chmod 755 /tmp/athba_repos
sudo chown $USER /tmp/athba_repos
```

### Disk Space
```
Error: No space left on device

Solution: Clean up old repositories
rm -rf /tmp/athba_repos/old_project_*
```

### Branch Name Errors
```
Error: Invalid branch name

Solution: Use sanitized names (alphanumeric, -, _)
Avoid: spaces, special chars, //, ...
```

## Resources

- [Developer Agent Documentation](DEVELOPER_AGENT.md)
- [Testing Guide](TESTING.md)
- [Git Official Docs](https://git-scm.com/doc)
- [GitPython Library](https://gitpython.readthedocs.io/)

## Author

Git Integration implemented as part of Phase 1B.

## License

Proprietary - Tom Pearce
