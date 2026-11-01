"""Pairs the pipeline's messages into trials and works out the latencies.

No ROS imports, so it runs (and is tested) anywhere. Every trial is keyed by
the `/sketch_image` header stamp (sec, nanosec). `/ground_truth` and
`/strokes` carry that stamp; `/digit_prediction` and `/turn_done` do not, so
they go to the one trial in flight (capture keeps a single sketch out per
turn). Trial numbers are only reported, never used to pair, because the
perception node's counter can drift from capture's.

All receive times are integer nanoseconds from the same clock that stamps the
sketch (`time.time_ns()`), so the subtraction needs no float rounding.
"""

import base64
import csv
import json
import os
import threading
from collections import OrderedDict, deque

CSV_COLUMNS = (
    'placement', 'trial', 'mnist_index', 'stamp_sec', 'stamp_nanosec',
    'true_digit', 'pred_digit', 'confidence', 'correct',
    'e2e_ms', 'compute_ms', 'network_ms', 'turn_ms', 'status')

STATUS_OK = 'ok'
STATUS_TIMEOUT = 'timeout'            # no /turn_done within trial_timeout_s
STATUS_SUPERSEDED = 'superseded'      # a newer sketch arrived first
STATUS_NO_STROKES = 'no_strokes'      # /turn_done arrived but /strokes never did

TOPICS = ('/sketch_image', '/ground_truth', '/digit_prediction',
          '/strokes', '/turn_done')

STALE_S = 10.0   # a topic or node silent for longer than this is shown red

_NS = 1_000_000_000
_KEEP_FINISHED_KEYS = 2000


def _ms(ns):
    return round(ns / 1e6, 3)


def _stamp_ns(stamp):
    return stamp[0] * _NS + stamp[1]


def _parse_stamp(obj):
    """(sec, nanosec) from a {'sec', 'nanosec'} dict, or None if unusable."""
    try:
        return int(obj['sec']), int(obj['nanosec'])
    except (KeyError, TypeError, ValueError):
        return None


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Trial:
    """Everything seen so far for one sketch stamp."""

    def __init__(self, key, first_seen_ns):
        self.key = key
        self.first_seen_ns = first_seen_ns
        self.sketch_ns = None
        self.truth_ns = None
        self.pred_ns = None
        self.strokes_ns = None
        self.done_ns = None
        self.image = None            # (bytes, width, height)
        self.mnist_index = None
        self.truth_trial = None
        self.true_digit = None
        self.topic_digit = None      # from /digit_prediction
        self.strokes_trial = None
        self.strokes_digit = None
        self.confidence = None
        self.publish_ns = None       # optional `publish_stamp` in /strokes
        self.status = None

    @property
    def start_ns(self):
        return self.sketch_ns if self.sketch_ns is not None else self.first_seen_ns

    @property
    def pred_digit(self):
        return self.strokes_digit if self.strokes_digit is not None else self.topic_digit

    @property
    def trial(self):
        return self.truth_trial if self.truth_trial is not None else self.strokes_trial

    def state(self):
        if self.status == STATUS_TIMEOUT:
            return 'timeout'
        if self.status is not None:
            return 'done'
        if self.strokes_ns is not None:
            return 'waiting_turn_done'
        return 'waiting_prediction'

    def latencies(self):
        """(e2e, compute, network, turn) in ms; None where an input is missing."""
        stamp = _stamp_ns(self.key)
        e2e = _ms(self.strokes_ns - stamp) if self.strokes_ns is not None else None
        compute = None
        if self.strokes_ns is not None and self.sketch_ns is not None:
            # publish_stamp (perception's own clock, same machine as ours)
            # beats our receive time of /strokes when the node provides it.
            end = self.publish_ns if self.publish_ns is not None else self.strokes_ns
            if end >= self.sketch_ns:
                compute = _ms(end - self.sketch_ns)
        network = round(e2e - compute, 3) if e2e is not None and compute is not None else None
        turn = _ms(self.done_ns - stamp) if self.done_ns is not None else None
        return e2e, compute, network, turn


