"""Read associated management state without constructing providers or executing work."""
from dataclasses import dataclass

from core.development.project_environment import ProjectEnvironmentService
from core.delivery_management.store import ManagementStore
from core.project_setup.records import ProjectSetupRepository


@dataclass(frozen=True)
class ProjectDeliveryView:
    records: ManagementStore
    parent: ProjectEnvironmentService

    def inspect(self, project_id: str) -> dict:
        parent = self.parent.repo.load(project_id)
        integrated = set(self.records.catalog(project_id).get("integrated_deliveries", ()))
        deliveries = self.records.deliveries(project_id)
        setup = ProjectSetupRepository(self.records.project_root).load(project_id)
        ready = {item.behavior.id for item in deliveries if item.id in integrated}
        represented = {item.behavior.id for item in deliveries}
        return {
            "delivery_model": "parallel_behavior_branches",
            "project_id": project_id,
            "application_main_ref": "refs/heads/" + parent.default_ref if parent else None,
            "application_integrated_revision": parent.trusted_base_sha if parent else None,
            "deliveries": [{**item.to_dict(), "integrated": item.id in integrated,
                "newer_main_available": item.synchronized_main != parent.trusted_base_sha if parent else None}
                for item in deliveries],
            "waiting_behaviors": [{"behavior_id": behavior.id,
                "waiting_on_integrated_dependencies": sorted(set(behavior.depends_on) - ready)}
                for behavior in setup.behaviors if behavior.id not in represented
                and not set(behavior.depends_on) <= ready] if setup else [],
            "operations": [item.to_dict() for item in self.records.merges(project_id)],
        }
