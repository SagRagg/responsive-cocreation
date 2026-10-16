# Interface contract

This file is the agreement between the sim stream (ROS 2 Jazzy) and the
perception stream (Pi). If either side wants to change something here,
agree it first, then update this file in the same pull request as the code.

## Setup
- ROS 2 domain ID: 30 (set on every machine)
- Standard ROS 2 message types only (`std_msgs`, `nav_msgs`, `sensor_msgs`), no custom messages

## Topics

| Topic | Type | Direction | Meaning |
|---|---|---|---|
| `/sketch_image` | `sensor_msgs/Image` | capture (VM) -> Pi | Full 280x280 `mono8` canvas of the human's sketch, black ink on white |
| `/digit_prediction` | `std_msgs/Int32` | Pi -> sim | Digit the Pi recognised (0-9) |
| `/strokes` | `nav_msgs/Path` | Pi -> sim | Corrected drawing for the arm to draw |
| `/turn_done` | `std_msgs/Bool` | sim -> Pi | `true` when the arm finishes drawing |

## Turn sequence
1. Capture (VM) publishes `/sketch_image` (the human's sketch is done). The
   `header.stamp` of this message is the start of the latency clock.
2. Pi receives the image and recognises the digit.
3. Pi publishes `/digit_prediction`, then `/strokes`.
4. Sim draws the strokes.
5. Sim publishes `/turn_done`. Capture waits for this before publishing the
   next sketch, so there is exactly one sketch in flight per turn.

## Sketch format (`/sketch_image`)
- `encoding` = `mono8`, `width` = `height` = 280, `step` = 280
- `header.frame_id` = "canvas"
- Black ink (0) on a white background (255), clean render with no noise
- QoS: reliable, keep last 1. Subscribe with reliable QoS too, so no sketch
  is dropped

## Stroke format (`/strokes`)
- One message = one full drawing, a list of poses in drawing order.
- `header.frame_id` = "canvas"
- `x`, `y` = position on the canvas, normalised 0.0 to 1.0
  (origin top-left, x to the right, y downward)
- `z` = pen state: 0.0 pen down (drawing), 1.0 pen up (moving)
- Orientation fields are unused (set `w = 1.0`)

## Latency timestamps
- Capture stamps `/sketch_image` `header.stamp` at the moment of publishing.
  Latency is measured from this stamp.
- Pi stamps `header.stamp` on every message at the moment of publishing.
- Clocks must be synced across machines (chrony), or latency is measured
  as round-trip on the Pi's clock only.

## Open questions
- (add anything undecided here)