class TrialTracker:
    def __init__(self, placement, timeout_s=30.0, on_finish=None):
        self.placement = placement
        self.timeout_ns = int(timeout_s * _NS)
        self.on_finish = on_finish
        self.rows = []                     # finished trials, oldest first
        self.orphans = 0                   # keyless messages with no trial in flight
        self.bad_messages = 0              # unparseable JSON
        self._open = OrderedDict()         # key -> Trial, in creation order
        self._finished_keys = set()
        self._finished_order = deque()
        self._last = None                  # most recently touched Trial
        self._lock = threading.RLock()

    # ---- inputs -----------------------------------------------------------

    def on_sketch(self, stamp, recv_ns, image=None, width=None, height=None):
        with self._lock:
            trial = self._get(stamp, recv_ns)
            if trial is None:
                return
            if trial.sketch_ns is None:
                trial.sketch_ns = recv_ns
            if image is not None and trial.image is None:
                trial.image = (bytes(image), width, height)

    def on_ground_truth(self, text, recv_ns):
        data = self._load(text)
        stamp = _parse_stamp(data.get('stamp')) if data else None
        if stamp is None:
            return
        with self._lock:
            trial = self._get(stamp, recv_ns)
            if trial is None:
                return
            trial.truth_ns = recv_ns
            trial.mnist_index = _as_int(data.get('mnist_index'))
            trial.truth_trial = _as_int(data.get('trial'))
            trial.true_digit = _as_int(data.get('digit'))

    def on_prediction(self, digit, recv_ns):
        with self._lock:
            trial = self._in_flight()
            if trial is None:
                self.orphans += 1
                return
            if trial.pred_ns is None:
                trial.pred_ns = recv_ns
                trial.topic_digit = _as_int(digit)

    def on_strokes(self, text, recv_ns):
        data = self._load(text)
        stamp = _parse_stamp(data.get('source_stamp')) if data else None
        if stamp is None:
            return
        with self._lock:
            trial = self._get(stamp, recv_ns)
            if trial is None or trial.strokes_ns is not None:
                return
            trial.strokes_ns = recv_ns
            trial.strokes_trial = _as_int(data.get('trial'))
            trial.strokes_digit = _as_int(data.get('digit'))
            trial.confidence = _as_float(data.get('confidence'))
            publish = _parse_stamp(data.get('publish_stamp'))
            if publish is not None:
                trial.publish_ns = _stamp_ns(publish)

    def on_turn_done(self, recv_ns):
        with self._lock:
            trial = self._in_flight()
            if trial is None:
                self.orphans += 1
                return
            trial.done_ns = recv_ns
            self._finish(trial, STATUS_OK if trial.strokes_ns is not None
                         else STATUS_NO_STROKES)

    def tick(self, now_ns):
        """Close trials that have waited longer than the timeout."""
        with self._lock:
            for trial in list(self._open.values()):
                if now_ns - trial.start_ns >= self.timeout_ns:
                    self._finish(trial, STATUS_TIMEOUT)

    # ---- outputs ----------------------------------------------------------

    def rows_since(self, seq):
        """Finished rows with a seq greater than `seq` (-1 gives all)."""
        with self._lock:
            return list(self.rows[seq + 1:])

    def snapshot_rows(self):
        with self._lock:
            return list(self.rows)

    def current(self, now_ns):
        """The trial in flight, or the latest finished one, as a JSON-able dict."""
        with self._lock:
            trial = self._in_flight() or self._last
            if trial is None:
                return None
            e2e, compute, _, turn = trial.latencies()
            image_b64 = width = height = None
            if trial.image is not None:
                image_b64 = base64.b64encode(trial.image[0]).decode('ascii')
                width, height = trial.image[1], trial.image[2]
            end = trial.done_ns if trial.done_ns is not None else now_ns
            return {
                'stamp_sec': trial.key[0], 'stamp_nanosec': trial.key[1],
                'trial': trial.trial, 'mnist_index': trial.mnist_index,
                'true_digit': trial.true_digit, 'pred_digit': trial.pred_digit,
                'confidence': trial.confidence, 'state': trial.state(),
                'e2e_ms': e2e, 'compute_ms': compute, 'turn_ms': turn,
                'elapsed_s': round(max(0, end - trial.start_ns) / 1e9, 1),
                'image_b64': image_b64, 'width': width, 'height': height,
            }

    def waiting(self, now_ns):
        """(state, seconds) of the trial in flight, or None when idle."""
        with self._lock:
            trial = self._in_flight()
            if trial is None:
                return None
            return trial.state(), (now_ns - trial.start_ns) / 1e9

    # ---- internals --------------------------------------------------------

    def _load(self, text):
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            data = None
        if not isinstance(data, dict):
            with self._lock:
                self.bad_messages += 1
            return None
        return data

    def _in_flight(self):
        if not self._open:
            return None
        return next(reversed(self._open.values()))

    def _get(self, key, recv_ns):
        """The open trial for `key`, creating it; None for a trial already closed."""
        trial = self._open.get(key)
        if trial is not None:
            self._last = trial
            return trial
        if key in self._finished_keys:
            return None            # late message for a closed trial
        for older in list(self._open.values()):
            self._finish(older, STATUS_SUPERSEDED)
        trial = Trial(key, recv_ns)
        self._open[key] = trial
        self._last = trial
        return trial

    def _finish(self, trial, status):
        trial.status = status
        del self._open[trial.key]
        self._finished_keys.add(trial.key)
        self._finished_order.append(trial.key)
        if len(self._finished_order) > _KEEP_FINISHED_KEYS:
            self._finished_keys.discard(self._finished_order.popleft())
        row = self._row(trial, len(self.rows))
        self.rows.append(row)
        if self.on_finish is not None:
            self.on_finish(row)

    def _row(self, trial, seq):
        e2e, compute, network, turn = trial.latencies()
        pred = trial.pred_digit
        correct = None
        if trial.true_digit is not None and pred is not None:
            correct = trial.true_digit == pred
        return {
            'seq': seq,
            'placement': self.placement,
            'trial': trial.trial,
            'mnist_index': trial.mnist_index,
            'stamp_sec': trial.key[0],
            'stamp_nanosec': trial.key[1],
            'true_digit': trial.true_digit,
            'pred_digit': pred,
            'confidence': trial.confidence,
            'correct': correct,
            'e2e_ms': e2e,
            'compute_ms': compute,
            'network_ms': network,
            'turn_ms': turn,
            'status': trial.status,
        }


