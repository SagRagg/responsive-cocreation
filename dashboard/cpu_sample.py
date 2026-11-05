#!/usr/bin/env python3
"""Log the CPU and memory use of named processes while a run is going.

Reads /proc (Linux) with the standard library only, every few seconds, so the
sampler itself costs next to nothing. CPU is a percentage of one core.

Output CSV columns (one row per watched process per sample):
  time_s   wall-clock epoch seconds of the sample
  name     the matched script file name
  pid      process id
  cpu_pct  CPU time used since the previous sample, % of one core
           (so 4 busy cores on a Pi 5 can show up to 400)
  rss_mb   resident memory in MB (10^6 bytes)

  cpu_sample.py --out run.csv --match mnist_perception_node.py --match telemetry_dashboard.py
  cpu_sample.py --summary run.csv
"""

import argparse
import csv
import os
import signal
import sys
import time

COLUMNS = ('time_s', 'name', 'pid', 'cpu_pct', 'rss_mb')


def script_name(tokens, names):
    """The wanted script this command line runs, or None.

    Only the interpreter and the script count, and a token must be a bare
    path, so a `bash -c '... script.py ...'` wrapper or this sampler's own
    arguments never match.
    """
    for token in tokens[:2]:
        if ' ' in token:
            continue
        base = os.path.basename(token)
        if base in names:
            return base
    return None


def find_processes(names, proc='/proc', skip_pid=None):
    """{pid: script name} for running processes that execute one of `names`."""
    found = {}
    for entry in os.listdir(proc):
        if not entry.isdigit() or int(entry) == skip_pid:
            continue
        try:
            with open(os.path.join(proc, entry, 'cmdline'), 'rb') as f:
                tokens = f.read().decode(errors='replace').split('\0')
        except OSError:
            continue
        name = script_name(tokens, names)
        if name:
            found[int(entry)] = name
    return found


def read_stat(pid, proc='/proc'):
    """(cpu ticks, resident pages) from /proc/<pid>/stat, or None if gone."""
    try:
        with open(os.path.join(proc, str(pid), 'stat')) as f:
            text = f.read()
    except OSError:
        return None
    return parse_stat(text)


def parse_stat(text):
    """(utime + stime ticks, rss pages) from the text of /proc/<pid>/stat."""
    # The command name sits in brackets and may itself contain spaces or
    # brackets, so split after the last closing bracket.
    fields = text[text.rindex(')') + 2:].split()
    # Index 0 here is field 3 (state) of proc(5): utime=14, stime=15, rss=24.
    utime, stime, rss_pages = int(fields[11]), int(fields[12]), int(fields[21])
    return utime + stime, rss_pages


def summarise(rows):
    """{name: stats} from sample rows (dicts with name, cpu_pct, rss_mb)."""
    by_name = {}
    for row in rows:
        by_name.setdefault(row['name'], []).append(
            (float(row['cpu_pct']), float(row['rss_mb'])))
    out = {}
    for name, samples in by_name.items():
        cpu = sorted(c for c, _ in samples)
        out[name] = {
            'samples': len(cpu),
            'cpu_mean': sum(cpu) / len(cpu),
            # Nearest-rank style p95 (no interpolation), unlike the page's
            # latency percentiles; fine for a coarse CPU summary.
            'cpu_p95': cpu[min(len(cpu) - 1, int(0.95 * len(cpu)))],
            'cpu_max': cpu[-1],
            'rss_max_mb': max(r for _, r in samples),
        }
    return out


def format_summary(stats, cores):
    """Plain-text table of `summarise` output, one line per process."""
    lines = [f'CPU as % of one core ({cores} cores on this machine)',
             f'{"process":<28}{"samples":>8}{"mean":>8}{"p95":>8}{"max":>8}{"rss MB":>9}']
    for name in sorted(stats):
        s = stats[name]
        lines.append(f'{name:<28}{s["samples"]:>8}{s["cpu_mean"]:>8.1f}'
                     f'{s["cpu_p95"]:>8.1f}{s["cpu_max"]:>8.1f}{s["rss_max_mb"]:>9.0f}')
    return '\n'.join(lines)


def read_rows(path):
    """Rows of a sample CSV as dicts."""
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


def sample(names, out_path, every_s, proc='/proc'):
    """Append one row per watched process to `out_path` every `every_s` s.

    Runs until SIGINT, SIGTERM or SIGHUP (tmux closing the window). Processes
    are looked up again on every pass, so a restarted node is picked up.
    """
    ticks_per_s = os.sysconf('SC_CLK_TCK')
    page_mb = os.sysconf('SC_PAGE_SIZE') / 1e6
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    previous = {}                                   # pid -> (ticks, monotonic)

    def stop(*_):
        raise SystemExit(0)
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)

    with open(out_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        f.flush()
        while True:
            now = time.monotonic()
            for pid, name in find_processes(names, proc, os.getpid()).items():
                stat = read_stat(pid, proc)
                if stat is None:
                    continue
                ticks, pages = stat
                # CPU% needs two readings: a pid's first pass only primes
                # `previous`, so a new process shows up one interval later.
                # Monotonic time for the interval, so a clock step from
                # chrony cannot distort it.
                if pid in previous:
                    last_ticks, last_t = previous[pid]
                    cpu = 100.0 * (ticks - last_ticks) / ticks_per_s / (now - last_t)
                    writer.writerow([f'{time.time():.1f}', name, pid,
                                     f'{cpu:.1f}', f'{pages * page_mb:.1f}'])
                previous[pid] = (ticks, now)
            f.flush()
            time.sleep(every_s)


def main():
    """Command line: sample with --out/--match, or print --summary of a CSV."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', help='CSV to write samples to')
    parser.add_argument('--match', action='append', default=[],
                        help='script file name to watch (repeatable)')
    parser.add_argument('--every', type=float, default=2.0, help='seconds between samples')
    parser.add_argument('--summary', help='print the summary of a sample CSV and exit')
    args = parser.parse_args()

    if args.summary:
        stats = summarise(read_rows(args.summary))
        if not stats:
            sys.exit('no samples in ' + args.summary)
        print(format_summary(stats, os.cpu_count()))
        return
    if not args.out or not args.match:
        parser.error('--out and at least one --match are needed (or use --summary)')
    sample(set(args.match), args.out, args.every)


if __name__ == '__main__':
    main()
