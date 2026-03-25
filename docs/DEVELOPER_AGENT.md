# Developer Agent Documentation

## Overview

The Developer Agent is responsible for claiming tickets from the Backlog, creating Git branches, generating code, and committing changes. It serves as the primary code writer in the ATHBA system, working in tandem with the Tester agent to implement features following TDD principles.

**Key Features:**
- 🎫 Claims tickets from Backlog automatically or by request
- 🌿 Creates isolated Git branches for each ticket
- 🔍 Analyzes ticket requirements using LLM
- 💻 Generates clean, production-ready code
- 💾 Commits code with meaningful messages
- 🔎 Requests code review from Tester agent

## LLM Configuration

**Local LLM**: The Developer agent uses local models (codellama-7b) for all operations, ensuring privacy and cost-efficiency.

Unlike the Architect agent which requires cloud API access, the Developer runs entirely offline using locally hosted models.

## Responsibilities

### 1. Ticket Management
- **Claim Tickets**: Select tickets from Backlog based on priority
- **Track Progress**: Move tickets through Kanban columns (Backlog → To Do → In Progress → Review)
- **Update History**: Record all actions in ticket history

### 2. Git Operations
- **Repository Initialization**: Set up Git repos for projects
- **Branch Creation**: Create feature branches named `ticket/<id>-<title>`
- **Commit Management**: Commit code with descriptive messages
- **Branch Status**: Track commits and file changes

### 3. Code Generation
- **Requirements Analysis**: Understand what needs to be built
- **Code Implementation**: Generate clean, well-documented code
- **File Organization**: Structure code appropriately
- **Error Handling**: Include proper error handling and edge cases

### 4. Code Review Workflow
- **Review Requests**: Move tickets to Review column
- **Tester Notification**: Assign Tester agent to tickets
- **Handoff**: Provide complete context for code review

## Behaviors

The Developer agent implements 7 behaviors:

### 1. Claim Ticket Behavior
**Intent**: `claim_ticket`

Claims a ticket from the Backlog and assigns it to the Developer.

**Actions**:
- Finds available tickets in Backlog
- Selects highest priority ticket (or specific ticket if ID provided)
- Moves ticket to "To Do" column
- Assigns Developer agent to ticket
- Updates ticket history

**Example**:
```
User: "Claim a ticket"
Developer: ✅ Successfully claimed ticket!
           Ticket: Implement user authentication
           ID: 65abc123...
           Severity: High
```

### 2. Create Branch Behavior
**Intent**: `create_branch`

Creates a Git branch for the claimed ticket.

**Actions**:
- Initializes Git repository if needed
- Generates branch name from ticket ID and title
- Creates branch from main
- Updates ticket with branch name
- Moves ticket to "In Progress"

**Branch Naming Convention**:
```
ticket/<ticket_id>-<sanitized-title>

Example: ticket/65abc123-implement-user-authentication
```

**Example**:
```
User: "Create a branch for this ticket"
Developer: ✅ Git branch created successfully!
           Branch: ticket/65abc123-implement-user-authentication
           Ticket: Implement user authentication
           Status: Moved to "In Progress"
```

### 3. Analyze Ticket Behavior
**Intent**: `analyze_ticket`

Analyzes ticket requirements using LLM to understand what needs to be implemented.

**Actions**:
- Retrieves ticket details
- Uses LLM to analyze requirements
- Provides implementation guidance
- Identifies potential challenges
- Suggests file structure

**Example**:
```
User: "Analyze the ticket"
Developer: 📋 Ticket Analysis
           
           Ticket: Implement user authentication
           
           Analysis:
           1. Key requirements:
              - JWT token-based authentication
              - Login/logout endpoints
              - Session management
           
           2. Implementation approach:
              - Create auth service with JWT utilities
              - Implement login/logout routes
              - Add middleware for protected routes
           
           3. Potential challenges:
              - Token expiration and refresh logic
              - Secure password hashing
              - Session storage strategy
```

### 4. Generate Code Behavior
**Intent**: `generate_code`

Generates code to implement the ticket using LLM (codellama-7b).

**Actions**:
- Retrieves ticket requirements
- Uses LLM to generate code
- Parses generated code (file path + content)
- Stores code in session (pending commit)
- Provides code preview

