"""CSV timing log: one row per drawn turn.

All times are ROS time in integer nanoseconds, taken on the drawing node's
clock. Columns:

- trial_number, digit, confidence: from the /strokes payload.
- source_stamp_ns: the /sketch_image header.stamp echoed back in /strokes.
- digit_rx_ns: when the preceding /digit_prediction arrived (blank if none).
- strokes_rx_ns: when /strokes arrived.
- goal_sent_ns, goal_done_ns: trajectory goal sent and result received.
- turn_done_ns: when /turn_done was published.
- strokes_latency_ms: strokes_rx_ns - source_stamp_ns, the sketch-to-strokes
  latency (only meaningful with clocks synced across machines).
- status: 'ok' or what went wrong.

Rows join with the sketch_capture CSV on trial number, or more robustly on
source_stamp_ns = publish_stamp_sec * 1e9 + publish_stamp_nanosec, since
the perception node's trial counter can drift from capture's.
"""

import csv
import os

COLUMNS = ('trial_number', 'digit', 'confidence', 'source_stamp_ns',
           'digit_rx_ns', 'strokes_rx_ns', 'goal_sent_ns', 'goal_done_ns',
           'turn_done_ns', 'strokes_latency_ms', 'status')


def latency_ms(source_ns, rx_ns):
    """Return `rx_ns - source_ns` in ms as text (3 decimals), or '' if
    either stamp is missing."""
    if source_ns is None or rx_ns is None:
        return ''
    return f'{(rx_ns - source_ns) / 1e6:.3f}'


class TurnLog:
    """Append-only CSV writer for drawn turns; usable as a context manager.

    Creates the parent folder, truncates any existing file and writes the
    header row. Every row is flushed at once so a crashed run keeps its data.
    """

    def __init__(self, path):
        """Open `path` (``~`` is expanded) and write the header."""
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
        """Close the file; safe to call more than once."""
        if not self._file.closed:
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
