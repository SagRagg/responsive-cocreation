"""Tests for TrialTracker and perception_health in trial_tracker.py: pairing
by sketch stamp (not trial number), latency maths at nanosecond precision,
out-of-order and missing messages, the four statuses (ok, timeout,
superseded, no_strokes), duplicates, bad JSON, and the `current` view the
page shows. Times are synthetic epoch ns built from STAMP."""

import json

import pytest

from trial_tracker import (STATUS_NO_STROKES, STATUS_OK, STATUS_SUPERSEDED,
                           STATUS_TIMEOUT, TrialTracker, perception_health)

NS = 1_000_000_000
SEC, NSEC = 1_761_540_000, 123_456_789
STAMP = (SEC, NSEC)
T0 = SEC * NS + NSEC          # the instant capture stamped the sketch
MS = 1_000_000


def truth(trial=1, index=6788, digit=7, stamp=STAMP):
    return json.dumps({'trial': trial, 'mnist_index': index, 'digit': digit,
                       'stamp': {'sec': stamp[0], 'nanosec': stamp[1]}})


def strokes(trial=1, digit=7, confidence=0.9981, stamp=STAMP, **extra):
    payload = {'trial': trial, 'digit': digit, 'confidence': confidence,
               'source_stamp': {'sec': stamp[0], 'nanosec': stamp[1]},
               'frame_id': 'canvas', 'strokes': [[[0.2, 0.1], [0.8, 0.1]]]}
    payload.update(extra)
    return json.dumps(payload)


def other_stamp(n):
    return (SEC + n, NSEC)


def other_t0(n):
    return (SEC + n) * NS + NSEC


@pytest.fixture
def tracker():
    return TrialTracker('edge', timeout_s=30)


def run_in_order(tracker, stamp=STAMP, true=7, pred=7, trial=1):
    """Feed one complete trial in the normal order, sketch 2 ms after its stamp."""
    t0 = stamp[0] * NS + stamp[1]
    tracker.on_sketch(stamp, t0 + 2 * MS, b'\x00' * 784, 28, 28)
    tracker.on_ground_truth(truth(trial, 100 + trial, true, stamp), t0 + 3 * MS)
    tracker.on_prediction(pred, t0 + 40 * MS)
    tracker.on_strokes(strokes(trial, pred, stamp=stamp), t0 + 41 * MS)
    tracker.on_turn_done(t0 + 5000 * MS)


def test_full_trial_in_order(tracker):
    run_in_order(tracker)
    (row,) = tracker.rows
    assert row == {
        'seq': 0, 'placement': 'edge', 'trial': 1, 'mnist_index': 101,
        'stamp_sec': SEC, 'stamp_nanosec': NSEC,
        'true_digit': 7, 'pred_digit': 7, 'confidence': 0.9981, 'correct': True,
        'e2e_ms': 41.0, 'compute_ms': 39.0, 'network_ms': 2.0, 'turn_ms': 5000.0,
        'status': STATUS_OK}


def test_latency_maths_uses_nanosecond_precision(tracker):
    # 1 ns of difference must survive: floats at this epoch could not hold it.
    tracker.on_sketch(STAMP, T0 + 1_500_001, None)
    tracker.on_ground_truth(truth(), T0 + 1_600_000)
    tracker.on_strokes(strokes(), T0 + 41_500_002)
    tracker.on_turn_done(T0 + 9_000_000_003)
    row = tracker.rows[0]
    assert row['e2e_ms'] == 41.5
    assert row['compute_ms'] == 40.0
    assert row['network_ms'] == 1.5
    assert row['turn_ms'] == 9000.0


def test_publish_stamp_replaces_strokes_arrival_for_compute(tracker):
    """With publish_stamp, compute ends at publish and network absorbs the rest."""
    publish = T0 + 30 * MS
    tracker.on_sketch(STAMP, T0 + 2 * MS, None)
    tracker.on_strokes(strokes(publish_stamp={'sec': publish // NS,
                                              'nanosec': publish % NS}),
                       T0 + 41 * MS)
    tracker.on_turn_done(T0 + 100 * MS)
    row = tracker.rows[0]
    assert row['compute_ms'] == 28.0         # 30 ms - 2 ms, not 41 ms - 2 ms
    assert row['e2e_ms'] == 41.0
    assert row['network_ms'] == 13.0


