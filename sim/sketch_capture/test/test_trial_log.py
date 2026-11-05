"""Tests for the sketch_capture trial CSV (sketch_capture.trial_log)."""

import csv

from sketch_capture.trial_log import COLUMNS, TrialLog


def test_rows_and_parent_dir(tmp_path):
    path = tmp_path / 'nested' / 'dir' / 'trials.csv'
    with TrialLog(str(path)) as log:
        log.write(1, 6788, 3, 1760000000, 123456789)
        log.write(2, 12, 7, 1760000005, 5)
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    assert tuple(rows[0]) == COLUMNS
    assert rows[1] == ['1', '6788', '3', '1760000000', '123456789']
    assert rows[2] == ['2', '12', '7', '1760000005', '5']


def test_rows_flushed_before_close(tmp_path):
    """Rows reach disk immediately, so a run that is killed keeps its log."""
    path = tmp_path / 'trials.csv'
    log = TrialLog(str(path))
    log.write(1, 0, 7, 1, 2)
    assert len(path.read_text().splitlines()) == 2
    log.close()
