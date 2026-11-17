import csv
import io
import json
import sqlite3
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import pytest
from queuepact.archive import Evidence,canonical,MAX_BYTES
from queuepact.repository import Repository,database_path
from queuepact.exports import csv_zip,csv_bytes
from queuepact.reports import report_html
from queuepact.presets import presets
from queuepact.engine import Engine
from queuepact.models import Policy,RunStatus,Action
from queuepact.experiments import PairedRun,RunRecord
from queuepact.experiments.readiness import readiness_pair
from queuepact.experiments.staffing import StaffTrial
from queuepact.experiments.replay import branches
from queuepact.ui.controller import Controller
from test_engine import config,student


def evidence(complete=True,name='Test, "admissions"'):
    e=Engine(config(2),(student('A'),student('B',ready=False)))
    e.run() if complete else e.advance(until=1)
    return Evidence.capture(name,[e]),e


def test_sqlite_restart_roundtrip_and_parent_versions(tmp_path):
    path=tmp_path/'archive.sqlite3'
    repo=Repository(path)
    s,_=evidence()
    rid=repo.save(s)
    again=Repository(path)
    assert again.get(rid)==s
    copy=again.save(s,parent_id=rid)
    assert copy!=rid and len(again.list())==2
    assert next(r for r in again.list() if r['id']==copy)['parent_id']==rid
    assert again.get(rid)==s


def test_concurrent_parameterized_saves_and_backup(tmp_path):
    repo=Repository(tmp_path/'archive.sqlite3')
    s,_=evidence(name="Robert'); DROP TABLE records;--")
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids=list(pool.map(lambda _:repo.save(s),range(8)))
    assert len(set(ids))==8 and len(repo.list())==8
    repo.backup(tmp_path/'backup.sqlite3')
    assert len(Repository(tmp_path/'backup.sqlite3').list())==8


def test_loaded_working_copies_are_independent(tmp_path):
    s,_=evidence()
    repo=Repository(tmp_path/'db.sqlite3')
    rid=repo.save(s)
    a,b=repo.get(rid).engines()[0],repo.get(rid).engines()[0]
    a.advance(until=1)
    assert b.status==RunStatus.READY and b.now==0 and not b.events
    assert repo.get(rid)==s


def test_immutable_capture_does_not_advance_and_keeps_observation():
    s,e=evidence(False)
    before=e.events,e.now
    second=Evidence.capture('another',[e])
    assert (e.events,e.now)==before
    data=s.data
    data['runs'][0]['metrics']['completed']=999
    e.run()
    assert s.data['runs'][0]['metrics']['completed']==0
    assert s.data['runs'][0]['observation_min']==1
    assert s.verify() and second.verify()


@pytest.mark.parametrize('field,value',[('schema',999),('engine_version','future-engine')])
def test_import_rejects_incompatible(field,value):
    s,_=evidence()
    d=s.data;d[field]=value
    with pytest.raises(ValueError,match='Unsupported|Incompatible'):
        Evidence.from_json(canonical(d))
    if field=='engine_version':
        assert 'Historical evidence' in report_html(Evidence.from_json(canonical(d),compatible=False))


@pytest.mark.parametrize('value',[b'not json',b'{"schema":NaN}',b'{"schema":1}',b'x'*(MAX_BYTES+1)],ids=['invalid','nonfinite','missing','oversized'])
def test_json_invalid_size_and_content(value):
    with pytest.raises(ValueError):
        Evidence.from_json(value)


def test_input_tamper_rejected_and_results_not_silently_trusted():
    s,_=evidence()
    d=s.data;d['runs'][0]['record']['specification']['scenario']['seed']=9
    with pytest.raises(ValueError,match='fingerprint'):
        Evidence.from_json(canonical(d))
    d=s.data;d['runs'][0]['metrics']['total_queue_wait']=999
    historical=Evidence.from_json(canonical(d))
    assert not historical.verify()


def test_csv_precision_quoting_and_formula_safety():
    s,_=evidence(name='=SUM(A1:A2)')
    d=s.data;d['runs'][0]['label']='=formula, "x"\nnext'
    z=zipfile.ZipFile(io.BytesIO(csv_zip(Evidence(canonical(d)))))
    metrics=list(csv.DictReader(io.StringIO(z.read('metrics.csv').decode('utf-8-sig'))))
    row=next(r for r in metrics if r['metric']=='average_completed_wait')
    assert row['run']=="'=formula, \"x\"\nnext"
    assert float(row['value'])==s.data['runs'][0]['metrics']['average_completed_wait']
    raw=csv_bytes([dict(text='\tbad',value=-2.75,missing=None)],['text','value','missing']).decode('utf-8-sig')
    parsed=list(csv.DictReader(io.StringIO(raw)))[0]
    assert parsed==dict(text="'\tbad",value='-2.75',missing='')