def test_missing_ground_truth_leaves_true_and_correct_empty(tracker):
    tracker.on_sketch(STAMP, T0 + MS, None)
    tracker.on_strokes(strokes(), T0 + 30 * MS)
    tracker.on_turn_done(T0 + 90 * MS)
    row = tracker.rows[0]
    assert row['true_digit'] is None
    assert row['correct'] is None
    assert row['pred_digit'] == 7
    assert row['trial'] == 1                 # falls back to the strokes counter


def test_wrong_prediction_is_marked_incorrect(tracker):
    run_in_order(tracker, true=3, pred=8)
    assert tracker.rows[0]['correct'] is False


def test_out_of_order_arrival(tracker):
    # strokes and keyless messages arrive before the sketch and the truth
    tracker.on_strokes(strokes(), T0 + 20 * MS)
    tracker.on_prediction(7, T0 + 21 * MS)
    tracker.on_ground_truth(truth(), T0 + 22 * MS)
    tracker.on_sketch(STAMP, T0 + 23 * MS, b'\x01' * 784, 28, 28)
    tracker.on_turn_done(T0 + 4000 * MS)
    (row,) = tracker.rows
    assert row['status'] == STATUS_OK
    assert row['true_digit'] == 7 and row['pred_digit'] == 7
    assert row['e2e_ms'] == 20.0
    assert row['compute_ms'] is None         # sketch seen after strokes: no valid span
    assert row['turn_ms'] == 4000.0


def test_ground_truth_before_sketch(tracker):
    tracker.on_ground_truth(truth(), T0 + MS)
    tracker.on_sketch(STAMP, T0 + 2 * MS, None)
    tracker.on_strokes(strokes(), T0 + 12 * MS)
    tracker.on_turn_done(T0 + 20 * MS)
    assert len(tracker.rows) == 1
    assert tracker.rows[0]['compute_ms'] == 10.0
    assert tracker.rows[0]['true_digit'] == 7


def test_missing_turn_done_times_out(tracker):
    tracker.on_sketch(STAMP, T0 + 2 * MS, None)
    tracker.on_ground_truth(truth(), T0 + 3 * MS)
    tracker.on_strokes(strokes(), T0 + 41 * MS)

    tracker.tick(T0 + 2 * MS + 29 * NS)
    assert tracker.rows == []                # not yet

    tracker.tick(T0 + 2 * MS + 30 * NS)
    (row,) = tracker.rows
    assert row['status'] == STATUS_TIMEOUT
    assert row['turn_ms'] is None
    assert row['e2e_ms'] == 41.0             # what was measured is kept
    assert row['correct'] is True


def test_timeout_without_any_reply(tracker):
    tracker.on_sketch(STAMP, T0, None)
    tracker.on_ground_truth(truth(), T0 + MS)
    tracker.tick(T0 + 31 * NS)
    row = tracker.rows[0]
    assert row['status'] == STATUS_TIMEOUT
    assert row['pred_digit'] is None and row['correct'] is None
    assert row['e2e_ms'] is None and row['compute_ms'] is None


def test_next_sketch_closes_the_stalled_trial(tracker):
    """A new sketch stamp closes the open trial as superseded."""
    tracker.on_sketch(STAMP, T0, None)
    tracker.on_strokes(strokes(), T0 + 40 * MS)          # no /turn_done ever
    run_in_order(tracker, other_stamp(60), trial=2)
    assert [r['status'] for r in tracker.rows] == [STATUS_SUPERSEDED, STATUS_OK]
    assert [r['seq'] for r in tracker.rows] == [0, 1]


def test_turn_done_without_strokes(tracker):
    tracker.on_sketch(STAMP, T0, None)
    tracker.on_prediction(4, T0 + 10 * MS)
    tracker.on_turn_done(T0 + 50 * MS)
    row = tracker.rows[0]
    assert row['status'] == STATUS_NO_STROKES
    assert row['pred_digit'] == 4            # from /digit_prediction


def test_pairing_ignores_trial_numbers(tracker):
    # perception restarted: its counter says 1 while capture is on trial 5
    run_in_order(tracker, other_stamp(0), trial=5)
    tracker.on_sketch(other_stamp(10), other_t0(10) + MS, None)
    tracker.on_ground_truth(truth(6, 7, 2, other_stamp(10)), other_t0(10) + 2 * MS)
    tracker.on_strokes(strokes(trial=1, digit=2, stamp=other_stamp(10)),
                       other_t0(10) + 30 * MS)
    tracker.on_turn_done(other_t0(10) + 99 * MS)
    second = tracker.rows[1]
    assert second['trial'] == 6              # capture's number wins
    assert second['true_digit'] == 2 and second['correct'] is True


