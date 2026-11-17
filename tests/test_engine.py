from collections import Counter
from dataclasses import asdict, FrozenInstanceError, replace
import json
import random
import pytest
from queuepact.engine import Engine
from queuepact.models import Scenario, StudentInput, Service as S, SERVICES, Policy, Status, RunStatus, Action
from queuepact.scenarios import generate_workload, scenario_json, load_scenario
from queuepact.events import events_json


def config(n=2, **kwargs):
    return Scenario(student_count=n, arrival_pattern='batch', counter_counts=(1, 1, 1, 1),
                    duration_ranges=((1, 1),)*4, **kwargs)


def student(id, arrival=0, durations=(1, 1, 1, 1), ready=True, prep=2):
    return StudentInput(id, arrival, durations, ready, prep)


def assert_invariants(engine):
    queued = [sid for queue in engine.queues.values() for sid in queue]
    active = [c.student_id for c in engine.counters.values() if c.student_id]
    assert len(queued+active) == len(set(queued+active))
    for sid, state in engine.students.items():
        assert (sid in queued) == (state.status == Status.WAITING)
        assert (sid in active) == (state.status == Status.SERVICE)
        if state.status == Status.PREPARING:
            assert sid not in queued+active
    completed = {}
    prepared = {s.source.id for s in engine.students.values() if s.source.documents_ready}
    occupied = {}
    for e in engine.events:
        done = completed.setdefault(e.student_id, set())
        if e.type == 'preparation_completed':
            prepared.add(e.student_id)
        if e.type == 'service_started':
            assert e.counter_id not in occupied
            occupied[e.counter_id] = e.student_id
            if e.service == S.DOCUMENT_VERIFICATION:
                assert e.student_id in prepared
            if e.service == S.FEE_PAYMENT:
                assert S.DOCUMENT_VERIFICATION in done
            if e.service == S.FINAL_ENROLLMENT:
                assert set(SERVICES[:3]) <= done
        if e.type == 'service_completed':
            assert occupied.pop(e.counter_id) == e.student_id
            assert e.service not in done
            done.add(e.service)


@pytest.mark.parametrize('policy', list(Policy))
def test_invariants_prerequisites_preparation_and_completion(policy):
    engine = Engine(config(8, missing_fraction=.7), policy=policy)
    while engine.status not in (RunStatus.COMPLETED, RunStatus.STALLED, RunStatus.LIMIT):
        engine.advance(max_events=1)
        assert_invariants(engine)
    assert engine.status == RunStatus.COMPLETED
    counts = Counter((e.student_id, e.service) for e in engine.events if e.type == 'service_completed')
    assert len(counts) == 32 and set(counts.values()) == {1}
    assert sum(e.type == 'preparation_completed' for e in engine.events) == sum(not s.documents_ready for s in engine.workload)


@pytest.mark.parametrize('policy', list(Policy))
def test_determinism_batching_and_workload(policy):
    c = config(12)
    workload = generate_workload(c)
    action = Action(2, 'PHOTO_CAPTURE-1', 'close')
    actions = (action, Action(8, action.counter_id, 'restore'))
    full = Engine(c, workload, policy, actions)
    full.run()
    for batch in (1, 3, 50):
        stepped = Engine(c, workload, policy, actions)
        while stepped.status != RunStatus.COMPLETED:
            stepped.advance(max_events=batch)
        assert stepped.events == full.events
        assert stepped.metrics() == full.metrics()
    clocked = Engine(c, workload, policy, actions)
    while clocked.status != RunStatus.COMPLETED:
        clocked.advance(until=clocked.now+.37)
    assert clocked.events == full.events
    assert clocked.metrics() == full.metrics()


def test_workload_is_isolated_shared_and_immutable():
    c = config(5)
    state = random.getstate()
    work = generate_workload(c)
    assert random.getstate() == state
    assert work == generate_workload(c)
    with pytest.raises(FrozenInstanceError):
        work[0].arrival = 10
    for policy in Policy:
        engine = Engine(c, work, policy)
        assert engine.workload is work
        engine.run()
        for e in engine.events:
            if e.type == 'service_started':
                assert e.details['duration'] == next(s for s in work if s.id == e.student_id).duration(e.service)


