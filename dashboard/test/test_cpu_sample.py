from cpu_sample import (find_processes, format_summary, parse_stat,
                        read_stat, script_name, summarise)

# pid 7, command name "(py (x) thon)" holds spaces and brackets on purpose.
# fields after it: state=S ... utime=150 (idx 11), stime=50 (idx 12), rss=2560 (idx 21)
STAT = ('7 (py (x) thon) S 1 7 7 0 -1 4194560 100 0 0 0 150 50 0 0 20 0 3 0 '
        '12345 99999999 2560 18446744073709551615')


def fake_proc(tmp_path, entries):
    for pid, cmdline in entries.items():
        d = tmp_path / str(pid)
        d.mkdir()
        (d / 'cmdline').write_bytes('\0'.join(cmdline).encode() + b'\0')
        (d / 'stat').write_text(STAT)
    (tmp_path / 'self').mkdir()          # non-numeric entries are ignored
    return str(tmp_path)


def test_parse_stat_handles_brackets_in_the_command_name():
    assert parse_stat(STAT) == (200, 2560)


def test_read_stat_missing_process_is_none(tmp_path):
    assert read_stat(4242, str(tmp_path)) is None


def test_script_name_matches_the_script_not_a_wrapper():
    names = {'telemetry_dashboard.py'}
    assert script_name(['python3', '/home/x/dashboard/telemetry_dashboard.py',
                        '--ros-args'], names) == 'telemetry_dashboard.py'
    assert script_name(['bash', '-c', 'python3 /x/telemetry_dashboard.py'], names) is None
    assert script_name(['cpu_sample.py', '--match', 'telemetry_dashboard.py'], names) is None
    assert script_name(['vim', 'notes.txt'], names) is None


def test_find_processes(tmp_path):
    proc = fake_proc(tmp_path, {
        101: ['/venv/bin/python', '/r/perception/mnist_perception_node.py'],
        102: ['python3', '/r/dashboard/telemetry_dashboard.py', '--ros-args'],
        103: ['bash'],
        104: ['python3', '/r/dashboard/cpu_sample.py', '--match', 'telemetry_dashboard.py'],
    })
    found = find_processes({'mnist_perception_node.py', 'telemetry_dashboard.py'}, proc)
    assert found == {101: 'mnist_perception_node.py', 102: 'telemetry_dashboard.py'}
    assert find_processes({'telemetry_dashboard.py'}, proc, skip_pid=102) == {}


def test_summarise_and_format():
    rows = [{'name': 'dash', 'cpu_pct': str(c), 'rss_mb': '40'} for c in range(0, 100, 5)]
    rows.append({'name': 'perc', 'cpu_pct': '80.0', 'rss_mb': '900.5'})
    stats = summarise(rows)
    assert stats['dash']['samples'] == 20
    assert stats['dash']['cpu_mean'] == 47.5
    assert stats['dash']['cpu_max'] == 95.0
    assert stats['dash']['cpu_p95'] == 95.0
    assert stats['perc']['rss_max_mb'] == 900.5
    text = format_summary(stats, 4)
    assert 'dash' in text and 'perc' in text and '4 cores' in text
