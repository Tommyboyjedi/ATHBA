from core.development.scenario_drafting_domain import ScenarioDraftAttempt, ScenarioDraftRunState
from core.development.strict_tdd_feature_execution_advance import _intent_review_is_pending


def test_invalid_candidate_requires_a_new_draft_submission():
    state = ScenarioDraftRunState(
        scenario_id="scenario",
        behavior_ref="behavior",
        source_requirement_refs=("SRC-1",),
        language_id="python",
        test_framework="pytest",
        allowed_test_path="tests/test_feature.py",
        development_base_revision="a" * 40,
        attempts=(
            ScenarioDraftAttempt(
                attempt_number=1,
                work_unit_id="scenario-draft-1",
                change_id="change-1",
                candidate_revision="b" * 40,
                evidence_location="evidence-1",
                status="candidate_invalid",
                feedback="candidate test identity does not match the behavior ticket",
            ),
        ),
    )

    assert not _intent_review_is_pending(state)
