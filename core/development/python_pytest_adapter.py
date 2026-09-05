"""Python/pytest implementation of the strict-TDD language adapter."""
from __future__ import annotations

import ast
import json
import os
import shutil
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from core.development.scenario_drafting_domain import (
    ScenarioAuthoringContract, ScenarioCandidateAssessment, ScenarioCandidateAssessmentRequest, ScenarioCandidateIssue,
    ScenarioCandidateIssueCode,
)
from core.development.microcycle_domain import (
    BoundaryAssessment, BoundaryClassificationRequest, BoundaryDiagnostic,
    BoundaryOutcome, DiagnosticFact, FinalTestMaterialisationRequest,
    FragmentSourceSpan, FragmentationRequest, FrontierExecutionRequest,
    FrontierMaterialisationRequest, LanguageAdapterDescriptor, MaterialisedTestArtifact,
    RegressionContract, RegressionContractRequest, ScenarioFragment, ScenarioModel,
    ScenarioParseRequest, ScenarioSourceCandidate, ScenarioStaticAnalysis, SourceSpan,
    SyntaxValidationRequest,
)

PYTHON_LANGUAGE_ID = "python"
PYTEST_ADAPTER_VERSION = "1.0.0"


class PythonFragmentKind(str, Enum):
    PRODUCTION_IMPORT = "production_import"
    DECLARATION = "declaration"
    CONSTRUCTOR = "constructor"
    CALL = "call"
    ASSERTION = "assertion"
    RAISES_BLOCK = "raises_block"
    IF_BLOCK = "if_block"
    LOOP_BLOCK = "loop_block"
    WITH_BLOCK = "with_block"
    TRY_BLOCK = "try_block"


@dataclass(frozen=True)
class _Node:
    kind: PythonFragmentKind
    source: str
    source_span: SourceSpan
    module_scope: bool
    capability: str


@dataclass(frozen=True)
class _NodeRequest:
    source: str
    node: ast.stmt
    module_scope: bool


@dataclass(frozen=True)
class _Emission:
    fragment: ScenarioFragment
    source: str
    indent: str


@dataclass
class _Buffer:
    rows: list[str]
    spans: list[FragmentSourceSpan]


@dataclass(frozen=True)
class _Parsed:
    scaffolding: tuple[str, ...]
    header: str
    nodes: tuple[_Node, ...]


@dataclass(frozen=True)
class _MockAnalysisRequest:
    module: ast.Module
    production_module: str