**Code Generation Prompt**:
The behavior uses a structured prompt that requests:
- Clean, readable code
- Proper documentation
- Error handling
- Unit tests (when appropriate)
- Meaningful naming

**Example**:
```
User: "Generate code for this ticket"
Developer: ✅ Code generated successfully!
           
           File: src/auth/jwt_service.py
           
           Code Preview:
           ```python
           import jwt
           from datetime import datetime, timedelta
           
           class JWTService:
               def __init__(self, secret_key):
                   self.secret_key = secret_key
           ...
           ```
           
           The code is ready to commit.
           Would you like me to commit it to branch ticket/65abc123?
```

### 5. Commit Code Behavior
**Intent**: `commit_code`

Commits generated code to the Git branch.

**Actions**:
- Takes pending code from session
- Writes files to repository
- Creates commit with message
- Updates ticket with commit SHA
- Clears pending code from session

**Commit Message Format**:
```
Implement <ticket_title>

Examples:
- Implement user authentication system
- Add order management interface
- Fix validation bug in user registration
```

**Example**:
```
User: "Commit the code"
Developer: ✅ Code committed successfully!
           
           Commit: a7f3b92
           Branch: ticket/65abc123-implement-user-authentication
           Message: Implement user authentication system
           
           Files committed:
             - src/auth/jwt_service.py
             - src/auth/auth_middleware.py
             - tests/test_auth.py
```

### 6. Request Review Behavior
**Intent**: `request_review`

Requests code review from the Tester agent.

**Actions**:
- Verifies ticket has committed code
- Moves ticket to "Review" column
- Adds Tester to assigned agents
- Updates ticket history

**Example**:
```
User: "Request code review"
Developer: ✅ Code review requested!
           
           Ticket: Implement user authentication
           Branch: ticket/65abc123-implement-user-authentication
           Status: Moved to "Review"
           
           Commits (2 total):
             - a7f3b92: Implement user authentication system
             - b8c4d15: Add unit tests for JWT service
           
           The Tester agent will now:
           1. Review the code changes
           2. Run tests to verify functionality
           3. Either approve or request modifications
```

### 7. Basic Reply Behavior
**Intent**: `basic_reply`

Handles general conversation and provides agent status.

**Example**:
```
User: "Hello"
Developer: Hello! I'm the Developer Agent. I'm responsible for 
           implementing tickets by writing code.
           
           Current Project Status:
           - Tickets in Backlog: 5
           - Tickets assigned to me: 2
           - Tickets in progress: 1
           
           Currently working on: Implement user authentication
           Branch: ticket/65abc123-implement-user-authentication
```

## Workflow Example

### Complete Ticket Implementation Flow

```
1. User: "Claim a ticket"
   → Developer claims highest priority ticket
   → Ticket moves to "To Do"

2. User: "Create a branch"
   → Developer creates Git branch: ticket/65abc123-implement-auth
   → Ticket moves to "In Progress"

3. User: "Analyze the ticket"
   → Developer analyzes requirements
   → Provides implementation guidance

4. User: "Generate code"
   → Developer generates code using LLM
   → Shows code preview

5. User: "Commit the code"
   → Developer commits to Git
   → Updates ticket with commit SHA

6. User: "Request code review"
   → Developer moves ticket to "Review"
   → Tester agent is notified
```

## Integration with Other Agents

### With Architect Agent
- **Receives**: Tickets generated from specifications
- **Input**: Ticket requirements and acceptance criteria

### With Tester Agent
- **Sends**: Code review requests
- **Collaboration**: TDD workflow (Developer writes code → Tester reviews/tests)

### With Resource Director
- **Managed By**: Resource allocation and model management
- **Coordination**: Project prioritization

## Git Repository Structure

Each project gets its own Git repository at `/tmp/athba_repos/<project_id>/`:

```
/tmp/athba_repos/
└── <project_id>/
    ├── .git/
    ├── README.md
    ├── src/
    │   └── <generated_code>.py
    ├── tests/
    │   └── <generated_tests>.py
    └── <other_files>
```

**Branch Structure**:
```
main                     # Protected branch
├── ticket/123-feature-a # Feature branch
├── ticket/124-feature-b # Feature branch
└── ticket/125-bugfix-c  # Bugfix branch
```

## Ticket Metadata

Tickets track Git-related information:

