"""Reproducible headless acceptance evidence, not a user-facing report exporter."""
import json
from pathlib import Path
from queuepact.models import Policy
from queuepact.experiments import ExperimentSpec, PairedRun, RunRecord
from queuepact.experiments.replay import branches, normalized_events
from queuepact.experiments.staffing import StaffTrial
from queuepact.experiments.results import result, findings
from queuepact.experiments.readiness import readiness_pair


def main():
    spec=ExperimentSpec.generate()
    pair=PairedRun(spec).run()
    staff=StaffTrial(RunRecord(spec,Policy.ORDINARY),horizon=60)
    staff.pair.run()
    ready=readiness_pair(spec,Policy.ORDINARY,1,.5,.75).run()
    for e in pair.engines:
        reconstructed=branches(RunRecord.capture(e),10).run()
        assert all(normalized_events(r)==normalized_events(e) and r.metrics()==e.metrics() for r in reconstructed.engines)
    output=dict(fingerprint=spec.fingerprint,comparison={label:result(e) for label,e in zip(pair.labels,pair.engines)},
                findings=findings(pair.engines,pair.labels),staff=staff.outcomes(),selected_staff=staff.placements[staff.selected_index],
                readiness={label:dict(metrics=result(e),overhead=e.overhead()) for label,e in zip(ready.labels,ready.engines)},
                unchanged_continuations='exact normalized events and metrics match')
    path=Path(__file__).with_name('phase3-results.json')
    path.write_text(json.dumps(output,indent=2,allow_nan=False),encoding='utf-8')
    print(path)
    print('\n'.join(output['findings']))


if __name__=='__main__':
    main()
