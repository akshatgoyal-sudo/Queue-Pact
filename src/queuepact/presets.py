"""Three intentional demonstrations; seed 42 throughout, no favourable-seed search."""
from dataclasses import dataclass
from .models import Scenario,Action
from .experiments import ExperimentSpec
from .actions import surge_action


@dataclass(frozen=True)
class Preset:
    name: str
    specification: ExperimentSpec
    speed: float
    observe: str


def presets():
    base=ExperimentSpec.generate(Scenario())
    return (
        Preset('Normal Admission Morning',base,5,'Original demo unchanged. Compare throughput and waiting; QueuePact is not guaranteed to win.'),
        Preset('Arrival Rush',base.with_action(surge_action(base.scenario,12,'rush',10,2)),5,'Ten extra students arrive from minute 12 to 14. Watch unfinished students and shared queues.'),
        Preset('Desk Disruption and Recovery',base.with_action(Action(10,'DOCUMENT_VERIFICATION-1','close','demo-close')).with_action(Action(25,'DOCUMENT_VERIFICATION-1','restore','demo-restore')),5,'V1 closes at minute 10 after its active service, and returns at minute 25. Watch recovery, not a promised gain.'),
    )
