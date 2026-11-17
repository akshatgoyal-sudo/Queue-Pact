import json
from dataclasses import replace
from pathlib import Path
import pytest
from queuepact.models import Policy,Scenario,StudentInput,SERVICES,PREP,Action
from queuepact.engine import Engine
from queuepact.experiments import RunRecord,ExperimentSpec,PairedRun
from queuepact.experiments.replay import normalized_events,branches
from queuepact.experiments.staffing import staff_action,StaffConstraints
from queuepact.actions import surge_action
from queuepact.archive import Evidence
from queuepact.reports import report_html
from queuepact.policies.v2 import score
from test_engine import assert_invariants


def test_legacy_record_identity_and_events():
 e=Engine(Scenario(),policy=Policy.SMART);e.run()
 legacy=RunRecord(ExperimentSpec(e.config,e.workload,e.actions),Policy.SMART,record_version=1)
 raw=legacy.to_json();r=RunRecord.from_json(raw)
 assert r.to_json()==raw and r.policy==Policy.SMART
 restored=r.engine();restored.run()
 assert normalized_events(restored)==normalized_events(e)
 assert e.metrics().average_completed_wait==pytest.approx(27.550247834566743)
 assert Policy('QueuePact')==Policy.SMART


def test_existing_export_still_verifies():
 old=Path('verification/phase4-browser/download.json')
 assert old.exists()
 assert Evidence.from_json(old.read_text(encoding='utf-8')).verify()


def test_version_validation():
 e=Engine(Scenario(),policy=Policy.V2);r=RunRecord.capture(e);d=json.loads(r.to_json())
 assert d['version']==2 and d['policy_version']==2
 d['policy_version']=1
 with pytest.raises(ValueError,match='policy version'):RunRecord.from_json(json.dumps(d))
 d['version']=1
 with pytest.raises(ValueError,match='Legacy'):RunRecord.from_json(json.dumps(d))


@pytest.mark.parametrize('budget',[1,17,10000])
def test_v2_disruptions_invariants_and_reproduction(budget):
 spec=ExperimentSpec.generate(Scenario(student_count=12,missing_fraction=.8))
 actions=(Action(2,'DOCUMENT_VERIFICATION-1','close','c'),Action(9,'DOCUMENT_VERIFICATION-1','restore','r'),Action(3,kind='slowdown',id='slow',payload_json=json.dumps(dict(service=SERVICES[1],multiplier=2))),surge_action(spec.scenario,5,'surge',3,1),staff_action(Engine(spec.scenario,spec.workload),SERVICES[0],4))
 e=Engine(spec.scenario,spec.workload,Policy.V2,actions)
 while e.status not in ('Completed','Safety limit reached','Stalled'):
  e.advance(max_events=budget);assert_invariants(e)
 assert e.status=='Completed' and len(e.students)==15
 other=Engine(spec.scenario,spec.workload,Policy.V2,actions);other.run()
 assert normalized_events(e)==normalized_events(other)
 assert e.metrics()==other.metrics()
 assert Evidence.capture('v2', [e]).verify()


def test_recorded_scores_and_ties():
 e=Engine(Scenario(student_count=2,missing_fraction=0),policy=Policy.V2);e.run()
 for ev in e.events:
  if ev.type!='routing_decision':continue
  options=ev.details['candidates']
  for o in options:
   assert o['score']==pytest.approx(o['estimate']+o['prerequisite_penalty'])
   assert o['information']=='configured_mean'
  winner=min(options,key=lambda o:(o['score'],(*SERVICES,PREP).index(o['task'])))
  assert winner['task']==ev.service
 options=[dict(task=SERVICES[0],duration=3,estimate=5),dict(task=SERVICES[1],duration=2,estimate=2)]
 score(options);assert options[0]['score']==options[1]['score'] # stable service order favours verification


def test_v2_short_photo_fills_large_current_wait():
 c=Scenario(student_count=2,missing_fraction=0,counter_counts=(1,1,1,1),duration_ranges=((10,10),(1,1),(2,2),(1,1)))
 w=(StudentInput('A',0,(10,1,2,1),True,2),StudentInput('B',1,(10,1,2,1),True,2))
 e=Engine(c,w,Policy.V2);e.advance(until=1)
 assert e.students['B'].task==SERVICES[1]
 assert next(x for x in e.events if x.type=='routing_decision' and x.student_id=='B').details['rule']=='prerequisite_head_start_estimated'