class PythonScenarioParser:
    """Parses one ordinary pytest test and rejects dynamic or ambiguous drafts."""

    def parse(self, source: str) -> _Parsed:
        try:
            module = ast.parse(source)
        except SyntaxError as error:
            raise ValueError(f"unsupported or invalid Python scenario syntax: {error.msg}") from error
        functions = [node for node in module.body if isinstance(node, ast.FunctionDef)]
        if len(functions) != 1 or any(
            not isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef))
            for node in module.body
        ):
            raise ValueError("supported scenarios contain module imports and exactly one test function")
        function = functions[0]
        if not function.name.startswith("test_") or any(self._is_parameterize(item) for item in function.decorator_list):
            raise ValueError("unsupported dynamic test generation")
        if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Yield, ast.YieldFrom, ast.Await)) for node in ast.walk(function) if node is not function):
            raise ValueError("unsupported dynamic test form")
        lines = source.splitlines()
        first_body = function.body[0].lineno if function.body else (function.end_lineno or function.lineno) + 1
        header_start = min([function.lineno, *(item.lineno for item in function.decorator_list)])
        header = "\n".join(lines[header_start - 1:first_body - 1])
        scaffolding, nodes = [], []
        for node in module.body:
            if isinstance(node, ast.FunctionDef):
                continue
            if self._is_pytest_import(node):
                scaffolding.append(self._source(source, node))
            else:
                nodes.append(self._node(_NodeRequest(source, node, True)))
        for node in function.body:
            if self._is_pytest_import(node):
                scaffolding.append(self._source(source, node))
            else:
                nodes.append(self._node(_NodeRequest(source, node, False)))
        if not nodes:
            raise ValueError("scenario must contain at least one behavior fragment")
        return _Parsed(tuple(scaffolding), header, tuple(nodes))

    def _node(self, request: _NodeRequest) -> _Node:
        kind = self._kind(request.node)
        return _Node(kind, self._source(request.source, request.node), SourceSpan(request.node.lineno, request.node.end_lineno or request.node.lineno), request.module_scope, self._capability(request.node))

    @staticmethod
    def _source(source: str, node: ast.AST) -> str:
        value = ast.get_source_segment(source, node)
        if not value:
            raise ValueError("parser could not recover a complete source fragment")
        return textwrap.dedent(value).strip("\n")

    @staticmethod
    def _is_pytest_import(node: ast.stmt) -> bool:
        return isinstance(node, ast.Import) and any(item.name == "pytest" for item in node.names) or isinstance(node, ast.ImportFrom) and node.module == "pytest"

    @staticmethod
    def _is_parameterize(node: ast.expr) -> bool:
        return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "parametrize"

    @staticmethod
    def _kind(node: ast.stmt) -> PythonFragmentKind:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return PythonFragmentKind.PRODUCTION_IMPORT
        if isinstance(node, ast.Assert):
            return PythonFragmentKind.ASSERTION
        if isinstance(node, ast.With):
            return PythonFragmentKind.RAISES_BLOCK if any(PythonScenarioParser._is_raises(item.context_expr) for item in node.items) else PythonFragmentKind.WITH_BLOCK
        if isinstance(node, ast.If):
            return PythonFragmentKind.IF_BLOCK
        if isinstance(node, (ast.For, ast.While)):
            return PythonFragmentKind.LOOP_BLOCK
        if isinstance(node, ast.Try):
            return PythonFragmentKind.TRY_BLOCK
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            return PythonFragmentKind.CONSTRUCTOR
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            return PythonFragmentKind.CALL
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            return PythonFragmentKind.DECLARATION
        raise ValueError(f"unsupported Python statement form: {type(node).__name__}")

    @staticmethod
    def _is_raises(expression: ast.expr) -> bool:
        return isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute) and expression.func.attr == "raises"

    @staticmethod
    def _capability(node: ast.stmt) -> str:
        if isinstance(node, ast.Import):
            return node.names[0].name
        if isinstance(node, ast.ImportFrom):
            return node.names[0].name
        call = node.value if isinstance(node, (ast.Assign, ast.Expr)) else None
        if isinstance(call, ast.Call):
            if isinstance(call.func, ast.Name):
                return call.func.id
            if isinstance(call.func, ast.Attribute):
                return call.func.attr
        return type(node).__name__


def _span(node: ast.stmt) -> SourceSpan:
    return SourceSpan(node.lineno, node.end_lineno or node.lineno)


def _issue(code: ScenarioCandidateIssueCode, detail: str, node: ast.stmt | None = None) -> ScenarioCandidateIssue:
    return ScenarioCandidateIssue(code.value, detail, None if node is None else _span(node))


def _decorator_name(node: ast.expr) -> str:
    return ast.unparse(node.func if isinstance(node, ast.Call) else node)


@dataclass(frozen=True)
class _TestFunctionDocstring:
    function_name: str
    node: ast.Expr


@dataclass(frozen=True)
class _StandaloneStringExpression:
    function_name: str
    node: ast.Expr


@dataclass(frozen=True)
class _CandidateAssessmentFacts:
    module_docstring_node: ast.stmt | None
    test_function_docstrings: tuple[_TestFunctionDocstring, ...]
    standalone_string_expressions: tuple[_StandaloneStringExpression, ...]
    tests: tuple[ast.FunctionDef, ...]
    helpers: tuple[ast.FunctionDef, ...]
    fixtures: tuple[ast.FunctionDef, ...]
    classes: tuple[ast.ClassDef, ...]
    async_functions: tuple[ast.AsyncFunctionDef, ...]
    parameterized: tuple[ast.FunctionDef, ...]
    unsupported_top: tuple[ast.stmt, ...]
    nested: tuple[ast.stmt, ...]
    references: tuple[str, ...]
    substitutes: tuple[str, ...]
    mocked: tuple[str, ...]
    evasions: tuple[str, ...]
    identities: tuple[str, ...]


