"""Immutable evidence envelopes. Capture never advances or reruns an engine."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import platform
from importlib.metadata import version
from .experiments.spec import RunRecord
from .experiments.results import result, series, findings
from .experiments.replay import normalized_events
from .models import RunStatus

SCHEMA = 1
ENGINE_VERSION = 'queuepact-engine-1'
APP_VERSION = '0.4.0'
MAX_BYTES = 10_000_000
KINDS = ('Single run','Policy comparison','Staffing','Branch comparison','Readiness','Scenario')
LIMITATIONS = ('Educational simulation; not validated against a real admissions institution.',
 'No guaranteed reduction in waiting. No travel, training or setup time.',
 'Queue wait excludes preparation and service. Averages and p90 cover completed visits only.',
 'P90 is nearest rank. Calendar utilization includes closures and time before added desks exist.')


def canonical(value):
    return json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':'))


def digest(value):
    def normalize(v):
        if isinstance(v,float) and v.is_integer():
            return int(v)
        if isinstance(v,dict):
            return {k:normalize(x) for k,x in v.items()}
        if isinstance(v,(list,tuple)):
            return [normalize(x) for x in v]
        return v
    return hashlib.sha256(canonical(normalize(value)).encode()).hexdigest()


@dataclass(frozen=True)
class Evidence:
    json_text: str

    @property
    def data(self):
        return json.loads(self.json_text)

    @classmethod
    def capture(cls, name, engines, labels=None, kind='Single run', settings=None, status=None):
        if not isinstance(name,str) or not name.strip() or len(name)>160:
            raise ValueError('Provide a name of 1–160 characters')
        engines=tuple(engines)
        labels=tuple(labels or [e.policy.value for e in engines])
        if kind not in KINDS or not 1<=len(engines)<=5 or len(labels)!=len(engines):
            raise ValueError('Unsupported experiment type or run count')
        runs=[]
        for label,e in zip(labels,engines):
            if e.env.peek()<=e.now and e.status not in (RunStatus.READY,RunStatus.COMPLETED):
                raise ValueError('Wait for the current event boundary to settle before saving')
            record=RunRecord.capture(e)
            students=[]
            for s in e.students.values():
                active_prep=next((e.now-event.time for event in reversed(e.events) if event.type=='preparation_started' and event.student_id==s.source.id),0) if s.status.value=='Preparing documents' else 0
                students.append(dict(student_id=s.source.id,status=s.status.value,arrival_min=s.source.arrival,
                    finished_min=s.finished_at,queue_wait_min=s.total_wait+e.current_wait(s),preparation_min=s.preparation_time+active_prep,
                    completed_tasks=sorted(s.completed),visit_min=None if s.finished_at is None else s.finished_at-s.source.arrival))
            runs.append(dict(label=label,record=json.loads(record.to_json()),input_id=record.fingerprint,
                observation_min=e.now,metrics=result(e),students=students,resources=[asdict(c) for c in e.counters.values()],
                actions=[asdict(a) for a in e.actions],series=series(e),event_digest=digest(normalized_events(e)),
                overhead=e.overhead() if hasattr(e,'overhead') else None))
        data=dict(schema=SCHEMA,engine_version=ENGINE_VERSION,app_version=APP_VERSION,
            runtime=dict(python=platform.python_version(),simpy=version('simpy'),nicegui=version('nicegui'),plotly=version('plotly')),
            created_utc=datetime.now(timezone.utc).isoformat(),name=name.strip(),kind=kind,
            status=status or ('Completed' if all(e.status==RunStatus.COMPLETED for e in engines) else 'Incomplete'),
            settings=settings or {},runs=runs,findings=findings(engines,labels) if len(engines)>1 else [],limitations=list(LIMITATIONS))
        data['input_id']=digest([r['record'] for r in runs])[:16]
        return cls(canonical(data))

    @classmethod
    def from_json(cls, text, compatible=True):
        try:
            if isinstance(text,bytes):
                text=text.decode('utf-8-sig')
            if len(text.encode('utf-8'))>MAX_BYTES:
                raise ValueError('Record exceeds the 10 MB limit')
            d=json.loads(text,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
            if not isinstance(d,dict):
                raise ValueError('A QueuePact JSON object is required')
            if d.get('schema')!=SCHEMA:
                raise ValueError('Unsupported saved-record schema')
            if compatible and d.get('engine_version')!=ENGINE_VERSION:
                raise ValueError('Incompatible engine version; historical viewing only')
            if d['kind'] not in KINDS or not isinstance(d['name'],str) or not d['name'].strip() or not 1<=len(d['name'])<=160:
                raise ValueError('Invalid experiment name or type')
            if not 1<=len(d['runs'])<=5 or not isinstance(d['settings'],dict):
                raise ValueError('Invalid run count or settings')
            for r in d['runs']:
                if not isinstance(r['label'],str) or len(r['label'])>160:
                    raise ValueError('Invalid run label')
                # Reject oversized inputs BEFORE constructing an event calendar.
                raw=r['record']['specification']
                if len(raw['workload'])>1000 or len(raw['actions'])>100 or len(r['students'])>4000 or len(r['series'])>100000:
                    raise ValueError('Record exceeds supported simulation limits')
                rec=RunRecord.from_json(canonical(r['record']))
                if r['input_id']!=rec.fingerprint:
                    raise ValueError('Run input fingerprint does not match its inputs')
                if not math.isfinite(r['observation_min']) or not 0<=r['observation_min']<=rec.specification.scenario.safety_limit:
                    raise ValueError('Invalid observation time')
                if not isinstance(r['metrics'],dict) or r['actions']!=[asdict(a) for a in rec.specification.actions]:
                    raise ValueError('Stored actions or metrics are inconsistent')
            if d['input_id']!=digest([r['record'] for r in d['runs']])[:16]:
                raise ValueError('Experiment fingerprint does not match')
            canonical(d)
            return cls(canonical(d))
        except (KeyError,TypeError,UnicodeError,RecursionError,OverflowError,json.JSONDecodeError) as exc:
            raise ValueError('Invalid QueuePact reproducibility JSON') from exc

    def engines(self):
        validated=Evidence.from_json(self.json_text).data
        return [RunRecord.from_json(canonical(r['record'])).engine() for r in validated['runs']]

    def verify(self):
        """Explicit reconstruction, separate from viewing historical evidence."""
        data=self.data
        engines=self.engines()
        for engine,stored in zip(engines,data['runs']):
            if stored['metrics']['status']!=RunStatus.READY:
                engine.advance(until=stored['observation_min'])
                if engine.status==RunStatus.STALLED:
                    engine.now=stored['observation_min']
            if json.loads(canonical(result(engine)))!=stored['metrics'] or digest(normalized_events(engine))!=stored['event_digest']:
                return False
        fresh=Evidence.capture(data['name'],engines,[r['label'] for r in data['runs']],data['kind'],data['settings'],data['status']).data
        for a,b in zip(fresh['runs'],data['runs']):
            if any(a[key]!=b[key] for key in ('students','resources','overhead','series')):
                return False
        return fresh['findings']==data['findings']
