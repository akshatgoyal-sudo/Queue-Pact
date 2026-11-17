"""Explicit persistence/export controls and historical views."""
from pathlib import Path
from html import escape
import json
from nicegui import ui,run,app
from fastapi.responses import HTMLResponse,Response
from ..archive import Evidence,MAX_BYTES,canonical
from ..repository import Repository
from ..exports import csv_zip
from ..reports import report_html


def artifact_controls(capture,parent=lambda:None,on_saved=lambda rid:None):
    frozen=None
    saved_id=None
    with ui.dialog() as dialog,ui.card().classes('qp-dialog'):
        ui.label('Save and export a frozen observation').classes('text-lg font-semibold')
        ui.label('The run may continue; every action below uses the same captured observation until you capture again.').classes('qp-footnote')
        name=ui.input('Saved name',value='Admission experiment').classes('w-full')
        caption=ui.label().classes('qp-footnote')
        with ui.row():
            ui.button('Capture again',on_click=lambda:freeze())
            ui.button('Save snapshot',on_click=lambda:save())
            ui.button('Save scenario copy',on_click=lambda:save_scenario()).props('outline')
        with ui.row():
            ui.button('Download CSV ZIP',on_click=lambda:download('csv')).props('outline')
            ui.button('Reproducibility JSON',on_click=lambda:download('json')).props('outline')
            ui.button('View report',on_click=lambda:view()).props('outline')
        ui.link('Saved runs / history','/history',new_tab=True)
        ui.button('Close',on_click=dialog.close).props('flat')

    def freeze():
        nonlocal frozen,saved_id
        try:
            frozen=capture(name.value)
            saved_id=None
            caption.set_text(f'Frozen: {frozen.data["status"]} · windows '+', '.join(f'{r["observation_min"]:.2f} min' for r in frozen.data['runs']))
        except Exception as exc:
            frozen=None
            caption.set_text(str(exc))
            ui.notify(str(exc),type='warning')

    def current():
        if frozen is None:
            raise ValueError('Capture a settled observation first')
        d=frozen.data
        if not name.value or len(name.value)>160:
            raise ValueError('Name must contain 1–160 characters')
        d['name']=name.value
        return Evidence.from_json(canonical(d))

    def save():
        nonlocal saved_id
        try:
            if saved_id is None:
                saved_id=Repository().save(current(),parent())
                on_saved(saved_id)
            caption.set_text(f'Saved immutable record {saved_id}. Change inputs and capture again to save a new version.')
            ui.notify('Saved to local history',type='positive')
            return saved_id
        except Exception as exc:
            ui.notify(str(exc),type='negative')

    def save_scenario():
        try:
            e=current().engines()[0]
            snapshot=Evidence.capture(name.value+' · scenario',[e],kind='Scenario')
            rid=Repository().save(snapshot,parent())
            caption.set_text(f'New scenario copy saved: {rid}')
        except Exception as exc:
            ui.notify(str(exc),type='negative')

    def download(kind):
        try:
            snapshot=current()
            ui.download.content(csv_zip(snapshot) if kind=='csv' else snapshot.json_text.encode('utf-8'),f'queuepact-{snapshot.data["input_id"]}.{ "zip" if kind=="csv" else "json"}')
        except Exception as exc:
            ui.notify(str(exc),type='negative')

    def view():
        rid=save()
        if rid:
            ui.navigate.to('/reports/'+rid,new_tab=True)

    def show():
        freeze()
        dialog.open()
    def renamed():
        nonlocal saved_id
        saved_id=None
    name.on_value_change(renamed)
    ui.button('Save / export',on_click=show).props('outline')


