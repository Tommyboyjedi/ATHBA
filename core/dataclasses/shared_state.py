from asyncio import Lock
from dataclasses import dataclass, field

from core.dataclasses.project_quota import ProjectQuota


@dataclass
class SharedState:
    pause_all: bool = False
    mem_threshold: float = 90.0  # NOS max per spec
    cpu_threshold: float = 95.0  # Optional system load guard
    mega_active: bool = False
    last_mem_usage: float = 0.0
    last_cpu_usage: float = 0.0
    lock: Lock = field(default_factory=Lock)

    project_quota: ProjectQuota = field(default_factory=ProjectQuota)