# TDD Workflow Guide

Complete guide to Test-Driven Development workflow in ATHBA following Uncle Bob's Three Laws.

## Table of Contents

1. [Uncle Bob's Three Laws of TDD](#uncle-bobs-three-laws-of-tdd)
2. [The Red-Green-Refactor Cycle](#the-red-green-refactor-cycle)
3. [ATHBA TDD Implementation](#athba-tdd-implementation)
4. [Complete Workflow Example](#complete-workflow-example)
5. [Best Practices](#best-practices)
6. [Common Pitfalls](#common-pitfalls)

## Uncle Bob's Three Laws of TDD

ATHBA strictly enforces Robert C. Martin's (Uncle Bob) **Three Laws of TDD**:

### Law #1: You must write a failing test before writing any production code

**In ATHBA:** The Tester agent MUST generate tests FIRST before the Developer writes implementation.

```
🔴 RED PHASE (Tester)
├─> Tester analyzes requirements
├─> Tester generates test code
├─> Tester commits test to branch
└─> Test FAILS (no implementation yet)
```

### Law #2: You must not write more of a test than is sufficient to fail

**In ATHBA:** The Tester generates focused, minimal tests that verify specific requirements.

**Example:**
```python
# Good - Minimal test that will fail
def test_user_authentication_returns_token():
    result = authenticate_user("user@test.com", "password123")
    assert result["token"] is not None

# Bad - Too much at once
def test_entire_authentication_system():
    # Tests login, logout, refresh, permissions, etc.
    # Too comprehensive - break into multiple tests
```

### Law #3: You must not write more production code than is sufficient to pass the test

**In ATHBA:** The Developer writes only enough code to make the current test pass.

**Example:**
```python
# Good - Minimal implementation to pass test
def authenticate_user(email, password):
    # Just enough to pass the test
    if email and password:
        return {"token": "abc123"}
    return {"token": None}

# Bad - Over-implementation
def authenticate_user(email, password):
    # Includes JWT generation, database lookup, 
    # password hashing, session management, etc.
    # when only token return was tested
```

## The Red-Green-Refactor Cycle

### 🔴 RED: Write a Failing Test

**Goal:** Create a test that fails because the functionality doesn't exist yet.

**In ATHBA:**
```
Tester: "generate test"
└─> Generates pytest code
└─> Test should FAIL
└─> Commit test to branch
```

**Example Test (RED Phase):**
```python
# tests/test_user_authentication.py
import pytest
from src.auth import authenticate_user

def test_authenticate_user_returns_success():
    """Test that valid credentials return success."""
    result = authenticate_user("test@example.com", "password123")
    
    assert result["success"] is True
    assert "token" in result
    assert result["token"] is not None
```

**Expected Output:**
```
FAILED tests/test_user_authentication.py::test_authenticate_user_returns_success
ModuleNotFoundError: No module named 'src.auth'
```

### 🟢 GREEN: Make the Test Pass

**Goal:** Write the minimal code to make the test pass.

**In ATHBA:**
```
Developer: "generate code"
└─> Generates implementation
└─> Code makes test pass
└─> Commit code to branch

Tester: "execute tests"
└─> Runs pytest
└─> Tests should PASS
```

**Example Implementation (GREEN Phase):**
```python
# src/auth.py
def authenticate_user(email, password):
    """Authenticate a user with email and password."""
    # Minimal implementation to pass test
    if email and password:
        return {
            "success": True,
            "token": "generated_token_" + email
        }
    return {
        "success": False,
        "token": None
    }
```

**Expected Output:**
```
PASSED tests/test_user_authentication.py::test_authenticate_user_returns_success
```

### 🔵 REFACTOR: Improve Code Quality

**Goal:** Clean up code while keeping tests green.

**In ATHBA:**
```
Developer/Tester: Discuss improvements
Developer: Refactors code
Tester: "execute tests"
└─> Tests should STILL PASS
```

**Example Refactoring:**
```python
# src/auth.py
import hashlib
from datetime import datetime

def authenticate_user(email, password):
    """Authenticate a user with email and password."""
    if not email or not password:
        return {"success": False, "token": None}
    
    # Refactored: Better token generation
    token = _generate_token(email)
    return {"success": True, "token": token}

def _generate_token(email):
    """Generate a token for the user."""
    timestamp = datetime.utcnow().isoformat()
    raw = f"{email}:{timestamp}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

**Tests still pass:**
```
PASSED tests/test_user_authentication.py::test_authenticate_user_returns_success
```

## ATHBA TDD Implementation

### Workflow Phases

#### Phase 1: Ticket Assignment

```
Developer → Backlog
  ├─> Claims ticket
  ├─> Creates branch (ticket/<id>-<title>)
  └─> Moves to "In Progress"
```

#### Phase 2: Initial Analysis

```
Developer → Analyze Requirements
  ├─> Reads ticket description
  ├─> LLM analyzes what to build
  └─> Requests review

Tester → Claims Review
  ├─> Claims ticket from Review
  ├─> Analyzes requirements
  └─> Prepares to generate tests
```

#### Phase 3: TDD RED - Test First

```
🔴 Tester → Generate Test (RED Phase)
  ├─> Generates pytest code
  ├─> Test should FAIL (no implementation)
  ├─> Commits test to branch
  └─> Updates ticket.test_files

Expected: Test FAILS because no implementation exists yet
```

#### Phase 4: TDD GREEN - Implementation

```
🟢 Developer → Generate Code (GREEN Phase)
  ├─> Reads failing tests
  ├─> Generates minimal implementation
  ├─> Commits code to branch
  └─> Requests review

Tester → Execute Tests
  ├─> Runs pytest on branch
  ├─> Captures results
  └─> Updates ticket.test_results

Expected: Tests PASS after implementation
```

#### Phase 5: Verification

```
Tester → Verify Pass (GREEN Verification)
  ├─> Checks all tests passing
  ├─> Verifies test coverage
  └─> Decides: Approve or Refactor

If all tests pass:
  └─> Tester → Approve Code → Done

If tests fail:
  └─> Tester → Reject Code → Developer fixes
      └─> Records failure for Developer
      └─> Escalates LLM tier if 3rd/6th failure
```

#### Phase 6: Completion

```
✅ Ticket Approved
  ├─> Moved to "Done" column
  ├─> All tests passing (100% pass rate)
  ├─> Failure counters reset
  └─> Ready for deployment
```

## Complete Workflow Example

### Scenario: Implement User Registration

**Ticket #456**: Implement user registration endpoint

**Requirements:**
- Accept email and password
- Validate email format
- Hash password before storage
- Return success/failure

---

### Step-by-Step Execution

#### 1. Developer Claims Ticket

```
User → Developer Agent

User: "claim ticket"
Developer: ✅ Claimed ticket #456: Implement user registration

User: "create branch"
Developer: ✅ Created branch: ticket/456-implement-user-registration

User: "analyze ticket"
Developer: 🔍 Analysis complete:
  - Need register_user() function
  - Email validation required
  - Password hashing required
  - Return dict with success/message

User: "request review"
Developer: ✅ Moved to Review, assigned to Tester
```

#### 2. Tester Claims and Analyzes

```
User → Tester Agent

User: "claim review"
Tester: ✅ Claimed ticket #456 for review

User: "analyze code"
Tester: 🔍 No implementation yet - will generate tests first (TDD RED)
```

#### 3. 🔴 RED: Tester Generates Test FIRST

```
User: "generate test"

Tester: ✅ Test Generated (TDD RED Phase)

File: tests/test_user_registration.py
```

**Generated Test:**
```python
# tests/test_user_registration.py
import pytest
from src.user_management import register_user

def test_register_user_with_valid_data():
    """Test user registration with valid email and password."""
    result = register_user("newuser@example.com", "SecurePass123")
    
    assert result["success"] is True
    assert "user_id" in result
    assert result["user_id"] is not None

def test_register_user_with_invalid_email():
    """Test registration fails with invalid email."""
    result = register_user("invalid-email", "password123")
    
    assert result["success"] is False
    assert "error" in result
    assert "email" in result["error"].lower()

def test_register_user_with_weak_password():
    """Test registration fails with weak password."""
    result = register_user("user@example.com", "123")
    
    assert result["success"] is False
    assert "error" in result
    assert "password" in result["error"].lower()
```

```
User: "commit test"
Tester: ✅ Tests committed to branch

TDD Status: 🔴 RED - Tests written, no implementation
Expected: Tests will FAIL
```

#### 4. Execute Tests (Should Fail)

```
User: "execute tests"

Tester: ❌ Test Execution Complete

Status: ERROR
- ❌ Failed: 0
- ⚠️ Errors: 3
- Total: 3
- Pass Rate: 0.0%

Output:
ModuleNotFoundError: No module named 'src.user_management'

✅ This is EXPECTED in RED phase!
Next: Developer implements code to make tests pass
```

#### 5. 🟢 GREEN: Developer Implements Code

```
User → Developer Agent

User: "generate code"

Developer: ✅ Code Generated

File: src/user_management.py
```

**Generated Implementation:**
```python
# src/user_management.py
import re
import hashlib
import uuid

def register_user(email, password):
    """
    Register a new user with email and password.
    
    Args:
        email: User email address
        password: User password
        
    Returns:
        Dict with success status and user_id or error message
    """
    # Validate email
    if not _is_valid_email(email):
        return {
            "success": False,
            "error": "Invalid email format"
        }
    
    # Validate password strength
    if len(password) < 8:
        return {
            "success": False,
            "error": "Password must be at least 8 characters"
        }
    
    # Hash password (minimal implementation)
    hashed_password = hashlib.sha256(password.encode()).hexdigest()
    
    # Generate user ID
    user_id = str(uuid.uuid4())
    
    # In real implementation, would save to database
    # For now, just return success
    return {
        "success": True,
        "user_id": user_id
    }

def _is_valid_email(email):
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None
```

```
User: "commit code"
Developer: ✅ Code committed

User: "request review"
Developer: ✅ Moved to Review for Tester
```

#### 6. Tester Executes Tests (Should Pass)

```
User → Tester Agent

User: "execute tests"

Tester: ✅ Test Execution Complete

Status: SUCCESS
- ✅ Passed: 3
- ❌ Failed: 0
- ⚠️ Errors: 0
- Total: 3
- Pass Rate: 100.0%
- Duration: 0.34s

All tests passing! 🎉
```

#### 7. Verify and Approve

```
User: "verify pass"

Tester: ✅ TDD GREEN Phase Complete!

TDD Cycle Status:
1. ✅ RED: Tests written first
2. ✅ GREEN: Code passes all tests
3. 🔵 REFACTOR: Optional

Next: Approve code or request refactoring

User: "approve code"

Tester: ✅ Code Approved!

Status: Moved to Done ✓
All 3 tests passing (100% pass rate)

Ticket #456 is complete!
```

---

## Best Practices

### 1. Write Minimal Tests

**Good:**
```python
def test_add_function_returns_sum():
    assert add(2, 3) == 5
```

**Bad:**
```python
def test_add_function_complete_suite():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0
    assert add(100, 200) == 300
    # Too much in one test - split into multiple tests
```

### 2. One Concept Per Test

**Good:**
```python
def test_user_creation():
    user = create_user("test@example.com")
    assert user is not None

def test_user_has_email():
    user = create_user("test@example.com")
    assert user.email == "test@example.com"
```

**Bad:**
```python
def test_user_everything():
    user = create_user("test@example.com")
    assert user is not None
    assert user.email == "test@example.com"
    assert user.is_active is True
    assert user.created_at is not None
    # Testing too many things - hard to debug failures
```

### 3. Test Behavior, Not Implementation

**Good:**
```python
def test_password_is_hashed():
    user = create_user("test@example.com", "password123")
    assert user.password != "password123"  # It's hashed
    assert len(user.password) > 20  # Hash is long
```

**Bad:**
```python
def test_password_uses_sha256():
    user = create_user("test@example.com", "password123")
    expected = hashlib.sha256("password123".encode()).hexdigest()
    assert user.password == expected
    # Too specific - locks in implementation
```

### 4. Follow the TDD Cycle Strictly

```
✅ Always write test FIRST
✅ Watch test FAIL
✅ Write minimal code to pass
✅ Watch test PASS
✅ Refactor if needed
✅ Repeat

❌ Don't write code before test
❌ Don't skip failing step
❌ Don't write extra features
❌ Don't refactor without tests
```

## Common Pitfalls

### 1. Writing Code Before Tests

**Problem:** Defeats the purpose of TDD

**Solution:** ALWAYS use Tester to generate tests FIRST

### 2. Tests That Always Pass

**Problem:** Tests that don't actually test anything

**Example:**
```python
def test_user_creation():
    user = create_user("test@example.com")
    assert True  # Always passes - useless test
```

**Solution:** Test real conditions
```python
def test_user_creation():
    user = create_user("test@example.com")
    assert user.email == "test@example.com"
```

### 3. Testing Too Much at Once

**Problem:** Hard to identify what failed

**Solution:** Break into smaller, focused tests

### 4. Skipping the RED Phase

**Problem:** Never confirming test can fail

**Solution:** Always run tests before implementation to see them fail

### 5. Over-Implementation

**Problem:** Writing more code than test requires

**Solution:** Write ONLY what's needed to pass current test

## LLM Escalation in TDD

### When Escalation Happens

**Developer Failures:**
- Cannot generate code that passes tests
- Code has syntax errors
- Logic errors prevent test passage

**Tester Failures:**
- Cannot generate valid test code
- Tests have syntax errors
- Tests don't properly validate requirements

### Escalation Tiers

```
STANDARD (Failures 0-2)
├─> Fast local LLM
├─> Basic code generation
└─> Good for simple tasks

HEAVY (Failures 3-5)
├─> More context
├─> Better reasoning
└─> Complex logic handling

MEGA (Failures 6+)
├─> Maximum capability
├─> Advanced reasoning
└─> Difficult problems
```

### Best Practices with Escalation

1. **Trust the Process**: Let escalation happen naturally
2. **Detailed Requirements**: Help prevent failures with clear specs
3. **Review Failures**: Learn from what caused escalation
4. **Reset Happens**: Success resets to STANDARD tier

## Summary

ATHBA's TDD implementation:

✅ **Enforces Uncle Bob's Three Laws**
✅ **Test-First Development** (RED phase)
✅ **Minimal Implementation** (GREEN phase)
✅ **Continuous Verification** (Test execution)
✅ **Quality Assurance** (Approve/Reject)
✅ **Automatic Escalation** (3-failure system)
✅ **Independent Tracking** (Dev & Test separate)

**Result:** True test-driven development with automatic quality enforcement and intelligent LLM escalation.
