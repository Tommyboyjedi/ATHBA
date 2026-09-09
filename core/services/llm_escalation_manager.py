"""
LLM Escalation Manager service.

This module manages LLM tier escalation based on failure counts for
Developer and Tester agents independently. Implements 3-failure escalation:
- STANDARD -> HEAVY (after 3 failures)
- HEAVY -> MEGA (after 3 more failures)
"""

from datetime import UTC, datetime
from typing import Tuple

from core.dataclasses.history_entry import HistoryEntry
from core.dataclasses.ticket_model import TicketModel
from core.datastore.repos.ticket_repo import TicketRepo
from core.services.service_requests import EscalationAgent, FailureRecordRequest
from llm_service.enums.etier import ETier


STANDARD_TIER = ETier.STANDARD.value


def _store_failure_state(ticket: TicketModel, agent_type: EscalationAgent, failure_count: int, tier: str) -> None:
    if agent_type == EscalationAgent.DEVELOPER:
        ticket.developer_failure_count = failure_count
        ticket.developer_llm_tier = tier
        return
    ticket.tester_failure_count = failure_count
    ticket.tester_llm_tier = tier


class LlmEscalationManager:
    def __init__(self, max_failures_per_tier: int = 3):
        self.ticket_repo = TicketRepo()
        self.max_failures_per_tier = max_failures_per_tier

    def _normalize_agent(self, agent_type: EscalationAgent | str) -> EscalationAgent:
        return agent_type if isinstance(agent_type, EscalationAgent) else EscalationAgent(agent_type)

    def _current_fields(self, ticket: TicketModel, agent_type: EscalationAgent) -> tuple[int, str]:
        if agent_type == EscalationAgent.DEVELOPER:
            return ticket.developer_failure_count, ticket.developer_llm_tier
        return ticket.tester_failure_count, ticket.tester_llm_tier

    async def record_failure(self, request_or_ticket, *args) -> Tuple[TicketModel, ETier]:
        if isinstance(request_or_ticket, FailureRecordRequest):
            request = request_or_ticket
        else:
            request = FailureRecordRequest(
                ticket=request_or_ticket,
                agent_type=self._normalize_agent(args[0]),
                reason=args[1],
            )
        failure_count, current_tier_str = self._current_fields(request.ticket, request.agent_type)
        failure_count += 1
        new_tier = self._calculate_tier(failure_count)
        _store_failure_state(request.ticket, request.agent_type, failure_count, new_tier.value)
        tier_changed = new_tier.value != current_tier_str
        history_msg = f"{request.agent_type.value} failure #{failure_count}: {request.reason}. "
        history_msg += (
            f"Escalated to {new_tier.value.upper()} tier."
            if tier_changed
            else f"Remaining on {new_tier.value.upper()} tier."
        )
        request.ticket.history.append(
            HistoryEntry(
                timestamp=datetime.now(UTC),
                agent=request.agent_type.value,
                action="llm_escalation",
                details=history_msg,
            )
        )
        request.ticket.updated_at = datetime.now(UTC)
        await self.ticket_repo.update(request.ticket)
        return request.ticket, new_tier

    async def record_success(self, ticket: TicketModel, agent_type: EscalationAgent | str) -> TicketModel:
        normalized = self._normalize_agent(agent_type)
        old_count, old_tier = self._current_fields(ticket, normalized)
        _store_failure_state(ticket, normalized, 0, STANDARD_TIER)
        if old_count > 0:
            ticket.history.append(
                HistoryEntry(
                    timestamp=datetime.now(UTC),
                    agent=normalized.value,
                    action="llm_escalation_reset",
                    details=(
                        f"{normalized.value} success! Reset failure count from {old_count} to 0. "
                        f"Tier reset to STANDARD (was {old_tier.upper()})."
                    ),
                )
            )
            ticket.updated_at = datetime.now(UTC)
            await self.ticket_repo.update(ticket)
        return ticket

    def _calculate_tier(self, failure_count: int) -> ETier:
        if failure_count < self.max_failures_per_tier:
            return ETier.STANDARD
        if failure_count < self.max_failures_per_tier * 2:
            return ETier.HEAVY
        return ETier.MEGA

    def get_current_tier(self, ticket: TicketModel, agent_type: EscalationAgent | str) -> ETier:
        normalized = self._normalize_agent(agent_type)
        _, tier_str = self._current_fields(ticket, normalized)
        return ETier(tier_str)
