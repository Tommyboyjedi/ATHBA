"""Project-facing operations; branch completion and application integration stay separate."""
from dataclasses import dataclass
import asyncio

from core.delivery_management.composition import TeamServices
from core.delivery_management.dispatch import DispatchRequest
from core.delivery_management.domain import ManagementRequest, MergeKind, MergeRecord, MergeStatus, TeamDelivery
from core.delivery_management.store import RecordIdentity
from core.project_setup.delivery import DeliveryRequest


@dataclass(frozen=True)
class DispatchResult:
    behavior_id: str
    delivery: TeamDelivery | None = None
    waiting_reason: str | None = None


@dataclass(frozen=True)
class TeamDeliveryService:
    services: TeamServices

    async def prepare(self, request: DeliveryRequest) -> TeamDelivery:
        return await self.services.admission.prepare(request)

    async def dispatch(self, request: DeliveryRequest) -> TeamDelivery:
        return await self.services.dispatch.dispatch(DispatchRequest(request))

    async def resume(self, request: DeliveryRequest) -> TeamDelivery:
        return await self.services.dispatch.dispatch(DispatchRequest(request, resume=True))

    async def dispatch_ready(self, requests: tuple[DeliveryRequest, ...]) -> tuple[DispatchResult, ...]:
        async def one(request: DeliveryRequest) -> DispatchResult:
            try:
                return DispatchResult(request.behavior_id, await self.dispatch(request))
            except ValueError as error:
                return DispatchResult(request.behavior_id, waiting_reason=str(error))
        return tuple(await asyncio.gather(*(one(request) for request in requests)))

    def synchronize(self, request: ManagementRequest) -> MergeRecord:
        return self.services.merges.request_sync(request)

    def submit(self, request: ManagementRequest) -> MergeRecord:
        sync = self.synchronize(request)
        if sync.status not in {MergeStatus.PUBLISHED, MergeStatus.NO_CHANGE}:
            return sync
        return self.services.merges.prepare(request, MergeKind.INTEGRATION)

    def recover_delivery(self, identity: RecordIdentity) -> TeamDelivery:
        from core.delivery_management.branch_environment import BranchEnvironment, BranchEnvironmentBinding
        with self.services.records.locked((identity.project_id, "worker-" + identity.record_id)):
            environment = BranchEnvironment(BranchEnvironmentBinding(
                self.services.parent_environment, self.services.records, identity))
            environment.recover_trusted_revision()
            result = self.services.records.delivery(identity)
            if result is None:
                raise ValueError("unknown recovered delivery")
            return result

    def inspect(self, project_id: str) -> dict:
        from core.delivery_management.inspection import ProjectDeliveryView
        return ProjectDeliveryView(self.services.records, self.services.parent_environment).inspect(project_id)
