"""Exact public call notation from authoritative source, independent of model prose."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

DECLARATION = re.compile(r"\b(?:Calling|calling|call|Call|method|function|operation)\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?)\(([^()]*)\)")
CLASS_DECLARATION = re.compile(r"\b([A-Za-z_]\w*)\s+class\b")
SIGNATURE_MISMATCH = "required_public_signature_mismatch"


@dataclass(frozen=True)
class RequiredPublicSignature:
    owner: str | None
    name: str
    parameters: tuple[str, ...]
    source_quote: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> RequiredPublicSignature:
        return cls(value["owner"], value["name"], tuple(value["parameters"]), value["source_quote"])


@dataclass(frozen=True)
class SignatureInspection:
    source: str
    signatures: tuple[RequiredPublicSignature, ...]
    complete: bool = False


def required_signatures(source: str) -> tuple[RequiredPublicSignature, ...]:
    """Recognize only explicit symbolic call declarations; never infer from examples."""
    owners = set(CLASS_DECLARATION.findall(source))
    values: dict[tuple[str | None, str], RequiredPublicSignature] = {}
    for match in DECLARATION.finditer(source):
        symbol, args = match.groups()
        parameters = tuple(part.strip() for part in args.split(",")) if args.strip() else ()
        if any(not name.isidentifier() for name in parameters):
            continue
        if len(set(parameters)) != len(parameters):
            raise ValueError("source public signature repeats a parameter")
        owner, separator, name = symbol.rpartition(".")
        if not separator:
            name = symbol
            if len(owners) > 1:
                raise ValueError("source public signature has ambiguous class ownership")
            owner = next(iter(owners), None)
        item = RequiredPublicSignature(owner, name, parameters, source[match.start(1):match.end()])
        key = (owner, name)
        if key in values and values[key].parameters != parameters:
            raise ValueError("source public signature declarations conflict")
        values[key] = item
    return tuple(values.values())


def validate_clause_signatures(source: str, clauses: tuple[str, ...]) -> None:
    for item in required_signatures(source):
        if not any(item.source_quote in clause for clause in clauses):
            raise ValueError(f"source public signature omitted from source deduction: {item.source_quote}")
