"""Bounded syntactic reduction opportunities; no application behavior inference."""
from __future__ import annotations
import ast
import hashlib
from collections import Counter
from dataclasses import dataclass, field

from core.development.production_reduction_syntax import (
    ReductionOpportunity, ReductionPlan, ReductionSource,
)
from core.development.python_reduction_provenance import constrain_completion_plan
from core.development.python_production_reduction_spans import (
    PythonReductionBuffer, child_suites, named_declaration, statement_key,
)


@dataclass(frozen=True)
class _Suite:
    before: tuple[ast.stmt, ...]
    current: tuple[ast.stmt, ...]
    identity: tuple[str, ...]
    module: bool = False


@dataclass
class _PlanBuilder:
    request: ReductionSource
    before: PythonReductionBuffer
    current: PythonReductionBuffer
    opportunities: list[ReductionOpportunity] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def add(self, identity: tuple[str, ...], edit: tuple[str, bytes | None]) -> None:
        description, replacement = edit
        if replacement == self.request.candidate:
            return
        if not self.preserves_baseline_material(replacement):
            self.limitations.append(f"Skipped {description}: shared baseline byte-lines would be removed")
            return
        if replacement is not None:
            try:
                PythonReductionBuffer(replacement).parse()
            except (ValueError, SyntaxError, UnicodeError) as error:
                self.limitations.append(f"Skipped {description}: {error}")
                return
        token = repr((self.request.path, identity, description)).encode()
        self.opportunities.append(ReductionOpportunity(
            hashlib.sha256(token).hexdigest(), self.request.path, replacement, description))


    def preserves_baseline_material(self, replacement: bytes | None) -> bool:
        baseline = Counter((self.request.baseline or b"").splitlines(keepends=True))
        candidate = Counter((self.request.candidate or b"").splitlines(keepends=True))
        reduced = Counter((replacement or b"").splitlines(keepends=True))
        return all(reduced[line] >= min(count, candidate[line]) for line, count in baseline.items())


@dataclass(frozen=True)
class _SuiteCorrespondence:
    suite: _Suite

    def pairs(self) -> dict[int, ast.stmt]:
        old_keys = [statement_key(node) for node in self.suite.before]
        new_keys = [statement_key(node) for node in self.suite.current]
        old_counts, new_counts = Counter(old_keys), Counter(new_keys)
        old = {key: node for key, node in zip(old_keys, self.suite.before) if old_counts[key] == 1}
        paired = {index: old[key] for index, key in enumerate(new_keys)
                  if key in old and new_counts[key] == 1}
        for (left_new, left_old), (right_new, right_old) in self.gaps(paired):
            if right_new - left_new == 2 and right_old - left_old == 2:
                node = self.suite.current[left_new + 1]
                prior = self.suite.before[left_old + 1]
                if type(node) is type(prior) and not named_declaration(node):
                    paired[left_new + 1] = prior
        return paired

    def gaps(self, paired: dict[int, ast.stmt]) -> tuple[tuple[tuple[int, int], tuple[int, int]], ...]:
        positions = {id(node): index for index, node in enumerate(self.suite.before)}
        anchors = [(-1, -1), *((new, positions[id(node)]) for new, node in sorted(paired.items())),
                   (len(self.suite.current), len(self.suite.before))]
        if any(right[1] <= left[1] for left, right in zip(anchors, anchors[1:])):
            return ()
        return tuple(zip(anchors, anchors[1:]))

    def added(self, index: int, paired: dict[int, ast.stmt]) -> bool:
        for (left_new, left_old), (right_new, right_old) in self.gaps(paired):
            if left_new < index < right_new:
                return right_old == left_old + 1
        return False


