"""HTTP side of the dashboard: the page, a history snapshot, saved runs and an
SSE stream. Standard library only; it never touches ROS, so it runs in its own
thread beside the spin loop.

Routes (GET only):
  /, /index.html   static/index.html
  /history.json    get_history(): all rows of the current run
  /runs.json       list_runs(csv_dir): saved run CSVs
  /runs/<name>     one saved CSV; the name must match _RUN_NAME, so no paths
  /events          Server-Sent Events, one `data:` line per update
"""

import json
import os
import queue
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_RUN_NAME = re.compile(r'^[A-Za-z0-9_.-]+\.csv$')
_CLIENT_QUEUE = 20


class Hub:
    """Fan-out of the latest update (a JSON string) to every SSE client."""

    def __init__(self):
        self._lock = threading.Lock()
        self._clients = set()
        self.latest = None

    def publish(self, text):
        """Store `text` as the latest update and queue it for every client."""
        with self._lock:
            self.latest = text
            for q in self._clients:
                if q.full():
                    try:
                        q.get_nowait()      # a slow browser loses old updates
                    except queue.Empty:
                        pass
                q.put_nowait(text)

    def subscribe(self):
        """New client queue, primed with the latest update so the page fills at once."""
        q = queue.Queue(maxsize=_CLIENT_QUEUE)
        with self._lock:
            if self.latest is not None:
                q.put_nowait(self.latest)
            self._clients.add(q)
        return q

    def unsubscribe(self, q):
        """Forget a client queue (its connection closed)."""
        with self._lock:
            self._clients.discard(q)

    def client_count(self):
        """Number of connected SSE clients."""
        with self._lock:
            return len(self._clients)


def list_runs(csv_dir):
    """Saved run CSVs in `csv_dir`, newest first, for /runs.json.

    Only files whose header starts with `placement,trial` count, so the CPU
    sample CSVs in the same folder are skipped. Each entry has name,
    placement (from the first row, else the file name prefix), rows (data
    rows), size (bytes) and mtime (epoch seconds).
    """
    runs = []
    try:
        names = os.listdir(csv_dir)
    except OSError:
        return runs
    for name in names:
        if not _RUN_NAME.match(name):
            continue
        path = os.path.join(csv_dir, name)
        try:
            stat = os.stat(path)
            with open(path, newline='') as f:
                header = f.readline()
                if not header.startswith('placement,trial'):
                    continue
                first = f.readline().split(',', 1)[0].strip()
                rows = sum(1 for line in f if line.strip()) + (1 if first else 0)
        except OSError:
            continue
        runs.append({'name': name, 'placement': first or name.split('_', 1)[0],
                     'rows': rows, 'size': stat.st_size, 'mtime': stat.st_mtime})
    runs.sort(key=lambda r: r['mtime'], reverse=True)
    return runs


def make_server(bind, port, static_dir, hub, get_history, csv_dir):
    """Build (not start) the HTTP server. `get_history()` returns a JSON-able dict."""
    csv_dir = os.path.abspath(os.path.expanduser(csv_dir))

    class Handler(BaseHTTPRequestHandler):
        """Request handler bound to this server's static dir, hub and csv_dir."""

        def log_message(self, *args):
            pass                              # keep the Pi's CPU and terminal quiet

        def _send(self, code, body, ctype, extra=None):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj):
            self._send(200, json.dumps(obj).encode(), 'application/json')

        def do_GET(self):
            path = self.path.split('?', 1)[0]
            if path in ('/', '/index.html'):
                try:
                    with open(os.path.join(static_dir, 'index.html'), 'rb') as f:
                        body = f.read()
                except OSError:
                    return self._send(404, b'index.html missing', 'text/plain')
                return self._send(200, body, 'text/html; charset=utf-8')
            if path == '/history.json':
                return self._json(get_history())
            if path == '/runs.json':
                return self._json(list_runs(csv_dir))
            if path.startswith('/runs/'):
                return self._serve_run(path[len('/runs/'):])
            if path == '/events':
                return self._stream()
            if path == '/favicon.ico':
                return self._send(204, b'', 'image/x-icon')
            self._send(404, b'not found', 'text/plain')

        def _serve_run(self, name):
            if not _RUN_NAME.match(name):
                return self._send(404, b'not found', 'text/plain')
            try:
                with open(os.path.join(csv_dir, name), 'rb') as f:
                    body = f.read()
            except OSError:
                return self._send(404, b'not found', 'text/plain')
            self._send(200, body, 'text/csv; charset=utf-8')

        def _stream(self):
            """Hold the connection open and write each hub update as an SSE event.

            A comment line goes out after 15 s of silence so idle connections
            are kept alive and a closed browser is noticed by the failed write.
            """
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Accel-Buffering', 'no')
            self.end_headers()
            q = hub.subscribe()
            try:
                while True:
                    try:
                        text = q.get(timeout=15)
                        self.wfile.write(f'data: {text}\n\n'.encode())
                    except queue.Empty:
                        self.wfile.write(b': keepalive\n\n')
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                hub.unsubscribe(q)

    server = ThreadingHTTPServer((bind, port), Handler)
    server.daemon_threads = True
    return server
