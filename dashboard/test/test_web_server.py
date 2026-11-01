import json
import threading
import urllib.error
import urllib.request

import pytest

from clock_sync import parse_tracking
from trial_tracker import CSV_COLUMNS
from web_server import Hub, list_runs, make_server

HEADER = ','.join(CSV_COLUMNS) + '\n'


@pytest.fixture
def served(tmp_path):
    static = tmp_path / 'static'
    static.mkdir()
    (static / 'index.html').write_text('<title>dash</title>')
    logs = tmp_path / 'logs'
    logs.mkdir()
    (logs / 'edge_a.csv').write_text(
        HEADER + 'edge,1,5,1,2,3,3,0.9,1,40,20,20,5000,ok\n'
        'edge,2,6,3,4,4,4,0.9,1,41,21,20,5000,ok\n')
    (logs / 'notes.csv').write_text('a,b\n1,2\n')      # not a run file
    (tmp_path / 'secret.csv').write_text('top secret')
    hub = Hub()
    history = {'placement': 'edge', 'rows': [], 'total': 0}
    server = make_server('127.0.0.1', 0, str(static), hub, lambda: history,
                         str(logs))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_address[1]}', hub, logs
    server.shutdown()
    server.server_close()


def get(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return r.status, r.headers, r.read()


def test_page_and_history(served):
    base, _, _ = served
    status, headers, body = get(base + '/')
    assert status == 200 and b'<title>dash</title>' in body
    assert headers['Content-Type'].startswith('text/html')
    assert json.loads(get(base + '/history.json')[2]) == {
        'placement': 'edge', 'rows': [], 'total': 0}


def test_runs_listing_and_download(served):
    base, _, logs = served
    runs = json.loads(get(base + '/runs.json')[2])
    assert [r['name'] for r in runs] == ['edge_a.csv']
    assert runs[0]['placement'] == 'edge' and runs[0]['rows'] == 2
    status, _, body = get(base + '/runs/edge_a.csv')
    assert status == 200 and body.startswith(b'placement,trial')


@pytest.mark.parametrize('path', ['/runs/../secret.csv', '/runs/%2e%2e/secret.csv',
                                  '/runs/missing.csv', '/runs/edge_a.txt', '/nope'])
def test_bad_paths_are_404(served, path):
    base, _, _ = served
    with pytest.raises(urllib.error.HTTPError) as err:
        get(base + path)
    assert err.value.code == 404


def test_event_stream_sends_latest_then_new_updates(served):
    base, hub, _ = served
    hub.publish('{"n": 1}')
    resp = urllib.request.urlopen(base + '/events', timeout=3)
    assert resp.headers['Content-Type'] == 'text/event-stream'
    assert resp.readline() == b'data: {"n": 1}\n'
    resp.readline()
    hub.publish('{"n": 2}')
    assert resp.readline() == b'data: {"n": 2}\n'
    resp.close()


def test_hub_drops_oldest_for_a_slow_client():
    hub = Hub()
    q = hub.subscribe()
    for n in range(100):
        hub.publish(str(n))
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    assert items[-1] == '99' and len(items) <= 20
    hub.unsubscribe(q)
    assert hub.client_count() == 0


def test_list_runs_missing_dir(tmp_path):
    assert list_runs(str(tmp_path / 'nope')) == []


def test_parse_chrony_tracking():
    sample = (
        'Reference ID    : C0A80101 (192.168.1.1)\n'
        'Stratum         : 3\n'
        'System time     : 0.000012345 seconds fast of NTP time\n'
        'Last offset     : +0.000010000 seconds\n')
    assert parse_tracking(sample) == {
        'available': True, 'offset_ms': 0.0123, 'stratum': 3, 'error': None}
    slow = sample.replace('fast', 'slow')
    assert parse_tracking(slow)['offset_ms'] == -0.0123
    bad = parse_tracking('506 Cannot talk to daemon')
    assert bad['available'] is False and bad['offset_ms'] is None
