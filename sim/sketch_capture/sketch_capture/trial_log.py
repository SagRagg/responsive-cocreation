"""CSV ground-truth log: one row per published trial.

Columns: trial_number (1-based), mnist_index (into the MNIST test split),
true_label, and the /sketch_image header.stamp split into publish_stamp_sec
and publish_stamp_nanosec. The stamp is kept as two integers, exactly as in
the message, so it can be matched to `source_stamp` in /strokes and to the
arm_drawing turn log without float rounding.
"""

import csv
import os

COLUMNS = ('trial_number', 'mnist_index', 'true_label',
           'publish_stamp_sec', 'publish_stamp_nanosec')


class TrialLog:
    """Append-only CSV writer for published trials; usable as a context
    manager.

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

    def write(self, trial_number, mnist_index, true_label, stamp_sec, stamp_nanosec):
        """Write and flush one row, in COLUMNS order."""
        self._writer.writerow(
            [trial_number, mnist_index, true_label, stamp_sec, stamp_nanosec])
        self._file.flush()

    def close(self):
        """Close the file; safe to call more than once."""
        if not self._file.closed:
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
