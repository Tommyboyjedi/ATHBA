
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

        # Remove leading/trailing backticks and whitespace
        cleaned = re.sub(r"^`+|`+$", "", raw.strip())

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
