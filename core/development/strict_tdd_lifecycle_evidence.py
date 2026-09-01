"""Typed lifecycle evidence, an append-only store, and passive proof reports."""
from __future__ import annotations
import fcntl, json, os, re, tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator, Protocol
from core.atomic_json_file import read_json_file, write_json_atomically
from core.development.microcycle_revision_state import MicrocycleRevisionState
from core.development.microcycle_domain import MicrocycleState
from core.development.scenario_drafting_domain import ScenarioDraftRunState
from core.development.strict_tdd_feature_domain import StrictTddFeatureState
_SECRET = re.compile('(?i)(?:api[_-]?key|password|authorization|bearer|token)\\s*[:=]\\s*\\S+|sk-[A-Za-z0-9_-]+')

class StrictTddLifecycleEventKind(str, Enum):
    RUN_STARTED = 'run_started'
    RUN_RESUMED = 'run_resumed'
    PROJECT_CREATED = 'project_created'
    PROJECT_LOADED = 'project_loaded'
    GATEKEEPER_STARTED = 'gatekeeper_started'
    GATEKEEPER_COMPLETED = 'gatekeeper_completed'
    BEHAVIOR_CONTRACT_STARTED = 'behavior_contract_started'
    BEHAVIOR_CONTRACT_COMPLETED = 'behavior_contract_completed'
    BEHAVIOR_SELECTED = 'behavior_selected'
    SCENARIO_DRAFTING_STARTED = 'scenario_drafting_started'
    SCENARIO_DRAFTING_COMPLETED = 'scenario_drafting_completed'
    SCENARIO_INTENT_STARTED = 'scenario_intent_started'
    SCENARIO_INTENT_COMPLETED = 'scenario_intent_completed'
    WORKING_REF_CREATED = 'working_ref_created'
    FRONTIER_MATERIALISED = 'frontier_materialised'
    FRONTIER_RED_ACCEPTED = 'frontier_red_accepted'
    DEVELOPER_STARTED = 'developer_started'
    DEVELOPER_COMPLETED = 'developer_completed'
    REGRESSION_STARTED = 'regression_started'
    REGRESSION_COMPLETED = 'regression_completed'
    CANONICAL_BASE_PROMOTED = 'canonical_base_promoted'
    FRONTIER_ADVANCED = 'frontier_advanced'
    SCENARIO_COMPLETED = 'scenario_completed'
    BEHAVIOR_REVIEW_STARTED = 'behavior_review_started'
    BEHAVIOR_REVIEW_COMPLETED = 'behavior_review_completed'
    BEHAVIOR_REPAIR_STARTED = 'behavior_repair_started'
    BEHAVIOR_REPAIR_COMPLETED = 'behavior_repair_completed'
    BEHAVIOR_COMPLETED = 'behavior_completed'
    RECONCILIATION_STARTED = 'reconciliation_started'
    RECONCILIATION_COMPLETED = 'reconciliation_completed'
    FEATURE_COMPLETED = 'feature_completed'
    FEATURE_BLOCKED = 'feature_blocked'
    TRANSITION_BLOCKED = 'transition_blocked'
    CONTROLLED_CHECKPOINT_STOP = 'controlled_checkpoint_stop'
    RUN_BLOCKED = 'run_blocked'
    RUN_COMPLETED = 'run_completed'

class StrictTddLifecycleStatus(str, Enum):
    STARTED = 'started'
    COMPLETED = 'completed'
    ACCEPTED = 'accepted'
    BLOCKED = 'blocked'
    CHECKPOINTED = 'checkpointed'

