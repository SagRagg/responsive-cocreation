"""CSV timing log: one row per drawn turn.

All times are ROS time in integer nanoseconds. Rows join with the
sketch_capture CSV on trial number.
"""

import csv
import os

COLUMNS = ('trial_number', 'digit', 'confidence', 'source_stamp_ns',
           'digit_rx_ns', 'strokes_rx_ns', 'goal_sent_ns', 'goal_done_ns',
           'turn_done_ns', 'strokes_latency_ms', 'status')


def latency_ms(source_ns, rx_ns):
    if source_ns is None or rx_ns is None:
        return ''
    return f'{(rx_ns - source_ns) / 1e6:.3f}'


class TurnLog:
    def __init__(self, path):
        self.path = os.path.abspath(os.path.expanduser(path))
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._file = open(self.path, 'w', newline='')
        self._writer = csv.writer(self._file)
        self._writer.writerow(COLUMNS)
        self._file.flush()

    def write(self, turn):
        """`turn` is a dict keyed by COLUMNS; missing values become blank.
        `strokes_latency_ms` is filled in from the stamps."""
        row = dict(turn)
        row['strokes_latency_ms'] = latency_ms(
            row.get('source_stamp_ns'), row.get('strokes_rx_ns'))
        self._writer.writerow(
            ['' if row.get(c) is None else row[c] for c in COLUMNS])
        self._file.flush()

    def close(self):
        if not self._file.closed:
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
