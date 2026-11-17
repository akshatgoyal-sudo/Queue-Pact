"""Explicit operational alternatives; the default Engine is unchanged."""
from dataclasses import dataclass
import math
from ..engine import Engine
from ..models import Status, SERVICES, PREP

SCREENING = 'READINESS_SCREENING'
VERIFICATION = SERVICES[0]


def readiness_pair(spec, policy, capacity, screening, discovery, horizon=None):
    from dataclasses import replace
    from .coordinator import PairedRun
    spec=replace(spec,policies=(policy,policy),assumptions=(*spec.assumptions,
        f'Early: {capacity} additional screening workers, {screening} min per student',
        f'Late: {discovery} min failed verification check; complete-document check included in normal verification'))
    engines = [ReadinessEngine(spec.scenario, spec.workload, policy, spec.actions,
               ReadinessConfig(mode, capacity, screening, discovery)) for mode in ('early', 'late')]
    return PairedRun(spec, horizon, engines, ['Early screening', 'Late discovery'])


@dataclass(frozen=True)
class ReadinessConfig:
    mode: str = 'early'
    screening_capacity: int = 1
    screening_duration: float = .5
    discovery_duration: float = .75

    def __post_init__(self):
        if self.mode not in ('early', 'late'):
            raise ValueError('Readiness mode must be early or late')
        if type(self.screening_capacity) is not int or not 1 <= self.screening_capacity <= 10:
            raise ValueError('Screening requires 1–10 dedicated workers')
        if any(not math.isfinite(v) or v <= 0 for v in (self.screening_duration, self.discovery_duration)):
            raise ValueError('Screening and failed-check durations must be nonzero finite minutes')


class ReadinessEngine(Engine):
    def __init__(self, config, workload, policy, actions=(), readiness=ReadinessConfig()):
        self.readiness = readiness
        self.checked = set()
        self.screening_active = {}
        self.screening_busy = 0.0
        self.failed_check_busy = 0.0
        super().__init__(config, workload, policy, actions)
        self.queues[SCREENING] = []

    def reset(self):
        return ReadinessEngine(self.config, self.workload, self.policy, self.actions, self.readiness)

    def _arrive(self, student):
        if self.readiness.mode == 'late':
            return super()._arrive(student)
        self._log('arrival', student)
        student.status = Status.WAITING
        student.task = SCREENING
        student.queued_at = student.wait_age = self.now
        self.queues[SCREENING].append(student.source.id)
        self._log('queue_entered', student, service=SCREENING, wait_age_since=self.now)
        self._screen()

    def _screen(self):
        while self.queues[SCREENING] and len(self.screening_active) < self.readiness.screening_capacity:
            student = self.students[self.queues[SCREENING][0]]
            self._leave_queue(student, 'screening_started')
            student.wait_age = None
            student.status = Status.SERVICE
            self.screening_active[student.source.id] = self.now
            self._log('screening_started', student, service=SCREENING, duration=self.readiness.screening_duration)
            self._schedule(self.now+self.readiness.screening_duration, 1, lambda s=student: self._screened(s))

    def _screened(self, student):
        self.screening_busy += self.now-self.screening_active.pop(student.source.id)
        self.checked.add(student.source.id)
        self._log('screening_completed', student, missing=not student.documents_ready)
        self._route(student)
        self._request_dispatch()
        self._screen()

    def _needs_check(self, student):
        return self.readiness.mode == 'late' and not student.documents_ready and student.source.id not in self.checked

    def _candidates(self, student):
        if self._needs_check(student):
            return [VERIFICATION]
        if not student.documents_ready:
            return [PREP]  # both operational variants prepare immediately after identification
        return super()._candidates(student)

    def _eligible(self, student):
        # Eligibility here is for an ATTEMPT, not completed verification.
        return [VERIFICATION] if self._needs_check(student) else super()._eligible(student)

    def effective_duration(self, student, service):
        if service == VERIFICATION and self._needs_check(student):
            return self.readiness.discovery_duration*self.multipliers[service]
        return super().effective_duration(student, service)

    def _start_event(self, student, service):
        return 'verification_check_started' if self._needs_check(student) else 'service_started'

    def _finish(self, counter, student):
        if counter.service == VERIFICATION and self._needs_check(student):
            duration = self.now-counter.started_at
            counter.busy_time += duration
            self.failed_check_busy += duration
            counter.student_id = None
            counter.started_at = counter.finishes_at = None
            self.checked.add(student.source.id)
            self._log('verification_check_failed', student, counter, counter.service, duration=duration)
            self._route(student)
            self._request_dispatch()
        else:
            super()._finish(counter, student)

    def overhead(self):
        failed_active = sum(self.now-c.started_at for c in self.counters.values()
                            if c.student_id and self._needs_check(self.students[c.student_id]))
        preparing = sum(self.now-e.time for e in self.events if e.type == 'preparation_started'
                        and self.students[e.student_id].status == Status.PREPARING)
        return dict(screening_workers=self.readiness.screening_capacity if self.readiness.mode == 'early' else 0,
                    screening_time=self.screening_busy+sum(self.now-t for t in self.screening_active.values()),
                    failed_check_time=self.failed_check_busy+failed_active,
                    preparation_time=sum(s.preparation_time for s in self.students.values())+preparing,
                    screening_waiting=len(self.queues[SCREENING]))
