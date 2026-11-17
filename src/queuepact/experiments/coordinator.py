"""Bounded event work and a common inclusive simulated-time display boundary."""
import math
from ..engine import Engine
from ..models import RunStatus

TERMINAL = (RunStatus.COMPLETED, RunStatus.STALLED, RunStatus.LIMIT)


class PairedRun:
    def __init__(self, specification, horizon=None, engines=None, labels=None):
        if horizon is not None and (not math.isfinite(horizon) or horizon <= 0 or horizon > specification.scenario.safety_limit):
            raise ValueError('Horizon must be positive and within the safety limit')
        self.specification = specification
        self.engines = list(engines) if engines is not None else [Engine(specification.scenario, specification.workload, p, specification.actions) for p in specification.policies]
        self.labels = labels or [e.policy.value for e in self.engines]
        self.horizon = horizon
        self.clock = 0.0
        self.target = None
        self.cancelled = False

    @property
    def done(self):
        return self.cancelled or all(e.status in TERMINAL or (self.horizon is not None and e.now >= self.horizon and e.env.peek() > self.horizon) for e in self.engines)

    @property
    def status(self):
        if self.cancelled:
            return 'Cancelled'
        if not self.done:
            return 'Running'
        if all(e.status == RunStatus.COMPLETED for e in self.engines):
            return 'Completed'
        if any(e.status == RunStatus.LIMIT for e in self.engines):
            return 'Safety limit reached'
        if any(e.status == RunStatus.STALLED for e in self.engines):
            return 'Blocked'
        return 'Horizon reached · unfinished visits included'

    def step(self, delta=1, budget=300, results=False):
        if self.done:
            return True
        if not math.isfinite(delta) or delta <= 0:
            raise ValueError('Playback increment must be positive')
        if self.target is None:
            self.target = min(self.horizon or self.specification.scenario.safety_limit,
                              self.clock+10 if results else self.clock+delta)
        reached = []
        for engine in self.engines:
            if engine.status not in TERMINAL:
                engine.advance(until=self.target, max_events=budget)
            if engine.status == RunStatus.STALLED and self.horizon is not None:
                # No further events can occur, but waiting continues to the specified observation end.
                engine.now = self.target
            reached.append(engine.status in TERMINAL or engine.env.peek() > self.target)
        if all(reached):
            self.clock = min(self.target, max(e.now for e in self.engines))
            if self.done and self.horizon is not None:
                for engine in self.engines:
                    if engine.status == RunStatus.STALLED:
                        engine.now = self.horizon
                        self.clock = self.horizon
            self.target = None
            return True
        return False  # do not render a partially processed boundary

    def cancel(self):
        self.cancelled = True

    def run(self, budget=300):
        while not self.done:
            self.step(budget=budget, results=True)
        return self

    def apply_shared(self, action):
        if self.done or self.target is not None or any(e.status in TERMINAL for e in self.engines):
            raise ValueError('Shared actions require two active runs at a settled boundary')
        if action.time != self.clock or not action.at_boundary:
            raise ValueError('Shared actions must follow the current common boundary')
        updated = self.specification.with_action(action)
        # Validate both before mutating either. Validation is cheap and headless.
        for engine in self.engines:
            Engine(engine.config, engine.workload, engine.policy, (*engine.actions, action))
        for engine in self.engines:
            engine.apply_action(action)
            engine.advance(until=self.clock)
        self.specification = updated
