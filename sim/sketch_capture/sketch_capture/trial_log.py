"""CSV ground-truth log: one row per published trial."""

import csv
import os

COLUMNS = ('trial_number', 'mnist_index', 'true_label',
           'publish_stamp_sec', 'publish_stamp_nanosec')


class TrialLog:
    def __init__(self, path):
        self.path = os.path.abspath(os.path.expanduser(path))
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._file = open(self.path, 'w', newline='')
        self._writer = csv.writer(self._file)
        self._writer.writerow(COLUMNS)
        self._file.flush()

    def write(self, trial_number, mnist_index, true_label, stamp_sec, stamp_nanosec):
        self._writer.writerow(
            [trial_number, mnist_index, true_label, stamp_sec, stamp_nanosec])
        self._file.flush()

    def close(self):
        if not self._file.closed:
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
