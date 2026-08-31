from core.development.failure_progression import (
    DependencyDecision,
    DependencyDisposition,
    FAILURE_PRIORITY,
    FailureClassification,
    FailureObservation,
    FailureProgressState,
    FailureProgressionPolicy,
    FailureRecordRequest,
    FailureRouteState,
    PacketKind,
    PrerequisiteDeferralRequest,
    ProgressionAction,
    RepairPacket,
    RetryBudget,
    RetryRoute,
    SplitChildStep,
    UnclassifiedAnalysis,
    WorkPacketSplit,
)


def observation(*classes: FailureClassification) -> FailureObservation:
    return FailureObservation(source="pytest", message="candidate failed", plausible=list(classes), evidence_refs=["packet.json"])


def test_every_documented_class_has_fixed_priority_and_action() -> None:
    policy = FailureProgressionPolicy()

    for classification in FailureClassification:
        decision = policy.decide([observation(classification)])
        assert decision.dominant is classification
        assert decision.priority == FAILURE_PRIORITY[classification]
        assert isinstance(decision.action, ProgressionAction)


def test_lowest_numeric_priority_is_dominant_and_all_plausible_classes_are_preserved() -> None:
    policy = FailureProgressionPolicy()
    decision = policy.decide([
        observation(FailureClassification.REVIEW_QUALITY_FAILURE, FailureClassification.TEST_COLLECTION_OR_BOOTSTRAP_FAILURE),
        observation(FailureClassification.DEVELOPER_CANDIDATE_DEFECT),
    ])

    assert decision.dominant is FailureClassification.TEST_COLLECTION_OR_BOOTSTRAP_FAILURE
    assert decision.plausible == [
        FailureClassification.TEST_COLLECTION_OR_BOOTSTRAP_FAILURE,
        FailureClassification.DEVELOPER_CANDIDATE_DEFECT,
        FailureClassification.REVIEW_QUALITY_FAILURE,
    ]


def test_empty_plausible_evidence_fails_closed_as_unclassified() -> None:
    decision = FailureProgressionPolicy().decide([FailureObservation(source="executor", message="unknown")])

    assert decision.dominant is FailureClassification.UNCLASSIFIED_FAILURE
    assert decision.action is ProgressionAction.ANALYZE_UNCLASSIFIED


def test_repair_packet_is_descriptive_and_round_trips() -> None:
    packet = RepairPacket(
        kind=PacketKind.REPAIR,
        role="Tester",
        work_unit_id="step--red",
        trusted_revision="abc",
        original_objective="prove duplicate identifiers are rejected",
        allowed_paths=["tests/test_component.py"],
        classification=FailureClassification.TESTER_CANDIDATE_DEFECT,
        previous_candidate="candidate",
        evidence=["The attempted test never reached the duplicate-id operation."],
        originating_phase="red",
        changed_paths=["docs/out_of_scope.md"],
    )

    restored = RepairPacket.from_dict(packet.to_dict())
    assert restored == packet
    assert "change" not in restored.evidence[0].lower()


def test_failure_observation_round_trips_policy_scope_evidence() -> None:
    observation = FailureObservation(
        source="green_execution",
        message="changed_paths out-of-scope edit",
        evidence_refs=["packet.json"],
        plausible=[FailureClassification.CHANGE_SCOPE_VIOLATION],
        status="checks_failed",
        work_unit_id="step--green",
        phase="green",
        allowed_paths=["reservation_book.py"],
        changed_paths=["docs/out_of_scope.md"],
    )

    assert FailureObservation.from_dict(observation.to_dict()) == observation


def test_retry_budgets_are_per_route_not_global() -> None:
    policy = FailureProgressionPolicy()
    state = FailureProgressState()
    decision = policy.decide([observation(FailureClassification.TESTER_CANDIDATE_DEFECT)])
    state = policy.record(
        FailureRecordRequest(
            state=state,
            decision=decision,
            route=RetryRoute.TESTER_REPAIR,
            next_state=FailureRouteState.AWAITING_REPAIR,
        )
    )

    assert not policy.retry_allowed(RetryBudget(state=state, route=RetryRoute.TESTER_REPAIR, budget=1))
    assert policy.retry_allowed(RetryBudget(state=state, route=RetryRoute.DEVELOPER_REPAIR, budget=1))


