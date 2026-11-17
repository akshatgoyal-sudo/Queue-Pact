"""Read-only Python presentation models; safe to use without NiceGUI."""
from dataclasses import dataclass
from .models import SERVICES, PREP, Status, Policy
from .policies import eligible

LABELS = dict(zip(SERVICES, ('Document verification', 'Photo capture', 'Fee payment', 'Final enrollment')))
LABELS[PREP] = 'Document preparation'
SHORT = dict(zip(SERVICES, ('V', 'P', 'F', 'E')))
COLORS = {Status.WAITING: '#2563eb', Status.SERVICE: '#7c3aed', Status.PREPARING: '#d97706'}


def desk_label(cid):
    service, number = cid.rsplit('-', 1)
    return SHORT[service] + number


def token_label(sid):
    label = sid.replace('G-A', 'G')
    return label if len(label) <= 8 else '…' + label[-7:]


@dataclass(frozen=True)
class Congestion:
    service: str | None
    title: str
    explanation: str
    waiting: int = 0
    longest_wait: float = 0
    open_desks: int = 0
    active_desks: int = 0
    workload: float = 0
    unavailable: bool = False


def congestion(engine):
    rows = []
    for service in SERVICES:
        queue = engine.queues[service]
        if not queue:
            continue
        desks = [c for c in engine.counters.values() if c.service == service]
        open_count = sum(c.open for c in desks)
        active = sum(c.student_id is not None for c in desks)
        work = sum(engine.effective_duration(engine.students[sid], service) for sid in queue)
        wait = max(engine.now-engine.students[sid].wait_age for sid in queue)
        explanation = (f'{LABELS[service]} is unavailable: no open desks accept new students. '
                       if not open_count else f'{LABELS[service]} has the highest queued work per open desk. ')
        explanation += f'{len(queue)} waiting · {active} serving / {open_count} open · {work:.1f} min queued work · longest wait {wait:.1f} min.'
        rows.append((not bool(open_count), work/open_count if open_count else work, -SERVICES.index(service),
            Congestion(service, 'Current congestion hotspot', explanation, len(queue), wait, open_count, active, work, not open_count)))
    return max(rows, key=lambda r: r[:3])[-1] if rows else Congestion(None, 'No current congestion', 'No students are waiting for counter service. Document preparation is a separate activity.')


