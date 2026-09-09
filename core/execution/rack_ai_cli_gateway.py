"""Gateway from ATHBA work units to Rack AI CLI transport."""

from __future__ import annotations

from core.development.work_unit import DevelopmentWorkUnit
from core.execution.rack_ai_cli_transport import RackAiCliConfig, RackAiCliTransport, RackAiCliTransportError
from core.execution.rack_ai_request import RackAiRequestBuildRequest, RackAiRequestFactory, RepositoryBinding
from core.execution.rack_ai_result import RackAiExecutionResultMapper, RackAiExpectedIdentity, RackAiGatewayResult
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
        try:
            return self.result_mapper.map(
                RackAiGatewayResult(
                    expected=RackAiExpectedIdentity(
                        work_unit_id=work_unit.id,
                        change_id=request.change_id,
                        repository_id=request.repository.repository_id,
                        base_sha=request.repository.base_sha,
                    ),
                    summary=response.summary,
                    packet_payload=response.packet_payload,
                )
            )
        except ValueError as error:
            raise RackAiCliTransportError(f"Rack AI returned untrustworthy output: {error}") from error


__all__ = [
    "RackAiCliConfig",
    "RackAiCliExecutionGateway",
    "RackAiCliTransportError",
]
