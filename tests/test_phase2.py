from dataclasses import asdict, replace
import json
import pytest
from queuepact.models import Action, Policy, RunStatus, SERVICES, Status
from queuepact.engine import Engine
from queuepact.actions import surge_action
from queuepact.presenters import hall_state, passport, congestion, event_feed, describe_event
from queuepact.ui.controller import Controller
from test_engine import config, student, assert_invariants


def slow(time, multiplier, aid='slow', boundary=False):
    return Action(time, kind='slowdown', id=aid, payload_json=json.dumps(dict(service=SERVICES[0], multiplier=multiplier)), at_boundary=boundary)


def test_hall_counts_closing_progress_and_bounded_markers():
    e = Engine(config(50), tuple(student(f'S{i:04}', durations=(5, 1, 1, 1)) for i in range(50)))
    e.advance(until=1)
    e.apply_action(Action(1, 'DOCUMENT_VERIFICATION-1', 'close', 'close'))
    e.advance(until=1)
    h = hall_state(e, selected='S0049')
    desk = h['desks'][0]
    assert desk['status'] == 'Closing' and desk['student'] == 'S0000'
    assert desk['progress'] == .2
    assert h['zones'][0]['waiting'] == e.snapshot().counters[0].queue_length == 49
    assert h['zones'][0]['extra'] == 42
    assert len(h['markers']) == 8 and any(m['id'] == 'S0049' and m['selected'] for m in h['markers'])
    e.advance(until=5)
    assert hall_state(e)['desks'][0]['status'] == 'Closed'
    assert hall_state(e)['desks'][0]['student'] is None


def test_passport_preparation_eligibility_completion_and_totals():
    e = Engine(config(1), (student('A', ready=False, prep=3),))
    assert passport(e, 'missing') is None
    assert passport(e, 'A')['elapsed'] is None
    e.advance(until=1)
    p = passport(e, 'A')
    assert p['preparation'] == 1 and p['waiting'] == p['service_time'] == 0
    assert p['tasks'][0]['state'] == 'Not eligible'
    assert p['tasks'][1]['state'] == 'Eligible next'
    assert 'finish preparation' in p['tasks'][1]['reason']
    e.advance(until=3.5)
    p = passport(e, 'A')
    assert p['desk'] == 'V1' and p['tasks'][0]['state'] == 'In service'
    assert p['service_time'] == .5
    e.run()
    p = passport(e, 'A')
    assert p['complete'] and p['elapsed'] == 7
    assert p['preparation'] == 3 and p['service_time'] == 4 and p['waiting'] == 0
    assert [t['completed_at'] for t in p['tasks']] == [4, 5, 6, 7]
    assert all(t['state'] == 'Completed' for t in p['tasks'])


def test_slowdown_future_only_set_not_compound_and_restore():
    e = Engine(config(3), tuple(student(s, durations=(2, 1, 1, 1)) for s in 'ABC'), actions=(slow(1, 2), slow(1.5, 2, 'again'), slow(3, 1, 'normal')))
    e.run()
    starts = [x for x in e.events if x.type == 'service_started' and x.service == SERVICES[0]]
    assert [x.details['duration'] for x in starts] == [2, 4, 2]
    assert [x.time for x in starts] == [0, 2, 6]
    assert [x.details['base_duration'] for x in starts] == [2, 2, 2]
    assert e.workload[1].durations[0] == 2
    assert passport(e, 'B')['service_time'] == 7
    assert_invariants(e)


def test_estimate_uses_multiplier_but_not_on_active_remaining():
    e = Engine(config(2), (student('A', durations=(4, 1, 1, 1)), student('B', durations=(2, 1, 1, 1))))
    e.advance(until=1)
    e.apply_action(slow(1, 2))
    e.advance(until=1)
    score = e._estimate(e.students['A'], SERVICES[0])
    assert score['queue_work'] == 4 and score['busy_remaining'] == 3 and score['duration'] == 8


@pytest.mark.parametrize('policy', list(Policy))
def test_surge_deterministic_payload_unique_bookkeeping_and_unchanged_base(policy):
    c = config(3)
    base = tuple(student(s) for s in 'ABC')
    surge = surge_action(c, 1, 'batch1', 5, 2)
    assert surge == surge_action(c, 1, 'batch1', 5, 2)
    actions = (slow(.5, 2), surge, Action(2, 'PHOTO_CAPTURE-1', 'close', 'close'), Action(7, 'PHOTO_CAPTURE-1', 'restore', 'restore'))
    e = Engine(c, base, policy, actions)
    while e.status not in (RunStatus.COMPLETED, RunStatus.STALLED, RunStatus.LIMIT):
        e.advance(max_events=1)
        assert_invariants(e)
    assert e.metrics().completed == 8 and e.metrics().unfinished == 0
    assert e.workload is base and len(base) == 3 and len(e.students) == 8
    replay_actions = tuple(Action(**a) for a in json.loads(json.dumps([asdict(a) for a in e.actions])))
    again = Engine(c, base, policy, replay_actions)
    again.run()
    assert again.events == e.events and again.metrics() == e.metrics()
    assert len({s.id for s in [state.source for state in e.students.values()]}) == 8
    e.reset().run()


