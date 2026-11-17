"""Immutable, versioned inputs. Running generators are never serialized."""
from dataclasses import dataclass, asdict, replace
import hashlib
import json
from ..models import Scenario, StudentInput, Policy, Action
from ..scenarios import generate_workload
from ..engine import Engine


@dataclass(frozen=True)
class ExperimentSpec:
    scenario: Scenario
    workload: tuple[StudentInput, ...]
    actions: tuple[Action, ...] = ()
    policies: tuple[Policy, ...] = (Policy.ORDINARY, Policy.SMART)
    assumptions: tuple[str, ...] = ('No travel/setup time', 'Dedicated qualified worker per desk',
                                  'Utilization uses elapsed calendar time, including closures')
    version: int = 1

    def __post_init__(self):
        object.__setattr__(self, 'workload', tuple(self.workload))
        object.__setattr__(self, 'actions', tuple(self.actions))
        object.__setattr__(self, 'policies', tuple(Policy(p) for p in self.policies))
        object.__setattr__(self, 'assumptions', tuple(self.assumptions))
        if self.version != 1:
            raise ValueError('Unsupported experiment schema version')
        if not self.policies or len(self.workload) > 1000 or len(self.actions) > 100:
            raise ValueError('Experiments support 0–1000 students, up to 100 actions and at least one policy')
        if sum(self.scenario.counter_counts) > 40 or self.scenario.safety_limit > 10000:
            raise ValueError('Lab limit: 40 base desks and 10000 simulated minutes')
        if len(self.workload) != self.scenario.student_count:
            raise ValueError('Scenario count must match workload')
        if len({a.id for a in self.actions}) != len(self.actions) or any(not a.id for a in self.actions):
            raise ValueError('Recorded actions require unique explicit IDs')
        Engine(self.scenario, self.workload, self.policies[0], self.actions)

    @classmethod
    def generate(cls, scenario=None):
        scenario = scenario or Scenario()
        return cls(scenario, generate_workload(scenario))

    def to_json(self):
        return json.dumps(asdict(self), sort_keys=True, allow_nan=False)

    @classmethod
    def from_json(cls, value):
        data = json.loads(value)
        data['scenario'] = Scenario(**data['scenario'])
        data['workload'] = tuple(StudentInput(**s) for s in data['workload'])
        data['actions'] = tuple(Action(**a) for a in data['actions'])
        return cls(**data)

    @property
    def fingerprint(self):
        return hashlib.sha256(self.to_json().encode()).hexdigest()[:16]

    def with_action(self, action):
        return replace(self, actions=(*self.actions, action))


@dataclass(frozen=True)
class RunRecord:
    specification: ExperimentSpec
    policy: Policy
    readiness_json: str | None = None
    record_version: int = 2

    @property
    def fingerprint(self):
        return hashlib.sha256(self.to_json().encode()).hexdigest()[:16]

    @classmethod
    def capture(cls, engine):
        readiness = json.dumps(asdict(engine.readiness),sort_keys=True) if hasattr(engine,'readiness') else None
        return cls(ExperimentSpec(engine.config, engine.workload, engine.actions), engine.policy, readiness)

    def engine(self):
        s = self.specification
        if self.readiness_json is not None:
            from .readiness import ReadinessEngine, ReadinessConfig
            return ReadinessEngine(s.scenario,s.workload,self.policy,s.actions,ReadinessConfig(**json.loads(self.readiness_json)))
        return Engine(s.scenario, s.workload, self.policy, s.actions)

    def to_json(self):
        data=dict(version=self.record_version, policy=self.policy, specification=json.loads(self.specification.to_json()),readiness_json=self.readiness_json)
        if self.record_version == 2:
            data['policy_version']=Policy(self.policy).algorithm_version
        return json.dumps(data, sort_keys=True)

    @classmethod
    def from_json(cls, text):
        data = json.loads(text)
        if data['version'] not in (1,2):
            raise ValueError('Unsupported run record version')
        policy=Policy(data['policy'])
        if data['version']==1 and policy==Policy.V2:
            raise ValueError('Legacy records cannot identify v2')
        if data['version']==2 and data.get('policy_version') != policy.algorithm_version:
            raise ValueError('Unsupported policy version')
        record=cls(ExperimentSpec.from_json(json.dumps(data['specification'])), policy,data.get('readiness_json'),data['version'])
        record.engine()  # validate optional operational configuration before accepting the record
        return record
