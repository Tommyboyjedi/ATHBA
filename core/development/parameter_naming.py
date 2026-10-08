"""Language boundary for source-grounded parameter naming inspection."""
from __future__ import annotations
from dataclasses import dataclass
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

def parameter_naming_mismatches(request: ParameterNamingInspection) -> tuple[ParameterNamingMismatch, ...]:
    # Syntax mechanics stay in the existing Python language adapter.
    from core.development.python_parameter_naming import PythonParameterNaming
    if any(not file.path.endswith(".py") for file in request.files):
        raise ValueError("parameter naming has no registered language adapter")
    return PythonParameterNaming().inspect(request)

def missing_signature_names(request: ParameterNamingInspection) -> tuple[str, ...]:
    from core.development.python_parameter_naming import PythonParameterNaming
    return PythonParameterNaming().missing_operations(request)
