"""Language boundary for source-grounded parameter naming inspection."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from core.development.required_public_signature import RequiredPublicSignature
from core.development.specification_evidence_policy import RevisionFile

@dataclass(frozen=True)
class ParameterNamingMismatch:
    owner: str | None
    operation: str
    index: int
    current_name: str
    required_name: str

@dataclass(frozen=True)
class ParameterNamingInspection:
    files: tuple[RevisionFile, ...]
    signatures: tuple[RequiredPublicSignature, ...]
    adapter: ParameterNamingAdapter | None = None

class ParameterNamingAdapter(Protocol):
    def inspect(self, request: ParameterNamingInspection) -> tuple[ParameterNamingMismatch, ...]: ...
    def missing_operations(self, request: ParameterNamingInspection) -> tuple[str, ...]: ...


def parameter_naming_mismatches(request: ParameterNamingInspection) -> tuple[ParameterNamingMismatch, ...]:
    if not request.signatures:
        return ()
    if request.adapter is None:
        raise ValueError("parameter naming has no configured language capability")
    return request.adapter.inspect(request)


def missing_signature_names(request: ParameterNamingInspection) -> tuple[str, ...]:
    if not request.signatures:
        return ()
    if request.adapter is None:
        raise ValueError("parameter naming has no configured language capability")
    return request.adapter.missing_operations(request)
