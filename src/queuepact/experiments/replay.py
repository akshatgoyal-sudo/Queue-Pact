"""Reconstruction uses original inputs and ordered actions, never SimPy snapshots."""
import math
from dataclasses import replace
from .coordinator import PairedRun
from ..models import RunStatus


def normalized_events(engine):
    """Exclude polling-dependent stall diagnostics, then renumber substantive events."""
    events = [e.to_dict() for e in engine.events if e.type != 'run_stalled']
    for i, event in enumerate(events, 1):
        event['sequence'] = i
    return events


def reconstruct(record, time):
    if not math.isfinite(time) or not 0 <= time <= record.specification.scenario.safety_limit:
        raise ValueError('Turning point must be within the simulation window')
    engine = record.engine()
    engine.advance(until=time)
    return engine


def branches(record, time, intervention=None):
    # All original events, including boundary actions and resulting dispatches,
    # at time have executed before the additive action is accepted.
    original = reconstruct(record, time)
    changed = reconstruct(record, time)
    if intervention is not None:
        if changed.status in (RunStatus.COMPLETED, RunStatus.LIMIT) or changed.now != time:
            raise ValueError('Choose a turning point before the run completes')
        if intervention.time != time:
            raise ValueError('Intervention must occur at the selected turning point')
        changed.apply_action(replace(intervention, at_boundary=True))
        changed.advance(until=time)
    pair = PairedRun(record.specification, engines=[original, changed], labels=['Unchanged continuation', 'Intervention branch'])
    pair.clock = time
    return pair
