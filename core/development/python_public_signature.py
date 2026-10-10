"""Bounded Python API-shape inspection behind the language evidence adapter."""
from __future__ import annotations

import ast
from core.development.python_specification_surface import DYNAMIC_SURFACE
from core.development.required_public_signature import RequiredPublicSignature, SIGNATURE_MISMATCH, SignatureAssurance


def production_signature_findings(source: str, signatures: tuple[RequiredPublicSignature, ...], complete: bool = False) -> tuple[str, ...]:
    return production_signature_assurance(source, signatures, complete).findings


def production_signature_assurance(source: str, signatures: tuple[RequiredPublicSignature, ...], complete: bool = False) -> SignatureAssurance:
    """Same bounded declaration inspection; unknown mechanics are not violations."""
    tree = ast.parse(source)
    failed, unknown, deferred, violated = [], [], [], []
    dynamic = any(isinstance(node, ast.Name) and node.id in DYNAMIC_SURFACE for node in ast.walk(tree))
    for item in signatures:
        owners = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == item.owner]
        mutations = any(
            isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)) and node.attr == item.name
            or isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)) and node.id == item.owner
            for node in ast.walk(tree))
        uncertain = dynamic or mutations or len(owners) > 1 or any(
            owner.bases or owner.keywords or owner.decorator_list for owner in owners)
        if uncertain:
            unknown.append(f"{SIGNATURE_MISMATCH}: {item.source_quote} has an unsupported dynamic declaration")
        bodies = [owner.body for owner in owners] if item.owner else [tree.body]
        definitions = [node for body in bodies for node in body
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == item.name]
        if not definitions and complete and not uncertain:
            deferred.append(item)
        if len(definitions) > 1:
            unknown.append(f"{SIGNATURE_MISMATCH}: {item.source_quote} has ambiguous declarations")
            continue
        for node in definitions:
            args = node.args
            names = tuple(arg.arg for arg in args.posonlyargs + args.args)
            receiver_valid = not item.owner or bool(names)
            if item.owner:
                names = names[1:]
            if uncertain or node.decorator_list or isinstance(node, ast.AsyncFunctionDef):
                unknown.append(f"{SIGNATURE_MISMATCH}: {item.source_quote}; unsupported declaration mechanics")
            elif (not receiver_valid or len(names) != len(item.parameters) or args.defaults or args.kwonlyargs
                  or args.vararg or args.kwarg or args.posonlyargs):
                failed.append(f"{SIGNATURE_MISMATCH}: {item.source_quote}; observed {ast.unparse(node.args)}")
                violated.append(item)
    return SignatureAssurance(tuple(failed), tuple(unknown), tuple(deferred), tuple(violated))


def scenario_signature_findings(source: str, signatures: tuple[RequiredPublicSignature, ...]) -> tuple[str, ...]:
    """Fail closed on calls to declared operations with unsupported or different shape."""
    tree = ast.parse(source)
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else (
            node.func.id if isinstance(node.func, ast.Name) else None)
        matches = [item for item in signatures if item.name == name]
        for item in matches:
            assigned: list[str | None] = list(item.parameters[:len(node.args)])
            assigned.extend(keyword.arg for keyword in node.keywords)
            if (any(isinstance(arg, ast.Starred) for arg in node.args)
                    or len(node.args) > len(item.parameters)
                    or None in assigned or len(set(assigned)) != len(assigned)
                    or set(assigned) != set(item.parameters)):
                findings.append(f"{SIGNATURE_MISMATCH}: {item.source_quote}; observed {ast.unparse(node)}")
    return tuple(findings)


