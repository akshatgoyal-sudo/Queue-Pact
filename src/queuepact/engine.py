"""SimPy event calendar with explicit action/completion/arrival/dispatch ordering."""
import json
import math
from dataclasses import replace
import simpy
from .models import (Scenario, Policy, StudentState, Counter, Action, Status,
                     RunStatus, SERVICES, PREP, Snapshot, StudentView, CounterView, StudentInput, Service)
from .events import SimulationEvent
from .scenarios import generate_workload
from .policies import candidates, eligible, dispatch_key


class Engine:
    def __init__(self, config: Scenario, workload=None, policy=Policy.ORDINARY, actions=()):
        self.config = config
        self.policy = Policy(policy)
        self.workload = tuple(generate_workload(config) if workload is None else workload)
        if len(self.workload) != config.student_count or len({s.id for s in self.workload}) != len(self.workload):
            raise ValueError('Workload must match student count and contain unique IDs')
        self.env = simpy.Environment()
        self.now = 0.0
        self.status = RunStatus.READY
        self.students = {s.id: StudentState(s, documents_ready=s.documents_ready) for s in sorted(self.workload, key=lambda s: s.id)}
        self.counters = {}
        for service, count in zip(SERVICES, config.counter_counts):
            for i in range(count):
                cid = f'{service.name}-{i+1}'
                self.counters[cid] = Counter(cid, service, f'STAFF-{cid}')
        self.queues = {s: [] for s in SERVICES}
        self._v2_started_multipliers = {}
        self._events = []
        self._actions = []
        self._action_ids = set()
        self._reserved_student_ids = set(self.students)
        self._reserved_counter_ids = set(self.counters)
        self._counter_activation = {cid: (0, -1) for cid in self.counters}
        self._pending_surges = 0
        self.multipliers = {s: 1.0 for s in SERVICES}
        self._dispatch_pending = False
        self._queue_sequence = 0
        for action in actions:
            self.apply_action(action)
        for student in self.students.values():
            self._schedule(student.source.arrival, 2, lambda s=student: self._arrive(s))
        self._request_dispatch()

    @property
    def events(self):
        return tuple(self._events)

    @property
    def actions(self):
        return tuple(self._actions)

    def reset(self):
        return Engine(self.config, self.workload, self.policy, self.actions)

    def _log(self, kind, student=None, counter=None, service=None, **details):
        self._events.append(SimulationEvent(len(self._events)+1, self.now, kind,
            student.source.id if student else None, counter.id if counter else None,
            service, json.dumps(details, sort_keys=True, allow_nan=False)))

    def _schedule(self, time, priority, callback):
        event = simpy.Event(self.env)
        event._ok = True
        event._value = None
        event.callbacks.append(lambda _: callback())
        self.env.schedule(event, priority=priority, delay=time-self.env.now)

    def _request_dispatch(self):
        if not self._dispatch_pending:
            self._dispatch_pending = True
            self._schedule(self.now, 3, self._dispatch)

    def apply_action(self, action: Action):
        if self.status in (RunStatus.COMPLETED, RunStatus.LIMIT):
            raise ValueError('Reset a terminal run before applying actions')
        if not math.isfinite(action.time) or action.time < self.now or action.time > self.config.safety_limit:
            raise ValueError('Action time must be finite, at or after the clock, and within the safety limit')
        action = replace(action, id=action.id or f'A{len(self._actions)+1:04}')
        if not isinstance(action.id, str) or not action.id or len(action.id) > 80:
            raise ValueError('Action needs a nonempty stable ID of at most 80 characters')
        if type(action.at_boundary) is not bool:
            raise ValueError('Action boundary flag must be boolean')
        if action.id in self._action_ids:
            raise ValueError(f'Action {action.id} has already been accepted')
        try:
            payload = action.payload
            if not isinstance(payload, dict):
                raise ValueError('Action payload must be a JSON object')
            if action.kind in ('close', 'restore'):
                if action.counter_id not in self._reserved_counter_ids:
                    raise ValueError('Choose an existing desk')
                activation = self._counter_activation[action.counter_id]
                if (action.time, 4 if action.at_boundary else 0) < activation:
                    raise ValueError('Desk action cannot precede the added resource')
            elif action.kind == 'add_staff':
                service = Service(payload['service'])
                if not action.counter_id.startswith(service.value+'-') or action.counter_id in self._reserved_counter_ids:
                    raise ValueError('Added desk needs a unique compatible service ID')
                if payload.get('qualified_service') != service.value or payload.get('spare_desk') is not True:
                    raise ValueError('A qualified worker and spare compatible desk are required')
            elif action.kind == 'slowdown':
                Service(payload['service'])
                multiplier = payload['multiplier']
                if type(multiplier) not in (float, int) or not math.isfinite(multiplier) or not 1 <= multiplier <= 3:
                    raise ValueError('Service multiplier must be between 1 and 3')
            elif action.kind == 'surge':
                inputs = tuple(StudentInput(**s) for s in payload['students'])
                if not 1 <= len(inputs) <= 30 or len({s.id for s in inputs}) != len(inputs):
                    raise ValueError('Surge needs 1–30 unique students')
                if any(s.id in self._reserved_student_ids for s in inputs):
                    raise ValueError('Surge student IDs must be unique across the run')
                if any(not action.time <= s.arrival <= min(action.time+10, self.config.safety_limit) for s in inputs):
                    raise ValueError('Surge arrivals must be within ten minutes of the action and within the safety limit')
            else:
                raise ValueError('Unknown disruption type')
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError('Invalid disruption payload') from exc
        if action.kind == 'surge':
            self._reserved_student_ids.update(s.id for s in inputs)
            self._pending_surges += 1
        if action.kind == 'add_staff':
            self._reserved_counter_ids.add(action.counter_id)
            self._counter_activation[action.counter_id] = (action.time, 4 if action.at_boundary else 0)
        self._action_ids.add(action.id)
        self._actions.append(action)
        self._schedule(action.time, 4 if action.at_boundary else 0, lambda: self._action(action))
        return action

    def _action(self, action):
        if action.kind == 'add_staff':
            service = Service(action.payload['service'])
            counter = Counter(action.counter_id, service, f'STAFF-{action.id}')
            self.counters[counter.id] = counter
            self._log('staff_added', counter=counter, service=service, action_id=action.id, payload=action.payload)
            self._request_dispatch()
            return
        if action.kind == 'slowdown':
            service = Service(action.payload['service'])
            self.multipliers[service] = action.payload['multiplier']
            self._log('service_slowdown', service=service, action_id=action.id,
                      multiplier=self.multipliers[service], payload=action.payload)
            return
        if action.kind == 'surge':
            self._pending_surges -= 1
            inputs = tuple(StudentInput(**s) for s in action.payload['students'])
            self._log('arrival_surge', action_id=action.id, count=len(inputs), payload=action.payload)
            for source in inputs:
                student = StudentState(source, documents_ready=source.documents_ready)
                self.students[source.id] = student
                self._schedule(source.arrival, 2, lambda s=student: self._arrive(s))
            return
        counter = self.counters[action.counter_id]
        changed = counter.open != (action.kind == 'restore')
        counter.open = action.kind == 'restore'
        self._log('counter_closed' if not counter.open else 'counter_restored', counter=counter,
                  service=counter.service, changed=changed, action_id=action.id,
                  finishing_student=counter.student_id)
        self._request_dispatch()

    def _arrive(self, student):
        student.status = Status.WAITING
        self._log('arrival', student)
        self._route(student)
        self._request_dispatch()

    def _estimate(self, student, task):
        if self.policy == Policy.V2:
            from .policies.v2 import estimate
            return estimate(self, student, task)
        if task == PREP:
            return dict(task=task, duration=student.source.preparation_duration, queue_work=0,
                        busy_remaining=0, open_desks=None, estimate=student.source.preparation_duration)
        desks = [c for c in self.counters.values() if c.service == task and c.open]
        queue_work = sum(self.effective_duration(self.students[sid], task) for sid in self.queues[task])
        remaining = sum(max(0, c.finishes_at-self.now) for c in desks if c.student_id)
        duration = self.effective_duration(student, task)
        estimate = (queue_work + remaining) / len(desks) + duration if desks else None
        return dict(task=task, duration=duration, queue_work=queue_work,
                    busy_remaining=remaining, open_desks=len(desks), estimate=estimate)

    def _route(self, student, preserve_age=False):
        if len(student.completed) == 4:
            student.status = Status.COMPLETE
            student.task = None
            student.finished_at = self.now
            self._log('visit_completed', student)
            return
        options = [self._estimate(student, t) for t in self._candidates(student)]
        if self.policy == Policy.V2:
            from .policies.v2 import score
            score(options, getattr(self, 'v2_factor', 1.0))
        selected = min(options, key=lambda o: (float('inf') if o.get('score', o['estimate']) is None else o.get('score', o['estimate']),
                                               (*SERVICES, PREP).index(o['task'])))
        task = selected['task']
        comparisons = '; '.join(f"{o['task']}: " + ('unavailable' if o['estimate'] is None else f"{o['estimate']:.2f} min") for o in options)
        self._log('routing_decision', student, service=task, candidates=options,
                  selected=task, rule='fixed_order' if self.policy == Policy.ORDINARY else 'prerequisite_head_start_estimated' if self.policy == Policy.V2 else 'minimum_estimated_completion',
                  reason='capacity_reconsideration' if preserve_age else 'next_activity',
                  explanation=f'{task} selected. Estimated completion: {comparisons}.' + (' Scores (completion + prerequisite penalty): ' + '; '.join(f"{o['task']}: {o['score']}" for o in options) + '. Configured means; no future information.' if self.policy == Policy.V2 else ''))
        student.task = task
        if task == PREP:
            student.status = Status.PREPARING
            student.carried_wait_age = self.now-student.wait_age if preserve_age and student.wait_age is not None else 0
            student.wait_age = None
            self._log('preparation_started', student, duration=student.source.preparation_duration)
            self._schedule(self.now+student.source.preparation_duration, 1, lambda: self._prepared(student))
        else:
            assert task in self._eligible(student)
            student.status = Status.WAITING
            student.queued_at = self.now
            if not preserve_age or student.wait_age is None:
                student.wait_age = self.now-student.carried_wait_age
                student.carried_wait_age = 0
            self._queue_sequence += 1
            student.queue_order = self._queue_sequence
            self.queues[task].append(student.source.id)
            self._log('queue_entered', student, service=task, wait_age_since=student.wait_age)

    def _prepared(self, student):
        student.documents_ready = True
        student.preparation_time += student.source.preparation_duration
        self._log('preparation_completed', student)
        self._route(student)
        self._request_dispatch()

    def _leave_queue(self, student, reason):
        self.queues[student.task].remove(student.source.id)
        wait = self.now-student.queued_at
        student.total_wait += wait
        student.queued_at = None
        self._log('queue_exited', student, service=student.task, wait=wait, reason=reason)

    def _dispatch(self):
        self._dispatch_pending = False
        # Reconsider only when every compatible desk is closed; never chase small score changes.
        if self.policy in (Policy.SMART, Policy.V2):
            for student in self.students.values():
                if student.status == Status.WAITING and student.task in SERVICES:
                    if not any(c.open and c.service == student.task for c in self.counters.values()):
                        alternatives = [self._estimate(student, t) for t in self._candidates(student)]
                        if any(o['estimate'] is not None for o in alternatives):
                            self._leave_queue(student, 'capacity_unavailable')
                            self._route(student, preserve_age=True)
        for counter in self.counters.values():
            if not counter.open or counter.student_id or not self.queues[counter.service]:
                continue
            waiting = [self.students[sid] for sid in self.queues[counter.service]]
            student = min(waiting, key=lambda s: dispatch_key(s, self.now, self.config.fair_wait, self.policy))
            assert counter.service in self._eligible(student)
            age = self.now-student.wait_age
            if self.policy in (Policy.SMART, Policy.V2) and age >= self.config.fair_wait:
                self._log('fair_wait_protection', student, counter, counter.service,
                          age=age, threshold=self.config.fair_wait,
                          queue_order=[s.source.id for s in sorted(waiting, key=lambda s: s.queue_order)])
            self._leave_queue(student, 'service_started')
            student.wait_age = None
            student.status = Status.SERVICE
            counter.student_id = student.source.id
            counter.started_at = self.now
            self._v2_started_multipliers[counter.id] = self.multipliers[counter.service]
            duration = self.effective_duration(student, counter.service)
            counter.finishes_at = self.now+duration
            self._log(self._start_event(student, counter.service), student, counter, counter.service, duration=duration,
                      base_duration=student.source.duration(counter.service), multiplier=self.multipliers[counter.service])
            self._schedule(counter.finishes_at, 1, lambda c=counter, s=student: self._finish(c, s))

    def _finish(self, counter, student):
        assert counter.service not in student.completed
        student.completed.add(counter.service)
        counter.busy_time += self.now-counter.started_at
        counter.student_id = None
        counter.started_at = counter.finishes_at = None
        self._log('service_completed', student, counter, counter.service)
        self._route(student)
        self._request_dispatch()

    def advance(self, until=None, max_events=None):
        if until is not None and (not math.isfinite(until) or until < self.now):
            raise ValueError('Target time must be finite and at or after the current clock')
        if max_events is not None and (type(max_events) is not int or max_events <= 0):
            raise ValueError('Event budget must be a positive integer')
        if self.status in (RunStatus.COMPLETED, RunStatus.LIMIT):
            return self.snapshot()
        if self.status == RunStatus.STALLED and self.env.peek() == float('inf'):
            return self.snapshot()
        self.status = RunStatus.RUNNING
        target = min(self.config.safety_limit, until if until is not None else self.config.safety_limit)
        count = 0
        while self.env.peek() <= target and (max_events is None or count < max_events):
            self.now = self.env.peek()
            self.env.step()
            count += 1
            if not self._pending_surges and all(s.status == Status.COMPLETE for s in self.students.values()):
                self.status = RunStatus.COMPLETED
                self._log('run_completed')
                return self.snapshot()
        if self.env.peek() == float('inf'):
            self.status = RunStatus.STALLED
            self._log('run_stalled', reason='No scheduled progress; required capacity is unavailable')
        elif self.env.peek() > target and (max_events is None or count < max_events):
            self.now = target
            if target == self.config.safety_limit:
                self.status = RunStatus.LIMIT
                self._log('run_limit_reached', limit=target)
        return self.snapshot()

    def run(self):
        self.advance()
        return self.metrics()

    def current_wait(self, student):
        return 0 if student.queued_at is None else self.now-student.queued_at

    def effective_duration(self, student, service):
        return student.source.duration(service) * self.multipliers[service]

    def _candidates(self, student):
        return candidates(student, self.policy)

    def _eligible(self, student):
        return eligible(student)

    def _start_event(self, student, service):
        return 'service_started'

    def snapshot(self):
        return Snapshot(self.now, self.status, self.policy,
            tuple(StudentView(s.source.id, s.status, tuple(t for t in SERVICES if t in s.completed),
                              s.task, s.total_wait+self.current_wait(s)) for s in self.students.values()),
            tuple(CounterView(c.id, c.service, c.open, c.student_id, len(self.queues[c.service]),
                              c.started_at, c.finishes_at) for c in self.counters.values()))

    def metrics(self):
        from .metrics import summarize
        return summarize(self)
