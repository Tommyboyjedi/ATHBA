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
    )

    restored = RepairPacket.from_dict(packet.to_dict())
    assert restored == packet
    assert "change" not in restored.evidence[0].lower()


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