class PythonCandidateAssessmentFactory:
    """Collects strict Python candidate facts without throwing away diagnostics."""

    def assess(self, request: ScenarioCandidateAssessmentRequest) -> ScenarioCandidateAssessment:
        if request.contract.language_id != PYTHON_LANGUAGE_ID or request.contract.framework != "pytest":
            raise ValueError("Python candidate assessment requires the python pytest contract")
        try:
            module = ast.parse(request.candidate.source)
        except SyntaxError as error:
            span = None if error.lineno is None else SourceSpan(error.lineno, error.lineno)
            issue = ScenarioCandidateIssue(ScenarioCandidateIssueCode.SYNTAX_INVALID.value, f"Candidate has invalid Python syntax at line {error.lineno}: {error.msg}.", span)
            return ScenarioCandidateAssessment(False, (), issues=(issue,))
        return self._assessment(request, module)

    def _assessment(self, request: ScenarioCandidateAssessmentRequest, module: ast.Module) -> ScenarioCandidateAssessment:
        facts = _candidate_facts(request, module)
        assessment = _assessment_from_facts(facts)
        if assessment.accepted:
            try:
                PythonScenarioParser().parse(request.candidate.source)
            except ValueError as error:
                issue = _issue(ScenarioCandidateIssueCode.UNUSABLE_ARTIFACT, str(error))
                return replace(assessment, issues=(issue,))
        return assessment