def test_progress_state_round_trips_decision_retry_lineage_and_blocker() -> None:
    policy = FailureProgressionPolicy()
    decision = policy.decide([observation(FailureClassification.EXECUTOR_INFRASTRUCTURE_FAILURE)])
    state = policy.record(
        FailureRecordRequest(
            state=FailureProgressState(),
            decision=decision,
            next_state=FailureRouteState.BLOCKED_EXECUTOR,
            blocker="executor evidence is unavailable",
        )
    )

    restored = FailureProgressState.from_dict(state.to_dict())
    assert restored == state
    assert restored.history[0].dominant is FailureClassification.EXECUTOR_INFRASTRUCTURE_FAILURE


def test_dependency_split_and_unclassified_records_are_typed_and_durable() -> None:
    dependency = DependencyDecision(
        DependencyDisposition.ALREADY_PLANNED,
        "REQ-002",
        ["REQ-001"],
        "The duplicate-id behavior needs the resource creation behavior.",
    )
    split = WorkPacketSplit("REQ-003--green", ["REQ-003a--green", "REQ-003b--green"], "Create a reservation.", "The resource budget was exceeded.")
    analysis = UnclassifiedAnalysis("tool returned an unknown result", "unsupported executor response", "no known class matches the result")
    state = FailureProgressState(dependency_decisions=[dependency], splits=[split], unclassified_analysis=analysis)

    assert FailureProgressState.from_dict(state.to_dict()) == state


def test_prerequisite_deferral_preserves_state_and_records_declared_dependency() -> None:
    policy = FailureProgressionPolicy()
    decision = policy.decide([observation(FailureClassification.DEPENDENCY_OR_PREREQUISITE_FAILURE)])

    state = policy.defer_for_prerequisites(
        PrerequisiteDeferralRequest(
            state=FailureProgressState(),
            decision=decision,
            requirement_ref="REQ-2",
            prerequisite_refs=["REQ-1"],
        )
    )

    assert state.state is FailureRouteState.DEFERRED_DEPENDENCY
    assert state.deferred_requirement_refs == ["REQ-2"]
    assert state.prerequisite_links == {"REQ-2": ["REQ-1"]}
    assert state.dependency_decisions[-1].disposition is DependencyDisposition.ALREADY_PLANNED


def test_split_record_round_trips_child_steps_and_completed_lineage() -> None:
    child_a = SplitChildStep(
        step_id="RB-1a",
        requirement_refs=["RB-1"],
        focused_behavior="Adding the resource stores the identifier.",
        test_name="tests/test_reservation_book.py::test_add_resource_stores_identifier",
        expected_result="The resource id appears in the in-memory store.",
        test_path="tests/test_reservation_book.py",
        production_path="reservation_book.py",
        red_objective="Add a failing test for storing the resource identifier.",
        green_objective="Implement only enough code to store the resource identifier.",
        reason_next_smallest="This isolates identifier persistence before capacity accounting.",
    )
    child_b = SplitChildStep(
        step_id="RB-1b",
        requirement_refs=["RB-1"],
        focused_behavior="Availability reports the stored capacity.",
        test_name="tests/test_reservation_book.py::test_add_resource_reports_capacity",
        expected_result="available('room-a') returns the stored capacity.",
        test_path="tests/test_reservation_book.py",
        production_path="reservation_book.py",
        red_objective="Add a failing test for capacity reporting.",
        green_objective="Implement only enough code to report the stored capacity.",
        reason_next_smallest="This proves the observable capacity behavior after storage exists.",
        depends_on=["RB-1a"],
    )
    split = WorkPacketSplit(
        parent_work_unit_id="RB-1--green",
        parent_step_id="RB-1",
        parent_requirement_ref="RB-1",
        child_work_unit_ids=["RB-1a", "RB-1b"],
        preserved_objective="Implement add_resource.",
        rationale="The packet exceeded the resource budget and was decomposed.",
        trusted_revision="b" * 40,
        split_depth=2,
        child_steps=[child_a, child_b],
        completed_child_ids=["RB-1a"],
    )

    restored = WorkPacketSplit.from_dict(split.to_dict())

    assert restored == split
    assert restored.to_dict()["child_step_ids"] == ["RB-1a", "RB-1b"]


def test_failure_progress_state_loads_legacy_payload_defaults() -> None:
    restored = FailureProgressState.from_dict(
        {
            "history": [],
            "retry_counts": {"tester_repair": 1},
            "deferred_requirement_refs": ["REQ-1"],
            "prerequisite_links": {"REQ-2": ["REQ-1"]},
            "split_children": {},
            "repair_packets": [],
            "dependency_decisions": [],
            "splits": [],
            "blocker": "blocked",
        }
    )

    assert restored.state is FailureRouteState.ACTIVE
    assert restored.retry_counts == {"tester_repair": 1}
    assert restored.blocker == "blocked"
