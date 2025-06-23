from dataclasses import dataclass

from core.dataclasses.priority import Priority


@dataclass
class ProjectQuota:
    critical: int = 90
    high: int = 70
    medium: int = 40
    low: int = 10

    def get_quota(self, priority: Priority) -> int:
        return getattr(self, priority.lower(), 10)