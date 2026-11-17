import argparse
from dataclasses import asdict
import json
from pathlib import Path
from .engine import Engine
from .models import Scenario, Policy, Action
from .scenarios import load_scenario, generate_workload
from .events import events_json


def main():
    parser = argparse.ArgumentParser(description='QueuePact admission simulation')
    parser.add_argument('mode', choices=['headless', 'ui'])
    parser.add_argument('--scenario', type=Path)
    parser.add_argument('--policy', choices=['ordinary', 'smart', 'v1', 'v2', 'both'], default='both')
    parser.add_argument('--actions', type=Path, help='JSON list of time/counter_id/kind objects')
    parser.add_argument('--output', type=Path, help='Directory for events and summary JSON')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    if args.mode == 'ui':
        from .ui.app import launch
        launch(args.port)
        return
    config = load_scenario(args.scenario) if args.scenario else Scenario()
    workload = generate_workload(config)
    actions = tuple(Action(**a) for a in json.loads(args.actions.read_text())) if args.actions else ()
    policies = [Policy.ORDINARY,Policy.SMART] if args.policy == 'both' else [Policy.ORDINARY if args.policy == 'ordinary' else Policy.V2 if args.policy == 'v2' else Policy.SMART]
    results = {}
    for policy in policies:
        engine = Engine(config, workload, policy, actions)
        metrics = engine.run()
        results[policy.value] = dict(status=engine.status, time=engine.now, metrics=asdict(metrics))
        if args.output:
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / f'{policy.value}-events.json').write_text(events_json(engine.events), encoding='utf-8')
    serialized = json.dumps(results, indent=2, allow_nan=False)
    print(serialized)
    if args.output:
        (args.output / 'summary.json').write_text(serialized, encoding='utf-8')
        (args.output / 'workload.json').write_text(json.dumps([asdict(s) for s in workload], indent=2), encoding='utf-8')
        (args.output / 'actions.json').write_text(json.dumps([asdict(a) for a in engine.actions], indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