def test_hand_calculated_metrics():
    engine = Engine(config(), (student('A'), student('B')))
    m = engine.run()
    # A: 0..4, no wait. B: waits 0..1, visits 0..5. Each desk works 2 minutes.
    assert engine.now == 5
    assert m.total_queue_wait == 1
    assert m.average_completed_wait == .5
    assert m.p90_completed_wait == 1
    assert m.average_completed_visit == 4.5
    assert all(b == 2 for _, b in m.counter_busy_time)
    assert all(u == .4 for _, u in m.counter_utilization)
    assert m.longest_current_wait is None


def test_preparation_not_counted_as_wait():
    e = Engine(config(1), (student('A', ready=False, prep=7),))
    e.advance(until=3)
    assert e.metrics().preparing == 1 and e.metrics().total_queue_wait == 0
    e.run()
    assert e.metrics().average_completed_visit == 11
    assert e.metrics().average_completed_wait == 0
    assert e.students['A'].preparation_time == 7


def test_busy_close_restore_and_utilization():
    cid = 'DOCUMENT_VERIFICATION-1'
    e = Engine(config(), (student('A', durations=(3, 1, 1, 1)), student('B')),
               actions=(Action(1, cid, 'close'), Action(6, cid, 'restore')))
    e.run()
    starts = [x for x in e.events if x.type == 'service_started' and x.counter_id == cid]
    assert [x.time for x in starts] == [0, 6]
    assert next(x.time for x in e.events if x.type == 'service_completed' and x.counter_id == cid) == 3
    assert e.metrics().completed == 2
    assert dict(e.metrics().counter_utilization)[cid] == 4/e.now


def test_stall_and_live_restore_no_loss():
    cid = 'DOCUMENT_VERIFICATION-1'
    e = Engine(config(), actions=(Action(0, cid, 'close'),))
    e.run()
    assert e.status == RunStatus.STALLED and e.metrics().waiting == 2
    events = e.events
    e.advance(until=100)
    assert e.events == events
    e.apply_action(Action(e.now, cid, 'restore'))
    e.run()
    assert e.status == RunStatus.COMPLETED
    replay = e.reset()
    replay.run()
    # Live recovery includes the observation of a stall; scheduled replay never stalled.
    assert replay.metrics() == e.metrics()


def test_no_configured_capacity():
    e = Engine(replace(config(1), counter_counts=(0, 0, 0, 0)))
    e.run()
    assert e.status == RunStatus.STALLED and e.metrics().unfinished == 1


def fairness_run(threshold):
    work = (student('0H', durations=(10, 100, 1, 1)), student('A', durations=(1, 20, 1, 1)),
            student('B', 1, (100, 10, 1, 1)), student('C', 2, (100, 1, 1, 1)))
    e = Engine(config(4, fair_wait=threshold), work, Policy.SMART,
               (Action(3, 'DOCUMENT_VERIFICATION-1', 'close'), Action(20, 'DOCUMENT_VERIFICATION-1', 'restore')))
    e.run()
    return e


def test_fairness_changes_order_and_preserves_age_on_closure():
    protected, fifo = fairness_run(2), fairness_run(10000)
    starts = lambda e: [x.student_id for x in e.events if x.type == 'service_started' and x.service == S.PHOTO_CAPTURE]
    assert starts(protected)[:3] == ['B', 'A', 'C']
    assert starts(fifo)[:3] == ['B', 'C', 'A']
    event = next(x for x in protected.events if x.type == 'fair_wait_protection' and x.student_id == 'A')
    assert event.details['age'] == 11
    assert_invariants(protected)


@pytest.mark.parametrize('policy', list(Policy))
def test_zero_students(policy):
    e = Engine(config(0), policy=policy)
    e.run()
    assert e.now == 0 and e.status == RunStatus.COMPLETED
    m = e.metrics()
    assert m.average_completed_wait is None and m.p90_completed_wait is None
    assert all(u is None for _, u in m.counter_utilization)


def test_incomplete_and_limit():
    e = Engine(config(2, safety_limit=.5), (student('A'), student('B')))
    e.run()
    m = e.metrics()
    assert e.status == RunStatus.LIMIT and e.now == .5
    assert m.waiting == m.in_service == 1
    assert m.unfinished == 2 and m.completed == 0
    assert m.total_queue_wait == m.longest_current_wait == .5
    assert m.average_completed_wait is None and m.average_completed_visit is None
    assert dict(m.counter_busy_time)['DOCUMENT_VERIFICATION-1'] == .5


