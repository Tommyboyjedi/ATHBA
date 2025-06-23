from dataclasses import dataclass


@dataclass
class LlmEvaluation:
    score: int
    reason: str
    escalate: bool = False