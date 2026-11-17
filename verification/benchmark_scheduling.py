"""Reproducible policy diagnosis; benchmark inputs independent of policies."""
import argparse,csv,json,time
from collections import Counter,defaultdict
from dataclasses import replace
from pathlib import Path
from statistics import mean
from queuepact.models import Scenario,Policy,Action,SERVICES,PREP
from queuepact.engine import Engine
from queuepact.experiments import ExperimentSpec
from queuepact.experiments.results import result,series
from queuepact.presets import presets

OUT=Path(__file__).parent/'scheduling'
FAMILIES=('light','normal','heavy','burst','verification','photo','payment','missing','closure','slowdown')
SPLITS={'development':tuple(range(100,110)),'heldout':tuple(range(200,210))}

def case(family,seed):
 c=Scenario(seed=seed)
 changes={'light':dict(arrival_rate=.3),'heavy':dict(arrival_rate=3),'burst':dict(arrival_pattern='batch'),'verification':dict(counter_counts=(1,2,2,1)),'photo':dict(counter_counts=(3,1,2,1),duration_ranges=((2,5),(3,6),(2,4),(1,2))),'payment':dict(counter_counts=(2,2,1,1),duration_ranges=((2,5),(1,3),(4,7),(1,2))),'missing':dict(missing_fraction=.8)}
 c=replace(c,**changes.get(family,{}));s=ExperimentSpec.generate(c)
 if family=='closure':s=replace(s,actions=(Action(10,'DOCUMENT_VERIFICATION-1','close','close'),Action(25,'DOCUMENT_VERIFICATION-1','restore','restore')))
 if family=='slowdown':s=replace(s,actions=tuple(Action(t,kind='slowdown',id=f'slow-{t}',payload_json=json.dumps(dict(service=SERVICES[0],multiplier=m))) for t,m in ((10,2),(30,1))))
 return s

def write(name,rows):
 OUT.mkdir(exist_ok=True);rows=list(rows)
 if rows:
  with (OUT/name).open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def run(spec,policy,engine_class=Engine):
 start=time.perf_counter();e=engine_class(spec.scenario,spec.workload,policy,spec.actions);e.run();runtime=time.perf_counter()-start
 m=result(e);return e,dict(status=m['status'],completed=m['completed'],unfinished=m['unfinished'],wait=m['average_completed_wait'],p90=m['p90_completed_wait'],maximum=m['max_completed_wait'],visit=m['average_completed_visit'],makespan=m['makespan'],runtime_seconds=runtime,fair_dispatches=sum(x.type=='fair_wait_protection' for x in e.events))

def diagnose():
 rows=[];waits=[];orders=[];students=[];queues=[];desks=[]
 for preset in presets():
  for label,policy,override in [('Ordinary',Policy.ORDINARY,None),('v1',Policy.SMART,None),('v1-no-fairness',Policy.SMART,'fair'),('v1-fixed-routing',Policy.SMART,'fixed'),('v1-prep-first',Policy.SMART,'prep'),('v1-verification-first',Policy.SMART,'verification'),('v1-mean-estimates',Policy.SMART,'means')]:
   spec=preset.specification
   if override=='fair':spec=replace(spec,scenario=replace(spec.scenario,fair_wait=1e9))
   class Fixed(Engine):
    def _candidates(self,s):return [PREP] if not s.documents_ready else [next(t for t in SERVICES if t not in s.completed)]
   class Ablation(Engine):
    def _candidates(self,s):
     if override=='prep' and not s.documents_ready:return [PREP]
     if override=='verification' and SERVICES[0] in super()._candidates(s):return [SERVICES[0]]
     return super()._candidates(s)
    def _estimate(self,s,t):
     if override=='means':
      from queuepact.policies.v2 import estimate
      return estimate(self,s,t)
     return super()._estimate(s,t)
   e,m=run(spec,policy,Fixed if override=='fixed' else Ablation);rows.append(dict(preset=preset.name,policy=label,**m))
   byservice=defaultdict(float);order=defaultdict(list);verified={};changed=0
   for ev in e.events:
    d=json.loads(ev.details_json)
    if ev.type=='queue_exited':byservice[ev.service]+=d['wait']
    if ev.type=='service_started':order[ev.student_id].append(ev.service)
    if ev.type=='service_completed' and ev.service==SERVICES[0]:verified[ev.student_id]=ev.time
    if ev.type=='fair_wait_protection' and d['queue_order'][0]!=ev.student_id:changed+=1
   rows[-1]['fair_changed_order']=changed
   waits.extend(dict(preset=preset.name,policy=label,service=k,total_wait_min=v) for k,v in byservice.items())
   orders.extend(dict(preset=preset.name,policy=label,task_order=' > '.join(k),count=v) for k,v in Counter(tuple(v) for v in order.values()).items())
   students.extend(dict(preset=preset.name,policy=label,student=s.source.id,arrival=s.source.arrival,verification=verified.get(s.source.id),finished=s.finished_at) for s in e.students.values())
   queues.extend(dict(preset=preset.name,policy=label,**r) for r in series(e))
   desks.extend(dict(preset=preset.name,policy=label,desk=k,utilization=v) for k,v in e.metrics().counter_utilization)
 for name,data in [('diagnosis',rows),('service-waits',waits),('task-orders',orders),('student-times',students),('queue-growth',queues),('utilization',desks)]:write(name+'.csv',data)
 print(json.dumps(rows,indent=2))


def benchmark(split):
 rows=[]
 for family in FAMILIES:
  for seed in SPLITS[split]:
   spec=case(family,seed)
   choices=[('Ordinary',Policy.ORDINARY,Engine),('v1',Policy.SMART,Engine),('v2',Policy.V2,Engine)]
   if split=='development':
    class FactorTwo(Engine):v2_factor=2.0
    choices.append(('candidate-2',Policy.V2,FactorTwo))
   for label,policy,cls in choices:
    e,m=run(spec,policy,cls);rows.append(dict(family=family,seed=seed,policy=label,input_id=spec.fingerprint,**m))
 write(split+'.csv',rows)
 summary=[]
 for family in (*FAMILIES,'ALL'):
  for policy in sorted({r['policy'] for r in rows}):
   rr=[r for r in rows if r['policy']==policy and (family=='ALL' or r['family']==family)]
   summary.append(dict(family=family,policy=policy,completed_runs=sum(r['unfinished']==0 for r in rr),runs=len(rr),**{key:mean(r[key] for r in rr) if all(r[key] is not None and (key=='runtime_seconds' or r['status']=='Completed') for r in rr) else None for key in ('wait','p90','maximum','visit','makespan','runtime_seconds')}))
 write(split+'-summary.csv',summary)
 print(json.dumps([r for r in summary if r['family']=='ALL'],indent=2))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['diagnose','development','heldout'],default='diagnose');a=parser.parse_args()
 diagnose() if a.mode=='diagnose' else benchmark(a.mode)

