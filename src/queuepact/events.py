from dataclasses import dataclass, asdict
import json


@dataclass(frozen=True)
class SimulationEvent:
    sequence: int
    time: float
    type: str
    student_id: str | None
    counter_id: str | None
    service: str | None
    details_json: str

    @property
    def details(self):
        return json.loads(self.details_json)

    def to_dict(self):
        data = asdict(self)
        data['details'] = data.pop('details_json')
        data['details'] = json.loads(data['details'])
        return data


def events_json(events):
    return json.dumps([e.to_dict() for e in events], indent=2, allow_nan=False)