@dataclass(frozen=True)
class _SuiteReducer:
    builder: _PlanBuilder

    def reduce(self, request: _Suite) -> None:
        old_counts = Counter(statement_key(node) for node in request.before)
        new_counts = Counter(statement_key(node) for node in request.current)
        correspondence = _SuiteCorrespondence(request)
        paired = correspondence.pairs()
        for index, node in enumerate(request.current):
            key = statement_key(node)
            if new_counts[key] != 1 or old_counts[key] > 1:
                self.builder.limitations.append(f"Ambiguous repeated syntax unit: {request.identity + (key,)}")
                continue
            prior = paired.get(index)
            added = prior is None and (
                named_declaration(node) and not old_counts[key] or correspondence.added(index, paired))
            if prior is None and not added:
                self.builder.limitations.append(f"No unambiguous baseline correspondence: {request.identity + (key,)}")
                continue
            self._unit(request, (node, prior, (*request.identity, key)))
        _DeletedUnitRestorer(self.builder).restore(request, paired)

    def _unit(self, suite: _Suite, item: tuple[ast.stmt, ast.stmt | None, tuple[str, ...]]) -> None:
        node, prior, identity = item
        builder = self.builder
        try:
            span = builder.current.span(node)
            if prior is None:
                scaffold = span.indent + b"pass" + span.newline if len(suite.current) == 1 and not suite.module else b""
                builder.add((*identity, "delete"), ("delete added syntax unit", builder.current.splice(span, scaffold)))
            elif builder.before.fragment(prior) != builder.current.fragment(node):
                builder.add((*identity, "restore"), ("restore baseline syntax unit", builder.current.splice(span, builder.before.fragment(prior))))
        except ValueError as error:
            builder.limitations.append(f"Skipped {identity}: {error}")
        old_suites = dict(child_suites(prior)) if prior is not None else {}
        for field_name, body in child_suites(node):
            self.reduce(_Suite(tuple(old_suites.get(field_name, ())), tuple(body), (*identity, field_name)))


@dataclass(frozen=True)
class _DeletedUnitRestorer:
    builder: _PlanBuilder

    def restore(self, request: _Suite, paired: dict[int, ast.stmt]) -> None:
        for (left_new, left_old), (right_new, right_old) in _SuiteCorrespondence(request).gaps(paired):
            if right_new != left_new + 1 or right_old <= left_old + 1:
                continue
            for node in request.before[left_old + 1:right_old]:
                key = statement_key(node)
                if sum(statement_key(item) == key for item in request.before) != 1:
                    self.builder.limitations.append(f"Ambiguous deleted baseline unit: {request.identity + (key,)}")
                    continue
                self._restore(request, (node, left_new, right_new))

    def _restore(self, request: _Suite, context: tuple[ast.stmt, int, int]) -> None:
        node, left_new, right_new = context
        builder = self.builder
        key = statement_key(node)
        try:
            position = builder.current.span(request.current[right_new]).start if right_new < len(request.current) else (
                builder.current.span(request.current[left_new]).end if left_new >= 0 else len(builder.current.source))
            fragment = builder.before.fragment(node)
            prefix = b"\n" if position and builder.current.source[position - 1:position] != b"\n" else b""
            replacement = builder.current.source[:position] + prefix + fragment + builder.current.source[position:]
            builder.add((*request.identity, key, "restore_deleted"), ("restore deleted baseline syntax unit", replacement))
        except ValueError as error:
            builder.limitations.append(f"Skipped deleted {key}: {error}")


class PythonProductionReductionAdapter:
    def plan(self, request: ReductionSource) -> ReductionPlan:
        if request.baseline == request.candidate:
            return ReductionPlan()
        if request.candidate is None:
            opportunity = ReductionOpportunity(
                hashlib.sha256((request.path + ":restore_file").encode()).hexdigest(),
                request.path, request.baseline, "restore deleted baseline file")
            return constrain_completion_plan(request, ReductionPlan((opportunity,)))
        before = PythonReductionBuffer(request.baseline or b"")
        current = PythonReductionBuffer(request.candidate)
        try:
            old_tree, new_tree = before.parse(), current.parse()
        except (ValueError, SyntaxError, UnicodeError) as error:
            return ReductionPlan(limitations=(f"Unsupported syntax for bounded reduction: {error}",))
        builder = _PlanBuilder(request, before, current)
        if request.baseline is None:
            builder.add(("file", "delete"), ("delete added file", None))
        _SuiteReducer(builder).reduce(_Suite(tuple(old_tree.body), tuple(new_tree.body), ("module",), True))
        return constrain_completion_plan(request, ReductionPlan(
            tuple(builder.opportunities), tuple(dict.fromkeys(builder.limitations))))
