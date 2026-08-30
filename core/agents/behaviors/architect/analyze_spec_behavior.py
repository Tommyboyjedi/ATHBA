from datetime import datetime, timedelta
import json
from typing import Any, Dict, List

from core.agents.interfaces import BehaviorExecution
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.history_entry import HistoryEntry
from core.dataclasses.ticket_model import TicketModel


class AnalyzeSpecBehavior:
    intent = ["analyze_spec"]

    async def run(self, execution_or_agent, *args) -> list[ChatMessage] | None:
        execution = execution_or_agent
        if not isinstance(execution, BehaviorExecution):
            execution = BehaviorExecution(agent=execution_or_agent, message=args[0], intent=args[1])
        agent = execution.agent
        llm_response = execution.intent
        if llm_response.intent not in self.intent:
            return None
        spec_versions = await agent.spec_repo.find(
            {"project_id": agent.session.project_id},
            [("version", -1)],
            1,
        )
        if not spec_versions:
            return [
                ChatMessage(
                    sender=agent.name,
                    content="❌ No specification found for this project. Please create and finalize a specification first.",
                )
            ]
        spec_text = self._extract_spec_text(spec_versions[0].get("content", {}))
        tickets = await self._generate_tickets_from_spec(agent, spec_text)
        if not tickets:
            return [
                ChatMessage(
                    sender=agent.name,
                    content="⚠️ I analyzed the specification but couldn't generate any tickets. The spec might need more detail.",
                )
            ]
        created_tickets = []
        for ticket_data in tickets:
            ticket = TicketModel(
                project_id=agent.session.project_id,
                title=ticket_data.get("title", "Untitled Ticket"),
                description=ticket_data.get("description", ""),
                due=datetime.utcnow() + timedelta(days=ticket_data.get("estimated_days", 7)),
                eta=ticket_data.get("eta", "1 week"),
                agents=[],
                label=ticket_data.get("label", "Feature"),
                severity=ticket_data.get("severity", "Medium"),
                column="Backlog",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                history=[
                    HistoryEntry(
                        timestamp=datetime.utcnow(),
                        event="created",
                        actor=agent.name,
                        details="Ticket generated from specification analysis",
                    )
                ],
                id="",
            )
            created_tickets.append(await agent.ticket_repo.create(ticket))
        ticket_summary = "\n".join(f"  • {ticket.title} [{ticket.severity}] - {ticket.label}" for ticket in created_tickets)
        return [
            ChatMessage(
                sender=agent.name,
                content=(
                    f"✅ I've analyzed the specification and created {len(created_tickets)} tickets:\n\n"
                    f"{ticket_summary}\n\nAll tickets have been added to the Backlog. You can view them on the Kanban board."
                ),
            )
        ]

    def _extract_spec_text(self, spec_content: Any) -> str:
        if isinstance(spec_content, dict) and "sections" in spec_content:
            return "\n\n".join(section["body"] for section in spec_content["sections"] if "body" in section) + "\n\n"
        if isinstance(spec_content, str):
            return spec_content
        return str(spec_content)

    async def _generate_tickets_from_spec(self, agent, spec_text: str) -> List[Dict[str, Any]]:
        from core.agents.helpers.llm_exchange import LlmExchange, LlmExchangeRequest

        prompt = f"""Analyze this project specification and break it down into development tickets.

Specification:
{spec_text[:3000]}  # Limit to avoid token overflow

For each distinct feature or requirement, create a ticket with:
- title: Clear, actionable title (max 80 chars)
- description: Detailed description including acceptance criteria
- severity: Critical, High, Medium, or Low
- label: Feature, Bug, Enhancement, Documentation, or Testing
- eta: Estimated time (e.g., \"2 days\", \"1 week\")
- estimated_days: Numeric estimate in days

Respond with a JSON array of tickets. Example:
[
  {{
    \"title\": \"Implement user authentication system\",
    \"description\": \"Create login/logout functionality with JWT tokens. Acceptance criteria: Users can register, login, logout, and maintain session state.\",
    \"severity\": \"High\",
    \"label\": \"Feature\",
    \"eta\": \"1 week\",
    \"estimated_days\": 7
  }}
]

Generate 3-8 tickets that cover the main features. Focus on high-level functionality first."""
        response = await LlmExchange(
            LlmExchangeRequest(agent=agent, session=agent.session, content=prompt, use_cloud=True)
        ).get_response()
        response_text = response if isinstance(response, str) else str(response)
        try:
            start_idx = response_text.find("[")
            end_idx = response_text.rfind("]") + 1
            if start_idx >= 0 and end_idx > start_idx:
                tickets = json.loads(response_text[start_idx:end_idx])
                validated_tickets = []
                for ticket in tickets:
                    if isinstance(ticket, dict) and "title" in ticket:
                        ticket.setdefault("description", "")
                        ticket.setdefault("severity", "Medium")
                        ticket.setdefault("label", "Feature")
                        ticket.setdefault("eta", "1 week")
                        ticket.setdefault("estimated_days", 7)
                        validated_tickets.append(ticket)
                return validated_tickets
            return self._create_fallback_tickets(spec_text)
        except json.JSONDecodeError:
            return self._create_fallback_tickets(spec_text)

    def _create_fallback_tickets(self, spec_text: str) -> List[Dict[str, Any]]:
        return [
            {
                "title": "Initial project setup",
                "description": "Set up project structure, dependencies, and basic configuration based on specification.",
                "severity": "High",
                "label": "Feature",
                "eta": "2 days",
                "estimated_days": 2,
            },
            {
                "title": "Implement core features from specification",
                "description": f"Implement the main features outlined in the specification:\n\n{spec_text[:500]}",
                "severity": "High",
                "label": "Feature",
                "eta": "2 weeks",
                "estimated_days": 14,
            },
            {
                "title": "Add tests for core functionality",
                "description": "Write comprehensive tests following TDD principles for all core features.",
                "severity": "Medium",
                "label": "Testing",
                "eta": "1 week",
                "estimated_days": 7,
            },
        ]