def hall_state(engine, selected=None, *, playing=False, speed=1, generation=0, reduced_motion=False):
    snap = engine.snapshot()
    hotspot = congestion(engine)
    max_desks = max((sum(c.service == s for c in snap.counters) for s in SERVICES), default=0)
    zone_height = max(210, ((max_desks+2)//3)*72+138)
    zones, desks, markers = [], [], []
    positions = {}
    for i, service in enumerate(SERVICES):
        x, y = 200+(i % 2)*395, 25+(i//2)*(zone_height+18)
        queue = engine.queues[service]
        zones.append(dict(id=service, label=LABELS[service], x=x, y=y, width=380, height=zone_height,
                          waiting=len(queue), extra=max(0, len(queue)-7), hotspot=hotspot.service == service,
                          multiplier=engine.multipliers[service]))
        service_desks = [c for c in snap.counters if c.service == service]
        for j, c in enumerate(service_desks):
            dx, dy = x+14+(j % 3)*118, y+65+(j//3)*72
            status = ('Serving' if c.student else 'Available') if c.open else ('Closing' if c.student else 'Closed')
            progress = (snap.time-c.started_at)/(c.finishes_at-c.started_at) if c.student else 0
            desks.append(dict(id=c.id, label=desk_label(c.id), service=LABELS[service], x=dx, y=dy,
                status=status, student=c.student, progress=max(0, min(1, progress)),
                text=f'{desk_label(c.id)} · {status}' + (f' · {c.student}' if c.student else '')))
            if c.student:
                positions[c.student] = (dx+78, dy+37)
        visible = queue[:7]
        if selected in queue and selected not in visible:
            visible = visible[:6]+[selected]
        for j, sid in enumerate(visible):
            positions[sid] = (x+28+j*48, y+zone_height-33)
    preparing = [s for s in snap.students if s.state == Status.PREPARING]
    visible_prep = preparing[:4]
    if selected in [s.id for s in preparing] and selected not in [s.id for s in visible_prep]:
        visible_prep = visible_prep[:3]+[next(s for s in preparing if s.id == selected)]
    for j, s in enumerate(visible_prep):
        positions[s.id] = (52+(j % 2)*66, 220+(j//2)*50)
    for student in snap.students:
        if student.id in positions:
            x, y = positions[student.id]
            markers.append(dict(id=student.id, label=token_label(student.id), x=x, y=y,
                color=COLORS[student.state], selected=selected == student.id,
                description=f'{student.id}: {student.state.value}. Select student passport.'))
    return dict(zones=zones, desks=desks, markers=markers, width=1000, height=zone_height*2+72,
        not_arrived=sum(s.state == Status.NOT_ARRIVED for s in snap.students), preparing=len(preparing),
        extra_preparing=max(0, len(preparing)-4), completed=sum(s.state == Status.COMPLETE for s in snap.students),
        playing=playing, speed=speed, generation=generation, reduced_motion=reduced_motion)


def describe_event(event):
    d, who = event.details, event.student_id or 'Student'
    if event.type == 'routing_decision':
        values = '; '.join(f"{LABELS.get(o['task'], o['task'])}: " + ('unavailable' if o['estimate'] is None else f"{o['estimate']:.2f} min") for o in d['candidates'])
        if d['rule']=='prerequisite_head_start_estimated':
            scores='; '.join(f"{LABELS.get(o['task'],o['task'])}: " + ('unavailable' if o['score'] is None else f"{o['estimate']:.2f} + {o['prerequisite_penalty']:.2f} = {o['score']:.2f}") for o in d['candidates'])
            return f"{who} → {LABELS[d['selected']]}. V2 prerequisite head-start. Estimated completion + prerequisite penalty: {scores}. Uses configured means."
        rule = 'Fixed order' if d['rule'] == 'fixed_order' else 'Lowest next-activity estimate'
        return f"{who} → {LABELS[d['selected']]}. {rule}. {values}."
    if event.type == 'counter_closed':
        return f"Desk {desk_label(event.counter_id)} " + (f"is closing after {d['finishing_student']}." if d.get('finishing_student') else 'is closed.')
    if event.type == 'counter_restored':
        return f'Desk {desk_label(event.counter_id)} is open for new starts.'
    if event.type == 'service_slowdown':
        return f"{LABELS[event.service]} set to {d['multiplier']:g}× duration for future starts. Active service keeps its duration."
    if event.type == 'arrival_surge':
        return f"Arrival surge accepted: {d['count']} students, action {d['action_id']}."
    if event.type == 'fair_wait_protection':
        return f"Fair-wait protection applied to {who} after {d['age']:.2f} min waiting."
    if event.type in ('service_started', 'service_completed'):
        return f"{who} · {LABELS[event.service]} {'started at' if event.type == 'service_started' else 'completed at'} desk {desk_label(event.counter_id)}."
    return f"{who if event.student_id else 'Run'} · {event.type.replace('_', ' ')}."


DISRUPTIONS = {'counter_closed', 'counter_restored', 'service_slowdown', 'arrival_surge'}


def event_feed(engine, mode='All events', selected=None, limit=18):
    result = []
    for event in reversed(engine.events):
        if mode == 'Routing decisions' and event.type != 'routing_decision':
            continue
        if mode == 'Disruptions' and event.type not in DISRUPTIONS:
            continue
        if mode == 'Selected student' and (not selected or event.student_id != selected):
            continue
        result.append(dict(sequence=event.sequence, time=event.time, type=event.type, text=describe_event(event)))
        if len(result) == limit:
            break
    return tuple(result)


def passport(engine, sid):
    if sid not in engine.students:
        return None
    s = engine.students[sid]
    events = [e for e in engine.events if e.student_id == sid]
    completed = {e.service: e.time for e in events if e.type == 'service_completed'}
    preparation = s.preparation_time
    if s.status == Status.PREPARING:
        start = next(e.time for e in reversed(events) if e.type == 'preparation_started')
        preparation += engine.now-start
    desk = next((c for c in engine.counters.values() if c.student_id == sid), None)
    service_time = sum(e.details['duration'] for e in events if e.type == 'service_started' and e.service in completed)
    if desk:
        service_time += engine.now-desk.started_at
    allowed = eligible(s)
    tasks = []
    for task in SERVICES:
        if task in completed:
            state, reason = 'Completed', f'At {completed[task]:.2f} min'
        elif s.task == task:
            state, reason = 'In service' if desk else 'Assigned queue', 'Recorded current assignment'
        elif s.status == Status.NOT_ARRIVED:
            state, reason = 'Not started', 'Visit has not begun'
        elif task in allowed:
            state, reason = 'Eligible next', 'Prerequisites ready; no assignment yet'
        else:
            needs = []
            if task == SERVICES[0] and not s.documents_ready:
                needs.append('ready documents')
            required = (SERVICES[0],) if task == SERVICES[2] else SERVICES[:3] if task == SERVICES[3] else ()
            needs.extend(LABELS[t].lower() for t in required if t not in completed)
            state, reason = 'Not eligible', 'Requires ' + ', '.join(needs)
        if s.status == Status.PREPARING and state == 'Eligible next':
            reason = 'Prerequisites ready; finish preparation first'
        tasks.append(dict(service=task, label=LABELS[task], state=state, reason=reason, completed_at=completed.get(task)))
    decision = next((describe_event(e) for e in reversed(events) if e.type == 'routing_decision'), None)
    protected = engine.policy in (Policy.SMART, Policy.V2) and s.status == Status.WAITING and engine.now-s.wait_age >= engine.config.fair_wait
    elapsed = None if s.status == Status.NOT_ARRIVED else (s.finished_at if s.finished_at is not None else engine.now)-s.source.arrival
    return dict(id=sid, arrival=s.source.arrival, state=s.status.value, tasks=tasks, task=LABELS.get(s.task),
        desk=desk_label(desk.id) if desk else None, waiting=s.total_wait+engine.current_wait(s),
        preparation=preparation, service_time=service_time, elapsed=elapsed, complete=s.status == Status.COMPLETE,
        latest_decision=decision, protected=protected,
        waiting_count=len(engine.queues[s.task]) if s.task in SERVICES else None)
