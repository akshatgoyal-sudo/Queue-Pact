"""One session's controls. No browser or NiceGUI dependency."""
import json
import time
from ..engine import Engine
from ..models import Scenario, Policy, RunStatus, Action
from ..actions import surge_action


class Controller:
    def __init__(self, config=None, policy=Policy.ORDINARY):
        self.engine = Engine(config or Scenario(), policy=policy)
        self.started = self.playing = False
        self.speed = 1
        self.selected = None
        self.generation = 0
        self._last_click = {}

    def start(self, config=None, policy=None):
        if self.started:
            return
        self.engine = Engine(config or self.engine.config, policy=policy or self.engine.policy)
        self.started = self.playing = True
        self.generation += 1
        self.engine.advance(until=0)
        self._stop_if_needed()

    def reset(self):
        self.engine = Engine(self.engine.config, self.engine.workload, self.engine.policy)
        self.started = self.playing = False
        self.selected = None
        self._last_click.clear()
        self.generation += 1

    def _stop_if_needed(self):
        if self.engine.status in (RunStatus.COMPLETED, RunStatus.LIMIT, RunStatus.STALLED):
            self.playing = False

    def tick(self, generation=None):
        if generation is not None and generation != self.generation:
            return
        if self.playing:
            self.engine.advance(until=self.engine.now + .25*self.speed)
            self._stop_if_needed()

    def toggle_pause(self):
        if self.started and self.engine.status in (RunStatus.RUNNING, RunStatus.STALLED):
            self.playing = not self.playing

    def select(self, sid):
        if sid in self.engine.students:
            self.selected = sid

    def disrupt(self, kind, *, counter_id='', service=None, multiplier=1, count=5, interval=2, now_wall=None):
        if not self.started or self.engine.status in (RunStatus.COMPLETED, RunStatus.LIMIT):
            raise ValueError('Start a run first, or reset the completed run')
        # Reject rapid repeats at the intent boundary, in addition to engine action-ID validation.
        wall = time.monotonic() if now_wall is None else now_wall
        key = (kind, counter_id, service, multiplier, count, interval)
        if wall-self._last_click.get(key, float('-inf')) < .7:
            raise ValueError('That action was just accepted; wait a moment before repeating it')
        aid = f'A{len(self.engine.actions)+1:04}'
        if kind == 'surge':
            action = surge_action(self.engine.config, self.engine.now, aid, count, interval, at_boundary=True)
        else:
            payload = dict(service=service, multiplier=multiplier) if kind == 'slowdown' else {}
            action = Action(self.engine.now, counter_id, kind, aid, json.dumps(payload), True)
        accepted = self.engine.apply_action(action)
        self._last_click[key] = wall
        self.engine.advance(until=self.engine.now)
        self._stop_if_needed()
        return accepted
