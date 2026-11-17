"""Session-local NiceGUI shell. Rendering never advances the engine."""
from html import escape
from pathlib import Path
from nicegui import ui
from ..models import Scenario, Policy, RunStatus, SERVICES
from ..presenters import LABELS, desk_label, hall_state, passport, congestion, event_feed
from .controller import Controller
from .hall import AdmissionHall


def number(value):
    return '—' if value is None else f'{value:.2f}'


def passport_html(p):
    if p is None:
        return '<div class="qp-empty"><span style="font-size:40px">▤</span><strong>A journey, step by step</strong><span>Select a student to follow their admission journey.</span></div>'
    totals = [('Visit', p['elapsed']), ('Queue wait', p['waiting']), ('Preparation', p['preparation']), ('Service', p['service_time'])]
    html = f'<div class="qp-passport-content"><div class="qp-eyebrow">Student visit passport</div><div class="qp-token">{escape(p["id"])}</div><span class="qp-tag">{escape(p["state"])}</span><p class="qp-footnote">Arrival {p["arrival"]:.2f} min'
    if p['desk']:
        html += f' · Desk {escape(p["desk"])}'
    html += '</p><div class="qp-totals">' + ''.join(f'<div><small>{label}{" · actual" if p["complete"] else " · elapsed"}</small>{number(value)} min</div>' for label, value in totals) + '</div>'
    if p['task']:
        html += f'<p style="font-size:12px"><b>Current:</b> {escape(p["task"])}</p>'
    if p['protected']:
        html += '<p class="qp-tag" style="background:#fff3d6;color:#98620f">Fair-wait protected · eligible queue priority</p>'
    if p['waiting_count'] is not None:
        html += f'<p class="qp-footnote">{p["waiting_count"]} waiting for this service. This is not a queue position.</p>'
    for task in p['tasks']:
        html += f'<div class="qp-step {"done" if task["state"] == "Completed" else ""}"><b>{"✓ " if task["state"] == "Completed" else ""}{escape(task["label"])}</b><span>{escape(task["state"])}</span><small>{escape(task["reason"])}</small></div>'
    if p['latest_decision']:
        html += f'<div class="qp-explanation"><b>Last recorded decision</b><br>{escape(p["latest_decision"])}</div>'
    return html + '</div>'