def _candidate_facts(request: ScenarioCandidateAssessmentRequest, module: ast.Module) -> _CandidateAssessmentFacts:
    functions = tuple(node for node in module.body if isinstance(node, ast.FunctionDef))
    async_functions = tuple(node for node in module.body if isinstance(node, ast.AsyncFunctionDef))
    tests = tuple(node for node in functions if node.name.startswith("test_"))
    helpers = tuple(node for node in functions if not node.name.startswith("test_"))
    classes = tuple(node for node in module.body if isinstance(node, ast.ClassDef))
    fixtures = tuple(node for node in functions if any(_decorator_name(item).endswith("fixture") for item in node.decorator_list))
    parameterized = tuple(node for node in tests if any(_decorator_name(item).endswith("parametrize") for item in node.decorator_list))
    doc_node = module.body[0] if ast.get_docstring(module) is not None else None
    allowed = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef)
    unsupported_top = tuple(node for node in module.body if not isinstance(node, allowed) and node is not doc_node)
    nested = tuple(node for test in tests for node in ast.walk(test) if node is not test and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    production_module = Path(request.production_path).with_suffix("").as_posix().replace("/", ".")
    production_name = production_module.rsplit(".", 1)[-1]
    references = (request.production_path,) if PythonCandidateAnalyzer._references(module, production_module) else ()
    substitutes = PythonCandidateAnalyzer._substitutes(module, production_name)
    mocked = PythonCandidateAnalyzer._mocked_targets(_MockAnalysisRequest(module, production_module))
    evasions = PythonCandidateAnalyzer._evasions(module)
    test_function_docstrings = tuple(
        _TestFunctionDocstring(test.name, test.body[0])
        for test in tests
        if ast.get_docstring(test) is not None and isinstance(test.body[0], ast.Expr)
    )
    docstring_nodes = {id(item.node) for item in test_function_docstrings}
    standalone_string_expressions = tuple(
        _StandaloneStringExpression(test.name, node)
        for test in tests
        for node in ast.walk(test)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        and id(node) not in docstring_nodes
    )
    identities = tuple(f"{request.candidate.test_path}::{node.name}" for node in tests)
    return _CandidateAssessmentFacts(
        doc_node, test_function_docstrings, standalone_string_expressions, tests,
        helpers, fixtures, classes, async_functions, parameterized, unsupported_top,
        nested, references, substitutes, mocked, evasions, identities,
    )


def _assessment_from_facts(facts: _CandidateAssessmentFacts) -> ScenarioCandidateAssessment:
    issues = _candidate_issues(facts)
    return ScenarioCandidateAssessment(
        True, facts.identities, tuple(node.name for node in facts.helpers), tuple(node.name for node in facts.fixtures),
        tuple(node.name for node in facts.classes), tuple(node.name for node in facts.async_functions),
        tuple(node.name for node in facts.parameterized), facts.module_docstring_node is not None,
        tuple(type(node).__name__ for node in facts.unsupported_top), tuple(type(node).__name__ for node in facts.nested),
        facts.references, facts.substitutes, facts.mocked, facts.evasions, tuple(issues),
    )


def _candidate_issues(facts: _CandidateAssessmentFacts) -> list[ScenarioCandidateIssue]:
    issues: list[ScenarioCandidateIssue] = []
    if facts.module_docstring_node is not None:
        issues.append(_issue(ScenarioCandidateIssueCode.MODULE_DOCSTRING, "Remove the module docstring; the contract permits imports, module data, and one ordinary top-level test only.", facts.module_docstring_node))
    for docstring in facts.test_function_docstrings:
        span = _span(docstring.node)
        detail = (
            f"Remove the standalone string literal at the start of test function "
            f"{docstring.function_name} at lines {span.start_line}-{span.end_line}. "
            "Test-function docstrings are not permitted by the strict one-scenario "
            "grammar. Preserve the remaining import, setup, operation and assertions."
        )
        issues.append(_issue(ScenarioCandidateIssueCode.TEST_FUNCTION_DOCSTRING, detail, docstring.node))
    for expression in facts.standalone_string_expressions:
        span = _span(expression.node)
        detail = (
            f"Remove the standalone string-expression statement at lines "
            f"{span.start_line}-{span.end_line} in test function {expression.function_name}; "
            "standalone string-expression statements are not permitted by the strict one-scenario grammar."
        )
        issues.append(_issue(ScenarioCandidateIssueCode.STANDALONE_STRING_EXPRESSION, detail, expression.node))
    if not facts.tests:
        issues.append(_issue(ScenarioCandidateIssueCode.NO_TEST, "Define exactly one supported pytest test: one ordinary top-level function named test_* ."))
    if len(facts.tests) > 1:
        issues.append(_issue(ScenarioCandidateIssueCode.MULTIPLE_TESTS, "Keep exactly one supported pytest test; remove the additional test functions.", facts.tests[1]))
    for node in facts.helpers:
        issues.append(_issue(ScenarioCandidateIssueCode.HELPER_FUNCTION, f"Remove helper function {node.name}; move its setup directly into the single test.", node))
    for node in facts.fixtures:
        issues.append(_issue(ScenarioCandidateIssueCode.FIXTURE, f"Remove fixture {node.name}; fixtures are not supported in a scenario candidate.", node))
    for class_node in facts.classes:
        issues.append(_issue(ScenarioCandidateIssueCode.TEST_CLASS, f"Remove class {class_node.name}; test classes are not supported.", class_node))
    for async_node in facts.async_functions:
        issues.append(_issue(ScenarioCandidateIssueCode.ASYNC_TEST, f"Replace async test {async_node.name} with an ordinary synchronous pytest test.", async_node))
    for node in facts.parameterized:
        issues.append(_issue(ScenarioCandidateIssueCode.PARAMETERIZED_TEST, f"Remove pytest parameterization from {node.name}; submit one ordinary test case.", node))
    for top_node in facts.unsupported_top:
        issues.append(_issue(ScenarioCandidateIssueCode.UNSUPPORTED_TOP_LEVEL, f"Remove unsupported top-level {type(top_node).__name__}; only imports, module data, and one test are allowed.", top_node))
    for nested_node in facts.nested:
        issues.append(_issue(ScenarioCandidateIssueCode.UNSUPPORTED_NESTED, f"Remove nested {type(nested_node).__name__}; dynamic nested declarations are unsupported.", nested_node))
    if not facts.references:
        issues.append(_issue(ScenarioCandidateIssueCode.MISSING_PRODUCTION_REFERENCE, "Import or directly reference the declared production module: the candidate does not reference the declared production path."))
    for name in facts.substitutes:
        issues.append(_issue(ScenarioCandidateIssueCode.SUBSTITUTE_IMPLEMENTATION, f"Remove substitute production implementation {name}; exercise the declared production module instead."))
    for target in facts.mocked:
        issues.append(_issue(ScenarioCandidateIssueCode.MOCKED_BEHAVIOR, f"Remove behavior mock {target}; it mocks the behavior under development, so exercise the real declared production path."))
    for marker in facts.evasions:
        code = ScenarioCandidateIssueCode.SKIP_OR_XFAIL if marker in {"skip", "xfail"} else ScenarioCandidateIssueCode.MISSING_CAPABILITY_EVASION
        issues.append(_issue(code, f"Remove {marker}; it is a missing-capability evasion, so do not skip, xfail, or evade a missing production capability."))
    return issues


def _patch_targets_production(call: ast.Call, production_module: str) -> bool:
    target = call.args[0] if call.args else next(
        (keyword.value for keyword in call.keywords if keyword.arg == "target"), None,
    )
    if target is None:
        return False
    spelling = target.value if isinstance(target, ast.Constant) and isinstance(target.value, str) else ast.unparse(target)
    return spelling == production_module or spelling.startswith(production_module + ".")


def _framework_reference(module: ast.Module, expression: ast.AST) -> str:
    """Recognise imported test-framework operations, never product member policy."""
    if not isinstance(expression, (ast.Name, ast.Attribute)):
        return ""
    spelling = ast.unparse(expression)
    root, _, suffix = spelling.partition(".")
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if root == (alias.asname or alias.name.split(".")[0]):
                    imported = alias.name if alias.asname else root
                    return ".".join(part for part in (imported, suffix) if part)
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if root == (alias.asname or alias.name):
                    return ".".join(part for part in (node.module, alias.name, suffix) if part)
        if isinstance(node, ast.FunctionDef) and root == "monkeypatch":
            if any(argument.arg == root for argument in node.args.args):
                return "pytest." + spelling
    return ""


class PythonCandidateAnalyzer:
    """Owns Python candidate validity and production-reference integrity facts."""

    def analyse(
        self,
        candidate: ScenarioSourceCandidate,
        production_path: str,
    ) -> ScenarioStaticAnalysis:
        module = ast.parse(candidate.source)
        functions = [node for node in module.body if isinstance(node, ast.FunctionDef)]
        if len(functions) != 1 or not functions[0].name.startswith("test_"):
            raise ValueError("candidate must define exactly one supported pytest test")
        function = functions[0]
        identity = f"{candidate.test_path}::{function.name}"
        production_module = Path(production_path).with_suffix("").as_posix().replace("/", ".")
        production_name = production_module.rsplit(".", 1)[-1]
        reference_paths = (production_path,) if self._references(module, production_module) else ()
        substitutes = self._substitutes(module, production_name)
        mocked_targets = self._mocked_targets(
            _MockAnalysisRequest(module, production_module)
        )
        evasions = self._evasions(module)
        analysis = ScenarioStaticAnalysis(
            identity,
            reference_paths,
            substitutes,
            mocked_targets,
            evasions,
        )
        if analysis.rejection_feedback() is None:
            PythonScenarioParser().parse(candidate.source)
        return analysis

    @staticmethod
    def _references(module: ast.Module, production_module: str) -> bool:
        for node in ast.walk(module):
            if isinstance(node, ast.Import) and any(
                item.name == production_module or item.name.startswith(f"{production_module}.")
                for item in node.names
            ):
                return True
            if isinstance(node, ast.ImportFrom) and node.module == production_module:
                return True
        return False

    @staticmethod
    def _substitutes(module: ast.Module, production_name: str) -> tuple[str, ...]:
        expected = re.sub(r"[^a-z0-9]", "", production_name.lower())
        matches = []
        for node in module.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                defined = re.sub(r"[^a-z0-9]", "", node.name.lower())
                if defined != "test" and expected in defined and not node.name.startswith("test_"):
                    matches.append(node.name)
        return tuple(matches)

    @staticmethod
    def _mocked_targets(request: _MockAnalysisRequest) -> tuple[str, ...]:
        matches = []
        for node in ast.walk(request.module):
            if not isinstance(node, ast.Call):
                continue
            operation = _framework_reference(request.module, node.func)
            if operation in {
                "unittest.mock.patch", "unittest.mock.patch.object",
                "pytest.monkeypatch.setattr", "pytest.monkeypatch.setitem",
            } and _patch_targets_production(node, request.production_module):
                matches.append(ast.unparse(node.func))
        return tuple(dict.fromkeys(matches))

    @staticmethod
    def _evasions(module: ast.Module) -> tuple[str, ...]:
        matches = []
        for node in ast.walk(module):
            expression = node.func if isinstance(node, ast.Call) else node
            operation = _framework_reference(module, expression)
            if operation in {"pytest.skip", "pytest.xfail", "pytest.mark.skip", "pytest.mark.skipif", "pytest.mark.xfail"}:
                matches.append("xfail" if operation.endswith("xfail") else "skip")
            if operation == "pytest.importorskip":
                matches.append("missing_capability_evasion")
            if isinstance(node, ast.Try):
                catches_import = any(
                    isinstance(handler.type, ast.Tuple)
                    and any(isinstance(item, ast.Name) and item.id in {"ImportError", "ModuleNotFoundError"} for item in handler.type.elts)
                    or isinstance(handler.type, ast.Name) and handler.type.id in {"ImportError", "ModuleNotFoundError"}
                    for handler in node.handlers
                )
                hides_failure = any(
                    isinstance(item, ast.Assert) and isinstance(item.test, ast.Constant) and item.test.value is True
                    for handler in node.handlers
                    for item in handler.body
                )
                if catches_import and hides_failure:
                    matches.append("missing_capability_evasion")
        return tuple(dict.fromkeys(matches))


class PythonCandidateCanonicaliser:
    """Renames one supported pytest function before ATHBA freezes its draft."""

    def canonicalise(
        self,
        candidate: ScenarioSourceCandidate,
        planned_identity: str,
    ) -> ScenarioSourceCandidate:
        planned_path, separator, planned_name = planned_identity.partition("::")
        if separator != "::" or planned_path != candidate.test_path or not planned_name.startswith("test_"):
            raise ValueError("planned pytest identity is invalid")
        module = ast.parse(candidate.source)
        function = next(node for node in module.body if isinstance(node, ast.FunctionDef))
        if function.name == planned_name:
            return candidate
        lines = candidate.source.splitlines()
        line_index = function.lineno - 1
        lines[line_index] = re.sub(
            rf"(\s*def\s+){re.escape(function.name)}(?=\s*\()",
            rf"\1{planned_name}",
            lines[line_index],
            count=1,
        )
        return replace(candidate, source="\n".join(lines) + "\n")


class PythonFrontierMaterialiser:
    """Emits complete modules and maps each emitted fragment to artifact lines."""

    def materialise(self, request: FrontierMaterialisationRequest) -> MaterialisedTestArtifact:
        parsed = PythonScenarioParser().parse(request.model.complete_source)
        if len(parsed.nodes) != len(request.fragments):
            raise ValueError("fragments do not match the approved Python scenario")
        selected_ids = set(request.frontier.materialised_fragment_ids)
        rows: list[str] = []
        spans: list[FragmentSourceSpan] = []
        buffer = _Buffer(rows, spans)
        self._append_scaffolding(rows, parsed.scaffolding)
        for index, node in enumerate(parsed.nodes):
            fragment = request.fragments[index]
            if node.module_scope and fragment.fragment_id in selected_ids:
                self._append_fragment(buffer, _Emission(fragment, node.source, ""))
        if rows:
            rows.append("")
        rows.extend(parsed.header.splitlines())
        body = [(request.fragments[index], node) for index, node in enumerate(parsed.nodes) if not node.module_scope and request.fragments[index].fragment_id in selected_ids]
        if not body:
            rows.append("    pass")
        for fragment, node in body:
            self._append_fragment(buffer, _Emission(fragment, node.source, "    "))
        source = "\n".join(rows) + "\n"
        active = request.frontier.active_fragment_id
        if active not in {item.fragment_id for item in request.fragments}:
            raise ValueError("active frontier fragment is unknown")
        return MaterialisedTestArtifact(
            "python-pytest", PYTEST_ADAPTER_VERSION, request.model.scenario_id,
            request.frontier.index, request.model.canonical_test_identity, source,
            active, tuple(spans), request.base_revision,
        )

    @staticmethod
    def _append_scaffolding(rows: list[str], scaffolding: tuple[str, ...]) -> None:
        for source in scaffolding:
            rows.extend(source.splitlines())

    @staticmethod
    def _append_fragment(buffer: _Buffer, emission: _Emission) -> None:
        start = len(buffer.rows) + 1
        buffer.rows.extend(textwrap.indent(emission.source, emission.indent).splitlines())
        buffer.spans.append(FragmentSourceSpan(emission.fragment.fragment_id, SourceSpan(start, len(buffer.rows))))


class PytestStructuredExecutor:
    """Runs pytest through hooks and converts facts without trusting console wording."""

    def execute(self, request: FrontierExecutionRequest) -> BoundaryDiagnostic:
        root = Path(request.project_root).resolve()
        path = (root / request.test_path).resolve()
        if root not in path.parents:
            return BoundaryDiagnostic("infrastructure", "test path escapes project root")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(request.artifact.complete_source, encoding="utf-8")
        self._invalidate_project_caches(root)
        syntax = self._syntax(path, request.test_path)
        if syntax is not None:
            return syntax
        node = request.artifact.canonical_test_identity
        command = [sys.executable, "-m", "core.development.python_pytest_probe", str(root), node, request.production_path or ""]
        environment = os.environ | {"PYTHONPATH": str(Path(__file__).resolve().parents[2])}
        completed = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=30)
        try:
            facts = json.loads(completed.stdout.splitlines()[-1])
        except json.JSONDecodeError:
            return BoundaryDiagnostic("infrastructure", "structured pytest probe did not return JSON", ("pytest-probe",))
        return self._diagnostic(facts)

    @staticmethod
    def _invalidate_project_caches(root: Path) -> None:
        for cache in root.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)

    @staticmethod
    def _syntax(path: Path, test_path: str) -> BoundaryDiagnostic | None:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as error:
            return BoundaryDiagnostic("syntax_error", error.msg, (test_path,), (DiagnosticFact("source_line", str(error.lineno or 0)),))
        return None

    @staticmethod
    def _diagnostic(facts: dict[str, object]) -> BoundaryDiagnostic:
        pairs = tuple(DiagnosticFact(str(name), str(value)) for name, value in facts.items() if value not in (None, "", [], False))
        evidence_value = facts.get("evidence_refs", ())
        evidence = tuple(str(item) for item in evidence_value) if isinstance(evidence_value, list) else ()
        outcome = str(facts.get("outcome", "error"))
        message = str(facts.get("failure_message") or outcome)
        if outcome == "passed":
            return BoundaryDiagnostic("green", message, evidence, pairs)
        if not facts.get("collection_succeeded", False):
            return BoundaryDiagnostic("collection_failure", message, evidence, pairs)
        return BoundaryDiagnostic("pytest_failure", message, evidence, pairs)


