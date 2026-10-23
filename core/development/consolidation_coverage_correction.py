"""Complete only omitted coverage metadata; the proposed test remains immutable."""
from __future__ import annotations

from dataclasses import asdict
import json

from core.development.consolidation_reasoning import (
    ConsolidationCoverageMissing, ConsolidationReplacement, _bounded_prompt, _object,
)
from core.execution.reasoning_gateway import ReasoningRequest

COVERAGE_CORRECTION_PURPOSE = "athba_completed_req_consolidation_coverage_correction"


def coverage_correction_request(original: ReasoningRequest,
                                omission: ConsolidationCoverageMissing) -> ReasoningRequest:
    previous = _object(original.prompt)
    prompt = {
        "task": "Complete only missing coverage metadata for the unchanged proposed test.",
        "validation_error": str(omission),
        "source": omission.replacement.source,
        "existing_coverage": [asdict(link) for link in omission.replacement.coverage],
        "replacement_test_name": previous["replacement_test_name"],
        "authority_refs": previous["authority_refs"],
        "missing_authority_refs": list(omission.missing_refs),
        "selected_completed_evidence": previous["selected_completed_evidence"],
        "required_output": previous["required_output"],
        "rules": [
            "Return one JSON object. Add only truthful coverage entries for the missing references.",
            "Keep the decoded source string and every existing coverage entry exactly unchanged.",
            "Do not change replacement identity, obligations, setup, inputs, assertions or expected results.",
            "Do not add test observations, invent references, choose another partner or rewrite the test.",
            "Use only the supplied selected original source, obligations, tests and observations.",
            "Do not claim coverage the unchanged test does not demonstrate; if completion is impossible, do not invent it.",
            "Complete references are not semantic approval; independent preservation review still follows.",
        ],
    }
    return ReasoningRequest(COVERAGE_CORRECTION_PURPOSE,
                            _bounded_prompt(json.dumps(prompt, sort_keys=True)), original.project_id)


def protect_coverage(omission: ConsolidationCoverageMissing, corrected: ConsolidationReplacement) -> None:
    """The ordinary decoder has already required unique, complete, valid mappings."""
    if corrected.source != omission.replacement.source:
        raise ValueError("coverage correction changed proposed test source")
    revised = {entry.authority_ref: entry for entry in corrected.coverage}
    for link in omission.replacement.coverage:
        if revised.get(link.authority_ref) != link:
            raise ValueError("coverage correction changed existing coverage")
