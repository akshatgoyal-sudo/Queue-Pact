from dataclasses import dataclass
from math import ceil
from .models import Status, SERVICES


@dataclass(frozen=True)
class Metrics:
    arrived: int
    completed: int
    unfinished: int
    not_arrived: int
    waiting: int
    in_service: int
    preparing: int
    total_queue_wait: float
    average_completed_wait: float | None
    p90_completed_wait: float | None
    longest_current_wait: float | None
    average_completed_visit: float | None
    queue_lengths: tuple[tuple[str, int], ...]
    counter_busy_time: tuple[tuple[str, float], ...]
    counter_utilization: tuple[tuple[str, float | None], ...]


def summarize(engine):
    students = list(engine.students.values())
    completed = [s for s in students if s.status == Status.COMPLETE]
    waits = sorted(s.total_wait for s in completed)
    current = [engine.now-s.wait_age for s in students if s.status == Status.WAITING]
    busy = tuple((c.id, c.busy_time + (engine.now-c.started_at if c.student_id else 0)) for c in engine.counters.values())
    count = lambda status: sum(s.status == status for s in students)
    return Metrics(len(students)-count(Status.NOT_ARRIVED), len(completed), len(students)-len(completed),
        count(Status.NOT_ARRIVED), count(Status.WAITING), count(Status.SERVICE), count(Status.PREPARING),
        sum(s.total_wait+engine.current_wait(s) for s in students),
        sum(waits)/len(waits) if waits else None, waits[ceil(.9*len(waits))-1] if waits else None,
        max(current) if current else None,
        sum(s.finished_at-s.source.arrival for s in completed)/len(completed) if completed else None,
        tuple((s, len(engine.queues[s])) for s in SERVICES), busy,
        tuple((cid, value/engine.now if engine.now else None) for cid, value in busy))
