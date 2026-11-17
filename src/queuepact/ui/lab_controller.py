"""Session-local playback/job state; generation tokens discard obsolete jobs."""
from ..experiments import ExperimentSpec, PairedRun, RunRecord
from ..experiments.readiness import readiness_pair


class LabController:
    def __init__(self):
        self.generation = 0
        self.reset()

    def reset(self):
        if getattr(self, 'pair', None):
            self.pair.cancel()
        self.generation += 1
        self.pair = None
        self.trial = None
        self.playing = False
        self.fast = False
        self.busy = False
        self.speed = 5
        self.sources = {}
        self.source_parents={}
        self.selected = None
        self.error = None
        self.last_action = None
        self.parent_id=None
        self.loaded_kind=None
        self.experiment_settings={}

    def begin(self):
        if self.busy or (self.pair and not self.pair.done and self.playing):
            raise ValueError('Pause or finish the current experiment first')
        self.remember()
        self.generation += 1
        self.busy = True
        return self.generation

    def install(self, pair, generation, trial=None):
        if generation != self.generation:
            return False
        self.pair = pair
        self.trial = trial
        self.busy = False
        self.playing = True
        self.fast = False
        self.error = None
        return True

    def remember(self):
        if self.pair:
            for label, engine in zip(self.pair.labels, self.pair.engines):
                key=f'{label} · run {self.generation}'
                self.sources[key] = RunRecord.capture(engine)
                self.source_parents[key]=self.parent_id
            # bounded session history; no mutable engines are retained
            self.sources = dict(list(self.sources.items())[-12:])
            self.source_parents={k:self.source_parents[k] for k in self.sources}

    def tick(self, generation=None):
        if generation is not None and generation != self.generation:
            return False
        if not self.pair or (not self.playing and self.pair.target is None) or self.busy:
            return False
        settled = self.pair.step(.25*self.speed, budget=200, results=self.fast)
        if self.pair.done:
            self.playing = False
            self.remember()
        return settled or self.pair.done

    def cancel(self):
        self.generation += 1
        self.busy = self.playing = False
        if self.pair:
            self.pair.cancel()
