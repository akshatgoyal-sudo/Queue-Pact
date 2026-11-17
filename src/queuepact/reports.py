"""Standalone offline HTML and SVG. PDF is the browser's print workflow."""
from html import escape
import json
from .presenters import desk_label,LABELS
from .models import Policy


def text(value):
    return escape(str(value))


def number(value):
    return '—' if value is None else f'{value:.2f}' if isinstance(value,float) else text(value)


def table(headers,rows):
    return '<table><thead><tr>'+''.join(f'<th>{text(h)}</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{v}</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table>'


def completion_chart(runs):
    colors=['#2563eb','#7c3aed','#059669','#b45309','#be123c']
    max_t=max((r['observation_min'] for r in runs),default=1) or 1
    max_n=max((r['metrics']['completed'] for r in runs),default=1) or 1
    svg='<svg viewBox="0 0 680 260" role="img" aria-label="Completed visits over simulated time"><rect width="680" height="260" fill="white"/>'
    for i in range(5):
        y=205-i*45
        svg+=f'<path d="M45 {y}H660" stroke="#e2e8f0"/><text x="5" y="{y+4}" font-size="11">{max_n*i/4:.0f}</text>'
    for index,r in enumerate(runs):
        points=[]
        previous=0
        for row in r['series']:
            x=45+615*row['time']/max_t
            points.extend([(x,205-180*previous/max_n),(x,205-180*row['completed']/max_n)])
            previous=row['completed']
        svg+=f'<polyline points="'+ ' '.join(f'{x:.2f},{y:.2f}' for x,y in points)+f'" fill="none" stroke="{colors[index]}" stroke-width="2"/>'
    svg+=f'<text x="45" y="225" font-size="11">0 min</text><text x="590" y="225" font-size="11">{max_t:.2f} min</text></svg>'
    return svg+'<div class="legend">'+''.join(f'<span style="color:{colors[i]}">● {text(r["label"])}</span>' for i,r in enumerate(runs))+'</div>'


def report_html(evidence):
    d=evidence.data
    runs=d['runs']
    incomplete=d['status']!='Completed' or any(r['metrics']['unfinished'] for r in runs)
    style='''
    *{box-sizing:border-box}body{font:14px Arial,sans-serif;color:#192b43;background:#edf1f6;margin:0;line-height:1.5}
    main{max-width:940px;margin:24px auto;background:white;padding:36px;border-radius:12px}h1{font-size:30px;margin:0}h2{font-size:18px;margin:24px 0 10px;color:#183862}h3{font-size:15px}
    .brand{color:#2563eb;font-weight:bold;letter-spacing:1px}.muted,footer{color:#52657d;font-size:12px}.notice{background:#fff4d6;padding:12px;border-left:4px solid #b77908}.toolbar{max-width:940px;margin:20px auto;display:flex;gap:16px;align-items:center}button,a{font:inherit;color:#205ac5}button{padding:10px;border:1px solid #b7c5d9;background:white;border-radius:6px;cursor:pointer}
    table{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}th,td{padding:8px;border:1px solid #dbe3ed;text-align:left;overflow-wrap:anywhere;vertical-align:top}th{background:#eef3fa}svg{width:100%;max-height:260px}.chart{break-inside:avoid}.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:11px}.metadata{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}footer{border-top:1px solid #dbe3ed;padding-top:12px;margin-top:24px;overflow-wrap:anywhere}
    @page{size:A4;margin:14mm}@media print{body{background:white;font-size:10pt}main{margin:0;padding:0;max-width:none;border-radius:0}.toolbar{display:none!important}h1{font-size:22pt}h2{break-after:avoid;font-size:14pt}table{font-size:9pt}th,td{padding:6px}h2{margin-top:18px}footer{break-inside:avoid;margin-top:14px;padding-top:8px}thead{display:table-header-group}tr,.notice{break-inside:avoid}svg{max-height:60mm}.chart{break-inside:avoid}footer{font-size:8pt}a{color:inherit;text-decoration:none}}
    '''
    html=f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{text(d["name"])} · QueuePact report</title><style>{style}</style></head><body><div class="toolbar"><a href="/history">Saved history</a><button onclick="window.print()">Print / Save as PDF</button><span>Uses your browser print dialog; this page is HTML.</span></div><main><div class="brand">QUEUEPACT</div><h1>{text(d["name"])}</h1><p>Queue coordination and decision testing for college admissions.</p><p class="muted">{text(d["kind"])} · Captured {text(d["created_utc"])}</p>'
    html+=f'<div class="notice"><b>{"INCOMPLETE OBSERVATION — " if incomplete else "Completed observation — "}{text(d["status"])}</b><br>Historical evidence, not automatically verified reproduction. Evaluation horizon: {text(d["settings"].get("horizon") or "full completion / captured observation")}. Each result uses its own stated observation window.</div>'
    question={'Single run':'How do students progress through the admission counters?','Scenario':'What initial admission conditions will be tested?','Policy comparison':'How do two scheduling policies behave with the same inputs?','Staffing':'Where should one additional qualified worker be assigned?','Branch comparison':'What changes after an intervention at the selected turning point?','Readiness':'What are the costs and outcomes of early screening versus late discovery?'}[d['kind']]
    html+='<h2>The question</h2><p>'+text(question)+'</p><h2>Inputs and resources</h2>'
    rows=[]
    for r in runs:
        c=r['record']['specification']['scenario']
        rows.append([text(r['label']),text(Policy(r['record']['policy']).label),str(c['seed']),str(c['student_count']),text(c['counter_counts']),number(c['missing_fraction']*100)+'%'])
    html+=table(['Run','Policy','Seed','Base students','Desks: V/P/F/E','Missing documents'],rows)
    html+='<p class="muted">V: verification · P: photo · F: fees · E: enrollment. Additional resources are listed with interventions below. Arrivals and service requirements are stored in the reproducibility JSON, at full precision.</p><h2>Actual results</h2>'
    keys=[('Observation window end (min)','window'),('Arrived students','arrived'),('Completed visits','completed'),('Students still in the process, including future arrivals','unfinished'),('Average wait for completed students (min)','average_completed_wait'),('P90 completed wait (min)','p90_completed_wait'),('Maximum completed wait (min)','max_completed_wait'),('All accrued queue waiting (student-min)','total_queue_wait'),('Unfinished students’ accrued wait (student-min)','unfinished_wait'),('Average completed visit duration (min)','average_completed_visit'),('Full completion makespan (min)','makespan')]
    html+=table(['Measure / population']+[r['label'] for r in runs],[[text(label)]+[number(r['metrics'][key]) for r in runs] for label,key in keys])
    html+='<p class="muted">Completed-only averages cannot describe delays of unfinished students. Queue waiting excludes preparation and service. P90 uses nearest rank; undefined values are —. Display rounds to two decimals; exports retain full precision.</p><section class="chart"><h2>Completed visits over simulated time</h2>'+completion_chart(runs)+'</section>'
    html+='<h2>Counter utilization</h2>'+table(['Run','Desk','Busy minutes','Calendar utilization'],[[text(r['label']),text(desk_label(cid)),number(busy),number(dict(r['metrics']['counter_utilization'])[cid]*100)+'%' if dict(r['metrics']['counter_utilization'])[cid] is not None else '—'] for r in runs for cid,busy in r['metrics']['counter_busy_time']])
    html+='<p class="muted">Denominator: zero to each run’s observation end, including closures and time before added desks exist. Finished runs retain their own window.</p>'
    if any(r['overhead'] for r in runs):
        html+='<h2>Readiness costs and extra resources</h2><p>Early screening uses additional dedicated workers. This is not a resource-equal policy comparison. Failed checks occupy verification desks without completing verification.</p>'+table(['Run','Additional screening workers','Screening busy min','Failed-check desk min','Preparation min'],[[text(r['label'])]+[number(r['overhead'][key]) for key in ('screening_workers','screening_time','failed_check_time','preparation_time')] for r in runs if r['overhead']])
    if d['kind']=='Staffing':
        html+='<h2>Staffing objective</h2><p>Most completed visits, then least accrued waiting across all arrived students, then stable service order. One worker per candidate; no setup or travel time. Best among tested candidates for this scenario and objective; the reference may still be better.</p>'
    if d['kind']=='Branch comparison':
        html+='<h2>Turning point</h2><p>Original events at the chosen boundary execute before the additive intervention. Existing future actions are retained.</p>'
    setting_names={'horizon':'Evaluation end (min)','preset':'Prepared scenario','turning_point':'Turning point (min)','intervention':'Intervention','assignment_time':'Worker assignment time (min)','objective':'Ranking objective','qualifications':'Worker qualifications','spare_desks':'Spare compatible desks'}
    rows=[]
    for key,label in setting_names.items():
        value=d['settings'].get(key)
        if value is not None:
            rows.append([label,text(', '.join(LABELS.get(v,v) for v in value) if isinstance(value,list) else value)])
    html+='<h2>Experiment settings</h2>'+(table(['Setting','Value'],rows) if rows else '<p>No additional experiment settings.</p>')
    candidates=d['settings'].get('staff_outcomes')
    if candidates:
        html+='<h3>Tested placements</h3>'+table(['Placement','Completed','Unfinished','Accrued wait (student-min)','Avg completed wait (min)'],[[text(LABELS.get(c['placement'],c['placement'] or 'Reference')),number(c['completed']),number(c['unfinished']),number(c['total_wait']),number(c['average_wait'])] for c in candidates])
        selected=d['settings'].get('selected_index')
        if selected is not None and 0<=selected<len(candidates):
            c=candidates[selected]
            html+='<p><b>Selected: '+text(LABELS.get(c['placement'],c['placement'] or 'Reference'))+'</b> — best among tested candidates for this objective.</p>'
    def action_detail(a):
        p=json.loads(a['payload_json'])
        if a['kind']=='surge':
            return f'{len(p["students"])} generated student arrivals; full inputs in JSON'
        if a['kind']=='slowdown':
            return f'{LABELS.get(p["service"],p["service"])}: {p["multiplier"]}× future duration'
        if a['kind']=='add_staff':
            return 'One qualified worker at '+desk_label(a['counter_id'])
        return desk_label(a['counter_id'])+(' · active service finishes' if a['kind']=='close' else ' · eligible dispatch resumes')
    actions=[[text(r['label']),text(a['id']),number(a['time']),text(a['kind']),text(action_detail(a))] for r in runs for a in r['actions']]
    html+='<h2>Recorded interventions</h2>'+(table(['Run','Action ID','Time (min)','Action','Actual effect'],actions) if actions else '<p>No external interventions in this captured record.</p>')
    html+='<h2>Findings</h2>'+''.join('<p>'+text(f)+'</p>' for f in d['findings'])
    if not d['findings']:
        html+='<p>These measured results describe this run only. No comparison or improvement is implied.</p>'
    assumptions=list(dict.fromkeys(a for r in runs for a in r['record']['specification']['assumptions']))
    html+='<h2>Assumptions and limitations</h2><ul>'+''.join('<li>'+text(a)+'</li>' for a in [*assumptions,*d['limitations']])+'</ul>'
    html+=f'<footer>Input fingerprint: {text(d["input_id"])} · schema {d["schema"]} · {text(d["engine_version"])} · app {text(d["app_version"])}<br>Runtime: {text(d.get("runtime",{}))}<br>Immutable result capture. Use Reproducibility JSON and explicit Verify reconstruction to test compatibility; viewing this report does not run a simulation.</footer></main></body></html>'
    return html
