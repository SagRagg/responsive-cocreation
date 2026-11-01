import csv

from trial_tracker import CSV_COLUMNS, CsvLog, TrialTracker

NS = 1_000_000_000
MS = 1_000_000


def row(**over):
    base = {'seq': 0, 'placement': 'cloud', 'trial': 4, 'mnist_index': 12,
            'stamp_sec': 1761540000, 'stamp_nanosec': 5, 'true_digit': 3,
            'pred_digit': 3, 'confidence': 0.99812345678, 'correct': True,
            'e2e_ms': 41.2, 'compute_ms': 22.9, 'network_ms': 18.3,
            'turn_ms': 5300.1234, 'status': 'ok'}
    base.update(over)
    return base


def read(path):
    with open(path, newline='') as f:
        return list(csv.reader(f))


def test_columns_are_the_agreed_ones():
    assert CSV_COLUMNS == (
        'placement', 'trial', 'mnist_index', 'stamp_sec', 'stamp_nanosec',
        'true_digit', 'pred_digit', 'confidence', 'correct',
        'e2e_ms', 'compute_ms', 'network_ms', 'turn_ms', 'status')


def test_file_is_created_on_first_row_only(tmp_path):
    log = CsvLog(str(tmp_path / 'logs'), 'edge_run')
    assert not (tmp_path / 'logs').exists()
    log.close()
    assert not (tmp_path / 'logs').exists()


def test_header_and_row_formatting(tmp_path):
    log = CsvLog(str(tmp_path / 'logs'), 'cloud_run')
    log.write(row())
    log.write(row(seq=1, correct=False, true_digit=None, confidence=None,
                  e2e_ms=None, compute_ms=None, network_ms=None,
                  turn_ms=None, status='timeout'))
    rows = read(log.path)
    assert log.path == str(tmp_path / 'logs' / 'cloud_run.csv')
    assert tuple(rows[0]) == CSV_COLUMNS
    assert rows[1] == ['cloud', '4', '12', '1761540000', '5', '3', '3',
                       '0.998123', '1', '41.200', '22.900', '18.300',
                       '5300.123', 'ok']
    assert rows[2][5] == '' and rows[2][7] == '' and rows[2][9:13] == [''] * 4
    assert rows[2][8] == '0' and rows[2][13] == 'timeout'


def test_unknown_correct_is_blank(tmp_path):
    log = CsvLog(str(tmp_path), 'r')
    log.write(row(correct=None))
    assert read(log.path)[1][8] == ''


def test_rows_are_flushed_before_close(tmp_path):
    log = CsvLog(str(tmp_path), 'r')
    log.write(row())
    assert len(read(log.path)) == 2          # header + row, file still open
    log.close()


def test_same_run_id_never_overwrites(tmp_path):
    first = CsvLog(str(tmp_path), 'edge_x')
    first.write(row())
    second = CsvLog(str(tmp_path), 'edge_x')
    second.write(row(trial=9))
    assert first.path != second.path
    assert read(first.path)[1][1] == '4'
    assert read(second.path)[1][1] == '9'


def test_tilde_in_csv_dir_is_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    log = CsvLog('~/dashboard_logs', 'r')
    log.write(row())
    assert log.path == str(tmp_path / 'dashboard_logs' / 'r.csv')


def test_tracker_writes_one_csv_row_per_trial(tmp_path):
    log = CsvLog(str(tmp_path), 'edge_run')
    tracker = TrialTracker('edge', 30, log.write)
    for n in range(30):
        stamp = (1761540000 + n * 10, 7)
        t0 = stamp[0] * NS + 7
        digit = n % 10
        tracker.on_sketch(stamp, t0 + MS, None)
        tracker.on_ground_truth(
            '{"trial": %d, "mnist_index": %d, "digit": %d, "stamp": '
            '{"sec": %d, "nanosec": 7}}' % (n + 1, n, digit, stamp[0]), t0 + MS)
        tracker.on_strokes(
            '{"trial": %d, "digit": %d, "confidence": 0.9, "source_stamp": '
            '{"sec": %d, "nanosec": 7}}' % (n + 1, digit, stamp[0]), t0 + 30 * MS)
        tracker.on_turn_done(t0 + 4000 * MS)
    rows = read(log.path)
    assert len(rows) == 31                   # header + 30 trials
    assert {r[0] for r in rows[1:]} == {'edge'}
    # confusion matrix over the CSV sums to the trial count
    matrix = [[0] * 10 for _ in range(10)]
    for r in rows[1:]:
        matrix[int(r[5])][int(r[6])] += 1
    assert sum(map(sum, matrix)) == 30