def test_report_metrics_incomplete_populations_and_safe_html():
    s,e=evidence(False,name='<script>alert(1)</script>')
    html=report_html(s)
    assert 'INCOMPLETE OBSERVATION' in html and 'Students still in the process' in html
    assert '<script>alert' not in html and '&lt;script&gt;' in html
    assert 'Print / Save as PDF' in html and '@page{size:A4' in html
    assert '<svg' in html and 'https://' not in html
    assert s.data['runs'][0]['metrics']['total_queue_wait']==e.metrics().total_queue_wait
    assert s.data['runs'][0]['students'][1]['preparation_min']==1


@pytest.mark.parametrize('preset_index',[0,1,2])
def test_preset_determinism_and_exported_reconstruction(preset_index):
    a,b=presets()[preset_index],presets()[preset_index]
    assert a==b
    pair=PairedRun(a.specification).run()
    s=Evidence.capture(a.name,pair.engines,pair.labels,'Policy comparison',status=pair.status)
    assert Evidence.from_json(s.json_text).verify()
    assert pair.engines[0].workload==presets()[0].specification.workload


@pytest.mark.parametrize('kind',['Staffing','Readiness','Branch comparison'])
def test_all_experiment_evidence_and_reports(kind):
    spec=presets()[0].specification
    settings={}
    if kind=='Staffing':
        trial=StaffTrial(RunRecord(spec,Policy.ORDINARY),horizon=20)
        pair=trial.pair
        settings={'horizon':20,'staff_outcomes':trial.outcomes()}
    elif kind=='Readiness':
        pair=readiness_pair(spec,Policy.ORDINARY,1,.5,.75,horizon=20)
    else:
        pair=branches(RunRecord(spec,Policy.ORDINARY),10,Action(10,'DOCUMENT_VERIFICATION-1','close','branch'))
        settings={'turning_point':10}
    pair.run()
    s=Evidence.capture(kind,pair.engines,pair.labels,kind,settings,pair.status)
    assert s.verify()
    html=report_html(s)
    if kind=='Readiness':
        assert 'not a resource-equal' in html and 'Screening busy min' in html
    if kind=='Staffing':
        assert 'Best among tested candidates' in html
    if kind=='Branch comparison':
        assert 'Turning point' in html


def test_demo_reset_preserves_saved_history(tmp_path):
    repo=Repository(tmp_path/'archive.sqlite3')
    s,_=evidence()
    rid=repo.save(s)
    c=Controller()
    c.start();c.reset();c.start();c.reset()
    assert repo.get(rid)==s and len(repo.list())==1


def test_database_location_independent_of_cwd(tmp_path,monkeypatch):
    monkeypatch.delenv('QUEUEPACT_DB',raising=False)
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    expected=tmp_path/'QueuePact'/'queuepact.sqlite3'
    monkeypatch.chdir(tmp_path)
    assert database_path()==expected
    monkeypatch.setenv('QUEUEPACT_DB','relative.sqlite3')
    with pytest.raises(ValueError,match='absolute'):
        database_path()


def test_unknown_database_schema_rejected(tmp_path):
    path=tmp_path/'bad.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA user_version=99')
    with pytest.raises(ValueError,match='Unsupported'):
        Repository(path)


def test_student_export_tampering_fails_reproduction():
    s,_=evidence()
    d=s.data;d['runs'][0]['students'][0]['queue_wait_min']=123
    assert not Evidence.from_json(canonical(d)).verify()
    with pytest.raises(ValueError,match='object'):
        Evidence.from_json('[]')


def test_csv_count_units_and_empty_hall_coordinates():
    from queuepact.ui.hall import AdmissionHall
    s,_=evidence(False)
    with zipfile.ZipFile(io.BytesIO(csv_zip(s))) as z:
        rows=list(csv.DictReader(io.StringIO(z.read('metrics.csv').decode('utf-8-sig'))))
    assert next(r for r in rows if r['metric']=='waiting')['unit']=='count'
    assert next(r for r in rows if r['metric']=='total_queue_wait')['unit']=='student-minutes'
    assert AdmissionHall.empty_model()['height']>133