def test_late_strokes_for_a_closed_trial_are_dropped(tracker):
    """Strokes after a timeout must not reopen the trial; the keyless
    /turn_done that follows has nothing in flight and counts as an orphan."""
    tracker.on_sketch(STAMP, T0, None)
    tracker.tick(T0 + 31 * NS)
    tracker.on_strokes(strokes(), T0 + 32 * NS)
    tracker.on_turn_done(T0 + 33 * NS)       # nothing in flight
    assert len(tracker.rows) == 1
    assert tracker.rows[0]['status'] == STATUS_TIMEOUT
    assert tracker.orphans == 1


def test_keyless_messages_with_nothing_in_flight_are_counted(tracker):
    tracker.on_prediction(3, T0)
    tracker.on_turn_done(T0)
    assert tracker.rows == [] and tracker.orphans == 2


def test_duplicate_messages_do_not_double_count(tracker):
    run_in_order(tracker)
    tracker.on_sketch(STAMP, T0 + 9 * MS, None)     # replay of a closed trial
    tracker.on_strokes(strokes(), T0 + 9 * MS)
    assert len(tracker.rows) == 1


def test_bad_json_is_counted_not_fatal(tracker):
    tracker.on_ground_truth('not json', T0)
    tracker.on_strokes('[1, 2]', T0)
    tracker.on_strokes(json.dumps({'digit': 3}), T0)       # no source_stamp
    assert tracker.bad_messages == 2
    assert tracker.rows == [] and tracker.current(T0) is None


def test_negative_end_to_end_is_kept_to_expose_clock_skew(tracker):
    tracker.on_sketch(STAMP, T0 + MS, None)
    tracker.on_strokes(strokes(), T0 - 5 * MS)       # remote clock ahead
    tracker.on_turn_done(T0 + 50 * MS)
    assert tracker.rows[0]['e2e_ms'] == -5.0


def test_on_finish_and_rows_since(tracker):
    seen = []
    tracker.on_finish = seen.append
    run_in_order(tracker, other_stamp(0), trial=1)
    run_in_order(tracker, other_stamp(30), trial=2)
    run_in_order(tracker, other_stamp(60), trial=3)
    assert [r['seq'] for r in seen] == [0, 1, 2]
    assert [r['seq'] for r in tracker.rows_since(-1)] == [0, 1, 2]
    assert [r['seq'] for r in tracker.rows_since(1)] == [2]
    assert tracker.rows_since(2) == []


def test_current_reports_the_trial_in_flight(tracker):
    tracker.on_sketch(STAMP, T0 + MS, bytes(range(256)) * 3 + bytes(16), 28, 28)
    tracker.on_ground_truth(truth(), T0 + 2 * MS)
    cur = tracker.current(T0 + 3 * NS)
    assert cur['state'] == 'waiting_prediction'
    assert cur['true_digit'] == 7 and cur['pred_digit'] is None
    assert cur['elapsed_s'] == 3.0
    assert (cur['width'], cur['height']) == (28, 28)
    assert tracker.waiting(T0 + 3 * NS)[0] == 'waiting_prediction'

    tracker.on_strokes(strokes(), T0 + 41 * MS)
    assert tracker.current(T0 + 4 * NS)['state'] == 'waiting_turn_done'
    tracker.on_turn_done(T0 + 5 * NS)
    cur = tracker.current(T0 + 9 * NS)
    assert cur['state'] == 'done' and cur['turn_ms'] == 5000.0
    assert tracker.waiting(T0 + 9 * NS) is None


def test_thirty_trials_give_thirty_rows(tracker):
    for n in range(30):
        digit = n % 10
        run_in_order(tracker, other_stamp(n * 10), true=digit,
                     pred=digit if n % 7 else (digit + 1) % 10, trial=n + 1)
    assert len(tracker.rows) == 30
    counted = [r for r in tracker.rows if r['correct'] is not None]
    assert len(counted) == 30
    assert sum(1 for r in counted if not r['correct']) == 5


def test_perception_health():
    assert perception_health(0, 1.0)[0] == 'red'
    assert perception_health(0, None)[0] == 'red'
    assert perception_health(1, None)[0] == 'amber'
    assert perception_health(1, 3.0)[0] == 'green'
    assert perception_health(1, 10.0)[0] == 'green'
    assert perception_health(1, 10.1)[0] == 'red'
    assert perception_health(None, 12.0)[0] == 'red'      # graph unknown, silent
    assert perception_health(None, 2.0)[0] == 'green'
