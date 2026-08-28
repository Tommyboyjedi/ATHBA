from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from core.dataclasses.history_entry import HistoryEntry


@dataclass
class TicketModel:
    project_id: str
    title: str
    description: str = ""
    due: Optional[datetime] = None
    eta: str = ""
    agents: List[str] = field(default_factory=list)
    label: str = "Feature"
    severity: str = "Medium"
    column: str = "Backlog"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    history: List[HistoryEntry] = field(default_factory=list)
    id: str = ""
    branch_name: Optional[str] = None
    commits: List[str] = field(default_factory=list)
    test_files: List[str] = field(default_factory=list)
    test_pass_rate: float = 0.0
    test_results: Dict = field(default_factory=dict)
    developer_failure_count: int = 0
    tester_failure_count: int = 0
    developer_llm_tier: str = "standard"
    tester_llm_tier: str = "standard"
