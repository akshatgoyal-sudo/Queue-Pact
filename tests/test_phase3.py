from dataclasses import replace
import json
import pytest
from queuepact.models import Policy, SERVICES, Action, RunStatus, Status
from queuepact.engine import Engine
from queuepact.actions import surge_action
from queuepact.experiments import ExperimentSpec, RunRecord, PairedRun
from queuepact.experiments.replay import reconstruct, branches
from queuepact.experiments.staffing import StaffConstraints, StaffTrial
from queuepact.experiments.readiness import ReadinessConfig, ReadinessEngine
from queuepact.experiments.results import result, series, difference
from test_engine import config, student, assert_invariants


def spec(n=4, actions=()):
    return ExperimentSpec(config(n), tuple(student(chr(65+i)) for i in range(n)), actions)


@pytest.mark.parametrize('budget', [1, 7, 300])
def test_pair_matches_independent_and_event_series(budget):
    s = spec()
    s = s.with_action(surge_action(s.scenario, 12, 'surge', 2, 1))
    pair = PairedRun(s).run(budget)
    assert pair.status == 'Completed'
    for e in pair.engines:
        independent = Engine(s.scenario, s.workload, e.policy, s.actions)
        independent.run()
        assert e.workload is s.workload
        assert e.events == independent.events
        assert e.metrics() == independent.metrics()
        assert series(e) == series(independent)
        assert e.metrics().completed == 6
        assert_invariants(e)


def test_playback_horizon_population_and_completion_window():
    s = spec()
    pair = PairedRun(s)
    while not pair.done:
        pair.step(.31, 2)
    reference = PairedRun(s).run()
    assert [e.metrics() for e in pair.engines] == [e.metrics() for e in reference.engines]
    limited = PairedRun(s, horizon=2).run()
    assert 'Horizon' in limited.status
    r = result(limited.engines[0])
    assert r['unfinished'] == 4 and r['unfinished_wait'] > 0
    assert r['average_completed_wait'] is None and r['makespan'] is None
    assert difference(2, 0) == dict(absolute=2, percent=None)
    assert difference(None, 2)['absolute'] is None


def test_record_reconstruction_same_boundary_and_continuation():
    s = spec(actions=(Action(1, 'PHOTO_CAPTURE-1', 'close', 'close', at_boundary=True), Action(5, 'PHOTO_CAPTURE-1', 'restore', 'restore')))
    s = s.with_action(surge_action(s.scenario, 8, 'surge', 3, 1))
    record = RunRecord(s, Policy.SMART)
    decoded = RunRecord.from_json(record.to_json())
    assert decoded == record and decoded.specification.fingerprint == s.fingerprint
    original = record.engine()
    original.advance(until=1)
    rebuilt = reconstruct(decoded, 1)
    assert original.events == rebuilt.events and original.snapshot() == rebuilt.snapshot()
    pair = branches(record, 1)
    pair.run(1)
    original.run()
    for e in pair.engines:
        assert e.events == original.events and e.metrics() == original.metrics()
        assert sum(x.type == 'arrival_surge' for x in e.events) == 1


def test_additive_branch_order_and_isolation():
    s = spec(actions=(Action(1, 'PHOTO_CAPTURE-1', 'close', 'original', at_boundary=True),))
    record = RunRecord(s, Policy.ORDINARY)
    pair = branches(record, 1, Action(1, 'PHOTO_CAPTURE-1', 'restore', 'new'))
    changed = pair.engines[1]
    assert [e.type for e in changed.events if e.type.startswith('counter_')] == ['counter_closed', 'counter_restored']
    pair.run()
    assert pair.engines[0].status == RunStatus.STALLED and changed.status == RunStatus.COMPLETED
    assert len(record.specification.actions) == 1
    replayed = RunRecord.capture(changed).engine()
    replayed.run()
    assert replayed.events == changed.events


def test_shared_action_and_ambiguous_rejection():
    pair = PairedRun(spec())
    pair.step(.5)
    a = surge_action(pair.specification.scenario, .5, 'shared', 2, 1, at_boundary=True)
    pair.apply_shared(a)
    assert pair.engines[0].actions == pair.engines[1].actions == (a,)
    before = [e.events for e in pair.engines]
    with pytest.raises(ValueError):
        pair.apply_shared(a)
    assert before == [e.events for e in pair.engines]
    pair.run()
    with pytest.raises(ValueError):
        pair.apply_shared(a)


