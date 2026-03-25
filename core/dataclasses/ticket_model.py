"""
Ticket model dataclass.

This module defines the TicketModel dataclass used throughout the ATHBA system
for managing development tickets.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict
from core.dataclasses.history_entry import HistoryEntry


@dataclass
class TicketModel:
    """
    Represents a development ticket in the ATHBA system.
    
    Attributes:
        project_id: Unique identifier of the project this ticket belongs to
        title: Short title of the ticket
        description: Detailed description of the ticket requirements
        due: Due date for ticket completion
        eta: Estimated time to complete (human-readable, e.g., "1 week")
        agents: List of agent names assigned to this ticket
        label: Ticket category (Feature, Bug, Enhancement, Documentation, Testing)
        severity: Priority level (Critical, High, Medium, Low)
        column: Current Kanban column (Backlog, To Do, In Progress, Review, Done)
        created_at: Timestamp when ticket was created
        updated_at: Timestamp when ticket was last updated
        history: List of history entries tracking ticket changes
        id: Unique identifier of the ticket (MongoDB ObjectId as string)
        branch_name: Git branch name associated with this ticket (optional)
        commits: List of commit SHAs associated with this ticket
    """
    project_id: str
    title: str
    description: str
    due: datetime
    eta: str
    agents: List[str]
    label: str
    severity: str
    column: str
    created_at: datetime
    updated_at: datetime
    history: List[HistoryEntry]
    id: str
    branch_name: Optional[str] = None
    commits: List[str] = field(default_factory=list)
