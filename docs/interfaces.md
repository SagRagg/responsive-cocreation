# Interface contract

This file is the agreement between the sim stream (ROS 2 Jazzy, `simulation`
branch) and the perception stream (`perception` branch; the ROS node
`perception/mnist_perception_node.py` is on `main`). If either side wants to
change something here, agree it first, then update this file in the same pull
request as the code.

## Setup
- ROS 2 domain ID: 30 (set on every machine)
- Standard ROS 2 message types only (`std_msgs`, `sensor_msgs`), no custom messages
- Same RMW (Fast DDS, the Jazzy default) on every machine. For the cloud
  placement discovery runs over Tailscale with `ROS_STATIC_PEERS` set to the
  other machine's Tailscale address

## Topics

| Topic | Type | Direction | Meaning |
|---|---|---|---|
| `/sketch_image` | `sensor_msgs/Image` | capture (VM) -> perception, dashboard | The human's sketch: 28x28 `mono8` MNIST digit, white on black |
| `/digit_prediction` | `std_msgs/Int32` | perception -> arm, dashboard | Digit recognised (0-9) |
| `/strokes` | `std_msgs/String` (JSON) | perception -> arm, dashboard | Clean template strokes for the recognised digit, plus trial number and the sketch's stamp |
| `/turn_done` | `std_msgs/Bool` | arm (VM) -> capture, dashboard | `true` when the arm finishes drawing (also sent after a failed turn, so a run never stalls). Always `Bool`, never `Empty`. The perception node does not subscribe |
| `/ground_truth` | `std_msgs/String` (JSON) | capture (VM) -> dashboard | The true label of the sketch just sent. For measurement only; the perception node must not use it |

All five topics are reliable. `/sketch_image` is keep last 1, the others keep
last 10. `arm_drawing` also publishes `/drawing_markers`
(`visualization_msgs/MarkerArray`) for RViz; it stays inside the VM and is not
part of the contract.

## Where the nodes run
| Node | Where | Code |
|---|---|---|
| Perception + stroke lookup (one process) | Machine under test: Pi 5 (edge) or GCP VM in Sydney (cloud) | `perception/mnist_perception_node.py` on `main` |
| Telemetry dashboard | Same machine as perception | `dashboard/` |
| `sketch_capture` | Sim VM, both placements | `sim/sketch_capture` |
| `arm_drawing` + simulated Gen3 | Sim VM, both placements | `sim/arm_drawing` |

Only the perception node and the dashboard move between the edge and cloud
runs.

## Turn sequence
1. Capture (VM) publishes `/sketch_image` (the human's sketch is done). The
   `header.stamp` of this message is the start of the latency clock.
2. Perception receives the image and recognises the digit.
3. Perception publishes `/digit_prediction`, then `/strokes`.
4. The arm draws the digit (from joint poses precomputed for that digit).
5. The arm publishes `/turn_done`. Capture waits for this before publishing the
   next sketch, so there is exactly one sketch in flight per turn.

## Sketch format (`/sketch_image`)
- `encoding` = `mono8`, `width` = `height` = 28, `step` = 28
- `header.frame_id` = "canvas"
- White digit (255) on a black background (0): the raw MNIST test image, no
  noise, so it goes straight into the model with no resizing or inverting
- Payload is 784 bytes. This matters for the cloud placement, where the image
  crosses the network every turn
- Optional: capture's `image_format:=canvas` sends a 280x280 render with
  black ink (0) on white (255) instead (78,400 bytes), like a photo of paper.
  The perception node only accepts the default 28x28 format
- QoS: reliable, keep last 1. Subscribe with reliable QoS too, so no sketch
  is dropped

## Stroke format (`/strokes`)
One `std_msgs/String` per turn. `data` is a JSON object:

```json
{
  "trial": 1,
  "digit": 7,
  "confidence": 0.9981,
  "source_stamp": {"sec": 1761540000, "nanosec": 123456789},
  "frame_id": "canvas",
  "strokes": [[[0.2, 0.1], [0.8, 0.1], [0.55, 0.45], [0.4, 0.9]]]
}
```

| Field | Meaning |
|---|---|
| `trial` | Running count of sketches received, starting at 1. Matches `trial_number` in the capture CSV |
| `digit` | Recognised digit, 0-9 (same value as `/digit_prediction`) |
| `confidence` | Model probability of `digit`, 0.0-1.0 |
| `source_stamp` | Copy of the `/sketch_image` `header.stamp` this answers. Used for latency |
| `frame_id` | Copy of the `/sketch_image` `header.frame_id` ("canvas") |
| `strokes` | List of strokes in drawing order. Each stroke is a list of `[x, y]` points drawn pen down; the pen lifts between strokes |

- `x`, `y` are canvas positions normalised 0.0 to 1.0 (origin top-left, x to
  the right, y downward).
- The strokes are a fixed template per digit, the same every time that digit
  is predicted. The arm side draws from joint poses precomputed from the same
  templates, so a template change must be made on both sides.
- QoS: reliable, keep last 10.

## Ground truth format (`/ground_truth`)
Published by capture straight after each `/sketch_image`. One `std_msgs/String`
per turn, `data` is a JSON object:

```json
{
  "trial": 1,
  "mnist_index": 6788,
  "digit": 7,
  "stamp": {"sec": 1761540000, "nanosec": 123456789}
}
```

- `trial` and `mnist_index` match `trial_number` and `mnist_index` in the
  capture CSV, `digit` matches `true_label`.
- `stamp` is exactly the `/sketch_image` `header.stamp` of that trial. It is
  the join key: match it to `/strokes` `source_stamp`. Never pair messages by
  `trial`, because the perception node's counter can drift from capture's
  (for example after a restart).
- QoS: reliable, keep last 10.

## Latency timestamps
- Capture stamps `/sketch_image` `header.stamp` at the moment of publishing
  (VM ROS time). Latency is measured from this stamp.
- `/digit_prediction` and `/strokes` have no header. `/strokes` carries the
  sketch's stamp back as `source_stamp`.
- Logs from all nodes join on the sketch stamp (`source_stamp` in `/strokes`,
  `stamp` in `/ground_truth`), not on trial number: the perception node keeps
  its own counter, which can drift from capture's.
- The dashboard (on the perception machine) records `compute_ms` =
  `/strokes` receive time minus `/sketch_image` receive time, both on its own
  clock, and `e2e_ms` = `/strokes` receive time minus the sketch stamp, which
  mixes the VM clock with the perception machine's. `network_ms` is
  `e2e_ms - compute_ms` and `turn_ms` is `/turn_done` receive time minus the
  sketch stamp. See [`dashboard/README.md`](../dashboard/README.md).
- `arm_drawing` logs its own receive times for both topics.
  `strokes_latency_ms` = VM receive time of `/strokes` minus `source_stamp`:
  the full round trip VM -> perception -> VM, on the VM clock only.
- Any figure that compares the sketch stamp with another machine's clock
  (`e2e_ms`, `network_ms`, `turn_ms`) needs the clocks synced with chrony,
  and is only as accurate as that sync.

## Open questions
- Adding a `publish_stamp` (perception's own clock) to the `/strokes` JSON
  would let `compute_ms` exclude the local DDS hop. The dashboard already uses
  it when present; the perception node on `main` does not send it yet.