class PythonBoundaryClassifier:
    """Accepts only evidence at the active complete Python fragment."""

    def classify(self, request: BoundaryClassificationRequest) -> BoundaryAssessment:
        facts = {item.name: item.value for item in request.diagnostic.facts}
        if request.diagnostic.kind == "green":
            return BoundaryAssessment(BoundaryOutcome.GREEN.value, request.active_fragment.fragment_id, request.diagnostic)
        if request.diagnostic.kind == "syntax_error":
            return BoundaryAssessment(BoundaryOutcome.INVALID_TEST_SYNTAX.value, request.active_fragment.fragment_id, request.diagnostic)
        if request.diagnostic.kind == "infrastructure":
            return BoundaryAssessment(BoundaryOutcome.INFRASTRUCTURE_FAILURE.value, request.active_fragment.fragment_id, request.diagnostic)
        if request.prior_frontier_status not in (None, BoundaryOutcome.GREEN.value) or not self._at_active_span(request, facts):
            return BoundaryAssessment(BoundaryOutcome.FAILURE_BEFORE_FRONTIER.value, request.active_fragment.fragment_id, request.diagnostic)
        if request.diagnostic.kind == "collection_failure":
            outcome = BoundaryOutcome.VALID_MISSING_CAPABILITY_RED if request.active_fragment.kind == PythonFragmentKind.PRODUCTION_IMPORT.value else BoundaryOutcome.FAILURE_BEFORE_FRONTIER
            return BoundaryAssessment(outcome.value, request.active_fragment.fragment_id, request.diagnostic)
        exception = facts.get("exception_type", "")
        active_kind = request.active_fragment.kind
        if exception == "AttributeError":
            proven = facts.get("missing_production_member") == "True" and all(
                facts.get(name) == expected for name, expected in (
                    ("collection_succeeded", "True"), ("requested_node_found", "True"),
                    ("requested_node_executed", "True"), ("setup_outcome", "passed"),
                    ("call_outcome", "failed"), ("teardown_outcome", "passed"),
                )
            )
            supported = active_kind in {item.value for item in PythonFragmentKind}
            outcome = BoundaryOutcome.VALID_MISSING_CAPABILITY_RED if proven and supported else BoundaryOutcome.UNSUPPORTED_LANGUAGE_BOUNDARY
            return BoundaryAssessment(outcome.value, request.active_fragment.fragment_id, request.diagnostic)
        if exception in {"ImportError", "ModuleNotFoundError", "NameError"} and active_kind in {item.value for item in (PythonFragmentKind.PRODUCTION_IMPORT, PythonFragmentKind.CONSTRUCTOR, PythonFragmentKind.CALL)}:
            return BoundaryAssessment(BoundaryOutcome.VALID_MISSING_CAPABILITY_RED.value, request.active_fragment.fragment_id, request.diagnostic)
        if active_kind == PythonFragmentKind.ASSERTION and (
            exception == "AssertionError" or request.diagnostic.message.lstrip().startswith("assert ")
        ):
            return BoundaryAssessment(BoundaryOutcome.VALID_BEHAVIORAL_RED.value, request.active_fragment.fragment_id, request.diagnostic)
        if active_kind == PythonFragmentKind.RAISES_BLOCK and "DID NOT RAISE" in request.diagnostic.message:
            return BoundaryAssessment(BoundaryOutcome.VALID_BEHAVIORAL_RED.value, request.active_fragment.fragment_id, request.diagnostic)
        return BoundaryAssessment(BoundaryOutcome.UNSUPPORTED_LANGUAGE_BOUNDARY.value, request.active_fragment.fragment_id, request.diagnostic)

    @staticmethod
    def _at_active_span(request: BoundaryClassificationRequest, facts: dict[str, str]) -> bool:
        line = int(facts.get("source_line", "0"))
        for span in request.artifact.fragment_source_spans:
            if span.fragment_id == request.active_fragment.fragment_id:
                return span.span.start_line <= line <= span.span.end_line
        return False


