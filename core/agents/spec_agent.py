import json
from core.agents.behaviors.behavior_loader import BehaviorLoader
from core.agents.helpers.llm_exchange import LlmExchange
from core.agents.interfaces import IAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.project import Project
from core.dataclasses.projses import Projses
from core.datastore.repos.ticket_repo import TicketRepo
from core.services.project_service import ProjectsService
from core.dataclasses.session_state import SessionState
from llm_service.enums.eagent import EAgent


class SpecBuilderAgent(IAgent):

    def report(self) -> dict:
        return {"agent": self.name, "status": "Idle", "project_id": getattr(self._session, "project_id", None)}

    def __init__(self, session: Projses):
        self._session = session
        self._session.agent_name = self.name
        self.ticket_repo = TicketRepo()
        self.behaviors = BehaviorLoader().load_for_agent(self)

    async def initialize(self):
        self._project = await ProjectsService().get_project_by_id(self._session.project_id)

    async def run(self, content: str) -> list[ChatMessage]:
        exchange = LlmExchange(agent=self, session=self._session, content=content)
        intents = await exchange.get_intents()
        results: list[ChatMessage] = []

        try:
            print(f"[Spec][{self._session.project_id}] Parsed {len(intents) if intents else 0} intents")
        except Exception:
            pass

        # If the LLM failed to return any intents (e.g., non-JSON output), attempt a repair pass
        if not intents:
            repair_prompt_empty = (
                "You are the Specification Builder Agent. The previous attempt returned no valid JSON. "
                "Extract one or more intents from the user's input. Prefer 'add_to_spec' for concrete requirements. "
                "Respond with ONLY a JSON array of objects following this exact schema per object: "
                "{\n  \"response\": \"<brief reply or clarifying question>\",\n  \"intent\": \"add_to_spec | ask_a_question | change_spec | start_spec | finalize_spec\",\n  \"agents_routing\": [],\n  \"entities\": {\n    \"projectName\": \"<name or empty>\",\n    \"humanIdeas\": [\"<idea 1>\", \"<idea 2>\"],\n    \"specSections\": [\"<section name>\"]\n  }\n}. "
                "Rules: 1) No code fences. 2) Always include all keys in entities. 3) Distill requirements into humanIdeas and sensible specSections (e.g., Backend, Database, Frontend, Architecture). 4) If uncertain, include ['Overview'] as a section.\n\n"
                f"User input: {content}\n\nReturn only the JSON array."
            )
            repaired_empty = await exchange.infer_with_prompt(repair_prompt_empty)
            if repaired_empty:
                intents = repaired_empty
            else:
                return [ChatMessage(sender=self.name, content="I couldn't parse that into actionable items. Please rephrase or try again.")]

        # Repair pass if entities missing/empty
        if self._intents_need_repair(intents):
            partial = [
                {
                    "response": i.response,
                    "intent": i.intent,
                    "agents_routing": i.agents_routing or [],
                    "entities": i.entities or {}
                } for i in intents
            ]
            repair_prompt = (
                "You are repairing previously generated Spec agent intents. "
                "Given the user input and the partial intents JSON, return a corrected JSON array with the SAME number of objects. "
                "Rules: keep each object's response and intent the same when sensible; ensure entities has keys projectName, humanIdeas, specSections. "
                "Populate humanIdeas and specSections with distilled requirements inferred from the user input. "
                "If a value is unknown, use empty string or empty array but prefer non-empty when possible. No code fences.\n\n"
                f"User input: {content}\n"
                f"Partial intents JSON: {json.dumps(partial, ensure_ascii=False)}\n\n"
                "Return only the JSON array."
            )
            repaired = await exchange.infer_with_prompt(repair_prompt)
            if repaired:
                intents = repaired

        for intent in intents:
            try:
                print(f"[Spec] Intent={getattr(intent, 'intent', None)} entities_keys={list((getattr(intent, 'entities', {}) or {}).keys())}")
            except Exception:
                pass
            for behavior in self.behaviors:
                messages = await behavior.run(self, content, intent)
                if messages:
                    if isinstance(messages, list):
                        results.extend(messages)
                    else:
                        results.append(messages)

            # Multi-agent routing per intent
            try:
                for route in intent.agents_routing or []:
                    agent_name = route[1:] if isinstance(route, str) and route.startswith("@") else route
                    if agent_name and agent_name != self.name:
                        results.append(SessionState(agent_name=agent_name))
            except Exception:
                pass

        return results

    def _intents_need_repair(self, intents) -> bool:
        try:
            for i in intents:
                entities = i.entities or {}
                keys_missing = not all(k in entities for k in ("projectName", "humanIdeas", "specSections"))
                empty_all = (
                    (not entities) or (
                        not (entities.get("humanIdeas") or entities.get("specSections"))
                    )
                )
                if keys_missing or empty_all:
                    return True
            return False
        except Exception:
            return True

    @property
    def llm_prompt(self) -> str:
        return """
            You are the Specification Builder Agent.
            You work as part of a data applications DevOps team. Your job is to elicit missing requirements with clarifying questions and turn user input into clear, concise specification blocks written in plain English (markdown-friendly).

            Guidance (follow strictly):
            - Prefer intent "add_to_spec" when the user provides concrete requirements. Produce a succinct distilled block.
            - If you must ask a clarifying question (intent "ask_a_question"):
              - Keep "response" as only the chat question for the user (no spec text there).
              - Still populate "entities.humanIdeas" with the certain, distilled requirements you can already add.
              - Populate "entities.specSections" with suitable section names for those ideas. If uncertain, include ["Overview"].
            - Use "change_spec" to modify existing content, "start_spec" to initialize a spec, and "finalize_spec" only when the user confirms completion.
            - Always populate the entities object keys shown below; when something is unknown use an empty string or empty array, but do include the keys.
            - Output raw JSON only. Do NOT use backticks or code fences.

            Available intents (map to application behaviors):
            - add_to_spec | ask_a_question | change_spec | start_spec | finalize_spec

            Respond with a JSON array containing one or more objects (multi-intent per turn is allowed). Use this schema per object:

            {
              "response": "<a brief reply and/or a clarifying question>",
              "intent": "<one of: add_to_spec | ask_a_question | change_spec | start_spec | finalize_spec>",
              "agents_routing": [],
              "entities": {
                "projectName": "<name or empty>",
                "humanIdeas": ["<idea summary 1>", "<idea summary 2>", "<...>"],
                "specSections": ["<section name>", "<another section name>"]
              }
            }

            Few-shot examples:
            User: "We need user login with email + MFA. Also, what DB do you recommend?"
            [
              {"response": "What database do you prefer (PostgreSQL, MySQL, or SQLite)?", "intent": "ask_a_question", "agents_routing": [],
               "entities": {"projectName": "", "humanIdeas": ["User authentication via email + password + MFA"], "specSections": ["Authentication"]}},
              {"response": "Added login requirement.", "intent": "add_to_spec", "agents_routing": [],
               "entities": {"projectName": "", "humanIdeas": ["MFA via email OTP or TOTP"], "specSections": ["Authentication"]}}
            ]

            User: "It replaces a spreadsheet. Django backend with Django ORM to a SQLite file DB. Frontend is minimal using Alpine.js and Bootstrap.css. No build step."
            [
              {"response": "Captured backend and database requirements.", "intent": "add_to_spec", "agents_routing": [],
               "entities": {"projectName": "", "humanIdeas": ["Django backend using Django ORM", "SQLite file database"], "specSections": ["Backend", "Database"]}},
              {"response": "Captured frontend constraints.", "intent": "add_to_spec", "agents_routing": [],
               "entities": {"projectName": "", "humanIdeas": ["Frontend with Alpine.js", "Bootstrap CSS styling", "No build step"], "specSections": ["Frontend", "Architecture"]}}
            ]

            User input:
            """

    @property
    def name(self) -> str:
        return "Spec"

    @property
    def agent_type(self) -> EAgent:
        return EAgent.Spec

    @property
    def project(self) -> Project:
        return self._project

    @property
    def session(self):
        return self._session