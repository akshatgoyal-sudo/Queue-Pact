from dataclasses import dataclass, field
from enum import StrEnum
import math


class Service(StrEnum):
    DOCUMENT_VERIFICATION = 'DOCUMENT_VERIFICATION'
    PHOTO_CAPTURE = 'PHOTO_CAPTURE'
    FEE_PAYMENT = 'FEE_PAYMENT'
    FINAL_ENROLLMENT = 'FINAL_ENROLLMENT'


SERVICES = tuple(Service)
PREP = 'DOCUMENT_PREPARATION'


class Policy(StrEnum):
    ORDINARY = 'Ordinary'
    SMART = 'QueuePact'  # stable legacy identifier: always v1
    V2 = 'QueuePact v2'

    @property
    def label(self):
        return {Policy.ORDINARY: 'Ordinary', Policy.SMART: 'QueuePact v1', Policy.V2: 'QueuePact v2 (experimental)'}[self]

    @property
    def algorithm_version(self):
        return 2 if self == Policy.V2 else 1


class Status(StrEnum):
    NOT_ARRIVED = 'Not arrived'
    WAITING = 'Waiting'
    SERVICE = 'In service'
    PREPARING = 'Preparing documents'
    COMPLETE = 'Completed'


class RunStatus(StrEnum):
    READY = 'Ready'
    RUNNING = 'Running'
    COMPLETED = 'Completed'
    STALLED = 'Stalled'
    LIMIT = 'Safety limit reached'


@dataclass(frozen=True)
class Scenario:
    seed: int = 42
    student_count: int = 40
    arrival_pattern: str = 'poisson'
    arrival_rate: float = 1.2
    counter_counts: tuple[int, ...] = (2, 1, 2, 1)
    duration_ranges: tuple[tuple[float, float], ...] = ((2, 5), (1, 3), (2, 4), (1, 2))
    missing_fraction: float = 0.25
    preparation_range: tuple[float, float] = (3, 8)
    fair_wait: float = 10
    safety_limit: float = 10000

    def __post_init__(self):
        if type(self.seed) is not int or type(self.student_count) is not int or self.student_count < 0:
            raise ValueError('Seed must be an integer; student count must be a nonnegative integer')
        if self.arrival_pattern not in ('poisson', 'regular', 'batch'):
            raise ValueError('Arrival pattern must be poisson, regular or batch')
        if not math.isfinite(self.arrival_rate) or self.arrival_rate <= 0:
            raise ValueError('Arrival rate must be finite and positive')
        if len(self.counter_counts) != 4 or any(type(n) is not int or n < 0 for n in self.counter_counts):
            raise ValueError('Provide four nonnegative integer counter counts')
        if not 0 <= self.missing_fraction <= 1:
            raise ValueError('Missing-document fraction must be between 0 and 1')
        if len(self.duration_ranges) != 4:
            raise ValueError('Provide one duration range per service')
        for bounds in (*self.duration_ranges, self.preparation_range):
            if len(bounds) != 2 or not all(math.isfinite(x) for x in bounds) or not 0 < bounds[0] <= bounds[1]:
                raise ValueError('Duration ranges must have finite positive minimum <= maximum')
        if not math.isfinite(self.fair_wait) or self.fair_wait < 0 or not math.isfinite(self.safety_limit) or self.safety_limit <= 0:
            raise ValueError('Fair wait must be nonnegative and safety limit positive, both finite')
        object.__setattr__(self, 'counter_counts', tuple(self.counter_counts))
        object.__setattr__(self, 'duration_ranges', tuple(tuple(x) for x in self.duration_ranges))
        object.__setattr__(self, 'preparation_range', tuple(self.preparation_range))


@dataclass(frozen=True)
class StudentInput:
    id: str
    arrival: float
    durations: tuple[float, ...]
    documents_ready: bool
    preparation_duration: float

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id or len(self.id) > 80 or not math.isfinite(self.arrival) or self.arrival < 0:
            raise ValueError('Student needs a stable ID and finite nonnegative arrival')
        if len(self.durations) != 4 or any(not math.isfinite(x) or x <= 0 for x in self.durations):
            raise ValueError('Student requires four finite positive service durations')
        if type(self.documents_ready) is not bool or not math.isfinite(self.preparation_duration) or self.preparation_duration <= 0:
            raise ValueError('Document readiness must be boolean and preparation duration finite positive')
        object.__setattr__(self, 'durations', tuple(self.durations))

    def duration(self, service):
        return self.durations[SERVICES.index(service)]


@dataclass
class StudentState:
    source: StudentInput
    status: Status = Status.NOT_ARRIVED
    documents_ready: bool = False
    completed: set[Service] = field(default_factory=set)
    task: str | None = None
    queued_at: float | None = None
    wait_age: float | None = None
    queue_order: int = 0
    total_wait: float = 0
    carried_wait_age: float = 0
    preparation_time: float = 0
    finished_at: float | None = None


@dataclass
class Counter:
    id: str
    service: Service
    staff_id: str  # Dedicated staff qualified for this counter's single service.
    open: bool = True
    student_id: str | None = None
    started_at: float | None = None
    finishes_at: float | None = None
    busy_time: float = 0


@dataclass(frozen=True)
class Action:
    time: float
    counter_id: str = ''
    kind: str = 'close'
    id: str = ''
    payload_json: str = '{}'
    at_boundary: bool = False

    @property
    def payload(self):
        import json
        return json.loads(self.payload_json)


@dataclass(frozen=True)
class StudentView:
    id: str
    state: Status
    completed: tuple[Service, ...]
    task: str | None
    waiting: float


@dataclass(frozen=True)
class CounterView:
    id: str
    service: Service
    open: bool
    student: str | None
    queue_length: int
    started_at: float | None = None
    finishes_at: float | None = None


@dataclass(frozen=True)
class Snapshot:
    time: float
    status: RunStatus
    policy: Policy
    students: tuple[StudentView, ...]
    counters: tuple[CounterView, ...]
