# dashboard

Live telemetry for the edge-vs-cloud benchmark. One rclpy node that runs on
the **same machine as the perception node** (the Pi 5 for edge, the GCP VM for
cloud), times every trial, writes one CSV row per trial and serves a web page
with latency, accuracy and node health. A separate sampler (`cpu_sample.py`)
logs the CPU and memory of the perception node and the dashboard.

It only subscribes. It publishes nothing and does not touch the perception
node. Only `rclpy` and the Python standard library are used on the backend, and
the page has no external files (no CDN, no fonts), so it works offline.

The topic contract is in [`docs/interfaces.md`](../docs/interfaces.md).

## Run it

For a benchmark run use `scripts/perception_side.sh edge|cloud`, which starts
perception, this dashboard and the CPU sampler in the right order (see
[`scripts/README.md`](../scripts/README.md)). By hand: source ROS 2 Jazzy, then
start the node with `python3` (no build step):

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=30
python3 dashboard/telemetry_dashboard.py --ros-args -p placement:=edge
```

Use `placement:=cloud` on the cloud VM. Then open the page:

| Where | URL |
|---|---|
| Pi (edge) | `http://<pi-ip>:8080` from a laptop on the LAN |
| Cloud VM | `http://<vm-tailscale-ip>:8080` from a laptop on the same tailnet |

On the cloud VM do not open a GCP firewall port. Bind to the Tailscale
address so nothing else can reach the page:

```bash
python3 dashboard/telemetry_dashboard.py --ros-args -p placement:=cloud \
  -p bind:=$(tailscale ip -4)
```

### Start order

1. Perception node.
2. This dashboard.
3. `sketch_capture` (and the arm).

The dashboard is a subscriber on `/sketch_image`, and capture starts as soon as
it sees any subscriber. If the dashboard comes up before perception while
capture is already running, capture publishes trial 1 to the dashboard alone
and the perception node never gets it, so the run stalls.

### One CSV per run

A new CSV is opened each time the dashboard starts, and every trial it sees
goes into it. Restart the dashboard right before each real run (with
perception left running and warm: `scripts/perception_side.sh new-run edge`),
so the CSV holds that run only and not the warm-up or dry-run trials.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `placement` | `edge` | `edge` or `cloud` (anything else is rejected). Shown as a badge and written on every CSV row |
| `port` | `8080` | HTTP port |
| `bind` | `0.0.0.0` | Address to listen on |
| `csv_dir` | `~/dashboard_logs` | Where the run CSVs go (and where the Compare view lists them from) |
| `trial_timeout_s` | `30.0` | A trial with no `/turn_done` this long after its sketch is closed as `timeout` |

## What it measures

| Topic | Type | Used for |
|---|---|---|
| `/sketch_image` | `sensor_msgs/Image` | Opens a trial; its `header.stamp` is the trial key and the latency start. The 28x28 image is shown on the page |
| `/ground_truth` | `std_msgs/String` (JSON) | Trial number, MNIST index and true digit; paired by `stamp` |
| `/strokes` | `std_msgs/String` (JSON) | Predicted digit and confidence; paired by `source_stamp`. Its arrival ends `e2e_ms` and `compute_ms` |
| `/digit_prediction` | `std_msgs/Int32` | Fallback predicted digit if `/strokes` never arrives |
| `/turn_done` | `std_msgs/Bool` | Ends the trial (`turn_ms`) |

Each trial is keyed by the `/sketch_image` `header.stamp`. `/ground_truth` and
`/strokes` (`source_stamp`) carry that stamp. `/digit_prediction` and
`/turn_done` carry none, so they are attached to the single trial in flight.
Trial numbers are shown but never used to pair messages, because the perception
node's counter can drift from capture's. Messages may arrive in any order.

Receive times are taken with `time.time_ns()` (wall clock, integer ns) as the
first thing in each callback. The sketch stamp is set by capture on the
simulation VM when it publishes.

| Column | Definition | Clocks involved |
|---|---|---|
| `e2e_ms` | receive time of `/strokes` here minus the sketch stamp | capture VM and this machine |
| `compute_ms` | receive time of `/strokes` minus receive time of `/sketch_image`, both here. Uses `publish_stamp` from the `/strokes` JSON as the end instead if the perception node provides one | this machine only |
| `network_ms` | `e2e_ms - compute_ms`, which (without `publish_stamp`) works out to sketch stamp to its arrival here: the one-way sketch delivery from the simulation VM | capture VM and this machine |
| `turn_ms` | receive time of `/turn_done` minus the sketch stamp: the whole turn including the arm drawing and the return of `/turn_done` | capture VM and this machine |

`compute_ms` is inference plus the perception node's own handling and local DDS
delivery, not inference alone. If the sketch is received after its strokes,
`compute_ms` and `network_ms` are left empty.

### Clock sync caveat

`e2e_ms`, `network_ms` and `turn_ms` subtract a stamp taken on the simulation
VM from a time taken on the Pi or cloud VM. They are only as accurate as the
clock sync (chrony) between those machines, and any residual offset ends up in
`network_ms`. Only `compute_ms` is measured on one clock. A negative `e2e_ms`
means the clocks disagree; it is kept in the CSV rather than hidden. The page
shows the local `chronyc tracking` offset (polled every 10 s) when `chronyc` is
available; that is this machine's offset from its NTP source, not the offset
to the simulation VM, so check both machines.

### Trial status

A trial is finished when `/turn_done` arrives (`ok`), or after
`trial_timeout_s` (`timeout`). Two more statuses can appear: `superseded` (the
next sketch arrived before `/turn_done`) and `no_strokes` (`/turn_done` came but
`/strokes` never did). Whatever was measured before a trial closed is kept.

