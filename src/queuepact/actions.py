"""Complete, deterministic external-action inputs. No UI or global randomness."""
from dataclasses import asdict
import hashlib
import json
import random
import re
from .models import Action, StudentInput


def surge_action(config, time, action_id, count=5, interval=2, *, at_boundary=False):
    if type(count) is not int or not 1 <= count <= 30:
        raise ValueError('A surge must contain 1–30 students')
    if not isinstance(interval, (int, float)) or not 0 <= interval <= 10:
        raise ValueError('Surge interval must be between 0 and 10 minutes')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', action_id):
        raise ValueError('Action ID must contain 1–40 letters, numbers, dashes or underscores')
    seed = int.from_bytes(hashlib.sha256(f'{config.seed}:{action_id}'.encode()).digest(), 'big')
    rng = random.Random(seed)
    students = tuple(StudentInput(f'G-{action_id}-{i+1:02}', time + (interval*i/(count-1) if count > 1 else 0),
        tuple(rng.uniform(*r) for r in config.duration_ranges), rng.random() >= config.missing_fraction,
        rng.uniform(*config.preparation_range)) for i in range(count))
    return Action(time, kind='surge', id=action_id, at_boundary=at_boundary,
        payload_json=json.dumps(dict(interval=interval, students=[asdict(s) for s in students]), allow_nan=False))