def register_history():
    @app.get('/reports/{rid}',response_class=HTMLResponse)
    def report(rid:str):
        try:
            return report_html(Repository().get(rid))
        except Exception as exc:
            return HTMLResponse('<h1>Report unavailable</h1><p>'+escape(str(exc))+'</p>',status_code=400)

    @app.get('/exports/{rid}/{format}')
    def export(rid:str,format:str):
        try:
            evidence=Repository().get(rid)
            if format not in ('json','csv'):
                raise ValueError('Choose JSON or CSV ZIP')
            return Response(evidence.json_text if format=='json' else csv_zip(evidence),media_type='application/json' if format=='json' else 'application/zip',headers={'Content-Disposition':f'attachment; filename="queuepact.{"json" if format=="json" else "zip"}"'})
        except Exception as exc:
            return Response(str(exc),status_code=400)

    @ui.page('/history')
    def history():
        ui.add_css(Path(__file__).with_name('style.css').read_text(encoding='utf-8'))
        with ui.header().classes('qp-header items-center'):
            ui.label('QueuePact · Saved history').classes('qp-logo')
            ui.space()
            ui.link('Live Operations','/').classes('text-white')
            ui.link('Comparison Lab','/lab').classes('text-white')
        with ui.column().classes('w-full p-6 gap-4'):
            ui.label('Shared saved evidence. Independent working runs.').classes('text-xl font-semibold')
            ui.label('Viewing a historical result does not verify reproducibility. Open as new creates fresh working state; saved evidence is never overwritten.').classes('qp-footnote')
            feedback=ui.label().classes('qp-footnote')
            table=ui.table(columns=[dict(name=k,label=v,field=k,align='left') for k,v in [('name','Name'),('kind','Experiment'),('created','Created UTC'),('status','Status'),('students','Students')]],rows=[],row_key='id',selection='single',pagination=10).classes('w-full qp-table')
            selected=lambda:table.selected[0]['id'] if table.selected else None
            with ui.row():
                ui.button('Refresh history',on_click=lambda:refresh())
                ui.button('View results / report',on_click=lambda:open_record('report'))
                ui.button('Open as new experiment',on_click=lambda:open_record('new'))
                ui.button('Verify reconstruction',on_click=lambda:verify()).props('outline')
                ui.button('Export CSV ZIP',on_click=lambda:open_record('csv')).props('outline')
                ui.button('Export JSON',on_click=lambda:open_record('json')).props('outline')
            async def imported(event):
                try:
                    evidence=Evidence.from_json(await event.file.read())
                    rid=await run.io_bound(lambda:Repository().save(evidence))
                    feedback.set_text(f'Imported as a new saved copy: {rid}. Historical metrics are not verified until reconstruction succeeds.')
                    refresh()
                except Exception as exc:
                    ui.notify(str(exc),type='negative')
            ui.upload(label='Import QueuePact reproducibility JSON · up to 10 MB',auto_upload=True,max_file_size=MAX_BYTES,on_upload=imported,on_rejected=lambda:ui.notify('Choose one JSON file under 10 MB',type='warning')).props('accept=.json').classes('w-full max-w-xl')
            storage=ui.label().classes('qp-footnote')

        def refresh():
            try:
                repository=Repository()
                table.rows=repository.list()
                table.selected=[]
                table.update()
                storage.set_text(f'Storage: {repository.path}. Back up the database with the app stopped, or use Repository.backup().')
                if not table.rows:
                    feedback.set_text('No saved runs yet. Use Save / export in Live Operations or the Lab.')
            except Exception as exc:
                feedback.set_text('Storage unavailable: '+str(exc))

        def open_record(mode):
            rid=selected()
            if not rid:
                ui.notify('Select a saved row first',type='warning')
                return
            ui.navigate.to('/reports/'+rid if mode=='report' else '/lab?saved='+rid if mode=='new' else '/exports/'+rid+'/'+mode,new_tab=True)

        verifying=False
        async def verify():
            nonlocal verifying
            if verifying:
                return
            rid=selected()
            if not rid:
                ui.notify('Select a saved row first',type='warning')
                return
            verifying=True
            feedback.set_text('Reconstructing from validated inputs… Historical records remain unchanged.')
            try:
                evidence=Repository().get(rid)
                matched=await run.io_bound(evidence.verify)
                feedback.set_text('Reproducibility VERIFIED: metrics and normalized event digest match.' if matched else 'Reproduction MISMATCH: historical evidence remains viewable; do not treat it as reproduced.')
            except Exception as exc:
                feedback.set_text('Cannot reproduce: '+str(exc))
            finally:
                verifying=False
        refresh()