def launch(port=8080):
    from .lab import register_lab
    from .history import register_history,artifact_controls
    from .presentation import presentation_controls
    from ..archive import Evidence
    register_history()
    register_lab()
    @ui.page('/')
    def page():
        controller = Controller()
        ui.add_css(Path(__file__).with_name('style.css').read_text(encoding='utf-8'))
        ui.colors(primary='#2563eb', secondary='#7c3aed', positive='#15803d', warning='#d97706')
        with ui.header().classes('qp-header items-center'):
            with ui.column().classes('gap-0'):
                ui.label('QueuePact').classes('qp-logo')
                ui.label('QUEUE COORDINATION AND DECISION TESTING FOR COLLEGE ADMISSIONS').classes('qp-subtitle')
            ui.space()
            policy_badge = ui.label('Ordinary').classes('text-sm text-blue-200 mr-4')
            run_status = ui.label('Ready').classes('text-sm mr-3')
            clock = ui.label('0.00 min').classes('qp-clock')
        with ui.element('nav').classes('qp-nav').props('aria-label="Main navigation"'):
            ui.html('<a href="#live"><b>▦</b>Live hall</a><a href="/lab"><b>⇄</b>Comparison Lab</a><a href="/history"><b>▤</b>Saved history</a><a href="#students"><b>☷</b>Students</a><a href="#decisions"><b>≡</b>Decisions</a>', sanitize=False)
        with ui.dialog() as config_dialog, ui.card().classes('qp-dialog'):
            ui.label('Configure your admission run').classes('text-xl font-semibold')
            ui.label('Settings apply on Start. Reset unlocks them for a new run.').classes('qp-footnote')
            with ui.grid(columns=2).classes('w-full gap-4'):
                seed = ui.number('Seed', value=42, step=1)
                count = ui.number('Students', value=40, min=0, max=1000, step=1)
                rate = ui.number('Arrivals per minute', value=1.2, min=.01, step=.1)
                policy = ui.select({p.value:p.label for p in Policy}, value='Ordinary', label='Scheduling policy')
                missing = ui.number('Missing documents (%)', value=25, min=0, max=100, step=1)
                fair = ui.number('Fair-wait threshold (min)', value=10, min=0, step=1)
            config_fields = [seed, count, rate, policy, missing, fair]
            ui.label('Same workload, different coordination. The recorded 40-student demo averaged 23.37 min queue wait with Ordinary and 27.55 min with QueuePact v1. V2 is experimental and did not improve overall held-out waiting. Outcomes depend on the workload.').classes('qp-footnote')
            ui.button('Done', on_click=config_dialog.close).classes('self-end')
        with ui.dialog() as disruption_dialog, ui.card().classes('qp-dialog'):
            ui.label('Disrupt the admission hall').classes('text-xl font-semibold')
            ui.label('Actions affect this run only. While paused, they apply at the frozen simulation clock.').classes('qp-footnote')
            ui.separator()
            ui.label('Desk availability').classes('font-semibold')
            desk_select = ui.select({c.id: f'{desk_label(c.id)} · {LABELS[c.service]}' for c in controller.engine.counters.values()}, value=next(iter(controller.engine.counters)), label='Desk').classes('w-full')
            desk_description = ui.label().classes('qp-footnote')
            with ui.row():
                close_button = ui.button('Close desk', on_click=lambda: disrupt('close', counter_id=desk_select.value)).props('outline color=negative')
                restore_button = ui.button('Restore desk', on_click=lambda: disrupt('restore', counter_id=desk_select.value)).props('outline')
            ui.separator()
            ui.label('Service duration').classes('font-semibold')
            with ui.row().classes('w-full'):
                service_select = ui.select({s: LABELS[s] for s in SERVICES}, value=SERVICES[0], label='Service').classes('grow')
                multiplier = ui.select({1: '1× · normal', 1.5: '1.5× duration', 2: '2× duration', 3: '3× duration'}, value=1.5, label='Set duration').classes('w-44')
            slowdown_description = ui.label().classes('qp-footnote')
            slowdown_button = ui.button('Apply duration', on_click=lambda: disrupt('slowdown', service=service_select.value, multiplier=multiplier.value)).props('outline')
            ui.separator()
            ui.label('Arrival surge').classes('font-semibold')
            with ui.row().classes('w-full'):
                surge_count = ui.number('Additional students', value=5, min=1, max=30, step=1).classes('grow')
                surge_interval = ui.number('Over minutes', value=2, min=0, max=10, step=.5).classes('w-44')
            surge_button = ui.button('Add arrival surge', on_click=lambda: disrupt('surge', count=surge_count.value, interval=surge_interval.value)).props('outline')
            feedback = ui.label().classes('qp-footnote')
            ui.button('Back to live hall', on_click=disruption_dialog.close).classes('self-end')
        with ui.column().classes('qp-shell'):
            with ui.element('div').classes('qp-toolbar'):
                ui.html('<div class="qp-intro"><strong>Live admissions</strong><small>Explore queue coordination and its effects.</small></div>', sanitize=False).classes('mr-auto')
                start_button = ui.button('Start run', on_click=lambda: start())
                pause_button = ui.button('Pause', on_click=lambda: pause()).props('outline')
                ui.button('Reset', on_click=lambda: reset()).props('flat color=grey-8')
                speed = ui.select({.25: '.25×', 1: '1×', 5: '5×', 20: '20×'}, value=1, label='Playback').props('dense outlined').classes('w-24')
                ui.button('Disruptions', on_click=disruption_dialog.open).props('outline color=secondary')
                ui.button('Configure', on_click=config_dialog.open).props('flat color=grey-8').classes('qp-config-trigger')
                artifact_controls(lambda name:Evidence.capture(name,[controller.engine]))
            presentation_controls(controller,lambda:render())
            metrics_html = ui.html('', sanitize=False).classes('w-full')
            statusline = ui.label().classes('qp-statusline')
            with ui.element('section').classes('qp-live').props('id=live'):
                with ui.card().classes('qp-hall-card'):
                    with ui.row().classes('items-center w-full justify-between'):
                        ui.label('Admission hall').classes('qp-card-heading')
                        motion = ui.switch('Reduced motion', value=False).props('dense').classes('text-xs')
                    hotspot_text = ui.label().classes('qp-hotspot')
                    hall = AdmissionHall(lambda sid: select(sid))
                    ui.html('<div class="qp-legend"><span style="--tone:#2563eb">Waiting</span><span style="--tone:#7c3aed">In service</span><span style="--tone:#d97706">Preparation / closing</span><span style="--tone:#dc2626">Unavailable</span><span style="--tone:#15803d">Complete</span></div>', sanitize=False)
                    ui.label('Movement illustrates state changes; it adds no travel time. Click a token to follow a student.').classes('qp-footnote mt-2')
                with ui.card().classes('qp-passport'):
                    with ui.tabs().classes('w-full text-sm') as side_tabs:
                        passport_tab = ui.tab('Passport')
                        insight_tab = ui.tab('Insights')
                    with ui.tab_panels(side_tabs, value=passport_tab).classes('w-full'):
                        with ui.tab_panel(passport_tab).classes('p-0'):
                            passport_panel = ui.html(passport_html(None), sanitize=False).classes('w-full')
                        with ui.tab_panel(insight_tab).classes('p-4'):
                            insight_panel = ui.html('', sanitize=False)
            with ui.expansion('Student directory', value=True).classes('qp-details bg-white rounded-xl').props('id=students'):
                ui.label('Select a row to open its visit passport above. Eligible tasks are not assignments.').classes('qp-footnote')
                table = ui.table(columns=[dict(name=k, label=label, field=k, align='left') for k, label in
                    [('id', 'Token'), ('state', 'Status'), ('task', 'Current assignment'), ('completed', 'Tasks done'), ('waiting', 'Queue wait (min)')]],
                    rows=[], row_key='id', pagination=8, selection='single', on_select=lambda e: select(e.selection[0]['id']) if e.selection else None).classes('qp-table')
                table.on('rowClick', lambda e: select(e.args[1]['id']), [[], ['id'], None])
            with ui.card().classes('qp-details').props('id=decisions'):
                with ui.row().classes('w-full items-center justify-between'):
                    ui.label('Decisions & activity').classes('qp-card-heading')
                    filter_select = ui.select(['All events', 'Routing decisions', 'Disruptions', 'Selected student'], value='All events', label='Show').props('dense outlined').classes('w-48')
                feed = ui.html('', sanitize=False).classes('qp-feed w-full')
                ui.label('Showing up to 18 matching events. Full structured history stays in the simulation.').classes('qp-footnote')
            ui.label('Educational simulation · No guaranteed waiting-time reduction · All displayed times are simulated minutes').classes('qp-footnote')

        def render():
            e, m = controller.engine, controller.engine.metrics()
            if speed.value != controller.speed:
                speed.set_value(controller.speed)
            policy_badge.set_text(e.policy.label)
            run_status.set_text('Paused' if controller.started and not controller.playing and e.status == RunStatus.RUNNING else e.status.value)
            clock.set_text(f'{e.now:.2f} min')
            values = [('Arrived', m.arrived, '#26354b'), ('Completed', m.completed, '#15803d'), ('Waiting', m.waiting, '#2563eb'), ('In service', m.in_service, '#7c3aed'), ('Average completed wait', number(m.average_completed_wait), '#26354b'), ('Longest current wait', number(m.longest_current_wait), '#b45309')]
            metrics_html.set_content('<div class="qp-metrics">'+''.join(f'<div class="qp-metric"><small>{label}</small><strong style="color:{color}">{value}</strong></div>' for label, value, color in values)+'</div>')
            statusline.set_text(f'{m.unfinished} unfinished · {m.not_arrived} to arrive · {m.waiting} waiting · {m.in_service} in service · {m.preparing} preparing documents' + (' · Restore required capacity to continue.' if e.status == RunStatus.STALLED else ''))
            insight = congestion(e)
            hotspot_text.set_text(insight.title + ' · ' + (LABELS[insight.service] + f' · {insight.waiting} waiting · {insight.workload:.1f} min queued work' if insight.service else 'No counter queues right now'))
            insight_panel.set_content(f'<div class="qp-eyebrow">Observable conditions</div><h3 class="qp-card-heading">{insight.title}</h3><p style="font-size:13px;line-height:1.7">{escape(insight.explanation)}</p><p class="qp-footnote">Unavailable queued services rank first, then queued work per open desk. Stable service order breaks ties. This is a congestion indicator, not a proven system bottleneck.</p><p class="qp-footnote">{m.preparing} students preparing documents outside counter queues.</p><hr><p class="qp-footnote">The routing heuristic estimates the next activity, not the whole visit. The unchanged demo averaged 23.37 min wait for Ordinary and 27.55 min for QueuePact.</p>')
            hall.present(hall_state(e, controller.selected, playing=controller.playing, speed=controller.speed, generation=controller.generation, reduced_motion=motion.value))
            passport_panel.set_content(passport_html(passport(e, controller.selected)))
            table.rows = [dict(id=s.id, state=s.state.value, task=LABELS.get(s.task, '—'), completed=f'{len(s.completed)} / 4', waiting=round(s.waiting, 2)) for s in e.snapshot().students]
            table.update()
            rows = event_feed(e, filter_select.value, controller.selected)
            feed.set_content(''.join(f'<div class="qp-event"><time>{r["time"]:.2f} min</time><span>{escape(r["text"])}</span></div>' for r in rows) or '<p class="qp-footnote">No matching events yet. Start a run or select a student.</p>')
            start_button.set_enabled(not controller.started)
            pause_button.set_text('Pause' if controller.playing else 'Resume')
            pause_button.set_enabled(controller.started and e.status in (RunStatus.RUNNING, RunStatus.STALLED))
            for field in config_fields:
                field.set_enabled(not controller.started)
            active = controller.started and e.status not in (RunStatus.COMPLETED, RunStatus.LIMIT)
            c = e.counters[desk_select.value]
            desk_description.set_text(('Available' if not c.student_id else f'Serving {c.student_id}') if c.open else (f'Closing after current student {c.student_id}' if c.student_id else 'Closed'))
            close_button.set_enabled(active and c.open)
            restore_button.set_enabled(active and not c.open)
            slowdown_button.set_enabled(active)
            surge_button.set_enabled(active)
            slowdown_description.set_text(f'Currently {e.multipliers[service_select.value]:g}× duration. Already-started service is unchanged.')

        def select(sid):
            controller.select(sid)
            side_tabs.set_value(passport_tab)
            render()
            ui.run_javascript('window.scrollTo({top: 0, behavior: "instant"})')

        def start():
            try:
                if int(seed.value) != seed.value or int(count.value) != count.value or count.value > 1000:
                    raise ValueError('Seed and count must be integers; the interface supports up to 1000 students')
                config = Scenario(seed=int(seed.value), student_count=int(count.value), arrival_rate=float(rate.value), missing_fraction=float(missing.value)/100, fair_wait=float(fair.value))
                controller.start(config, Policy(policy.value))
                render()
            except (ValueError, TypeError, OverflowError) as exc:
                ui.notify(str(exc), type='negative')

        def pause():
            controller.toggle_pause()
            render()

        def reset():
            controller.reset()
            table.selected = []
            feedback.set_text('')
            render()

        def disrupt(kind, **kwargs):
            try:
                if kind == 'surge':
                    if int(kwargs['count']) != kwargs['count']:
                        raise ValueError('Surge count must be an integer')
                    kwargs['count'] = int(kwargs['count'])
                action = controller.disrupt(kind, **kwargs)
                text = f'Accepted {action.id} at {action.time:.2f} min.'
                feedback.set_text(text)
                ui.notify(text, type='positive')
            except (ValueError, TypeError, OverflowError) as exc:
                feedback.set_text(str(exc))
                ui.notify(str(exc), type='warning')
            render()

        def tick():
            if controller.playing:
                controller.tick(controller.generation)
                render()

        def change_speed():
            controller.speed = speed.value
            render()

        speed.on_value_change(change_speed)
        motion.on_value_change(render)
        filter_select.on_value_change(render)
        desk_select.on_value_change(render)
        service_select.on_value_change(render)
        timer = ui.timer(.25, tick)
        ui.context.client.on_delete(timer.cancel)
        render()

    ui.run(title='QueuePact · Live Admissions', host='127.0.0.1', port=port, reload=False, show=False)