```python
{
    "id": "65abc123...",
    "title": "Implement user authentication",
    "branch_name": "ticket/65abc123-implement-user-authentication",
    "commits": [
        "a7f3b9234f567890abcdef1234567890abcdef12",
        "b8c4d15234f567890abcdef1234567890abcdef23"
    ],
    "agents": ["Developer"],
    "column": "In Progress",
    "history": [
        {
            "timestamp": "2026-03-25T12:00:00Z",
            "event": "claimed",
            "actor": "Developer",
            "details": "Ticket claimed by Developer"
        },
        {
            "timestamp": "2026-03-25T12:05:00Z",
            "event": "branch_created",
            "actor": "Developer",
            "details": "Created branch: ticket/65abc123-implement-user-authentication"
        }
    ]
}
```

## Configuration

### LLM Model
The Developer agent uses `codellama-7b` for code generation. This can be configured in the model registry:

```python
EAgent.Developer: [
    AgentModelConfig(
        tier=ETier.Standard,
        model_id="codellama-7b-instruct.Q4_K_M.gguf",
        context_window=4096,
        n_threads=4
    )
]
```

### Repository Base Path
Git repositories are stored at `/tmp/athba_repos` by default. This can be customized:

```python
git_service = GitService(repos_base_path="/custom/path")
```

## Error Handling

The Developer agent handles various error scenarios:

### No Tickets Available
```
❌ No tickets available in the Backlog. Please create tickets first.
```

### Ticket Not Found
```
❌ Ticket 123abc not found.
```

### No Git Branch
```
❌ No Git branch exists for this ticket. Please create a branch first.
```

### Commit Without Code
```
❌ No pending code to commit. Please generate code first.
```

### Review Without Commits
```
❌ No code has been committed for this ticket. Please commit code before requesting review.
```

## Testing

The Developer agent includes comprehensive test coverage:

**Git Service Tests** (12 tests, all passing):
- Repository initialization
- Branch creation and checkout
- File commits
- Branch status
- Multiple commits

**Developer Agent Tests** (planned):
- Ticket claiming
- Branch creation
- Code generation
- Commit workflow
- Review requests

Run tests:
```bash
pytest tests/services/test_git_service.py -v
```

## Future Enhancements

### Planned Features
1. **Automatic Code Review**: Self-review code before committing
2. **Conflict Resolution**: Handle merge conflicts automatically
3. **Code Formatting**: Apply linters and formatters
4. **Test Generation**: Generate unit tests alongside code
5. **PR Creation**: Create pull requests for completed tickets

### Integration Plans
1. **CI/CD Pipeline**: Trigger builds on commits
2. **Code Quality Metrics**: Track code quality scores
3. **Performance Monitoring**: Monitor code execution performance

## Troubleshooting

### Git Repository Issues
If Git operations fail, check:
1. Git is installed: `git --version`
2. Repository path exists and is writable
3. Branch names are valid (no special characters)

### Code Generation Issues
If code generation fails:
1. Check LLM model is loaded
2. Verify ticket has clear requirements
3. Review LLM response for errors

### Commit Failures
If commits fail:
1. Ensure files were generated
2. Check branch exists
3. Verify no uncommitted changes

## API Reference

### DeveloperAgent Class

```python
class DeveloperAgent(IAgent):
    def __init__(self, session: Projses)
    async def initialize()
    async def run(self, content: str) -> list[ChatMessage]
    def report() -> dict
```

### GitService Class

```python
class GitService:
    def __init__(self, repos_base_path: str = "/tmp/athba_repos")
    async def initialize_repo(project_id: str, project_name: str) -> Dict
    async def create_branch(project_id: str, branch_name: str) -> Dict
    async def commit_files(project_id: str, files: Dict, message: str) -> Dict
    async def get_branch_status(project_id: str, branch_name: Optional[str]) -> Dict
    async def list_branches(project_id: str) -> List[str]
    async def checkout_branch(project_id: str, branch_name: str) -> Dict
    def repo_exists(project_id: str) -> bool
```

## Resources

- [Git Integration Documentation](GIT_INTEGRATION.md)
- [Testing Guide](TESTING.md)
- [Architecture Overview](ARCHITECTURE.md)
- [Phase 1B Implementation Summary](PHASE_1B_SUMMARY.md)

## Author

Developer Agent implemented as part of Phase 1B.

## License

Proprietary - Tom Pearce
