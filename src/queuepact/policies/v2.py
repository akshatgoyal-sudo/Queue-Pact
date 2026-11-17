"""Estimate-based prerequisite head-start; no access to future input records."""
from ..models import SERVICES,PREP

PHOTO_PENALTY = 1.0  # frozen candidate coefficient; chosen on development cases only

def estimate(engine,student,task):
    if task==PREP:
        duration=sum(engine.config.preparation_range)/2
        return dict(task=task,duration=duration,queue_work=0,busy_remaining=0,open_desks=None,estimate=duration,information='configured_mean')
    duration=sum(engine.config.duration_ranges[SERVICES.index(task)])/2*engine.multipliers[task]
    desks=[c for c in engine.counters.values() if c.open and c.service==task]
    # Started services retain their original multiplier. Estimate residual from
    # configured mean and elapsed time, not the scheduled actual finish time.
    remaining=[max(0,sum(engine.config.duration_ranges[SERVICES.index(task)])/2*engine._v2_started_multipliers.get(c.id,1)-(engine.now-c.started_at)) if c.student_id else 0 for c in desks]
    slots=list(remaining)
    for _ in engine.queues[task]:
        if slots:
            i=min(range(len(slots)),key=lambda i:(slots[i],i));slots[i]+=duration
    finish=min(slots)+duration if slots else None
    return dict(task=task,duration=duration,queue_work=len(engine.queues[task])*duration,busy_remaining=sum(remaining),open_desks=len(desks),estimate=finish,information='configured_mean',desk_loads=slots)

def score(options,factor=PHOTO_PENALTY):
    """Photo may fill a substantial estimated wait; critical tasks win near ties."""
    critical=next((o for o in options if o['task']==PREP),None)
    if critical is None:
        critical=next((o for t in (SERVICES[0],SERVICES[2]) for o in options if o['task']==t),None)
    for o in options:
        penalty=0
        if critical is not None and o['task']==SERVICES[1]:
            penalty=(critical['estimate'] or 0) if critical['task']==PREP else factor*critical['duration']
        o['prerequisite_penalty']=penalty
        o['score']=None if o['estimate'] is None else o['estimate']+penalty
        o['penalty_factor']=factor
    return options
