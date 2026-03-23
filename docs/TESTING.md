# Testing Guide for ATHBA Phase 1A

## Overview

This guide covers testing the Architect Agent and Specification-to-Tickets workflow implemented in Phase 1A.

## Quick Start

### Install Test Dependencies

```bash
# Using Poetry (recommended)
poetry install

# Or update if already installed
poetry update
```

This will install:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `pytest-mock` - Mocking utilities
- `pytest-django` - Django integration

### Run All Tests

```bash
# Run all tests with verbose output
poetry run pytest -v

# Run with coverage report
poetry run pytest --cov=core --cov-report=html

# Run specific test file
poetry run pytest tests/agents/test_architect_agent.py -v

# Run specific test
poetry run pytest tests/agents/test_architect_agent.py::test_architect_agent_initialization -v
```

## Test Organization

```
tests/
├── conftest.py                          # Shared fixtures
├── agents/
│   ├── __init__.py
│   └── test_architect_agent.py         # 7 test cases
├── behaviors/
│   ├── __init__.py
│   └── test_analyze_spec_behavior.py   # 8 test cases
├── api/
│   ├── __init__.py
│   └── test_tickets.py                 # 5 test cases
└── integration/
    ├── __init__.py
    └── test_spec_to_tickets_flow.py    # 5 test cases

Total: 25 test cases
```

## Test Categories

### Unit Tests

#### Architect Agent Tests
Location: `tests/agents/test_architect_agent.py`

Tests:
- Agent initialization and configuration
- Behavior loading
- LLM prompt structure
- Agent execution and behavior triggering
- Report generation

```bash
poetry run pytest tests/agents/test_architect_agent.py -v
```

#### Analyze Spec Behavior Tests
Location: `tests/behaviors/test_analyze_spec_behavior.py`

Tests:
- Intent recognition
- Spec retrieval and parsing
- Ticket generation from LLM responses
- JSON parsing with extra text
- Fallback ticket generation
- Section text extraction
- Error handling

```bash
poetry run pytest tests/behaviors/test_analyze_spec_behavior.py -v
```

#### Ticket Repository Tests
Location: `tests/api/test_tickets.py`

Tests:
- Listing all tickets
- Creating tickets
- Getting backlog tickets
- Counting tickets
- Query filters

```bash
poetry run pytest tests/api/test_tickets.py -v
```

### Integration Tests

Location: `tests/integration/test_spec_to_tickets_flow.py`

Tests:
- Spec finalization triggering Architect
- Full workflow from spec to tickets
- Ticket metadata correctness
- Spec approval metadata
- Async delegation

```bash
poetry run pytest tests/integration/ -v
```

## Test Fixtures

Available in `tests/conftest.py`:

### `sample_session`
Creates a test Projses session object.

### `sample_project`
Creates a test Project object.

### `sample_spec_content`
Provides sample specification content with sections.

### `sample_spec_document`
Complete spec document as stored in MongoDB.

### `sample_ticket`
Single ticket example.

### `sample_tickets`
List of 3 sample ticket data dictionaries.

## Manual Testing Workflow

### Prerequisites

1. **Start MongoDB** (if using MongoDB backend):
   ```bash
   mongod --dbpath /path/to/data
   ```

2. **Start LLM Server**:
   ```bash
   poetry run uvicorn llm_service.llm_server:app --host 127.0.0.1 --port 8011 --reload
   ```

3. **Start Django App**:
   ```bash
   poetry run uvicorn athba.asgi:app --host 0.0.0.0 --port 8000 --reload
   ```

### Test Workflow Steps

#### 1. Create a Project

```
Navigate to: http://localhost:8000
Chat: "Create a new project called Test Project"
```

Expected: PM agent creates project and routes to Spec agent.

#### 2. Build Specification

```
Chat: "This is a web app for managing customer orders. 
       Users should be able to:
       - Register and login
       - Create and view orders  
       - Track order status
       - Make payments via Stripe"
```

