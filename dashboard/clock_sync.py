"""Clock offset from `chronyc tracking`, polled in a background thread."""

import re
import subprocess
import threading

_SYSTEM_TIME = re.compile(
    r'^System time\s*:\s*([0-9.eE+-]+) seconds (fast|slow) of NTP time', re.M)
_STRATUM = re.compile(r'^Stratum\s*:\s*(\d+)', re.M)


def parse_tracking(text):
    """Signed offset in ms (positive = this clock is fast) and stratum.

    Returns a dict shaped like the `chrony` field of the dashboard updates.
    """
    match = _SYSTEM_TIME.search(text)
    if not match:
        return {'available': False, 'offset_ms': None, 'stratum': None,
                'error': 'unexpected chronyc output'}
    offset_ms = float(match.group(1)) * 1000.0
    if match.group(2) == 'slow':
        offset_ms = -offset_ms
    stratum = _STRATUM.search(text)
    return {'available': True, 'offset_ms': round(offset_ms, 4),
            'stratum': int(stratum.group(1)) if stratum else None,
            'error': None}


def _query():
    try:
        out = subprocess.run(['chronyc', 'tracking'], capture_output=True,
                             text=True, timeout=2)
    except FileNotFoundError:
        return {'available': False, 'offset_ms': None, 'stratum': None,
                'error': 'chronyc not installed'}
    except subprocess.TimeoutExpired:
        return {'available': False, 'offset_ms': None, 'stratum': None,
                'error': 'chronyc timed out'}
    if out.returncode != 0:
        return {'available': False, 'offset_ms': None, 'stratum': None,
                'error': (out.stderr or out.stdout).strip()[:120] or 'chronyc failed'}
    return parse_tracking(out.stdout)


class ClockSyncPoller:
    """Runs `chronyc tracking` every `period_s` seconds (a few ms of work)."""

    def __init__(self, period_s=10.0):
        self.period_s = period_s
        self._status = {'available': False, 'offset_ms': None, 'stratum': None,
                        'error': 'not polled yet'}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def status(self):
        return dict(self._status)

    def _run(self):
        while not self._stop.is_set():
            self._status = _query()
            self._stop.wait(self.period_s)