## Output

### Run CSV

One CSV per dashboard start in `csv_dir`, named
`<placement>_<YYYYmmdd-HHMMSS>.csv` (`_2`, `_3`, ... appended rather than
overwrite). It is created when the first trial finishes, so starting and
stopping the dashboard leaves no empty file, and it is flushed after every row.
Empty cells mean unknown.

| Column | Meaning | Unit / format |
|---|---|---|
| `placement` | `edge` or `cloud`, from the parameter | text |
| `trial` | capture's trial number from `/ground_truth` (perception's from `/strokes` if there was no ground truth) | integer |
| `mnist_index` | index of the MNIST test image that was drawn | integer |
| `stamp_sec`, `stamp_nanosec` | `/sketch_image` `header.stamp`, the trial key; joins with capture's and perception's logs | s, ns |
| `true_digit` | digit from `/ground_truth` | 0-9 |
| `pred_digit` | digit from `/strokes`, else from `/digit_prediction` | 0-9 |
| `confidence` | model confidence from `/strokes` | 0-1, 6 decimals |
| `correct` | `pred_digit == true_digit` | `1` / `0`, empty if either is missing |
| `e2e_ms` | see above | ms, 3 decimals |
| `compute_ms` | see above | ms, 3 decimals |
| `network_ms` | see above | ms, 3 decimals |
| `turn_ms` | see above | ms, 3 decimals |
| `status` | `ok`, `timeout`, `superseded` or `no_strokes` | text |

### CPU and memory CSV

`cpu_sample.py` reads `/proc` (Linux only) every `--every` seconds (default
2) and writes one row per watched process. `perception_side.sh` starts it as
`cpu_<placement>_<YYYYmmdd-HHMMSS>.csv` in the same folder, watching
`mnist_perception_node.py` and `telemetry_dashboard.py`.

| Column | Meaning | Unit |
|---|---|---|
| `time_s` | wall-clock time of the sample | epoch s, 1 decimal |
| `name` | matched script file name | text |
| `pid` | process id | integer |
| `cpu_pct` | user + system CPU time since the previous sample of that pid, divided by the interval | % of one core (up to 400 on the 4-core Pi 5) |
| `rss_mb` | resident memory | MB (10^6 bytes) |

A process is matched by the script it runs (`python3 <path>/<name>`), not by a
wrapper's command line. Its first sample only primes the counter, so it shows
up one interval after it starts. Summarise a file with:

```bash
python3 dashboard/cpu_sample.py --summary ~/dashboard_logs/cpu_edge_<...>.csv
```

which prints samples, mean, p95 and max CPU and the peak RSS per process
(`perception_side.sh stop` does this for the latest file).

## Page

Live view: input image, predicted vs true digit, rolling (last 30) and overall
accuracy, latency over time with p50/p95/mean tiles, history table (last 200
rows), confusion matrix, topic health, the chrony offset and the placement
badge. A browser refresh, or a reconnect, reloads the history from the node.
If the dashboard is restarted, the page notices the new run id and clears the
old run.

**Compare runs** tab: pick two or more saved CSVs from `csv_dir`, or load
CSVs from your laptop (parsed in the browser, nothing is uploaded), to see
edge and cloud side by side: latency distributions, p50/p95, accuracy and
counts, median per true digit, and the cloud-minus-edge difference when one
run of each is loaded. A live dashboard only ever sees one placement, so this
is where the comparison happens. Latency statistics there use rows with status
`ok` only; the live tiles use every row that has a value. Percentiles are
linearly interpolated (the same as numpy's default).

Health colours: a topic is green under 5 s since its last message, amber up to
10 s, red beyond that. The perception indicator is red when nothing publishes
`/strokes` or when `/strokes` has been silent for more than 10 s. That includes
a long wait for the arm, so a slow drawing can briefly show red.

HTTP endpoints (all GET): `/` the page, `/history.json` all rows of the current
run, `/events` the live update stream (Server-Sent Events, 5 Hz),
`/runs.json` the saved run CSVs, `/runs/<name>.csv` one of them.

## Overhead

The ROS callbacks only record a timestamp and hand the message to the tracker.
The browser gets one update at most every 0.2 s (5 Hz). `chronyc` runs every
10 s. There is no TensorFlow or numpy import. HTTP requests are not logged.
The CPU sampler watches the dashboard too, so its cost is in the CPU CSV.

## Files

| File | Job |
|---|---|
| `telemetry_dashboard.py` | The ROS node: parameters, subscriptions, 5 Hz update, wiring |
| `trial_tracker.py` | Stamp-keyed pairing, latency maths, CSV writer, perception health |
| `web_server.py` | `http.server` page, `/history.json`, `/runs.json`, `/runs/<name>`, SSE `/events` |
| `clock_sync.py` | `chronyc tracking` reader |
| `cpu_sample.py` | CPU and memory sampler and its `--summary` |
| `static/index.html` | The page (hand-drawn charts, light and dark) |
| `test/` | Unit tests for the non-ROS modules |

## Unit tests

No ROS needed, only Python and pytest:

```bash
cd dashboard
python3 -m pytest
```

| File | Covers |
|---|---|
| `test_trial_tracker.py` | stamp pairing, latency maths at ns precision, `publish_stamp`, out-of-order and missing messages, all four statuses, duplicates, bad JSON, perception health |
| `test_csv_log.py` | column order, cell formatting, lazy file creation, flushing, no overwrite, `~` expansion |
| `test_web_server.py` | page, history, run listing and download, 404 on bad or traversal paths, SSE stream, slow-client queue, `chronyc` output parsing |
| `test_cpu_sample.py` | `/proc/<pid>/stat` parsing, process matching, summary |
