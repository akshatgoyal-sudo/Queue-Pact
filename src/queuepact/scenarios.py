from dataclasses import asdict
import json
import random
from .models import Scenario, StudentInput


def generate_workload(config: Scenario) -> tuple[StudentInput, ...]:
    rng = random.Random(config.seed)
    arrival = 0.0
    students = []
    for i in range(config.student_count):
        if i and config.arrival_pattern != 'batch':
            arrival += rng.expovariate(config.arrival_rate) if config.arrival_pattern == 'poisson' else 1 / config.arrival_rate
        students.append(StudentInput(f'S{i+1:04}', arrival,
            tuple(rng.uniform(*r) for r in config.duration_ranges),
            rng.random() >= config.missing_fraction, rng.uniform(*config.preparation_range)))
    return tuple(students)


def scenario_json(config):
    return json.dumps(asdict(config), indent=2, allow_nan=False)


def load_scenario(path):
    with open(path, encoding='utf-8') as f:
        return Scenario(**json.load(f))
