"""Gateway from ATHBA work units to Rack AI CLI transport."""

from __future__ import annotations

from core.development.work_unit import DevelopmentWorkUnit
from core.execution.rack_ai_cli_transport import RackAiCliConfig, RackAiCliTransport, RackAiCliTransportError
from core.execution.rack_ai_request import RackAiRequestBuildRequest, RackAiRequestFactory, RepositoryBinding
from core.execution.rack_ai_result import RackAiExecutionResultMapper, RackAiGatewayResult
from core.execution.work_unit_gateway import WorkUnitExecutionResult


class RackAiCliExecutionGateway:
    """Invoke Rack AI without leaking worker/model/GPU choices into ATHBA."""

    def __init__(self, workload_id: str, config: RackAiCliConfig | None = None):
        self.workload_id = workload_id
        self.config = config or RackAiCliConfig()
        self.request_factory = RackAiRequestFactory()
        self.transport = RackAiCliTransport(self.config)
        self.result_mapper = RackAiExecutionResultMapper()

    async def execute(self, work_unit: DevelopmentWorkUnit, repository_binding: RepositoryBinding) -> WorkUnitExecutionResult:
        request = self.request_factory.build(RackAiRequestBuildRequest(self.workload_id, repository_binding, work_unit))
        response = await self.transport.execute(request)
        return self.result_mapper.map(RackAiGatewayResult(work_unit.id, response.summary, response.packet_payload))


__all__ = [
    "RackAiCliConfig",
    "RackAiCliExecutionGateway",
    "RackAiCliTransportError",
]
