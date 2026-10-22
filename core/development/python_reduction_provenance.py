"""Conservative syntax-only eligibility for explicitly scoped completion changes."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from collections import Counter
from difflib import SequenceMatcher

from core.development.production_reduction_syntax import ReductionPlan, ReductionSource
from core.development.python_production_reduction_spans import PythonReductionBuffer, child_suites, statement_key


@dataclass(frozen=True)
class _Unit:
    identity: tuple[str, ...]
    fragment: bytes
    start: int
    end: int


def _units(source: bytes | None) -> tuple[dict[tuple[str, ...], _Unit], set[tuple[str, ...]]]:
    buffer = PythonReductionBuffer(source or b"")
    tree = buffer.parse()
    result: dict[tuple[str, ...], _Unit] = {}
    ambiguous: set[tuple[str, ...]] = set()

    def visit(value: tuple[list[ast.stmt], tuple[str, ...]]) -> None:
        nodes, prefix = value
        for node in nodes:
            identity = (*prefix, statement_key(node))
            if identity in result:
                ambiguous.add(identity)
            else:
                span = buffer.span(node)
                result[identity] = _Unit(identity, buffer.fragment(node), span.start, span.end)
            for field, children in child_suites(node):
                visit((children, (*identity, field)))
    visit((tree.body, ("module",)))
    return result, ambiguous


def _eligible(request: ReductionSource) -> tuple[set[tuple[str, ...]], dict[tuple[str, ...], _Unit]]:
    baseline, ambiguous = _units(request.baseline)
    current, uncertain = _units(request.candidate)
    ambiguous.update(uncertain)
    selected: set[tuple[str, ...]] = set()
    protected: set[tuple[str, ...]] = set(baseline)
    for contribution in request.contributions:
        before, old_ambiguous = _units(contribution.before)
        after, new_ambiguous = _units(contribution.after)
        ambiguous.update(old_ambiguous | new_ambiguous)
        changed = {key for key in before.keys() | after.keys()
                   if (before[key].fragment if key in before else None)
                   != (after[key].fragment if key in after else None)}
        (selected if contribution.selected else protected).update(changed)
    # A duplicate ancestor makes correspondence of every nested unit ambiguous.
    uncertain_ids = {key for key in current
                     if any(key[:len(item)] == item or item[:len(key)] == key
                            for item in ambiguous)}
    return selected - protected - uncertain_ids, current


def _required_headers(value: tuple[bytes | None, ReductionSource]) -> dict[tuple[str, ...], str]:
    source, request = value
    result = {}
    tree = PythonReductionBuffer(source or b"").parse()
    def visit(value: tuple[list[ast.stmt], tuple[str, ...]]) -> None:
        nodes, owners = value
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                visit((node.body, (*owners, node.name)))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                required = any(item.name == node.name and (
                    item.owner is None or item.owner == ".".join(owners)
                ) for item in request.protected_identifiers)
                if required:
                    key = (*owners, node.name)
                    if key in result:
                        raise ValueError("ambiguous required public declaration")
                    result[key] = repr((type(node).__name__, ast.dump(node.args),
                                        tuple(ast.dump(item) for item in node.decorator_list),
                                        ast.dump(node.returns) if node.returns else None))
    visit((tree.body, ()))
    return result



def _validate_required_resolution(value: tuple[bytes | None, ReductionSource]) -> None:
    source, request = value
    headers = _required_headers(value)
    tree = PythonReductionBuffer(source or b"").parse()
    occurrences = Counter(node.name for node in ast.walk(tree)
                          if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
    for required in request.protected_identifiers:
        matches = tuple(key for key in headers if key[-1] == required.name and (
            required.owner is None or ".".join(key[:-1]) == required.owner))
        if len(matches) != 1 or occurrences[required.name] != 1:
            qualified = ".".join(part for part in (required.owner, required.name) if part)
            raise ValueError("required public declaration is unresolved, nested or ambiguous: " + qualified)


def _changed_spans(value: tuple[bytes, bytes]) -> tuple[tuple[int, int, bytes], ...]:
    before, after = value
    old, new = before.splitlines(keepends=True), after.splitlines(keepends=True)
    offsets = [0]
    for line in old:
        offsets.append(offsets[-1] + len(line))
    return tuple((offsets[left], offsets[right], b"".join(new[start:end]))
                 for tag, left, right, start, end in SequenceMatcher(None, old, new, autojunk=False).get_opcodes()
                 if tag != "equal")


def constrain_completion_plan(request: ReductionSource, plan: ReductionPlan) -> ReductionPlan:
    if not request.contributions:
        return plan
    limitations = list(plan.limitations)
    accepted = []
    try:
        eligible, units = _eligible(request)
        _validate_required_resolution((request.candidate, request))
        headers = _required_headers((request.candidate, request))
        spans = tuple(units[key] for key in eligible if key in units)
        for opportunity in plan.opportunities:
            replacement = opportunity.replacement or b""
            edits = _changed_spans((request.candidate or b"", replacement))
            safe = bool(edits)
            for start, end, added in edits:
                # Completion scope admits deletions and necessary empty-suite syntax only.
                if start == end or (added.strip() and added.strip() != b"pass"):
                    safe = False
                if not any(unit.start <= start and end <= unit.end for unit in spans):
                    safe = False
            if _required_headers((opportunity.replacement, request)) != headers:
                safe = False
            if safe:
                accepted.append(opportunity)
            else:
                limitations.append("Skipped completion opportunity: protected, shared or unsupported provenance")
    except (ValueError, SyntaxError, UnicodeError) as error:
        return ReductionPlan(limitations=(*limitations, f"Unsupported completion provenance: {error}"))
    return ReductionPlan(tuple(accepted), tuple(dict.fromkeys(limitations)))