def test_reset_fresh_and_snapshot_readonly():
    e = Engine(config(3))
    e.run()
    fresh = e.reset()
    assert fresh.status == RunStatus.READY and fresh.now == 0 and not fresh.events
    assert not any(s.completed for s in fresh.students.values())
    fresh.run()
    assert fresh.events == e.events and fresh.metrics() == e.metrics()
    with pytest.raises(FrozenInstanceError):
        e.snapshot().time = 9
    detail = e.events[0].details
    detail['mutated'] = True
    assert 'mutated' not in e.events[0].details


def test_json_roundtrip(tmp_path):
    c = config(2)
    path = tmp_path/'scenario.json'
    path.write_text(scenario_json(c))
    assert load_scenario(path) == c
    e = Engine(c)
    e.run()
    assert json.loads(events_json(e.events)) == [event.to_dict() for event in e.events]
    assert json.loads(json.dumps([asdict(Action(1, 'PHOTO_CAPTURE-1', 'close'))]))[0]['time'] == 1


@pytest.mark.parametrize('kwargs', [dict(student_count=-1), dict(arrival_rate=0), dict(counter_counts=(1,)),
    dict(missing_fraction=2), dict(fair_wait=-1), dict(safety_limit=float('inf')),
    dict(duration_ranges=((0, 1),)*4), dict(preparation_range=(3, 2)), dict(arrival_pattern='unknown')])
def test_invalid_scenarios(kwargs):
    with pytest.raises(ValueError):
        Scenario(**kwargs)


def test_invalid_actions_and_advance():
    e = Engine(config())
    for action in (Action(-1, 'PHOTO_CAPTURE-1', 'close'), Action(1, 'bad', 'close'), Action(1, 'PHOTO_CAPTURE-1', 'delete')):
        with pytest.raises(ValueError):
            e.apply_action(action)
    with pytest.raises(ValueError):
        e.advance(max_events=0)
    with pytest.raises(ValueError):
        e.advance(until=-1)


def test_smart_preparation_competes_with_photo_and_decisions_are_actual():
    e = Engine(config(1), (student('A', durations=(1, 1, 1, 1), ready=False, prep=5),), Policy.SMART)
    e.run()
    first = next(x for x in e.events if x.type == 'routing_decision')
    assert first.details['selected'] == S.PHOTO_CAPTURE
    assert [o['estimate'] for o in first.details['candidates']] == [1, 5]
    assert e.metrics().completed == 1


def test_same_time_close_precedes_completion_and_arrival():
    cid = 'DOCUMENT_VERIFICATION-1'
    e = Engine(config(), (student('A'), student('B', 1)), actions=(Action(1, cid, 'close'), Action(3, cid, 'restore')))
    e.run()
    at_one = [x.type for x in e.events if x.time == 1]
    assert at_one.index('counter_closed') < at_one.index('service_completed') < at_one.index('arrival')
    assert next(x.time for x in e.events if x.type == 'service_started' and x.student_id == 'B') == 3


def test_closure_to_preparation_preserves_only_accrued_queue_age():
    work = (student('0H', durations=(100, 10, 1, 1)), student('A', durations=(1, 20, 1, 1), ready=False, prep=30))
    e = Engine(config(2, fair_wait=2), work, Policy.SMART, (Action(3, 'PHOTO_CAPTURE-1', 'close'),))
    e.advance(until=33)
    assert e.students['A'].wait_age == 30  # 3 minutes carried; preparation's 30 minutes excluded.
    assert e.metrics().longest_current_wait == 3
    assert e.students['A'].total_wait == 3
    assert_invariants(e)


@pytest.mark.parametrize('seed', range(5))
@pytest.mark.parametrize('policy', list(Policy))
def test_varied_workloads_with_disruptions(seed, policy):
    c = Scenario(seed=seed, student_count=15, missing_fraction=.5)
    e = Engine(c, policy=policy, actions=(Action(2, 'PHOTO_CAPTURE-1', 'close'), Action(12, 'PHOTO_CAPTURE-1', 'restore')))
    while e.status not in (RunStatus.COMPLETED, RunStatus.STALLED, RunStatus.LIMIT):
        e.advance(max_events=1)
        assert_invariants(e)
    assert e.status == RunStatus.COMPLETED