def test_future_surge_prevents_premature_completion():
    c = config(1)
    e = Engine(c, (student('A'),), actions=(surge_action(c, 8, 'later', 2, 1),))
    e.advance(until=5)
    assert e.status != RunStatus.COMPLETED
    e.run()
    assert e.metrics().completed == 3


def test_reject_duplicates_collisions_bad_payload_and_terminal_surge():
    c = config(1)
    e = Engine(c, (student('A'),))
    a = surge_action(c, 1, 'batch', 2, 1)
    e.apply_action(a)
    with pytest.raises(ValueError, match='already'):
        e.apply_action(a)
    with pytest.raises(ValueError, match='IDs'):
        e.apply_action(replace(a, id='other'))
    for a in (slow(1, float('nan')), slow(1, 0), Action(1, kind='surge', payload_json='{}'), Action(1, kind='unknown')):
        with pytest.raises(ValueError):
            e.apply_action(a)
    assert len(e.actions) == 1
    e.run()
    with pytest.raises(ValueError, match='Reset'):
        e.apply_action(surge_action(c, e.now, 'after', 1, 0))


def test_hotspot_ranking_ties_unavailable_and_preparation_separate():
    e = Engine(config(2), (student('A', ready=False), student('B', ready=False)))
    e.advance(until=0)
    assert congestion(e).service is None
    assert hall_state(e)['preparing'] == 2
    e.advance(until=2)
    assert congestion(e).service == SERVICES[0]
    e.apply_action(Action(2, 'DOCUMENT_VERIFICATION-1', 'close'))
    e.advance(until=2)
    insight = congestion(e)
    assert insight.unavailable and insight.open_desks == 0 and insight.active_desks == 1
    assert 'no open desks' in insight.explanation
    e.apply_action(Action(2, 'DOCUMENT_VERIFICATION-1', 'restore'))
    e.run()
    assert congestion(e).service is None


def test_controller_pause_reset_stale_tick_double_click_and_isolation():
    c = Controller(config(4))
    other = Controller(config(4))
    c.start()
    c.toggle_pause()
    time = c.engine.now
    c.select('S0001')
    c.disrupt('surge', count=3, now_wall=1)
    with pytest.raises(ValueError, match='just accepted'):
        c.disrupt('surge', count=3, now_wall=1.1)
    assert c.engine.now == time and not c.playing
    assert len(c.engine.students) == 7 and len(other.engine.students) == 4
    old_generation = c.generation
    c.reset()
    assert c.selected is None and not c.started and not c.playing
    assert len(c.engine.students) == 4 and not c.engine.actions
    c.start()
    c.tick(old_generation)
    assert c.engine.now == 0
    c.tick(c.generation)
    assert c.engine.now == .25


def test_live_boundary_actions_reproduce_at_same_timestamp():
    c = Controller(config(4))
    c.start()
    c.engine.advance(until=1)  # Completion and dispatch already observed.
    c.disrupt('slowdown', service=SERVICES[0], multiplier=2, now_wall=1)
    c.disrupt('surge', count=2, now_wall=2)
    c.disrupt('close', counter_id='PHOTO_CAPTURE-1', now_wall=3)
    c.engine.apply_action(Action(7, 'PHOTO_CAPTURE-1', 'restore', 'restore'))
    c.engine.run()
    replay = c.engine.reset()
    replay.run()
    assert replay.events == c.engine.events
    assert replay.metrics() == c.engine.metrics()


def test_feed_filters_and_honest_recorded_values():
    c = Controller(config(2))
    c.start()
    c.disrupt('close', counter_id='DOCUMENT_VERIFICATION-1')
    disruptions = event_feed(c.engine, 'Disruptions')
    assert len(disruptions) == 1 and 'closing after' in disruptions[0]['text']
    routes = event_feed(c.engine, 'Routing decisions')
    assert routes and all(r['type'] == 'routing_decision' for r in routes)
    assert '1.00 min' in routes[-1]['text']
    assert len(event_feed(c.engine, limit=2)) == 2
    assert not event_feed(c.engine, 'Selected student', None)


def test_phase1_demo_metrics_unchanged():
    from queuepact.models import Scenario
    for policy, wait in ((Policy.ORDINARY, 23.368975025990355), (Policy.SMART, 27.550247834566743)):
        e = Engine(Scenario(), policy=policy)
        assert e.run().average_completed_wait == pytest.approx(wait)


def test_congestion_tie_uses_stable_service_order():
    work = (student('A', durations=(10, 100, 1, 1)), student('B', durations=(100, 10, 1, 1)),
            student('C', durations=(1, 100, 1, 1)), student('D', durations=(100, 1, 1, 1)))
    e = Engine(config(4), work, Policy.SMART)
    e.advance(until=0)
    assert len(e.queues[SERVICES[0]]) == len(e.queues[SERVICES[1]]) == 1
    assert congestion(e).service == SERVICES[0]
    before = e.events, e.now, e.metrics()
    hall_state(e)
    passport(e, 'A')
    congestion(e)
    event_feed(e)
    assert (e.events, e.now, e.metrics()) == before
