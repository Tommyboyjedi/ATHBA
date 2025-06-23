from core.agents.interfaces import IAgent

class DeveloperAgent(IAgent):
    def __init__(self, behaviors):
        self.name = "Developer"
        self.behaviors = behaviors

    def run(self, ticket_id: str) -> dict:
        results = []
        for behavior in self.behaviors:
            results.append(behavior(self, ticket_id))
        return {"agent": self.name, "results": results}

    def report(self) -> dict:
        return {"agent": self.name, "status": "Idle"}
