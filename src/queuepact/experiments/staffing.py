"""One-worker exhaustive trials, ranked on throughput then ALL accrued waiting."""
from dataclasses import dataclass
import json
import math
from ..models import SERVICES, Service, Action
from .replay import reconstruct
from .coordinator import PairedRun


@dataclass(frozen=True)
class StaffConstraints:
    qualifications: tuple[Service, ...] = SERVICES
    spare_desks: tuple[Service, ...] = SERVICES

    def __post_init__(self):
        object.__setattr__(self, 'qualifications', tuple(Service(s) for s in self.qualifications))
        object.__setattr__(self, 'spare_desks', tuple(Service(s) for s in self.spare_desks))

    @property
    def feasible(self):
        return tuple(s for s in SERVICES if s in self.qualifications and s in self.spare_desks)


def staff_action(engine, service, time, action_id='extra-worker'):
    service = Service(service)
    if action_id == 'extra-worker':
        suffix = 1
        while action_id in engine._action_ids:
            action_id = f'extra-worker-{suffix}'
            suffix += 1
    index = 1
    while f'{service.value}-{index}' in engine._reserved_counter_ids:
        index += 1
    return Action(time, f'{service.value}-{index}', 'add_staff', action_id,
                  json.dumps(dict(service=service, qualified_service=service, spare_desk=True)), True)


class StaffTrial:
    def __init__(self, record, constraints=StaffConstraints(), time=0, horizon=60):
        if not math.isfinite(horizon) or not time < horizon <= record.specification.scenario.safety_limit:
            raise ValueError('Evaluation end time must follow the turning point and respect safety limit')
        self.record = record
        self.constraints = constraints
        self.time = time
        self.placements = (None, *constraints.feasible)
        engines = [reconstruct(record, time) for _ in self.placements]
        for service, engine in zip(self.placements[1:], engines[1:]):
            engine.apply_action(staff_action(engine, service, time))
        self.pair = PairedRun(record.specification, horizon, engines, ['Reference']+[s.value.replace('_',' ').title() for s in constraints.feasible])
        self.pair.clock = time

    def outcomes(self):
        return [dict(placement=s, completed=e.metrics().completed, unfinished=e.metrics().unfinished,
                     total_wait=e.metrics().total_queue_wait, average_wait=e.metrics().average_completed_wait)
                for s, e in zip(self.placements, self.pair.engines)]

    @property
    def selected_index(self):
        if not self.pair.done or self.pair.cancelled or not self.constraints.feasible:
            return None
        return min(range(1, len(self.placements)), key=lambda i: (-self.pair.engines[i].metrics().completed,
                   self.pair.engines[i].metrics().total_queue_wait, SERVICES.index(self.placements[i])))

    def open_selected(self):
        from .spec import RunRecord
        index = self.selected_index
        if index is None:
            raise ValueError('No completed feasible trial to open')
        return RunRecord.capture(self.pair.engines[index])
