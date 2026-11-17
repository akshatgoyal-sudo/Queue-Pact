"""Comparison Lab: one bounded playback timer and isolated session state."""
import json
import time
from dataclasses import replace
from html import escape
from pathlib import Path
from nicegui import ui, run
import plotly.graph_objects as go
from ..models import Scenario, Policy, SERVICES, Action, RunStatus
from ..actions import surge_action
from ..presenters import hall_state, LABELS, passport
from ..experiments import ExperimentSpec, PairedRun,RunRecord
from ..experiments.replay import branches
from ..experiments.staffing import StaffConstraints, StaffTrial, staff_action
from ..experiments.results import result, findings, charts
from ..experiments.readiness import ReadinessEngine
from .lab_controller import LabController, readiness_pair
from .hall import AdmissionHall
from .responsive_plot import ResponsivePlot


def register_lab():
    @ui.page('/lab')
    def page(saved: str | None = None,preset: int | None = None):
        from .app import passport_html, number
        from .history import artifact_controls
        from ..archive import Evidence
        state = LabController()
        ui.add_css(Path(__file__).with_name('style.css').read_text(encoding='utf-8'))
        ui.add_css('''
        .lab-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;width:100%}
        .lab-panel{min-width:0;width:100%;display:block;padding:16px}
        .lab-panel .admission-hall{max-height:300px;min-height:230px}
        .lab-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:10px 0}
        .lab-metrics div{background:#f4f6fb;border-radius:8px;padding:9px}
        .lab-metrics small{display:block;color:#64748b;font-size:11px}.lab-metrics strong{font-size:20px}
        .lab-controls{display:flex;flex-wrap:wrap;gap:12px;width:100%;align-items:center}
        .lab-detail{border-collapse:collapse;width:100%;font-size:12px}.lab-detail td,.lab-detail th{text-align:left;padding:8px;border-bottom:1px solid #e8edf5}
        .lab-charts{width:100%;min-width:0}.lab-charts .js-plotly-plot{max-width:100%}
        @media(max-width:1050px){.lab-grid{grid-template-columns:minmax(0,1fr)}}
        ''')
        with ui.header().classes('qp-header items-center'):
            with ui.column().classes('gap-0'):
                ui.label('QueuePact').classes('qp-logo')
                ui.label('COMPARISON & EXPERIMENT LAB').classes('qp-subtitle')
            ui.space()
            status = ui.label('Ready').classes('text-sm')
            clock = ui.label('0.00 min').classes('qp-clock')
        with ui.element('nav').classes('qp-nav'):
            ui.html('<a href="/"><b>▦</b>Live operations</a><a href="/lab"><b>⇄</b>Comparison Lab</a><a href="/history"><b>▤</b>Saved history</a><a href="#workbench"><b>⚗</b>Experiments</a>', sanitize=False)
        with ui.column().classes('qp-shell'):
            with ui.element('div').classes('qp-toolbar'):
                ui.html('<div class="qp-intro"><strong>Explore the trade-offs</strong><small>Identical inputs. Measured outcomes. No universal winner.</small></div>', sanitize=False)
                start_button = ui.button('Start comparison', on_click=lambda: start('comparison'))
                pause_button = ui.button('Pause', on_click=lambda: pause()).props('outline')
                results_button = ui.button('Run to results', on_click=lambda: fast()).props('outline')
                cancel_button = ui.button('Cancel', on_click=lambda: cancel()).props('flat')
                ui.button('Reset lab', on_click=lambda: reset()).props('flat')
                speed = ui.select({1:'1×',5:'5×',20:'20×',50:'50×'}, value=5, label='Playback').props('dense outlined').classes('w-24')
                artifact_controls(lambda name:freeze_evidence(name),lambda:state.parent_id,lambda rid:saved_parent(rid))
            with ui.expansion('Scenario & experiment settings', value=True).classes('w-full bg-white rounded-xl') as settings:
                with ui.element('div').classes('lab-controls'):
                    policy_left = ui.select({p.value:p.label for p in Policy},value=Policy.ORDINARY.value,label='Left policy').classes('w-64')
                    policy_right = ui.select({p.value:p.label for p in Policy},value=Policy.SMART.value,label='Right policy').classes('w-64')
                    seed = ui.number('Seed', value=42, step=1).classes('w-24')
                    count = ui.number('Students', value=40, min=0, max=1000, step=1).classes('w-28')
                    rate = ui.number('Arrivals / min', value=1.2, min=.01).classes('w-32')
                    missing = ui.number('Missing docs %', value=25, min=0, max=100).classes('w-32')
                    horizon = ui.number('End time · 0 = completion', value=0, min=0, max=10000).classes('w-48')
                    shared_button = ui.button('Shared disruption', on_click=lambda: disruption_dialog.open()).props('outline')
                ui.label('New experiments use these explicit settings. Existing runs retain their original immutable inputs. All time values are simulated minutes.').classes('qp-footnote')
            info = ui.label('Start a paired comparison, or configure a readiness trial below.').classes('qp-statusline')
            with ui.element('div').classes('lab-grid'):
                panels, halls, headings = [], [], []
                for i, name in enumerate(['Ordinary', 'QueuePact']):
                    with ui.card().classes('lab-panel'):
                        headings.append(ui.label(name).classes('qp-card-heading'))
                        panels.append(ui.html('Waiting for experiment', sanitize=False).classes('w-full'))
                        halls.append(AdmissionHall(lambda sid, index=i: select(index, sid)))
            with ui.expansion('Metric definitions & detailed results').classes('w-full bg-white rounded-xl'):
                detail = ui.html('', sanitize=False).classes('w-full')
                ui.label('Queue wait excludes preparation, screening service and counter service. Averages, p90 (nearest rank) and maximum cover completed visits only. Total accrued wait includes unfinished arrivals. Utilization uses 0 to each run’s own completion/horizon, including closures and time before an added desk exists. Completed runs freeze at their own end time.').classes('qp-footnote')
            insight = ui.html('', sanitize=False).classes('w-full bg-white rounded-xl p-4')
            with ui.expansion('Comparison charts', value=True).classes('w-full bg-white rounded-xl'):
                ui.label('Event-derived series · settled simulated timestamps · completed-only wait distribution').classes('qp-footnote')
                ui.button('Refresh charts', on_click=lambda: draw_charts()).props('flat')
                with ui.element('div').classes('lab-grid'):
                    plots = [ResponsivePlot(go.Figure()).classes('lab-charts') for _ in range(4)]
            with ui.card().classes('w-full qp-details').props('id=workbench'):
                ui.label('Experiment workbench').classes('qp-card-heading')
                ui.label('Pause the current run to start a trial. Sources are immutable input records; the original runs are never modified.').classes('qp-footnote')
                with ui.row().classes('w-full items-center'):
                    source = ui.select({}, label='Recorded source run').classes('grow')
                    ui.button('Capture current runs', on_click=lambda: capture()).props('outline')
                with ui.tabs().classes('w-full') as tabs:
                    staff_tab = ui.tab('Extra staff')
                    branch_tab = ui.tab('Turning point')
                    readiness_tab = ui.tab('Document readiness')
                with ui.tab_panels(tabs, value=staff_tab).classes('w-full'):
                    with ui.tab_panel(staff_tab):
                        ui.label('Where should one additional staff member be assigned?').classes('font-semibold')
                        with ui.element('div').classes('lab-controls'):
                            qualified = ui.select({s:LABELS[s] for s in SERVICES}, multiple=True, value=list(SERVICES), label='Worker qualifications').classes('w-72')
                            spare = ui.select({s:LABELS[s] for s in SERVICES}, multiple=True, value=list(SERVICES), label='Services with a spare desk').classes('w-72')
                            staff_time = ui.number('Assignment time', value=0, min=0).classes('w-32')
                            staff_end = ui.number('Evaluation end time', value=60, min=.1).classes('w-40')
                        ui.label('Objective: most completed visits, then least accrued queue wait across all arrived students, then stable service order. One extra qualified worker; no setup or travel time.').classes('qp-footnote')
                        ui.button('Test staff placements', on_click=lambda: start('staff'))
                        staff_results = ui.html('', sanitize=False).classes('w-full')
                        open_candidate = ui.button('Open selected candidate branch', on_click=lambda: start('candidate')).props('outline')
                    with ui.tab_panel(branch_tab):
                        ui.label('Reconstruct from inputs and action history').classes('font-semibold')
                        with ui.element('div').classes('lab-controls'):
                            turning = ui.number('Turning point (min)', value=10, min=0).classes('w-44')
                            intervention = ui.select(['Unchanged','Close desk','Restore desk','Service multiplier','Extra staff','Arrival surge'], value='Unchanged', label='Additive intervention').classes('w-52')
                            branch_service = ui.select({s:LABELS[s] for s in SERVICES}, value=SERVICES[0], label='Service').classes('w-60')
                            branch_desk = ui.number('Desk number', value=1, min=1, step=1).classes('w-28')
                            branch_multiplier = ui.number('Multiplier (1–3)', value=1.5, min=1,max=3).classes('w-36')
                            branch_count = ui.number('Surge students', value=5,min=1,max=30).classes('w-36')
                        ui.label('The boundary includes all original events at this time. The new action follows them. Existing future actions remain in both branches. Extra staff uses the qualifications and spare-desk selections in the Extra staff tab.').classes('qp-footnote')
                        ui.button('Reconstruct & branch', on_click=lambda: start('branch'))
                        timeline = ResponsivePlot(go.Figure()).classes('w-full')
                    with ui.tab_panel(readiness_tab):
                        with ui.element('div').classes('lab-controls'):
                            ready_policy = ui.select({p:p.label for p in Policy}, value=Policy.ORDINARY, label='Fixed scheduling policy').classes('w-44')
                            screening_capacity = ui.number('Screening workers', value=1,min=1,max=10,step=1).classes('w-40')
                            screening_duration = ui.number('Screening minutes / student', value=.5,min=.01).classes('w-56')
                            discovery = ui.number('Failed check minutes', value=.75,min=.01).classes('w-44')
                        ui.label('Early: every student uses an additional screening worker; missing documents trigger preparation. Late: missing students queue at verification for a failed check, prepare, then requeue. Complete-document students receive normal verification; its base duration includes their check. This is not a resource-equal policy comparison.').classes('qp-footnote')
                        ui.button('Compare readiness approaches', on_click=lambda: start('readiness'))
        with ui.dialog() as passport_dialog, ui.card().classes('qp-dialog'):
            passport_panel = ui.html('', sanitize=False)
            ui.button('Close passport', on_click=passport_dialog.close)
        with ui.dialog() as disruption_dialog, ui.card().classes('qp-dialog'):
            ui.label('One action, both runs, one simulated time').classes('text-lg font-semibold')
            ui.label('Available only for the Ordinary / QueuePact pair while both are active at a settled boundary.').classes('qp-footnote')
            action_kind = ui.select(['Close desk','Restore desk','Service multiplier','Arrival surge'],value='Service multiplier',label='Action').classes('w-full')
            action_service = ui.select({s:LABELS[s] for s in SERVICES},value=SERVICES[0],label='Service').classes('w-full')
            action_desk = ui.number('Desk number',value=1,min=1,step=1)
            action_multiplier = ui.number('Duration multiplier',value=1.5,min=1,max=3)
            action_count = ui.number('Surge students · over 2 min',value=5,min=1,max=30,step=1)
            apply_both = ui.button('Apply to both',on_click=lambda: shared())
            ui.button('Close controls',on_click=disruption_dialog.close).props('flat')

        def get_spec():
            for value in (seed.value,count.value):
                if int(value) != value:
                    raise ValueError('Seed and student count must be integers')
            if policy_left.value == policy_right.value:
                raise ValueError('Choose two distinct policies')
            return replace(ExperimentSpec.generate(Scenario(seed=int(seed.value),student_count=int(count.value),arrival_rate=float(rate.value),missing_fraction=float(missing.value)/100)),policies=(Policy(policy_left.value),Policy(policy_right.value)))

        def capture():
            state.remember()
            source.options = {k:k for k in state.sources}
            if source.value not in source.options:
                source.value = next(iter(source.options),None)
            source.update()
            draw_timeline()

        def make_action(kind, spec, time, service, desk, multiplier, count, aid):
            if kind == 'Arrival surge':
                if int(count) != count:
                    raise ValueError('Surge count must be an integer')
                return surge_action(spec.scenario,time,aid,int(count),2,at_boundary=True)
            if kind == 'Service multiplier':
                return Action(time,kind='slowdown',id=aid,payload_json=json.dumps(dict(service=service,multiplier=multiplier)),at_boundary=True)
            if int(desk) != desk:
                raise ValueError('Desk number must be an integer')
            return Action(time,f'{service}-{int(desk)}','close' if kind == 'Close desk' else 'restore',aid,at_boundary=True)

        async def start(kind):
            generation = None
            try:
                generation = state.begin()
                render()
                # Copy widget values before background work; worker never accesses UI.
                if kind in ('comparison','readiness'):
                    state.parent_id=None
                    spec = get_spec()
                    end = float(horizon.value) or None
                    if kind == 'comparison':
                        build = lambda: PairedRun(spec,end)
                    else:
                        if int(screening_capacity.value) != screening_capacity.value:
                            raise ValueError('Screening workers must be an integer')
                        args = (spec,Policy(ready_policy.value),int(screening_capacity.value),float(screening_duration.value),float(discovery.value),end)
                        build = lambda: readiness_pair(*args)
                elif kind == 'candidate':
                    if not state.trial:
                        raise ValueError('Run a feasible staffing trial first')
                    record = state.trial.open_selected()
                    build = lambda: PairedRun(record.specification,engines=[record.engine(),record.engine()],labels=['Selected candidate','Identical reconstruction'])
                else:
                    if source.value not in state.sources:
                        raise ValueError('Capture and select a source run first')
                    record = state.sources[source.value]
                    state.parent_id=state.source_parents.get(source.value)
                    constraints = StaffConstraints(tuple(qualified.value),tuple(spare.value))
                    if kind == 'staff':
                        point, end = float(staff_time.value),float(staff_end.value)
                        build = lambda: StaffTrial(record,constraints,point,end)
                    else:
                        point = float(turning.value)
                        action = None
                        aid = f'branch-{generation}'
                        if intervention.value == 'Extra staff':
                            if branch_service.value not in constraints.feasible:
                                raise ValueError('Select a qualified service with a spare desk')
                            action = staff_action(record.engine(),branch_service.value,point,aid)
                        elif intervention.value != 'Unchanged':
                            action = make_action(intervention.value,record.specification,point,branch_service.value,branch_desk.value,branch_multiplier.value,branch_count.value,aid)
                        build = lambda: branches(record,point,action)
                built = await run.io_bound(build)
                trial = built if isinstance(built,StaffTrial) else None
                if state.install(trial.pair if trial else built,generation,trial):
                    state.loaded_kind=None
                    state.experiment_settings=dict(horizon=(trial.pair if trial else built).horizon,turning_point=float(turning.value) if kind=='branch' else None,intervention=intervention.value if kind=='branch' else None)
                    settings.set_value(False)
                    if trial:
                        state.fast = True
                    render()
                    draw_charts()
                    draw_timeline()
            except Exception as exc:
                if generation is None or generation == state.generation:
                    state.busy = False
                    state.error = str(exc)
                    ui.notify(str(exc),type='negative')
                    render()

        def render():
            p = state.pair
            status.set_text('Preparing experiment…' if state.busy else state.error or ('Ready' if not p else p.status if p.done else 'Running' if state.playing else 'Paused'))
            clock.set_text(f'{p.clock if p else 0:.2f} min')
            pause_button.set_text('Pause' if state.playing else 'Resume')
            pause_button.set_enabled(bool(p and not p.done and not state.busy))
            results_button.set_enabled(bool(p and not p.done and not state.busy))
            cancel_button.set_enabled(state.busy or bool(p and not p.done))
            start_button.set_enabled(not state.busy and not state.playing)
            open_candidate.set_enabled(bool(state.trial and state.trial.selected_index is not None))
            shared_ok=bool(p and not state.busy and not p.done and p.target is None and p.labels == [e.policy.value for e in p.engines] and len({e.policy for e in p.engines})==2 and all(e.status not in (RunStatus.COMPLETED,RunStatus.STALLED,RunStatus.LIMIT) for e in p.engines))
            shared_button.set_enabled(shared_ok)
            apply_both.set_enabled(shared_ok)
            for field in (seed,count,rate,missing,horizon,policy_left,policy_right):
                field.set_enabled(not state.playing and not state.busy)
            if not p:
                info.set_text('Start a comparison. Each browser session owns an independent lab.')
                for panel,hall in zip(panels,halls):
                    panel.set_content('Waiting for experiment')
                    hall.set_visibility(False)
                    hall.present({})
                for heading,label in zip(headings,['Ordinary','QueuePact']):
                    heading.set_text(label)
                detail.set_content('')
                insight.set_content('No measured findings yet.')
                staff_results.set_content('')
                return
            if p.target is not None and not p.cancelled:
                return  # retain the last fully settled pair while draining a bounded batch
            info.set_text(f'Input {p.specification.fingerprint} · {len(p.specification.workload)} base students · {len(p.specification.actions)} shared recorded actions · common display boundary {p.clock:.2f} min')
            if p.cancelled and p.target is not None:
                info.set_text(f'Cancelled between boundaries · last common boundary {p.clock:.2f} min · panels show their individual measurement windows')
            engines = p.engines[:2]
            labels = [Policy(label).label if label in list(Policy) else label for label in p.labels[:2]]
            if len(engines) < 2:
                headings[1].set_text('No feasible placement' if state.trial else 'Single working run')
                panels[1].set_content('Select an overlapping qualification and spare desk.' if state.trial else 'This saved input contains one run. Capture it as a source to try staffing or branching.')
                halls[1].set_visibility(False)
            for i,(e,label) in enumerate(zip(engines,labels)):
                headings[i].set_text(Policy(label).label if label in list(Policy) else label.replace('_',' ').title() if '_' in label else label)
                r = result(e)
                values = [('Completed',r['completed']),('Unfinished',r['unfinished']),('Avg completed wait',number(r['average_completed_wait'])),('Arrived',r['arrived']),('Current longest wait',number(r['longest_current_wait'])),('All accrued wait',number(r['total_queue_wait']))]
                text = '<div class="lab-metrics">'+''.join(f'<div><small>{k}</small><strong>{v}</strong></div>' for k,v in values)+'</div>'
                text += f'<div class="qp-footnote">{e.status.value} · measurement window 0–{e.now:.2f} min · {r["waiting"]} waiting · {r["preparing"]} preparing · {len(e.actions)} recorded actions</div>'
                if isinstance(e,ReadinessEngine):
                    o=e.overhead()
                    text += f'<p>Screening: {o["screening_workers"]} additional workers, {o["screening_time"]:.2f} busy min. Failed checks: {o["failed_check_time"]:.2f} desk min. Preparation: {o["preparation_time"]:.2f} min.</p>'
                panels[i].set_content(text)
                halls[i].set_visibility(not isinstance(e,ReadinessEngine))
                if not isinstance(e,ReadinessEngine):
                    halls[i].present(hall_state(e,playing=state.playing,speed=state.speed,generation=state.generation))
            rows = [('Completed visits','completed'),('Unfinished students','unfinished'),('Average completed wait','average_completed_wait'),('P90 completed wait','p90_completed_wait'),('Maximum completed wait','max_completed_wait'),('Longest current wait','longest_current_wait'),('Average completed visit','average_completed_visit'),('Accrued wait of unfinished students','unfinished_wait'),('Full completion makespan','makespan')]
            detail.set_content('<table class="lab-detail"><tr><th>Measure (minutes unless count)</th>'+''.join(f'<th>{escape(l)}</th>' for l in labels)+'</tr>'+''.join('<tr><td>'+title+'</td>'+''.join(f'<td>{number(result(e)[key])}</td>' for e in engines)+'</tr>' for title,key in rows)+'</table>')
            insight.set_content(''.join(f'<p class="text-sm">{escape(t)}</p>' for t in findings(engines,labels)) if len(engines)>1 or state.trial else 'No policy comparison is implied by this single working run.')
            if state.trial:
                trial=state.trial
                rows=trial.outcomes()
                selected=trial.selected_index
                message = 'No feasible placement: qualifications and spare compatible desks do not overlap.' if not trial.constraints.feasible else ('Evaluating all feasible placements…' if selected is None else f'Best among tested placements for this scenario and objective: {LABELS[trial.placements[selected]]}. Ranked by completions, then all accrued waiting. Compare the reference below; adding staff need not improve every measure.')
                staff_results.set_content(f'<p>{escape(message)}</p><table class="lab-detail"><tr><th>Placement</th><th>Completed</th><th>Unfinished</th><th>All wait</th><th>Avg completed wait</th></tr>'+''.join(f'<tr><td>{LABELS.get(r["placement"],"Reference")}</td><td>{r["completed"]}</td><td>{r["unfinished"]}</td><td>{r["total_wait"]:.2f}</td><td>{number(r["average_wait"])}</td></tr>' for r in rows)+'</table>')
            else:
                staff_results.set_content('')

        def draw_charts():
            if state.pair:
                for plot,fig in zip(plots,charts(state.pair.engines[:2],[Policy(label).label if label in list(Policy) else label for label in state.pair.labels[:2]])):
                    plot.figure=fig
                    plot.update()

        def draw_timeline():
            fig=go.Figure()
            record=state.sources.get(source.value)
            if record:
                actions=record.specification.actions
                fig.add_scatter(x=[a.time for a in actions],y=[1]*len(actions),mode='markers+text',text=[a.kind for a in actions],textposition='top center',hovertext=[a.id+' '+a.payload_json for a in actions],name='Recorded actions')
            if state.pair:
                for i,e in enumerate(state.pair.engines[:2]):
                    fig.add_scatter(x=[a.time for a in e.actions],y=[.4-i*.3]*len(e.actions),mode='markers',text=[a.id+' · '+a.kind for a in e.actions],name=state.pair.labels[i])
            fig.add_vline(x=float(turning.value or 0),line_dash='dash',line_color='#d97706')
            fig.update_layout(title='Action timeline · dashed line is turning point',height=220,margin=dict(l=20,r=20,t=45,b=35),template='plotly_white',yaxis_visible=False,xaxis_title='Simulated minutes')
            timeline.figure=fig
            timeline.update()

        def select(index,sid):
            if state.pair:
                passport_panel.set_content(passport_html(passport(state.pair.engines[index],sid)))
                passport_dialog.open()

        def pause():
            state.playing=not state.playing
            state.fast=False
            render()
            if not state.playing:
                draw_charts()

        def fast():
            state.fast=state.playing=True

        def cancel():
            state.cancel()
            render()
            draw_charts()

        def reset():
            state.reset()
            passport_dialog.close()
            source.options={}
            source.value=None
            source.update()
            for plot in [*plots,timeline]:
                plot.figure=go.Figure()
                plot.update()
            render()

        def shared():
            try:
                p=state.pair
                if not p or (p.labels != [e.policy.value for e in p.engines] or len({e.policy for e in p.engines})!=2):
                    raise ValueError('Start an Ordinary / QueuePact pair for shared disruptions')
                aid=f'shared-{len(p.specification.actions)+1}'
                signature=(action_kind.value,action_service.value,action_desk.value,action_multiplier.value,action_count.value)
                wall=time.monotonic()
                if state.last_action and state.last_action[0] == signature and wall-state.last_action[1] < .8:
                    raise ValueError('This action was just accepted; wait before repeating it')
                a=make_action(action_kind.value,p.specification,p.clock,action_service.value,action_desk.value,action_multiplier.value,action_count.value,aid)
                p.apply_shared(a)
                state.last_action=(signature,wall)
                ui.notify(f'{a.id} accepted for both runs at {a.time:.2f} min',type='positive')
                render()
                draw_timeline()
            except (ValueError,TypeError) as exc:
                ui.notify(str(exc),type='warning')

        def tick():
            try:
                if state.tick():
                    render()
                    if state.pair.done:
                        capture()
                        draw_charts()
            except Exception as exc:
                state.error=str(exc)
                state.cancel()
                render()
                ui.notify(str(exc),type='negative')

        speed.on_value_change(lambda: setattr(state,'speed',speed.value))
        source.on_value_change(draw_timeline)
        turning.on_value_change(draw_timeline)
        timer=ui.timer(.25,tick)
        def cleanup():
            state.cancel()
            timer.cancel()
        ui.context.client.on_delete(cleanup)
        def freeze_evidence(name):
            p=state.pair
            if not p:
                raise ValueError('Start an experiment before saving')
            if p.target is not None:
                raise ValueError('Wait for a settled boundary before saving')
            kind='Staffing' if state.trial else 'Readiness' if any(isinstance(e,ReadinessEngine) for e in p.engines) else 'Branch comparison' if p.labels[0]=='Unchanged continuation' else 'Policy comparison'
            kind=getattr(state,'loaded_kind',None) or ('Single run' if len(p.engines)==1 and not state.trial else kind)
            settings=dict(getattr(state,'experiment_settings',{}),horizon=p.horizon)
            if state.trial:
                settings.update(staff_outcomes=state.trial.outcomes(),qualifications=list(state.trial.constraints.qualifications),spare_desks=list(state.trial.constraints.spare_desks),assignment_time=state.trial.time,selected_index=state.trial.selected_index,objective='Most completed visits, then least total accrued wait, then stable service order')
            elif kind=='Staffing':
                outcomes=[]
                for e in p.engines:
                    additions=[a for a in e.actions if a.kind=='add_staff']
                    m=e.metrics()
                    outcomes.append(dict(placement=additions[-1].payload['service'] if additions else None,completed=m.completed,unfinished=m.unfinished,total_wait=m.total_queue_wait,average_wait=m.average_completed_wait))
                selected=min(range(1,len(outcomes)),key=lambda i:(-outcomes[i]['completed'],outcomes[i]['total_wait'],i)) if p.done and len(outcomes)>1 else None
                settings.update(staff_outcomes=outcomes,selected_index=selected)
            return Evidence.capture(name,p.engines,p.labels,kind,settings,p.status if p.done else 'Incomplete · paused' if not state.playing else 'Incomplete · running')
        def saved_parent(rid):
            state.parent_id=rid
            state.remember()
        if saved or preset is not None:
            try:
                if saved:
                    from ..repository import Repository
                    evidence=Repository().get(saved)
                    engines=evidence.engines()
                    d=evidence.data
                    state.pair=PairedRun(RunRecord.capture(engines[0]).specification,d['settings'].get('horizon'),engines,[r['label'] for r in d['runs']])
                    state.parent_id=saved
                    state.loaded_kind='Single run' if d['kind']=='Scenario' else d['kind']
                    state.experiment_settings=d['settings']
                    cfg=engines[0].config
                    seed.set_value(cfg.seed);count.set_value(cfg.student_count);rate.set_value(cfg.arrival_rate);missing.set_value(cfg.missing_fraction*100)
                    horizon.set_value(d['settings'].get('horizon') or 0)
                else:
                    from ..presets import presets
                    choices=presets()
                    if not 0<=preset<len(choices):
                        raise ValueError('Unknown prepared scenario')
                    state.pair=PairedRun(choices[preset].specification)
                    state.speed=choices[preset].speed
                state.playing=False
                settings.set_value(False)
            except Exception as exc:
                state.error='Cannot open working copy: '+str(exc)
        render()
