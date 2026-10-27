# Interface contract

This file is the agreement between the sim stream (ROS 2 Jazzy) and the
perception stream (Pi). If either side wants to change something here,
agree it first, then update this file in the same pull request as the code.

## Setup
- ROS 2 domain ID: 30 (set on every machine)
- Standard ROS 2 message types only (`std_msgs`, `sensor_msgs`), no custom messages

## Topics

| Topic | Type | Direction | Meaning |
|---|---|---|---|
| `/sketch_image` | `sensor_msgs/Image` | capture (VM) -> Pi | The human's sketch: 28x28 `mono8` MNIST digit, white on black |
| `/digit_prediction` | `std_msgs/Int32` | Pi -> sim | Digit the Pi recognised (0-9) |
| `/strokes` | `std_msgs/String` (JSON) | Pi -> sim | Clean template strokes for the recognised digit, plus trial number and the sketch's stamp |
| `/turn_done` | `std_msgs/Bool` | sim -> capture, Pi | `true` when the arm finishes drawing. Always `Bool`, never `Empty` |

## Where the nodes run
Perception and the stroke lookup run together on the machine under test (Pi
for edge, cloud VM for cloud). They may be one process; the perception node
already does both. Capture and the arm always run in the sim VM.

## Turn sequence
1. Capture (VM) publishes `/sketch_image` (the human's sketch is done). The
   `header.stamp` of this message is the start of the latency clock.
2. Pi receives the image and recognises the digit.
3. Pi publishes `/digit_prediction`, then `/strokes`.
4. Sim draws the strokes.
5. Sim publishes `/turn_done`. Capture waits for this before publishing the
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

## Latency timestamps
- Capture stamps `/sketch_image` `header.stamp` at the moment of publishing.
  Latency is measured from this stamp.
- `/digit_prediction` and `/strokes` have no header. `/strokes` carries the
  sketch's stamp back as `source_stamp`, and the sim logs its own receive time
  for both topics, so sketch-to-strokes latency = sim receive time of
  `/strokes` minus `source_stamp`.
- Logs from all nodes join on trial number.
- Clocks must be synced across machines (chrony), or latency is measured
  as round-trip on the Pi's clock only.

## Open questions
- Adding a `publish_stamp` to the `/strokes` JSON would split the latency into
  compute time and network time.