"""Headless archive/preset acceptance evidence. Does not change demo inputs."""
from pathlib import Path
import json
from queuepact.archive import Evidence
from queuepact.repository import Repository
from queuepact.presets import presets
from queuepact.experiments import PairedRun,RunRecord
from queuepact.experiments.staffing import StaffTrial
from queuepact.experiments.readiness import readiness_pair
from queuepact.experiments.replay import branches
from queuepact.models import Policy,Action


def prepare(database):
    repository=Repository(database)
    reports={};outcomes={}
    for demo in presets():
        pair=PairedRun(demo.specification).run()
        snapshot=Evidence.capture(demo.name,pair.engines,pair.labels,'Policy comparison',dict(horizon=None,preset=demo.name),pair.status)
        assert snapshot.verify()
        rid=repository.save(snapshot)
        reports[demo.name]=rid
        outcomes[demo.name]=[{k:r['metrics'][k] for k in ('completed','unfinished','average_completed_wait','p90_completed_wait','makespan')} for r in snapshot.data['runs']]
    spec=presets()[0].specification
    record=RunRecord(spec,Policy.ORDINARY)
    e=record.engine();e.advance(until=15)
    reports['Single run']=repository.save(Evidence.capture('Incomplete live observation',[e]))
    trial=StaffTrial(record,horizon=60);trial.pair.run()
    reports['Staffing']=repository.save(Evidence.capture('One additional worker',trial.pair.engines,trial.pair.labels,'Staffing',dict(horizon=60,staff_outcomes=trial.outcomes(),selected_index=trial.selected_index,objective='Most completed visits, then least all-student accrued wait, then service order'),trial.pair.status))
    ready=readiness_pair(spec,Policy.ORDINARY,1,.5,.75).run()
    reports['Readiness']=repository.save(Evidence.capture('Early screening and late discovery',ready.engines,ready.labels,'Readiness',dict(horizon=None),ready.status))
    branch=branches(record,10,Action(10,'DOCUMENT_VERIFICATION-1','close','report-branch')).run()
    reports['Branch comparison']=repository.save(Evidence.capture('Turning point at minute 10',branch.engines,branch.labels,'Branch comparison',dict(turning_point=10,intervention='Close V1; active service finishes'),branch.status))
    for rid in reports.values():
        assert repository.get(rid).verify()
    return reports,outcomes


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    reports,outcomes=prepare(root/'.local'/'phase4-evidence.sqlite3')
    target=root/'verification'/'phase4-results.json'
    target.write_text(json.dumps(dict(reports=reports,outcomes=outcomes),indent=2),encoding='utf-8')
    print(json.dumps(outcomes,indent=2))