def test_staff_constraints_one_worker_ranking_source_unchanged():
    record = RunRecord(spec(), Policy.ORDINARY)
    source = record.to_json()
    constraints = StaffConstraints((SERVICES[0], SERVICES[1]), (SERVICES[1], SERVICES[2]))
    trial = StaffTrial(record, constraints, horizon=8)
    assert trial.placements == (None, SERVICES[1])
    trial.pair.run(1)
    assert len(trial.pair.engines[1].counters) == len(trial.pair.engines[0].counters)+1
    assert trial.selected_index == 1
    assert record.to_json() == source
    opened = trial.open_selected().engine()
    opened.run()
    assert_invariants(opened)
    assert len([a for a in opened.actions if a.kind == 'add_staff']) == 1
    empty = StaffTrial(record, StaffConstraints((), ()), horizon=8)
    empty.pair.run()
    assert empty.selected_index is None
    with pytest.raises(ValueError, match='No completed'):
        empty.open_selected()


def test_staff_stable_tie_and_cancellation():
    record = RunRecord(spec(), Policy.SMART)
    trial = StaffTrial(record, horizon=.01)
    trial.pair.run()
    outcomes = trial.outcomes()[1:]
    best = min(outcomes, key=lambda r: (-r['completed'], r['total_wait'], SERVICES.index(r['placement'])))
    assert trial.placements[trial.selected_index] == best['placement']
    pair = PairedRun(spec())
    pair.cancel()
    before = pair.engines[0].events
    pair.step()
    assert pair.status == 'Cancelled' and pair.engines[0].events == before


@pytest.mark.parametrize('policy', list(Policy))
@pytest.mark.parametrize('mode', ['early', 'late'])
def test_readiness_overhead_preparation_and_prerequisites(mode, policy):
    c = config(2)
    work = (student('A', ready=False, prep=2), student('B'))
    e = ReadinessEngine(c, work, policy, readiness=ReadinessConfig(mode, 1, .5, .75))
    e.run()
    assert e.metrics().completed == 2
    assert e.workload is work and not work[0].documents_ready
    assert e.overhead()['preparation_time'] == 2
    assert_invariants(e)
    assert len([x for x in e.events if x.type == 'service_completed']) == 8
    if mode == 'early':
        assert e.overhead()['screening_time'] == 1
        assert e.overhead()['failed_check_time'] == 0
        assert next(x.time for x in e.events if x.type == 'preparation_started') == .5
    else:
        failed = next(x for x in e.events if x.type == 'verification_check_failed')
        assert failed.time == .75
        assert e.overhead()['failed_check_time'] == .75
        completed = next(x for x in e.events if x.type == 'service_completed' and x.student_id == 'A' and x.service == SERVICES[0])
        assert completed.time >= 3.75
    again = e.reset()
    again.run()
    assert again.events == e.events


def test_screening_queue_cost_and_no_zero_cost():
    work = (student('A'), student('B'))
    e = ReadinessEngine(config(2), work, Policy.ORDINARY, readiness=ReadinessConfig('early', 1, 2, 1))
    e.advance(until=1)
    assert e.metrics().total_queue_wait == 1 and e.overhead()['screening_time'] == 1
    assert not any(x.type == 'service_started' for x in e.events)
    with pytest.raises(ValueError):
        ReadinessConfig(screening_duration=0)


def test_version_and_input_validation():
    with pytest.raises(ValueError):
        replace(spec(), version=3)
    with pytest.raises(ValueError):
        spec(actions=(Action(1, id='dup'), Action(2, id='dup')))
    with pytest.raises(ValueError):
        PairedRun(spec(), horizon=float('nan'))


def test_lab_reset_stale_jobs_and_session_isolation():
    from queuepact.ui.lab_controller import LabController
    a,b=LabController(),LabController()
    generation=a.begin()
    with pytest.raises(ValueError):
        a.begin()
    a.reset()
    assert not a.install(PairedRun(spec()),generation)
    generation=a.begin()
    a.install(PairedRun(spec()),generation)
    a.tick(generation)
    assert b.pair is None
    a.selected='A'
    a.remember()
    a.reset()
    assert not a.sources and a.selected is None and not a.playing
    assert not a.tick(generation)


