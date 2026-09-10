"""Deterministic exact excerpts and bounded omissions from one source clause."""
from __future__ import annotations

from dataclasses import dataclass
import re

OMISSION_MARKER = "..."
PROVENANCE_ERROR = "specification checklist provenance is not grounded in original source"
# Conservative boundaries: ambiguous punctuation is never crossed by an omission.
CLAUSE_BOUNDARY = re.compile(
    r"[.!?;:,\r\n\u2028\u2029\u2013\u2014]|"
    r"\b(?:but|whereas|although|while|however|unless|otherwise)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SourceQuoteProvenance:
    context: str
    quoted_segments: tuple[str, ...]

    def grounds_subject(self, subject: str) -> bool:
        # Subjects may not bridge an omission or refer only to omitted words.
        return any(subject.lower() in segment.lower() for segment in self.quoted_segments)


def resolve_source_quote(source: str, quote: str) -> SourceQuoteProvenance:
    if not quote.strip():
        raise ValueError(PROVENANCE_ERROR)
    if quote in source:
        # Preserve the original exact-excerpt lookup and modality context unchanged.
        return SourceQuoteProvenance(_exact_context(source, quote), (quote,))
    segments = _omission_segments(quote)
    for context in _source_clauses(source):
        if _ordered_segments(context, segments):
            return SourceQuoteProvenance(context, segments)
    raise ValueError(PROVENANCE_ERROR)


def _omission_segments(quote: str) -> tuple[str, ...]:
    if OMISSION_MARKER not in quote or re.search(r"\.{4,}|\u2026", quote):
        raise ValueError(PROVENANCE_ERROR)
    # Only horizontal padding directly beside the marker is insignificant.
    segments = tuple(part.strip(" \t") for part in quote.split(OMISSION_MARKER))
    if any(not re.search(r"\w", segment) for segment in segments):
        raise ValueError(PROVENANCE_ERROR)
    return segments


def _source_clauses(source: str) -> tuple[str, ...]:
    clauses = []
    start = 0
    for boundary in CLAUSE_BOUNDARY.finditer(source):
        # A final punctuation character may itself be quoted, never crossed.
        end = boundary.end() if len(boundary.group()) == 1 else boundary.start()
        clauses.append(source[start:end])
        start = boundary.end()
    clauses.append(source[start:])
    return tuple(clauses)


def _ordered_segments(context: str, segments: tuple[str, ...]) -> bool:
    cursor = 0
    for segment in segments:
        # Do not splice partial words into an apparent identifier or phrase.
        left = r"(?<!\w)" if re.match(r"\w", segment[0]) else ""
        right = r"(?!\w)" if re.match(r"\w", segment[-1]) else ""
        match = re.compile(left + re.escape(segment) + right).search(context, cursor)
        if match is None:
            return False
        cursor = match.end()
    return True


def _exact_context(source: str, quote: str) -> str:
    start = source.index(quote)
    left = max(source.rfind(mark, 0, start) for mark in (".", "!", "?", "\n")) + 1
    end = start + len(quote)
    boundaries = [position for mark in (".", "!", "?", "\n") if (position := source.find(mark, end)) >= 0]
    right = min(boundaries) if boundaries else len(source)
    return source[left:right] if not re.search(r"[.!?]$", quote) else source[left:end]