def perception_health(strokes_publishers, strokes_age_s):
    """Status of the perception node from the graph and the /strokes silence.

    Returns (colour, reason). `strokes_publishers` is None when unknown.
    """
    if strokes_publishers == 0:
        return 'red', 'no node is publishing /strokes'
    if strokes_age_s is None:
        return 'amber', 'waiting for the first /strokes'
    if strokes_age_s > STALE_S:
        return 'red', f'no /strokes for {strokes_age_s:.0f} s'
    return 'green', f'last /strokes {strokes_age_s:.1f} s ago'


class CsvLog:
    """One CSV per run. The file is created on the first finished trial, so
    starting and stopping the dashboard leaves nothing behind."""

    def __init__(self, csv_dir, run_id):
        self.dir = os.path.abspath(os.path.expanduser(csv_dir))
        self.run_id = run_id
        self.path = None
        self._file = None
        self._writer = None

    def write(self, row):
        if self._file is None:
            os.makedirs(self.dir, exist_ok=True)
            self.path = self._free_path()
            self._file = open(self.path, 'w', newline='')
            self._writer = csv.writer(self._file)
            self._writer.writerow(CSV_COLUMNS)
        self._writer.writerow([_cell(c, row.get(c)) for c in CSV_COLUMNS])
        self._file.flush()

    def close(self):
        if self._file is not None and not self._file.closed:
            self._file.close()

    def _free_path(self):
        base = os.path.join(self.dir, self.run_id)
        path, n = base + '.csv', 1
        while os.path.exists(path):
            n += 1
            path = f'{base}_{n}.csv'
        return path


def _cell(column, value):
    if value is None:
        return ''
    if column == 'correct':
        return 1 if value else 0
    if column == 'confidence':
        return f'{value:.6f}'
    if column.endswith('_ms'):
        return f'{value:.3f}'
    return value