def _safe(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be non-empty')
    if _SECRET.search(value):
        raise ValueError(f'{label} must not contain a secret-like value')
    return value

def redact_secret_like_text(value: str) -> str:
    return '[REDACTED]' if _SECRET.search(value) else value

@dataclass(frozen=True)
class StrictTddLifecycleRunContext:
    run_id: str
    project_id: str
    original_requirement: str
    athba_version: str
    rack_ai_version: str

    def __post_init__(self) -> None:
        for value, label in ((self.run_id, 'run id'), (self.project_id, 'project id'), (self.original_requirement, 'original requirement'), (self.athba_version, 'ATHBA version'), (self.rack_ai_version, 'Rack AI version')):
            _safe(value, label)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> 'StrictTddLifecycleRunContext':
        return cls(**{key: str(item) for key, item in value.items()})

@dataclass(frozen=True)
class StrictTddLifecycleEvent:
    event_id: str
    sequence_number: int
    occurred_at_utc: datetime
    run_id: str
    project_id: str
    event_kind: StrictTddLifecycleEventKind
    status: StrictTddLifecycleStatus
    evidence_refs: tuple[str, ...]
    scenario_id: str | None = None
    behavior_ref: str | None = None
    frontier_index: int | None = None
    canonical_ref: str | None = None
    canonical_revision: str | None = None
    working_ref: str | None = None
    working_revision: str | None = None
    message: str | None = None
    candidate_revision: str | None = None

    def __post_init__(self) -> None:
        for value in (self.event_id, self.run_id, self.project_id, *self.evidence_refs, *tuple((item for item in (self.scenario_id, self.behavior_ref, self.canonical_ref, self.canonical_revision, self.working_ref, self.working_revision, self.message, self.candidate_revision) if item is not None))):
            _safe(value, 'event value')
        if self.sequence_number < 0:
            raise ValueError('event sequence number must be non-negative')
        if self.occurred_at_utc.tzinfo is None or self.occurred_at_utc.utcoffset() != UTC.utcoffset(self.occurred_at_utc):
            raise ValueError('event timestamp must be UTC-aware')
        if not self.evidence_refs:
            raise ValueError('event evidence references must not be empty')
        if self.frontier_index is not None and (self.frontier_index < 0 or self.scenario_id is None):
            raise ValueError('frontier index requires a scenario')
        if (self.working_ref is None) != (self.working_revision is None):
            raise ValueError('working revision requires a working ref')
        if (self.canonical_ref is None) != (self.canonical_revision is None):
            raise ValueError('canonical revision requires a canonical ref')
        if self.status == StrictTddLifecycleStatus.COMPLETED and self.frontier_index is not None:
            raise ValueError('completed events must not claim an active frontier')

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), 'occurred_at_utc': self.occurred_at_utc.isoformat(), 'event_kind': self.event_kind.value, 'status': self.status.value, 'evidence_refs': list(self.evidence_refs)}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> 'StrictTddLifecycleEvent':
        return cls(str(value['event_id']), int(value['sequence_number']), datetime.fromisoformat(str(value['occurred_at_utc'])), str(value['run_id']), str(value['project_id']), StrictTddLifecycleEventKind(str(value['event_kind'])), StrictTddLifecycleStatus(str(value['status'])), tuple((str(item) for item in value['evidence_refs'])), value.get('scenario_id'), value.get('behavior_ref'), value.get('frontier_index'), value.get('canonical_ref'), value.get('canonical_revision'), value.get('working_ref'), value.get('working_revision'), value.get('message'), value.get('candidate_revision'))

@dataclass(frozen=True)
class LifecycleEventDraft:
    event_id: str
    event_kind: StrictTddLifecycleEventKind
    status: StrictTddLifecycleStatus
    evidence_refs: tuple[str, ...]
    scenario_id: str | None = None
    behavior_ref: str | None = None
    frontier_index: int | None = None
    canonical_ref: str | None = None
    canonical_revision: str | None = None
    working_ref: str | None = None
    working_revision: str | None = None
    message: str | None = None
    candidate_revision: str | None = None

    def materialise(self, context: StrictTddLifecycleRunContext, sequence: int) -> StrictTddLifecycleEvent:
        return StrictTddLifecycleEvent(self.event_id, sequence, datetime.now(UTC), context.run_id, context.project_id, self.event_kind, self.status, self.evidence_refs, self.scenario_id, self.behavior_ref, self.frontier_index, self.canonical_ref, self.canonical_revision, self.working_ref, self.working_revision, self.message, self.candidate_revision)

@dataclass(frozen=True)
class LifecycleEventAppendRequest:
    context: StrictTddLifecycleRunContext
    event: StrictTddLifecycleEvent

    def __post_init__(self) -> None:
        if (self.event.run_id, self.event.project_id) != (self.context.run_id, self.context.project_id):
            raise ValueError('event identity must match run context')

class StrictTddLifecycleEventRepository:

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def append(self, request: LifecycleEventAppendRequest) -> StrictTddLifecycleEvent:
        directory = self._directory(request.context.run_id)
        directory.mkdir(parents=True, exist_ok=True)
        with _locked(directory / '.events.lock'):
            self._context(directory, request.context)
            events = self._read(directory)
            same = _duplicate(events, request.event)
            if same is not None:
                return same
            if request.event.sequence_number != len(events):
                raise ValueError('lifecycle event sequence must be consecutive and monotonic')
            _write(directory / 'events.jsonl', (*events, request.event))
            return request.event

    def events(self, context: StrictTddLifecycleRunContext) -> tuple[StrictTddLifecycleEvent, ...]:
        directory = self._directory(context.run_id)
        if not directory.exists():
            return ()
        with _locked(directory / '.events.lock'):
            self._context(directory, context)
            return self._read(directory)

    def next_sequence(self, context: StrictTddLifecycleRunContext) -> int:
        return len(self.events(context))

    def _directory(self, run_id: str) -> Path:
        if not re.fullmatch('[A-Za-z0-9_-]{1,128}', run_id):
            raise ValueError('run id must be safe')
        return self.root / 'lifecycle-runs' / sha256(run_id.encode()).hexdigest()

    def _context(self, directory: Path, context: StrictTddLifecycleRunContext) -> None:
        path = directory / 'metadata.json'
        if not path.exists():
            write_json_atomically(path, context.to_dict())
        elif StrictTddLifecycleRunContext.from_dict(read_json_file(path)) != context:
            raise ValueError('persisted lifecycle metadata differs from run context')

    def _read(self, directory: Path) -> tuple[StrictTddLifecycleEvent, ...]:
        path = directory / 'events.jsonl'
        if not path.exists():
            return ()
        raw = path.read_bytes()
        if raw and (not raw.endswith(b'\n')):
            raise ValueError('lifecycle event store contains a truncated record')
        try:
            events = tuple((StrictTddLifecycleEvent.from_dict(json.loads(line)) for line in raw.splitlines() if line))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError('malformed lifecycle event record') from error
        if any((item.sequence_number != index for index, item in enumerate(events))) or len({item.event_id for item in events}) != len(events):
            raise ValueError('lifecycle event stream is invalid')
        return events

