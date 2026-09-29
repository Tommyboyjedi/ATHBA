"""Deterministic exact excerpts and ordered citations from one source passage."""
from __future__ import annotations

from dataclasses import dataclass
import re

OMISSION_MARKER = "..."
PROVENANCE_ERROR = "specification checklist provenance is not grounded in original source"
PASSAGE_BOUNDARY = re.compile(r"[.!?](?=\s|$)|[;:\r\n\u2028\u2029\u2013\u2014]")
TOKEN = re.compile(
    r"-?\d+(?:\.\d+)?|[A-Za-z_]\w*|==|!=|<=|>=|->|\.\.\.|\u2026|\S",
)


@dataclass(frozen=True)
class _SourcePassage:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class _Token:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class SourceQuoteProvenance:
    context: str
    quoted_segments: tuple[str, ...]
    source_runs: tuple[str, ...] = ()
    match_spans: tuple[tuple[int, int], ...] = ()

    def __post_init__(self) -> None:
        if not self.source_runs:
            object.__setattr__(self, "source_runs", self.quoted_segments)

    def grounds_subject(self, subject: str) -> bool:
        # Subjects may not bridge an omission or refer only to omitted words.
        return any(subject.casefold() in segment.casefold() for segment in self.source_runs)


def resolve_source_quote(source: str, quote: str) -> SourceQuoteProvenance:
    if not quote.strip():
        raise ValueError(PROVENANCE_ERROR)
    if quote in source:
        # Preserve the original exact-excerpt lookup and modality context unchanged.
        return _exact_provenance(source, quote)

    quote_tokens = _quote_tokens(quote)
    matches = [
        provenance
        for passage in _source_passages(source)
        if (provenance := _ordered_token_provenance(passage, quote, quote_tokens)) is not None
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"{PROVENANCE_ERROR}: source_quote is ambiguous across source passages")
    raise ValueError(f"{PROVENANCE_ERROR}: source_quote tokens are absent, reordered, or cross source passages")


def _quote_tokens(quote: str) -> tuple[str, ...]:
    for marker in re.finditer(r"\.{2,}", quote):
        if marker.group() != OMISSION_MARKER:
            raise ValueError(f"{PROVENANCE_ERROR}: malformed omission marker")
    omission = re.compile(r"\.\.\.|\u2026")
    stripped = quote.strip()
    markers = tuple(omission.finditer(stripped))
    if markers and (markers[0].start() == 0 or markers[-1].end() == len(stripped)):
        raise ValueError(f"{PROVENANCE_ERROR}: omission marker must separate retained words")
    if re.search(r"(?:\.\.\.|\u2026)\s*(?:\.\.\.|\u2026)", quote):
        raise ValueError(f"{PROVENANCE_ERROR}: omission marker must separate retained words")
    for segment in omission.split(quote):
        if segment.strip(" \t") and not any(re.search(r"\w", token.text) for token in _tokens(segment)):
            raise ValueError(f"{PROVENANCE_ERROR}: retained citation segment has no source words")
    tokens = tuple(token.text for token in _tokens(omission.sub(" ", quote)))
    if not tokens:
        raise ValueError(PROVENANCE_ERROR)
    return tokens


def _source_passages(source: str) -> tuple[_SourcePassage, ...]:
    passages = []
    start = 0
    for boundary in PASSAGE_BOUNDARY.finditer(source):
        end = boundary.end() if boundary.group() in ".!?" else boundary.start()
        if source[start:end].strip():
            passages.append(_SourcePassage(source[start:end], start, end))
        start = boundary.end()
    if source[start:].strip():
        passages.append(_SourcePassage(source[start:], start, len(source)))
    return tuple(passages)


def _ordered_token_provenance(
    passage: _SourcePassage,
    quote: str,
    quote_tokens: tuple[str, ...],
) -> SourceQuoteProvenance | None:
    source_tokens = _tokens(passage.text)
    cursor = 0
    spans: list[tuple[int, int]] = []
    for expected in quote_tokens:
        for index in range(cursor, len(source_tokens)):
            token = source_tokens[index]
            if token.text == expected:
                spans.append((token.start, token.end))
                cursor = index + 1
                break
        else:
            return None
    return SourceQuoteProvenance(
        passage.text,
        _citation_segments(quote),
        tuple(_source_runs(passage.text, spans)),
        tuple(spans),
    )


def _tokens(text: str) -> tuple[_Token, ...]:
    return tuple(_Token(match.group(), match.start(), match.end()) for match in TOKEN.finditer(text))


def _citation_segments(quote: str) -> tuple[str, ...]:
    omission = re.compile(r"\.\.\.|\u2026")
    if not omission.search(quote):
        return (quote,)
    return tuple(part.strip(" \t") for part in omission.split(quote) if part.strip(" \t"))


def _source_runs(context: str, spans: list[tuple[int, int]]) -> list[str]:
    runs: list[str] = []
    run_start, run_end = spans[0]
    for start, end in spans[1:]:
        if _tokens(context[run_end:start]):
            runs.append(context[run_start:run_end])
            run_start = start
        run_end = end
    runs.append(context[run_start:run_end])
    return runs


def _exact_provenance(source: str, quote: str) -> SourceQuoteProvenance:
    context = _exact_context(source, quote)
    start = context.index(quote)
    return SourceQuoteProvenance(context, (quote,), (quote,), ((start, start + len(quote)),))


def _exact_context(source: str, quote: str) -> str:
    start = source.index(quote)
    left = max(source.rfind(mark, 0, start) for mark in (".", "!", "?", "\n")) + 1
    end = start + len(quote)
    boundaries = [position for mark in (".", "!", "?", "\n") if (position := source.find(mark, end)) >= 0]
    right = min(boundaries) if boundaries else len(source)
    return source[left:right] if not re.search(r"[.!?]$", quote) else source[left:end]