def test_no_future_or_individual_duration_knowledge():
 c=Scenario(student_count=2,missing_fraction=0)
 w=(StudentInput('A',0,(3,2,3,1),True,4),StudentInput('B',100,(3,2,3,1),True,4))
 a=Engine(c,w,Policy.V2)
 b=Engine(c,(replace(w[0],durations=(99,99,99,99)),replace(w[1],arrival=200)),Policy.V2,(Action(50,'DOCUMENT_VERIFICATION-1','close','future'),))
 a.advance(until=0);b.advance(until=0)
 assert [e.details for e in a.events if e.type=='routing_decision']==[e.details for e in b.events if e.type=='routing_decision']
 assert a._estimate(a.students['A'],SERVICES[0])==b._estimate(b.students['A'],SERVICES[0])


def test_missing_prepares_and_closed_capacity_unavailable():
 e=Engine(Scenario(student_count=1,missing_fraction=1,counter_counts=(0,1,1,1)),policy=Policy.V2)
 e.advance(until=0)
 assert e.students['S0001'].task==PREP
 e.run();assert e.status=='Stalled'
 assert e._estimate(e.students['S0001'],SERVICES[0])['estimate'] is None


def test_two_policy_pair_export_and_branch():
 spec=replace(ExperimentSpec.generate(Scenario(student_count=5)),policies=(Policy.SMART,Policy.V2))
 pair=PairedRun(spec).run();saved=Evidence.capture('Versions',pair.engines)
 assert saved.verify() and 'QueuePact v2 (experimental)' in report_html(saved)
 loaded=saved.engines();assert [e.policy for e in loaded]==[Policy.SMART,Policy.V2]
 branch=branches(RunRecord.capture(pair.engines[1]),0);branch.run()
 assert all(e.policy==Policy.V2 for e in branch.engines)
 assert normalized_events(branch.engines[0])==normalized_events(pair.engines[1])


def test_benchmark_split_and_inputs():
 import importlib.util
 location=Path('verification/benchmark_scheduling.py')
 module_spec=importlib.util.spec_from_file_location('benchmark',location);m=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(m)
 assert set(m.SPLITS['development']).isdisjoint(m.SPLITS['heldout'])
 for family in m.FAMILIES:
  spec=m.case(family,100)
  engines=[Engine(spec.scenario,spec.workload,p,spec.actions) for p in Policy]
  assert all(e.workload is spec.workload and e.actions==spec.actions for e in engines)

def test_wait_accounting_matches_event_segments_and_visit_identity():
 for p in Policy:
  e=Engine(Scenario(student_count=8,missing_fraction=.8),policy=p);e.run()
  assert sum(x.details['wait'] for x in e.events if x.type=='queue_exited')==pytest.approx(e.metrics().total_queue_wait)
  for s in e.students.values():
   actual_service=sum(x.details['duration'] for x in e.events if x.student_id==s.source.id and x.type=='service_started')
   assert s.finished_at-s.source.arrival==pytest.approx(s.total_wait+s.preparation_time+actual_service)


def test_estimated_free_desk_is_not_averaged_with_busy_desk():
 c=Scenario(student_count=1,missing_fraction=0,duration_ranges=((10,10),)*4)
 a=Engine(c,policy=Policy.SMART);b=Engine(c,policy=Policy.V2)
 for e in (a,b):
  desk=e.counters['DOCUMENT_VERIFICATION-1'];desk.student_id='occupant';desk.started_at=0;desk.finishes_at=10
 assert a._estimate(a.students['S0001'],SERVICES[0])['estimate']==15
 assert b._estimate(b.students['S0001'],SERVICES[0])['estimate']==10


def test_v2_csv_and_explanation_identify_actual_rule():
 import csv,io,zipfile
 from queuepact.exports import csv_zip
 from queuepact.presenters import describe_event
 e=Engine(Scenario(student_count=2),policy=Policy.V2);e.run()
 artifact=Evidence.capture('version',[e])
 with zipfile.ZipFile(io.BytesIO(csv_zip(artifact))) as z:
  rows=list(csv.DictReader(io.StringIO(z.read('metrics.csv').decode('utf-8-sig'))))
 assert all(r['policy_version']=='2' and r['policy_identifier']=='QueuePact v2' for r in rows)
 ev=next(x for x in e.events if x.type=='routing_decision')
 assert 'prerequisite head-start' in describe_event(ev)
 assert 'Lowest next-activity estimate' not in describe_event(ev)
