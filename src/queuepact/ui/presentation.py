"""Presentation captions do not drive simulation events."""
from nicegui import ui
from ..presets import presets
from ..engine import Engine
from ..models import RunStatus

GUIDE=(
 '1 · Workflow: verification needs ready documents; payment follows verification; enrollment needs verification, photo and payment.',
 '2 · Load a prepared scenario and Start demo. All service requirements were generated before the run.',
 '3 · Follow one student. Queue wait, preparation and service are separate parts of their visit.',
 '4 · Observe the scheduled surge or desk closure. These are real engine actions, not presentation effects.',
 '5 · Inspect the current congestion hotspot and students still in the process. A hotspot is an observable indicator.',
 '6 · Open the same preset in Comparison Lab; inspect its two policies or test one additional staff placement.',
 '7 · Run to results and use Save / export. Discuss measured trade-offs, then open the printable report.',
)


def presentation_controls(controller,render):
    demos=presets()
    step=0
    loaded=None
    with ui.expansion('Prepared demos & presentation mode').classes('qp-demo w-full bg-white rounded-xl'):
        with ui.row().classes('w-full items-center'):
            choice=ui.select({i:d.name for i,d in enumerate(demos)},value=0,label='Prepared scenario').classes('w-72')
            ui.button('Load preset',on_click=lambda:request_load(False)).props('outline')
            ui.button('Start demo',on_click=lambda:start_demo())
            ui.button('Reset Demo',on_click=lambda:load(False)).props('flat')
            mode=ui.switch('Presentation mode',on_change=lambda:ui.run_javascript('document.body.classList.toggle("qp-present", '+str(bool(mode.value)).lower()+')'))
            async def fullscreen():
                ok=await ui.run_javascript('''return (async()=>{try{if(document.fullscreenElement){await document.exitFullscreen();return true;}if(!document.fullscreenEnabled)return false;await document.documentElement.requestFullscreen();return true;}catch{return false;}})()''')
                if not ok:
                    ui.notify('Fullscreen is unavailable in this browser surface; maximize the browser window instead.',type='info')
            ui.button('Fullscreen / exit',on_click=fullscreen).props('flat')
        caption=ui.label(GUIDE[0]).classes('qp-guide')
        observation=ui.label(demos[0].observe).classes('qp-footnote')
        with ui.row():
            ui.button('Previous caption',on_click=lambda:move(-1)).props('flat')
            ui.button('Next caption',on_click=lambda:move(1)).props('flat')
            ui.button('Follow one student',on_click=lambda:follow()).props('outline')
            ui.button('Open preset comparison',on_click=lambda:ui.navigate.to('/lab?preset='+str(choice.value),new_tab=True)).props('outline')
        ui.label('Captions never apply actions. Scheduled actions run once on simulated time. Reset Demo preserves saved history.').classes('qp-footnote')
    with ui.dialog() as confirm,ui.card().classes('qp-dialog'):
        ui.label('Replace the current working run?').classes('text-lg')
        ui.label('Unsaved live progress will be replaced by the selected preset. Saved history is preserved.')
        ui.button('Replace with preset',on_click=lambda:confirmed())
        ui.button('Keep current run',on_click=confirm.close).props('flat')
    pending_start=False
    with ui.row().classes('qp-present-only w-full items-center gap-2'):
        compact=ui.label(GUIDE[0]).classes('grow text-sm')
        ui.button('Back',on_click=lambda:move(-1)).props('flat dense')
        ui.button('Next',on_click=lambda:move(1)).props('flat dense')
        ui.button('Follow student',on_click=lambda:follow()).props('outline dense')
        ui.button('Fullscreen',on_click=fullscreen).props('flat dense')
        ui.button('Exit presentation',on_click=lambda:mode.set_value(False)).props('outline dense')

    def load(play):
        nonlocal loaded,step
        demo=demos[choice.value]
        s=demo.specification
        controller.engine=Engine(s.scenario,s.workload,controller.engine.policy,s.actions)
        controller.started=True
        controller.playing=play
        controller.selected=None
        controller.generation+=1
        controller._last_click.clear()
        controller.speed=demo.speed
        controller.engine.advance(until=0)
        loaded=choice.value
        step=0
        caption.set_text(GUIDE[0]);compact.set_text(GUIDE[0])
        observation.set_text(demo.observe)
        render()

    def request_load(play):
        nonlocal pending_start
        pending_start=play
        if controller.started:
            confirm.open()
        else:
            load(play)

    def confirmed():
        load(pending_start)
        confirm.close()

    def start_demo():
        if loaded==choice.value and controller.started and controller.engine.status==RunStatus.RUNNING:
            controller.playing=True
            render()
        else:
            request_load(True)

    def move(delta):
        nonlocal step
        step=max(0,min(len(GUIDE)-1,step+delta))
        caption.set_text(GUIDE[step])
        compact.set_text(GUIDE[step])

    def follow():
        arrived=[s for s in controller.engine.students.values() if s.source.arrival<=controller.engine.now]
        if not controller.started or not arrived:
            ui.notify('Start the demo first',type='info')
            return
        controller.select(arrived[0].source.id)
        render()
