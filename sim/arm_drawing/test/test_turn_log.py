import csv

from arm_drawing.turn_log import COLUMNS, TurnLog


def test_rows_latency_and_blanks(tmp_path):
    path = tmp_path / 'nested' / 'turns.csv'
    with TurnLog(str(path)) as log:
        log.write({'trial_number': 1, 'digit': 7, 'confidence': 0.5,
                   'source_stamp_ns': 1_000_000_000,
                   'strokes_rx_ns': 1_012_345_678, 'status': 'ok'})
        log.write({'status': 'bad_message'})
    with open(path, newline='') as f:
        rows = list(csv.DictReader(f))
    assert tuple(rows[0]) == COLUMNS
    assert rows[0]['strokes_latency_ms'] == '12.346'
    assert rows[0]['digit_rx_ns'] == ''
    assert rows[1]['status'] == 'bad_message'
    assert rows[1]['strokes_latency_ms'] == ''
