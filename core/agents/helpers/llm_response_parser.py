
import json
import re


class LlmResponseParser:
    @staticmethod
    def parse(raw: str) -> list[dict]:
        """
        Cleans and parses a raw LLM string response into a list of dicts.
        Handles:
        - Backtick wrapping
        - Double-stringified JSON
        - Empty or malformed data

        Raises:
            ValueError with helpful explanation
        """
        if not raw or not isinstance(raw, str):
            raise ValueError("Empty or invalid LLM response string")

        # Normalize whitespace
        cleaned = raw.strip()

        # Remove code fences like ```json ... ``` or ``` ... ``` if present
        if cleaned.startswith("```"):
            # Drop the opening fence with optional language
            cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
            # Drop the trailing fence if present
            cleaned = re.sub(r"\s*```\s*$", "", cleaned)

        # Also remove any stray leading/trailing backticks
        cleaned = re.sub(r"^`+|`+$", "", cleaned)

        # Handle stringified-JSON-inside-string case
        try:
            obj = json.loads(cleaned)
            if isinstance(obj, str):
                # It was double-wrapped: parse again
                obj = json.loads(obj)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON from LLM: {e}") from e

        if not isinstance(obj, list):
            obj = [obj]

        return obj