@contextmanager
def _locked(path: Path) -> Iterator[None]:
    with path.open('a+', encoding='utf-8') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

def _duplicate(events: tuple[StrictTddLifecycleEvent, ...], event: StrictTddLifecycleEvent) -> StrictTddLifecycleEvent | None:
    same = next((item for item in events if item.event_id == event.event_id), None)
    if same is not None:
        if not _equivalent_duplicate(same, event):
            raise ValueError('duplicate lifecycle event id conflicts')
        return same
    if any((item.sequence_number == event.sequence_number for item in events)):
        raise ValueError('duplicate lifecycle event sequence conflicts')
    return None

def _equivalent_duplicate(left: StrictTddLifecycleEvent, right: StrictTddLifecycleEvent) -> bool:
    left_value = left.to_dict()
    right_value = right.to_dict()
    left_value.pop("occurred_at_utc")
    right_value.pop("occurred_at_utc")
    return left_value == right_value


def _write(path: Path, events: tuple[StrictTddLifecycleEvent, ...]) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            for event in events:
                handle.write(json.dumps(event.to_dict(), sort_keys=True) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise

class StrictTddLifecycleEventSink(Protocol):

    def record(self, draft: LifecycleEventDraft) -> StrictTddLifecycleEvent | None:
        ...

class NoOpStrictTddLifecycleEventSink:

    def record(self, draft: LifecycleEventDraft) -> StrictTddLifecycleEvent | None:
        return None

@dataclass(frozen=True)
class PersistingLifecycleEventSinkDependencies:
    repository: StrictTddLifecycleEventRepository
    context: StrictTddLifecycleRunContext

class PersistingStrictTddLifecycleEventSink:

    def __init__(self, dependencies: PersistingLifecycleEventSinkDependencies):
        self.repository = dependencies.repository
        self.context = dependencies.context

    def record(self, draft: LifecycleEventDraft) -> StrictTddLifecycleEvent:
        return self.repository.append(LifecycleEventAppendRequest(self.context, draft.materialise(self.context, self.repository.next_sequence(self.context))))

@dataclass(frozen=True)
class StrictTddProofReportInput:
    context: StrictTddLifecycleRunContext
    feature_state: StrictTddFeatureState | None
    scenario_states: tuple[ScenarioDraftRunState, ...]
    revision_states: tuple[MicrocycleRevisionState, ...]
    events: tuple[StrictTddLifecycleEvent, ...]
    microcycle_states: tuple[MicrocycleState, ...] = ()

@dataclass(frozen=True)
class StrictTddProofReport:
    structured: dict[str, object]
    markdown: str

class StrictTddProofReportBuilder:

    def build(self, input: StrictTddProofReportInput) -> StrictTddProofReport:
        feature = None if input.feature_state is None else input.feature_state.to_dict()
        events = [item.to_dict() for item in input.events]
        status = 'completed' if feature and feature['status'] == 'completed' else 'incomplete'
        if any((item['event_kind'] == 'run_blocked' for item in events)):
            status = 'blocked'
        sections = {'run': {'available': True, **input.context.to_dict(), 'final_status': status}, 'feature_application': _available(feature), 'scenario_draft_state': _available([item.to_dict() for item in input.scenario_states]), 'microcycle_state': _available([item.to_dict() for item in input.microcycle_states]), 'revision_lifecycle': _available([item.to_dict() for item in input.revision_states]), 'lifecycle_events': _available(events), 'final_reconciliation': _available(None if feature is None else feature['final_reconciliation']), 'attempt_counts': {'available': bool(input.scenario_states), 'scenario_drafting_attempts': [len(item.attempts) for item in input.scenario_states]}}
        redacted = _redact({'schema': 'pr23-lifecycle-evidence-v1', 'sections': sections})
        assert isinstance(redacted, dict)
        structured = redacted
        section_value = structured['sections']
        assert isinstance(section_value, dict)
        markdown = '\n'.join(['# PR23 Strict-TDD lifecycle evidence', ''] + [f"## {name.replace('_', ' ').title()}\n\n~~~json\n{json.dumps(value, indent=2, sort_keys=True)}\n~~~" for name, value in section_value.items()])
        return StrictTddProofReport(structured, markdown)

def _available(value: object) -> dict[str, object]:
    return {'available': value not in (None, [], ()), 'value': value if value not in (None, [], ()) else 'unavailable/incomplete'}

def _redact(value: object) -> object:
    if isinstance(value, str):
        return redact_secret_like_text(value)
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redact(item) for key, item in value.items()}
    return value