Expected: Spec agent adds content to specification.

#### 3. Finalize Specification

```
Chat: "finalize the spec"
```

Expected:
- Spec agent confirms finalization
- Architect agent is triggered automatically
- Tickets are generated
- Chat shows ticket summary

#### 4. View Kanban Board

```
Navigate to: http://localhost:8000/api/kanban/
```

Expected:
- Kanban board displays
- "Backlog" column contains generated tickets
- Each ticket shows title, severity, label
- Tickets are from the specification

#### 5. Verify Tickets in Database

```bash
# Connect to MongoDB
mongosh

use athba
db.tickets.find({"project_id": "your-project-id"}).pretty()
```

Expected fields:
- `title`, `description`
- `severity`: High, Medium, or Low
- `label`: Feature, Testing, etc.
- `column`: "Backlog"
- `agents`: [] (empty)
- `history`: Contains creation event by Architect

### Expected Ticket Examples

Based on the sample spec above, expect tickets like:

```
✅ I've analyzed the specification and created 5 tickets:

  • Implement user authentication system [High] - Feature
  • Build order management interface [High] - Feature
  • Add order status tracking [Medium] - Feature
  • Integrate Stripe payment processing [Medium] - Feature
  • Write comprehensive test suite [Medium] - Testing
```

## Troubleshooting

### Tests Fail with Import Errors

```bash
# Ensure you're in the project root
cd /path/to/ATHBA

# Reinstall dependencies
poetry install

# Set PYTHONPATH
export PYTHONPATH=$PYTHONPATH:/path/to/ATHBA
```

### Tests Fail with Django Settings Error

```bash
# Ensure DJANGO_SETTINGS_MODULE is set
export DJANGO_SETTINGS_MODULE=athba.settings

# Or use pytest.ini (already configured)
```

### LLM-Related Tests Timeout

LLM tests use mocks and should not actually call the LLM server. If they timeout:
- Check that mocks are properly configured
- Ensure `patch` decorators are applied
- Verify async/await patterns

### MongoDB Connection Issues

For tests that use MongoDB:
- Tests should use mocks for MongoDB operations
- Real MongoDB is only needed for manual testing
- Check that `AsyncMock` is used for async repo methods

## Test Coverage Goals

Current coverage targets:

- **Agent Classes**: 90%+ (core functionality)
- **Behaviors**: 85%+ (including error paths)
- **Repositories**: 80%+ (CRUD operations)
- **Integration**: 70%+ (happy paths)

Run coverage report:
```bash
poetry run pytest --cov=core --cov-report=term-missing
poetry run pytest --cov=core --cov-report=html
# View: open htmlcov/index.html
```

## Continuous Integration

### GitHub Actions Setup (Future)

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install poetry
          poetry install
      - name: Run tests
        run: |
          poetry run pytest --cov=core --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## Performance Testing

For manual performance verification:

1. **Spec Analysis Time**: Should complete in < 30 seconds
2. **Ticket Creation**: Should handle 10+ tickets without issues
3. **Kanban Load**: Should render 50+ tickets smoothly
4. **Chat Response**: Real-time streaming should feel instant

## Next Steps

After verifying Phase 1A tests pass:

1. **Phase 1B**: Add Git integration tests
2. **Phase 1C**: Add Developer/Tester agent tests
3. **UI Tests**: Add Selenium/Playwright for UI testing
4. **Load Tests**: Test with multiple concurrent projects

## Support

If you encounter test failures:

1. Check the error message and stack trace
2. Verify fixtures are properly configured
3. Ensure mocks match actual method signatures
4. Review test documentation above
5. Check that dependencies are up to date

## Summary

The Phase 1A test suite provides comprehensive coverage of:
- Architect agent functionality
- Spec-to-tickets workflow
- Ticket repository operations
- Integration between agents
- Error handling and fallbacks

Running these tests validates that the core functionality is working correctly before proceeding to Phase 1B (Git integration) and Phase 1C (TDD workflow).