def test_fixed_horizon_blocked_wait_and_frozen_completed_window():
    blocked=replace(spec(),scenario=replace(config(4),counter_counts=(0,1,1,1)))
    pair=PairedRun(blocked,horizon=10).run()
    assert pair.engines[0].now == 10
    assert result(pair.engines[0])['total_queue_wait'] == 40
    pair=PairedRun(spec(),horizon=50).run()
    for e in pair.engines:
        independent=Engine(e.config,e.workload,e.policy)
        independent.run()
        assert e.metrics().counter_utilization == independent.metrics().counter_utilization
        assert e.now == independent.now


def test_added_resource_action_order_validation():
    from queuepact.experiments.staffing import staff_action
    e=spec().policies
    engine=RunRecord(spec(),Policy.ORDINARY).engine()
    extra=staff_action(engine,SERVICES[0],2)
    engine.apply_action(extra)
    with pytest.raises(ValueError,match='precede'):
        engine.apply_action(Action(1,extra.counter_id,'close','early'))
    engine.apply_action(Action(3,extra.counter_id,'close','later'))
    engine.run()
    assert_invariants(engine)


@pytest.mark.parametrize('mode',['early','late'])
def test_readiness_disruptions_and_recorded_surge(mode):
    s=spec()
    surge=surge_action(s.scenario,2,'extra',2,1)
    actions=(surge,Action(1,'DOCUMENT_VERIFICATION-1','close','close'),Action(4,'DOCUMENT_VERIFICATION-1','restore','restore'))
    e=ReadinessEngine(s.scenario,s.workload,Policy.SMART,actions,ReadinessConfig(mode))
    e.run()
    assert e.metrics().completed == 6
    assert_invariants(e)


def test_plotly_series_and_undefined_charts():
    from queuepact.experiments.results import charts
    p=PairedRun(spec(0)).run()
    figs=charts(p.engines,p.labels)
    assert len(figs)==4
    assert all(f.to_json() for f in figs)


def test_readiness_single_visit_time_partition():
    for mode,overhead in [('early',.5),('late',.75)]:
        e=ReadinessEngine(config(1),(student('A',ready=False,prep=2),),Policy.ORDINARY,readiness=ReadinessConfig(mode))
        e.run()
        assert e.now == 4+2+overhead
        assert e.students['A'].total_wait == 0
        assert e.students['A'].preparation_time == 2


def test_normalized_replay_after_observed_stall():
    from queuepact.experiments.replay import normalized_events
    e=Engine(config(1), (student('A'),), actions=(Action(0,'DOCUMENT_VERIFICATION-1','close','close'),))
    e.run()
    assert e.status == RunStatus.STALLED
    e.apply_action(Action(5,'DOCUMENT_VERIFICATION-1','restore','restore'))
    e.run()
    again=RunRecord.capture(e).engine()
    again.run()
    assert normalized_events(e) == normalized_events(again)
    assert e.metrics() == again.metrics()


def test_future_surge_in_unfinished_population():
    s=spec(1)
    p=PairedRun(s.with_action(surge_action(s.scenario,20,'future',3,1)),horizon=10).run()
    assert result(p.engines[0])['unfinished'] == 3
    assert result(p.engines[0])['not_arrived'] == 3


def test_no_feasible_presenter_is_readable():
    from queuepact.experiments.results import findings
    t=StaffTrial(RunRecord(spec(),Policy.ORDINARY),StaffConstraints((),()))
    t.pair.run()
    assert 'reference only' in findings(t.pair.engines,t.pair.labels)[0]


@pytest.mark.parametrize('mode',['early','late'])
def test_readiness_record_and_branch_preserve_operational_model(mode):
    s=spec()
    engine=ReadinessEngine(s.scenario,s.workload,Policy.SMART,readiness=ReadinessConfig(mode))
    engine.run()
    record=RunRecord.from_json(RunRecord.capture(engine).to_json())
    pair=branches(record,1)
    pair.run()
    assert all(e.events == engine.events for e in pair.engines)
    assert all(e.overhead() == engine.overhead() for e in pair.engines)
