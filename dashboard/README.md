# dashboard

Live telemetry for the edge-vs-cloud benchmark. One rclpy node that runs on
the **same machine as the perception node** (the Pi for edge, the cloud VM for
cloud) and serves a web page with latency, accuracy and node health.

It only subscribes. It publishes nothing and does not touch the perception
node. Only `rclpy` and the Python standard library are used on the backend, and
the page has no external files (no CDN, no fonts), so it works offline.

The topic contract is in [`docs/interfaces.md`](../docs/interfaces.md).

## Run it

Source ROS 2 Jazzy, then start the node with `python3` (no build step):

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

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `placement` | `edge` | `edge` or `cloud`. Shown as a badge and written on every CSV row |
| `port` | `8080` | HTTP port |
| `bind` | `0.0.0.0` | Address to listen on |
| `csv_dir` | `~/dashboard_logs` | Where the run CSVs go (and where the Compare view lists them from) |
| `trial_timeout_s` | `30.0` | A trial with no `/turn_done` this long after its sketch is closed as `timeout` |

## What it measures

Each trial is keyed by the `/sketch_image` `header.stamp`. `/ground_truth` and
`/strokes` (`source_stamp`) carry that stamp. `/digit_prediction` and
`/turn_done` carry none, so they are attached to the single trial in flight.
Trial numbers are shown but never used to pair messages, because the perception
node's counter can drift from capture's. Messages may arrive in any order.

| Column | Definition | Needs clock sync? |
|---|---|---|
| `e2e_ms` | dashboard receive time of `/strokes` minus the sketch stamp | Yes, chrony on both machines |
| `compute_ms` | receive time of `/strokes` minus receive time of `/sketch_image`, both here. Uses `publish_stamp` from the `/strokes` JSON instead if the perception node ever adds one | No |
| `network_ms` | `e2e_ms - compute_ms` (so it also absorbs any clock offset) | Yes |
| `turn_ms` | receive time of `/turn_done` minus the sketch stamp | Yes |

`compute_ms` is close to inference time plus local DDS, not exactly inference.
A negative `e2e_ms` means the two clocks disagree. The page shows the local
`chronyc tracking` offset when `chronyc` is available.

A trial is finished when `/turn_done` arrives (`status` = `ok`), or after
`trial_timeout_s` (`timeout`). Two more statuses can appear: `superseded` (the
next sketch arrived before `/turn_done`) and `no_strokes` (`/turn_done` came but
`/strokes` never did).

## Output

One CSV per run in `csv_dir`, named `<placement>_<YYYYmmdd-HHMMSS>.csv`, created
when the first trial finishes and flushed after every row:

```
placement, trial, mnist_index, stamp_sec, stamp_nanosec, true_digit, pred_digit,
confidence, correct, e2e_ms, compute_ms, network_ms, turn_ms, status
```

`correct` is `1` or `0`, empty when there is no ground truth. Empty cells mean
unknown.

## Page

Live view: input image, predicted vs true digit, rolling (last 30) and overall
accuracy, latency over time with p50/p95/mean tiles, history table, confusion
matrix, topic health and the placement badge. A browser refresh reloads the
history from the node.

**Compare runs** tab: pick two or more saved CSVs from `csv_dir`, or upload
CSVs from your laptop, to see edge and cloud side by side (latency
distributions, p50/p95, accuracy, per-digit latency). A live dashboard only
ever sees one placement, so this is where the comparison happens.

Health colours: a topic is green under 5 s since its last message, amber up to
10 s, red beyond that. The perception indicator is red when nothing publishes
`/strokes` or when `/strokes` has been silent for more than 10 s. That includes
a long wait for the arm, so a slow drawing can briefly show red.

## Overhead

The ROS callbacks only record a timestamp and hand the message to the tracker.
The browser gets one update at most every 0.2 s (5 Hz). `chronyc` runs every
10 s. There is no TensorFlow or numpy import. Check it on the target with
`top -p $(pgrep -f telemetry_dashboard)` during a run.

## Files

| File | Job |
|---|---|
| `telemetry_dashboard.py` | The ROS node: subscriptions, 5 Hz update, wiring |
| `trial_tracker.py` | Stamp-keyed pairing, latency maths, CSV writer, perception health |
| `web_server.py` | `http.server` pages, `/history.json`, `/runs.json`, SSE `/events` |
| `clock_sync.py` | `chronyc tracking` reader |
| `static/index.html` | The page (hand-drawn charts, light and dark) |
| `test/` | Unit tests for the non-ROS modules |

## Unit tests

No ROS needed, only Python and pytest:

```bash
cd dashboard
python3 -m pytest
```
