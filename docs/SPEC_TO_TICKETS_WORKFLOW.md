# Specification to Tickets Workflow

## Overview

This document describes the end-to-end workflow for transforming a project specification into actionable development tickets in ATHBA.

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     SPECIFICATION PHASE                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  PM Agent        │
                    │ (User Interface) │
                    └────────┬─────────┘
                             │ "Create new project"
                             ▼
                    ┌──────────────────┐
                    │  Spec Agent      │
                    │ (Spec Builder)   │
                    └────────┬─────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
                ▼                         ▼
    User asks questions         Spec Agent adds content
    provides requirements       to specification document
                │                         │
                └────────────┬────────────┘
                             │
                             ▼
                    Multiple iterations
                    of refinement
                             │
                             ▼
                    User: "finalize spec"
                             │
┌────────────────────────────┴────────────────────────────┐
│                  FINALIZATION PHASE                      │
└──────────────────────────────────────────────────────────┘
                             │
                             ▼
            ┌────────────────────────────┐
            │ FinalizeSpecBehavior       │
            │ - Mark spec as approved    │
            │ - Add approval metadata    │
            └────────────┬───────────────┘
                         │
                         ▼
            Spawn async task to trigger
            Architect Agent
                         │
┌────────────────────────┴────────────────────────────┐
│                  ANALYSIS PHASE                      │
└──────────────────────────────────────────────────────┘
                         │
                         ▼
            ┌────────────────────────────┐
            │  Architect Agent           │
            │  AnalyzeSpecBehavior       │
            └────────────┬───────────────┘
                         │
                         ▼
            Retrieve approved spec from MongoDB
                         │
                         ▼
            Extract text from spec sections
                         │
                         ▼
            ┌────────────────────────────┐
            │ LLM Ticket Generation      │
            │ - Analyze requirements     │
            │ - Break into features      │
            │ - Create ticket structure  │
            └────────────┬───────────────┘
                         │
                ┌────────┴────────┐
                │                 │
                ▼                 ▼
        Success: JSON        Failure: Parse error
        tickets array                │
                │                    ▼
                │            Fallback ticket
                │            generation
                │                    │
                └────────┬───────────┘
                         │
                         ▼
            Validate ticket structure
            (title, description, severity, etc.)
                         │
┌────────────────────────┴────────────────────────────┐
│                  TICKET CREATION PHASE               │
└──────────────────────────────────────────────────────┘
                         │
                         ▼
            For each ticket:
            - Set project_id
            - Set column = "Backlog"
            - Set agents = []
            - Add creation history entry
            - Calculate due date
                         │
                         ▼
            ┌────────────────────────────┐
            │ TicketRepo.create()        │
            │ - Insert into MongoDB      │
            │ - Return with ID           │
            └────────────┬───────────────┘
                         │
                         ▼
            Stream success message to chat
            with ticket summary
                         │
┌────────────────────────┴────────────────────────────┐
│                  VISUALIZATION PHASE                 │
└──────────────────────────────────────────────────────┘
                         │
                         ▼
            ┌────────────────────────────┐
            │  Kanban Board UI           │
            │  - Display in Backlog      │
            │  - Available for editing   │
            │  - Ready for assignment    │
            └────────────────────────────┘
```

## Detailed Steps

### 1. Specification Creation

**Actors**: User, PM Agent, Spec Agent

**Process**:
1. User initiates project creation through PM agent
2. PM delegates to Spec agent
3. Spec agent engages in dialogue to gather requirements
4. User provides project details, features, requirements
5. Spec agent structures information into specification document
6. Spec is saved to MongoDB with versioning

**MongoDB Structure**:
```json
{
  "project_id": "uuid",
  "version": 1,
  "content": {
    "sections": [
      {
        "name": "overview",
        "body": "Project description..."
      },
      {
        "name": "requirements",
        "body": "1. Requirement one\n2. Requirement two..."
      }
    ]
  },
  "author": "human",
  "created_at": "2024-01-15T10:00:00Z"
}
```

### 2. Specification Finalization

**Actor**: Spec Agent (FinalizeSpecBehavior)

**Trigger**: User says "finalize spec" or equivalent

**Process**:
1. Spec agent detects `finalize_spec` intent
2. Retrieves latest spec version from MongoDB
3. Updates spec document with approval metadata:
   ```python
   {
     "approved": True,
     "approved_by": "human",
     "approved_at": datetime.utcnow()
   }
   ```
4. Returns confirmation message to user
5. Spawns async task to run Architect agent

**Key Code**:
```python
asyncio.create_task(self._run_architect(agent.session))
```

### 3. Ticket Generation

**Actor**: Architect Agent (AnalyzeSpecBehavior)

**Process**:

#### 3.1 Spec Retrieval
```python
spec_versions = await agent.spec_repo.find(
    {"project_id": agent.session.project_id},
    sort=[("version", -1)],
    limit=1
)
```

#### 3.2 Text Extraction
- Iterate through spec sections
- Concatenate body text
- Handle different content formats (dict, string, sections)

#### 3.3 LLM Analysis
```python
prompt = f"""Analyze this specification and create tickets.
Specification: {spec_text}
Return JSON array of tickets with title, description, severity, label, eta."""

