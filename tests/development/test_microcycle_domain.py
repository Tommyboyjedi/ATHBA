import pytest

from core.development.microcycle_domain import (
    BoundaryAssessment,
    BoundaryDiagnostic,
    DeveloperAttempt,
    FragmentSourceSpan,
    LanguageAdapterCatalog,
    LanguageAdapterDescriptor,
    MaterialisedTestArtifact,
    MicrocycleMigrationError,
    MicrocycleState,
    RegressionState,
    RetryCounts,
    ScenarioCompletion,
    ScenarioFragment,
    ScenarioFrontier,
    ScenarioIntentResult,
    ScenarioModel,
    SourceSpan,
    TestScenarioDraft,
)


def draft(language_id="python"):
    return TestScenarioDraft("scenario-1", "behavior-1", language_id, "complete test", "tests::test_example", "tests/test_example")


def fragments():
    return (
        ScenarioFragment("construct", "scenario-1", "statement", "book = Book()", "construct"),
        ScenarioFragment("loop", "scenario-1", "block", "for item in items:\n    use(item)", "iterate", ("construct",)),
    )


def state(items=None, frontier=None):
    items = fragments() if items is None else items
    frontier = ScenarioFrontier("scenario-1", 1, "loop", ("construct", "loop")) if frontier is None else frontier
    return MicrocycleState(
        draft(), ScenarioIntentResult("scenario-1", "approved", "intent evidence", ("intent",)),
        ScenarioModel("scenario-1", "python", "1", "tests::test_example", "complete test", "tests/test_example"),
        items, frontier, "base-1", "red-1", RetryCounts(2, 1, 3),
        (BoundaryAssessment("valid_missing_capability_red", "loop", BoundaryDiagnostic("missing_symbol", "Book", ("diagnostic",))),),
        (DeveloperAttempt(1, 1, "base-1", "candidate-1", ("attempt",)),),
        RegressionState("pending", ("pytest", "-q")), ScenarioCompletion("pending"),
    )


def test_persisted_microcycle_round_trip_includes_retries_and_adapter_version():
    payload = state().to_dict()
    restored = MicrocycleState.from_dict(payload)
    assert restored.to_dict() == payload
    assert restored.retry_counts == RetryCounts(2, 1, 3)
    assert restored.model.adapter_version == "1"


def test_legacy_pr17_payload_fails_with_explicit_migration_message():
    with pytest.raises(MicrocycleMigrationError, match="explicit migration"):
        MicrocycleState.from_dict({})


def test_duplicate_fragment_ids_are_rejected():
    duplicate = ScenarioFragment("construct", "scenario-1", "statement", "other", "other")
    with pytest.raises(ValueError, match="unique"):
        state((fragments()[0], duplicate), ScenarioFrontier("scenario-1", 1, "construct", ("construct", "construct")))


def test_invalid_frontier_order_and_dependency_cycle_are_rejected():
    with pytest.raises(ValueError, match="ordered"):
        state(frontier=ScenarioFrontier("scenario-1", 1, "loop", ("loop", "construct")))
    cyclic = (
        ScenarioFragment("first", "scenario-1", "statement", "a()", "a", ("second",)),
        ScenarioFragment("second", "scenario-1", "statement", "b()", "b", ("first",)),
    )
    with pytest.raises(ValueError, match="earlier and known"):
        state(cyclic, ScenarioFrontier("scenario-1", 1, "second", ("first", "second")))


def test_materialised_artifact_validates_source_spans():
    with pytest.raises(ValueError, match="source-span"):
        MaterialisedTestArtifact("fixture", "1", "scenario-1", 0, "test", "def test(): pass", "missing", (), "base")
    with pytest.raises(ValueError, match="source span"):
        SourceSpan(4, 3)


def test_unsupported_languages_fail_closed():
    with pytest.raises(ValueError, match="unsupported language boundary"):
        LanguageAdapterCatalog(()).for_language("rust")


class BlockFixture:
    """Small conformance fixture; its fragments are blocks, not raw source lines."""

    def __init__(self, language_id, complete_source, block_source):
        self.descriptor = LanguageAdapterDescriptor(f"{language_id}-fixture", "1", language_id)
        self.complete_source = complete_source
        self.block_source = block_source

    def fragment(self):
        return ScenarioFragment("block", "scenario-1", "block", self.block_source, "block")

    def materialise(self):
        fragment = self.fragment()
        return MaterialisedTestArtifact(
            self.descriptor.adapter_id, self.descriptor.adapter_version, "scenario-1", 0,
            "fixture::test", self.complete_source, fragment.fragment_id,
            (FragmentSourceSpan(fragment.fragment_id, SourceSpan(1, len(self.complete_source.splitlines()))),), "base",
        )


@pytest.mark.parametrize(
    ("language_id", "complete_source", "block_source", "closure"),
    (
        ("python", "def test_loop():\n    for item in items:\n        use(item)\n", "for item in items:\n        use(item)", "use(item)"),
        ("csharp", "[Fact]\nvoid Test() {\n  foreach (var item in items) { Use(item); }\n}\n", "foreach (var item in items) { Use(item); }", "}"),
        ("vba", "Public Sub Test()\n  If ok Then\n    UseItem\n  End If\nEnd Sub\n", "If ok Then\n    UseItem\n  End If", "End If"),
    ),
)
def test_language_conformance_fixtures_preserve_complete_blocks(language_id, complete_source, block_source, closure):
    fixture = BlockFixture(language_id, complete_source, block_source)
    artifact = fixture.materialise()
    assert artifact.complete_source == complete_source
    assert closure in fixture.fragment().source
    assert fixture.fragment().kind == "block"
    assert artifact.fragment_source_spans[0].fragment_id == "block"
