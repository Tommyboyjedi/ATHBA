# LLM Escalation System

Complete guide to the 3-failure LLM escalation system in ATHBA with independent tracking for Developer and Tester agents.

## Table of Contents

1. [Overview](#overview)
2. [Escalation Tiers](#escalation-tiers)
3. [The 3-Failure Rule](#the-3-failure-rule)
4. [Independent Tracking](#independent-tracking)
5. [Escalation Flow](#escalation-flow)
6. [Failure Scenarios](#failure-scenarios)
7. [Reset Conditions](#reset-conditions)
8. [Implementation Details](#implementation-details)

## Overview

The LLM Escalation System automatically manages which LLM tier (STANDARD, HEAVY, or MEGA) each agent uses based on their success/failure rate. This ensures:

- ✅ **Efficiency**: Use fast, lightweight LLMs for simple tasks
- ✅ **Quality**: Escalate to more powerful LLMs when needed
- ✅ **Independence**: Developer and Tester track separately
- ✅ **Automatic**: No manual intervention required
- ✅ **Fair**: Each agent gets 3 attempts per tier

### Key Principles

1. **Start Simple**: All agents begin with STANDARD tier (fast, local LLM)
2. **Escalate on Failure**: After 3 consecutive failures, move to next tier
3. **Reset on Success**: Any success resets back to STANDARD tier
4. **Independent Tracking**: Developer and Tester have separate counters
5. **Persistent**: Failure counts and tiers stored per ticket

## Escalation Tiers

### STANDARD Tier (Default)

**Characteristics:**
- Local LLM (codellama-7b for Developer/Tester)
- Fast inference (~1-2 seconds)
- Lower memory usage (~4GB)
- Good for straightforward tasks

**Best For:**
- Simple CRUD operations
- Basic test generation
- Standard patterns
- Common use cases

**Example:**
```python
ETier.STANDARD
# Uses: codellama-7b
# Speed: Fast
# Context: Basic
```

### HEAVY Tier (After 3 Failures)

**Characteristics:**
- Local LLM with more context
- Medium inference speed (~3-5 seconds)
- Moderate memory usage (~8GB)
- Better reasoning capabilities

**Best For:**
- Complex business logic
- Multi-step algorithms
- Advanced test scenarios
- Edge case handling

**Example:**
```python
ETier.HEAVY
# Uses: llama-3.2-3b or similar
# Speed: Medium
# Context: Enhanced
```

### MEGA Tier (After 6 Failures)

**Characteristics:**
- Maximum local LLM capability
- Slower inference (~5-10 seconds)
- Higher memory usage (~16GB)
- Best reasoning and understanding

**Best For:**
- Very complex algorithms
- System architecture
- Difficult edge cases
- Problem-solving

**Example:**
```python
ETier.MEGA
# Uses: llama-4-scout or similar
# Speed: Slower
# Context: Maximum
```

## The 3-Failure Rule

### Escalation Thresholds

```
Failure Count  →  Tier
─────────────────────────────
   0-2         →  STANDARD
   3-5         →  HEAVY
   6+          →  MEGA
   Success     →  STANDARD (reset)
```

### Why 3 Failures?

1. **Not Too Aggressive**: Gives LLM multiple chances at each tier
2. **Not Too Lenient**: Escalates before wasting too much time
3. **Balanced**: Good trade-off between speed and quality
4. **Tested**: Industry standard for retry logic

### Escalation Timeline Example

```
Attempt 1 (STANDARD) → Failure 1 ❌
Attempt 2 (STANDARD) → Failure 2 ❌
Attempt 3 (STANDARD) → Failure 3 ❌
                     → ESCALATE TO HEAVY ⬆️

Attempt 4 (HEAVY)    → Failure 4 ❌
Attempt 5 (HEAVY)    → Failure 5 ❌
Attempt 6 (HEAVY)    → Failure 6 ❌
                     → ESCALATE TO MEGA ⬆️

Attempt 7 (MEGA)     → Success ✅
                     → RESET TO STANDARD ⬇️
```

## Independent Tracking

### Why Independent?

Developer and Tester perform different tasks and may have different failure patterns:

**Developer:**
- Generates implementation code
- May struggle with complex algorithms
- Different failure modes than Tester

**Tester:**
- Generates test code
- May struggle with edge cases
- Different failure modes than Developer

**Independent tracking ensures fair escalation for each role.**

### Separate Counters

Each ticket tracks:

```python
@dataclass
class TicketModel:
    # Developer tracking
    developer_failure_count: int = 0
    developer_llm_tier: str = "standard"
    
    # Tester tracking (independent!)
    tester_failure_count: int = 0
    tester_llm_tier: str = "standard"
```

### Example: Independent Escalation

**Scenario:** Developer succeeds, Tester struggles

```
Developer:
  Attempt 1 → Success ✅
  Tier: STANDARD (never escalated)
  Count: 0

Tester:
  Attempt 1 → Failure ❌ (count: 1)
  Attempt 2 → Failure ❌ (count: 2)
  Attempt 3 → Failure ❌ (count: 3)
  → ESCALATE TO HEAVY ⬆️
  Attempt 4 → Success ✅
  → RESET TO STANDARD ⬇️
  Count: 0
```

**Result:** Each agent escalates independently based on their own performance.

## Escalation Flow

### Developer Escalation Flow

```
1. Developer Generates Code
   ├─> Code has syntax error → Failure
   ├─> Code doesn't pass tests → Failure
   └─> Code passes tests → Success

2. Record Result
   ├─> Failure → Increment developer_failure_count
   │   └─> Check if count % 3 == 0
   │       └─> Yes → Escalate developer_llm_tier
   │       └─> No → Stay on current tier
   │
   └─> Success → Reset developer_failure_count to 0
               └─> Reset developer_llm_tier to STANDARD
```

### Tester Escalation Flow

```
1. Tester Generates Test
   ├─> Test has syntax error → Failure
   ├─> Test doesn't run → Failure
   └─> Test runs successfully → Success

2. Record Result
   ├─> Failure → Increment tester_failure_count
   │   └─> Check if count % 3 == 0
   │       └─> Yes → Escalate tester_llm_tier
   │       └─> No → Stay on current tier
   │
   └─> Success → Reset tester_failure_count to 0
               └─> Reset tester_llm_tier to STANDARD
```

### Code Example

```python
from core.services.llm_escalation_manager import LlmEscalationManager

escalation_mgr = LlmEscalationManager()

# Record a failure
ticket, new_tier = await escalation_mgr.record_failure(
    ticket=ticket,
    agent_type="Developer",  # or "Tester"
    reason="Code generation failed: syntax error"
)

print(f"Failure count: {ticket.developer_failure_count}")
print(f"Current tier: {new_tier.value}")

# If it was the 3rd failure:
# Failure count: 3
# Current tier: heavy

# Record a success
ticket = await escalation_mgr.record_success(
    ticket=ticket,
    agent_type="Developer"
)

print(f"Failure count: {ticket.developer_failure_count}")  # 0
print(f"Current tier: {ticket.developer_llm_tier}")  # standard
```

## Failure Scenarios

### Developer Failure Scenarios

#### 1. Syntax Error

```python
# Generated code has syntax error
def calculate_total(items:
    return sum(items)
#                  ^ SyntaxError: invalid syntax
```

**Result:**
- Failure recorded for Developer
- Increment developer_failure_count
- Retry with same or escalated tier

#### 2. Logic Error

```python
# Code doesn't pass tests
def calculate_discount(price, percentage):
    return price * percentage  # Wrong! Should be price * (1 - percentage/100)
```

**Result:**
- Tests fail in execution
- Failure recorded for Developer
- Developer must fix and retry

#### 3. Runtime Error

```python
# Code crashes during execution
def divide_numbers(a, b):
    return a / b  # ZeroDivisionError if b == 0
```

**Result:**
- Tests fail with error
- Failure recorded for Developer
- Escalate if 3rd failure

### Tester Failure Scenarios

#### 1. Invalid Test Syntax

```python
# Test has syntax error
def test_calculation(:
    assert calculate(5) == 10
#                      ^ SyntaxError
```

**Result:**
- Failure recorded for Tester
- Increment tester_failure_count
- Retry with same or escalated tier

#### 2. Test Doesn't Run

```python
# Missing imports or invalid pytest
def test_something():
    result = nonexistent_function()  # NameError
    assert result == True
```

**Result:**
- pytest execution fails
- Failure recorded for Tester
- Escalate if 3rd failure

#### 3. Poor Test Coverage

```python
# Test doesn't actually test anything useful
def test_function_exists():
    assert calculate_total is not None  # Useless test
```

**Result:**
- May be flagged during review
- Could record failure
- Regenerate with better guidance

## Reset Conditions

### When Reset Happens

**Automatic Reset on Success:**

```python
# Any success resets to STANDARD tier

# Developer scenario:
Developer generates code → Success
├─> developer_failure_count = 0
└─> developer_llm_tier = "standard"

# Tester scenario:
Tester generates test → Success
├─> tester_failure_count = 0
└─> tester_llm_tier = "standard"
```

### Why Reset?

1. **Start Fresh**: Each ticket gets a fair start
2. **Efficiency**: Don't waste powerful LLM on simple tasks
3. **Learning**: Agent may have learned from failures
4. **Fair Escalation**: Success proves capability

### Reset Examples

#### Example 1: Developer Escalates Then Succeeds

```
Ticket #123 (Complex Algorithm)
├─> Failure 1 (STANDARD) ❌
├─> Failure 2 (STANDARD) ❌
├─> Failure 3 (STANDARD) ❌
├─> ESCALATE TO HEAVY ⬆️
├─> Failure 4 (HEAVY) ❌
├─> Failure 5 (HEAVY) ❌
├─> Failure 6 (HEAVY) ❌
├─> ESCALATE TO MEGA ⬆️
└─> Success 7 (MEGA) ✅
    └─> RESET TO STANDARD ⬇️

Ticket #124 (Simple CRUD)
└─> Success 1 (STANDARD) ✅
    └─> Already at STANDARD, no change
```

#### Example 2: Mixed Success/Failure

```
Ticket #125
├─> Success 1 (STANDARD) ✅
│   └─> Reset (already at STANDARD)
├─> Failure 1 (STANDARD) ❌ (new ticket)
├─> Success 2 (STANDARD) ✅
│   └─> Reset to count 0
└─> Next attempt starts at STANDARD
```

## Implementation Details

### LlmEscalationManager Class

**Location:** `core/services/llm_escalation_manager.py`

**Key Methods:**

```python
class LlmEscalationManager:
    def __init__(self, max_failures_per_tier: int = 3):
        self.max_failures_per_tier = 3  # Configurable
    
    async def record_failure(
        ticket: TicketModel,
        agent_type: str,  # "Developer" or "Tester"
        reason: str
    ) -> Tuple[TicketModel, ETier]:
        """Records failure and escalates if needed."""
        # Increments failure count
        # Calculates new tier
        # Updates ticket
        # Returns updated ticket and new tier
    
    async def record_success(
        ticket: TicketModel,
        agent_type: str
    ) -> TicketModel:
        """Records success and resets to STANDARD."""
        # Resets failure count to 0
        # Resets tier to STANDARD
        # Updates ticket
        # Returns updated ticket
    
    def get_current_tier(
        ticket: TicketModel,
        agent_type: str
    ) -> ETier:
        """Gets current tier for agent on ticket."""
        # Returns ETier.STANDARD, .HEAVY, or .MEGA
```

### Usage in Agent Behaviors

#### Developer Behavior Example

```python
# In generate_code_behavior.py

try:
    # Generate code with LLM
    code = await llm_exchange.get_response()
    
    # Code generation succeeded
    await agent.escalation_manager.record_success(
        ticket=ticket,
        agent_type="Developer"
    )
    
except Exception as e:
    # Code generation failed
    ticket, new_tier = await agent.escalation_manager.record_failure(
        ticket=ticket,
        agent_type="Developer",
        reason=f"Code generation failed: {str(e)}"
    )
    
    # new_tier is automatically escalated if 3rd/6th failure
```

#### Tester Behavior Example

```python
# In generate_test_behavior.py

# Get current tier for this ticket
current_tier = agent.escalation_manager.get_current_tier(
    ticket=ticket,
    agent_type="Tester"
)

# Use escalated tier in LLM request
response = await LlmExchange(
    agent=agent,
    session=session,
    content=prompt,
    tier=current_tier,  # Uses escalated tier if applicable
    use_cloud=False
).get_response()

# Record result based on success/failure
```

### Database Persistence

**Ticket Fields:**

```python
@dataclass
class TicketModel:
    # Developer escalation
    developer_failure_count: int = 0
    developer_llm_tier: str = "standard"
    
    # Tester escalation
    tester_failure_count: int = 0
    tester_llm_tier: str = "standard"
```

**History Tracking:**

```python
# Escalation events are logged in history
HistoryEntry(
    timestamp=datetime.utcnow(),
    agent="Developer",
    action="llm_escalation",
    details="Developer failure #3: Syntax error. Escalated to HEAVY tier."
)
```

## Monitoring and Visibility

### Viewing Escalation Status

**In Ticket History:**
```
10:30 AM - Developer claimed ticket
10:31 AM - Developer failure #1: Code generation error
10:32 AM - Developer failure #2: Syntax error in generated code
10:33 AM - Developer failure #3: Logic error. Escalated to HEAVY tier.
10:35 AM - Developer failure #4: Still failing at HEAVY
10:36 AM - Developer failure #5: Edge case not handled
10:37 AM - Developer failure #6: Complex algorithm. Escalated to MEGA tier.
10:40 AM - Developer success! Code passes all tests. Tier reset to STANDARD.
```

**In Agent Status:**
```
User: "status"

Developer: 📊 Developer Status
Current Ticket: #456 - Complex Algorithm
Failure Count: 4
Current LLM Tier: HEAVY
Next Escalation: After 2 more failures → MEGA
```

## Best Practices

### 1. Trust the System

- ✅ Let escalation happen naturally
- ✅ Don't manually intervene
- ✅ System learns optimal tier per task

### 2. Provide Detailed Requirements

- ✅ Clear ticket descriptions reduce failures
- ✅ Examples help LLM understand
- ✅ Edge cases documented upfront

### 3. Review Patterns

- ✅ Check which tickets escalate frequently
- ✅ Identify complex requirements early
- ✅ Improve ticket quality over time

### 4. Monitor Escalations

- ✅ Track escalation frequency
- ✅ Identify problematic patterns
- ✅ Adjust ticket complexity if needed

## Configuration

### Adjusting Failure Threshold

Default is 3 failures per tier. Can be configured:

```python
# In LlmEscalationManager initialization
escalation_mgr = LlmEscalationManager(max_failures_per_tier=5)

# Now escalates after 5 failures instead of 3
```

**Considerations:**
- **Lower (2)**: Faster escalation, but less patience
- **Higher (5)**: More patience, but slower to adapt
- **Default (3)**: Balanced approach

### Adding New Tiers

Future: Could add more tiers like ULTRA or use cloud LLMs:

```python
class ETier(str, Enum):
    STANDARD = "standard"   # Local, fast
    HEAVY = "heavy"         # Local, powerful
    MEGA = "mega"           # Local, maximum
    ULTRA = "ultra"         # Cloud, Claude
```

## Summary

The LLM Escalation System provides:

✅ **Automatic Intelligence**: Right LLM for the task
✅ **Efficiency**: Start fast, escalate as needed
✅ **Fairness**: 3 attempts per tier
✅ **Independence**: Developer and Tester track separately
✅ **Transparency**: Full history of escalations
✅ **Reset on Success**: Rewards good performance
✅ **Persistence**: Survives across sessions

**Result:** Optimal LLM usage with automatic quality management.
