"""Observed metrics and deterministic event-derived series, independent of refresh."""
from ..models import Status, RunStatus, SERVICES


def result(engine):
    from dataclasses import asdict
    m = asdict(engine.metrics())
    waits = [s.total_wait for s in engine.students.values() if s.status == Status.COMPLETE]
    pending = len(engine._reserved_student_ids-set(engine.students))
    m['unfinished'] += pending
    m['not_arrived'] += pending
    m.update(max_completed_wait=max(waits) if waits else None,
             makespan=engine.now if engine.status == RunStatus.COMPLETED else None,
             window=engine.now, status=engine.status.value,
             unfinished_wait=sum(s.total_wait+engine.current_wait(s) for s in engine.students.values() if s.status != Status.COMPLETE))
    return m


def difference(value, reference):
    if value is None or reference is None:
        return dict(absolute=None, percent=None)
    return dict(absolute=value-reference, percent=(value-reference)/reference*100 if reference else None)


def series(engine):
    times = {0.0, engine.now}
    times.update(e.time for e in engine.events)
    queues = {s: 0 for s in SERVICES}
    completed = 0
    rows = []
    events = iter(engine.events)
    event = next(events, None)
    for time in sorted(times):
        while event is not None and event.time <= time:
            if event.type == 'visit_completed':
                completed += 1
            if event.service in queues:
                if event.type == 'queue_entered':
                    queues[event.service] += 1
                elif event.type == 'queue_exited':
                    queues[event.service] -= 1
            event = next(events, None)
        rows.append(dict(time=time, completed=completed, **{s.value: queues[s] for s in SERVICES}))
    return rows


def findings(engines, labels):
    if len(engines) < 2:
        return ['Observed: reference only. No qualified placement with a spare compatible desk is available.']
    a, b = [result(e) for e in engines[:2]]
    label = labels[1]
    output = []
    for key, title, unit in [('average_completed_wait', 'completed-visit average wait', 'min'),
                             ('completed', 'completed visits', 'visits'),
                             ('total_queue_wait', 'accumulated queue wait across all arrived students', 'min')]:
        d = difference(b[key], a[key])['absolute']
        if d is not None:
            output.append(f'Observed: {label} {title}: {abs(d):.2f} {unit} '+('higher' if d > 0 else 'lower' if d < 0 else 'difference')+'.')
    for engine, name in zip(engines, labels):
        first={}
        for event in engine.events:
            if event.type=='service_completed':
                first.setdefault(event.student_id,event.service)
        early=sum(service==SERVICES[1] for service in first.values())
        output.append(f'Observed: {name}: {early} students completed photo before verification.')
    if engines[0].policy != engines[1].policy:
        output.append('Possible explanation: choosing a short next activity can shift demand into later queues. These observations do not establish causation or an overall winner.')
    else:
        output.append('Interpretation: the scheduling policy is held fixed. Resource or operational changes may affect different measures differently; inspect unfinished visits alongside completed-only averages.')
    return output


def charts(engines, labels):
    import plotly.graph_objects as go
    figures = [go.Figure() for _ in range(4)]
    colors = ['#2563eb', '#7c3aed']
    for i, (engine, label) in enumerate(zip(engines, labels)):
        rows = series(engine)
        figures[0].add_scatter(x=[r['time'] for r in rows], y=[r['completed'] for r in rows], name=label, line=dict(color=colors[i % 2], shape='hv'))
        for service in SERVICES:
            figures[1].add_scatter(x=[r['time'] for r in rows], y=[r[service] for r in rows], name=f'{label} · {service.value.replace("_", " ").title()}', line_shape='hv')
        figures[2].add_box(y=[s.total_wait for s in engine.students.values() if s.status == Status.COMPLETE], name=label, boxpoints='all', jitter=0, marker_color=colors[i % 2])
        utilization = engine.metrics().counter_utilization
        short = dict(zip(SERVICES, ('V','P','F','E')))
        figures[3].add_bar(x=[short[engine.counters[c].service]+c.rsplit('-',1)[-1] for c, _ in utilization], y=[None if v is None else 100*v for _, v in utilization], name=f'{label} · 0–{engine.now:.2f} min')
    for fig, title, ylabel in zip(figures, ['Completed visits over time', 'Service queues over time', 'Completed-visit total queue wait', 'Counter utilization · calendar window includes closures'], ['Visits', 'Waiting students', 'Minutes', 'Percent']):
        fig.update_layout(title=dict(text=title, font_size=15), height=330, margin=dict(l=45,r=20,t=55,b=55), template='plotly_white', font=dict(family='Arial',size=11), yaxis_title=ylabel, legend=dict(orientation='h', font_size=10))
    figures[1].update_layout(height=410)
    for fig in figures[:2]:
        fig.update_xaxes(title='Simulated minutes')
    return figures