response = await LlmExchange.get_response()
```

#### 3.4 Parsing & Validation
- Extract JSON array from LLM response
- Validate required fields
- Set defaults for missing fields
- Fallback to hardcoded tickets on parse failure

#### 3.5 Ticket Creation
```python
for ticket_data in tickets:
    ticket = TicketModel(
        project_id=project_id,
        title=ticket_data["title"],
        description=ticket_data["description"],
        severity=ticket_data["severity"],
        label=ticket_data["label"],
        eta=ticket_data["eta"],
        column="Backlog",
        agents=[],
        history=[HistoryEntry(
            event="created",
            actor="Architect",
            details="Generated from spec"
        )]
    )
    created = await ticket_repo.create(ticket)
```

### 4. Ticket Storage

**Repository**: TicketRepo

**MongoDB Collection**: `tickets`

**Document Structure**:
```json
{
  "_id": ObjectId("..."),
  "project_id": "uuid",
  "title": "Implement user authentication",
  "description": "Create login/logout with JWT...",
  "severity": "High",
  "label": "Feature",
  "eta": "1 week",
  "estimated_days": 7,
  "column": "Backlog",
  "agents": [],
  "due": ISODate("2024-01-22T10:00:00Z"),
  "created_at": ISODate("2024-01-15T10:00:00Z"),
  "updated_at": ISODate("2024-01-15T10:00:00Z"),
  "history": [
    {
      "timestamp": ISODate("2024-01-15T10:00:00Z"),
      "event": "created",
      "actor": "Architect",
      "details": "Ticket generated from specification analysis"
    }
  ]
}
```

### 5. User Notification

**Method**: Server-Sent Events (SSE) via chat stream

**Message Format**:
```
✅ I've analyzed the specification and created 5 tickets:

  • Implement user authentication [High] - Feature
  • Build order management interface [High] - Feature
  • Integrate Stripe payments [Medium] - Feature
  • Add user profile management [Medium] - Feature
  • Write comprehensive tests [Medium] - Testing

All tickets have been added to the Backlog. You can view them on the Kanban board.
```

### 6. Kanban Visualization

**Endpoint**: `/api/kanban/`

**Process**:
1. User navigates to Kanban board
2. Endpoint fetches tickets for current project:
   ```python
   tickets = await TicketRepo().list_all(project_id)
   ```
3. Template renders tickets in columns:
   - Backlog (initial state)
   - To Do
   - In Progress
   - Review
   - Done

**UI Features**:
- View all tickets by column
- Edit mode for updating ticket details
- Color coding by severity
- Label badges

## Error Handling

### No Specification Found
```
❌ No specification found for this project. 
Please create and finalize a specification first.
```

### LLM Parsing Failure
- Automatically falls back to creating 3 default tickets
- Logs error for debugging
- Still provides usable tickets to user

### Network/LLM Server Issues
```
⚠️ I analyzed the specification but couldn't generate any tickets.
The spec might need more detail.
```

## State Transitions

```
Spec State:      [Draft] → [Approved] → [Tickets Generated]
                              ↓
Ticket State:               [Created in Backlog]
                              ↓
                         [Assigned to Agents]
                              ↓
                         [Moved through Kanban]
```

## Success Criteria

A successful workflow completion includes:

1. ✅ Spec marked as approved in MongoDB
2. ✅ Architect agent triggered automatically
3. ✅ 3-8 tickets generated from spec content
4. ✅ All tickets saved to MongoDB
5. ✅ Tickets visible in Kanban Backlog
6. ✅ User notified via chat
7. ✅ Each ticket has:
   - Valid title and description
   - Appropriate severity level
   - Correct label (Feature, Testing, etc.)
   - Realistic time estimate
   - Complete history entry

## Performance Considerations

- **Async Execution**: Architect runs in background to avoid blocking
- **LLM Timeout**: 120 second timeout for spec analysis
- **Fallback Speed**: Immediate fallback tickets if parsing fails
- **Database Batch**: Single insert per ticket (could be optimized)

## Future Enhancements

1. **Progressive Streaming**: Stream tickets as they're generated
2. **Batch Insert**: Create all tickets in single MongoDB operation
3. **Dependency Detection**: Auto-detect and link dependent tickets
4. **Smart Splitting**: Break large tickets into subtasks
5. **Template Matching**: Use predefined templates for common features
6. **Human Review**: Optional approval step before ticket creation

## Related Documentation

- [Architect Agent](./ARCHITECT_AGENT.md)
- [Architecture](./ARCHITECTURE.md)
- [Kanban Board](./KANBAN.md)
- [Testing Guide](./TESTING.md)