class PythonPytestAdapter:
    descriptor = LanguageAdapterDescriptor("python-pytest", PYTEST_ADAPTER_VERSION, PYTHON_LANGUAGE_ID)

    def parse_scenario(self, request: ScenarioParseRequest) -> ScenarioModel:
        if request.draft.language_id != PYTHON_LANGUAGE_ID:
            raise ValueError("unsupported language boundary")
        PythonScenarioParser().parse(request.draft.source)
        return ScenarioModel(request.draft.scenario_id, PYTHON_LANGUAGE_ID, PYTEST_ADAPTER_VERSION, request.draft.canonical_test_identity, request.draft.source, request.draft.test_path)

    def validate_scenario_syntax(self, request: SyntaxValidationRequest) -> bool:
        PythonScenarioParser().parse(request.model.complete_source)
        return True

    def analyse_candidate(
        self,
        candidate: ScenarioSourceCandidate,
        production_path: str,
    ) -> ScenarioStaticAnalysis:
        return PythonCandidateAnalyzer().analyse(candidate, production_path)

    def assess_candidate(
        self,
        request: ScenarioCandidateAssessmentRequest,
    ) -> ScenarioCandidateAssessment:
        return PythonCandidateAssessmentFactory().assess(request)

    def canonicalise_candidate(
        self,
        candidate: ScenarioSourceCandidate,
        planned_identity: str,
    ) -> ScenarioSourceCandidate:
        return PythonCandidateCanonicaliser().canonicalise(candidate, planned_identity)

    def fragment_scenario(self, request: FragmentationRequest) -> tuple[ScenarioFragment, ...]:
        parsed = PythonScenarioParser().parse(request.model.complete_source)
        result: list[ScenarioFragment] = []
        for index, node in enumerate(parsed.nodes):
            result.append(ScenarioFragment(f"python-{index + 1}-{node.kind.value}", request.model.scenario_id, node.kind.value, node.source, node.capability, tuple(item.fragment_id for item in result), node.source_span))
        return tuple(result)

    def materialise_frontier(self, request: FrontierMaterialisationRequest) -> MaterialisedTestArtifact:
        return PythonFrontierMaterialiser().materialise(request)

    def execute_frontier(self, request: FrontierExecutionRequest) -> BoundaryDiagnostic:
        return PytestStructuredExecutor().execute(request)

    def classify_boundary(self, request: BoundaryClassificationRequest) -> BoundaryAssessment:
        return PythonBoundaryClassifier().classify(request)

    def materialise_final_test(self, request: FinalTestMaterialisationRequest) -> MaterialisedTestArtifact:
        fragments = request.fragments
        frontier = type("FinalFrontier", (), {"index": len(fragments) - 1, "active_fragment_id": fragments[-1].fragment_id, "materialised_fragment_ids": tuple(item.fragment_id for item in fragments)})()
        return self.materialise_frontier(FrontierMaterialisationRequest(request.model, fragments, frontier, request.base_revision))

    def regression_contract(self, request: RegressionContractRequest) -> RegressionContract:
        return RegressionContract((sys.executable, "-m", "pytest", "-q"))
