# Interface contract

This file is the agreement between the sim stream (MATLAB) and the
perception stream (Pi). If either side wants to change something here,
agree it first, then update this file in the same pull request as the code.

## Setup
- ROS 2 domain ID: 30 (set on every machine)
- Standard message types only, so MATLAB needs no custom message setup

## Topics

| Topic | Type | Direction | Meaning |
|---|---|---|---|
| `/digit_prediction` | `std_msgs/Int32` | Pi -> sim | Digit the Pi recognised (0-9) |
| `/strokes` | `nav_msgs/Path` | Pi -> sim | Corrected drawing for the arm to draw |
| `/turn_done` | `std_msgs/Bool` | sim -> Pi | `true` when the arm finishes drawing |

## Turn sequence
1. Pi captures the human's drawing and recognises the digit.
2. Pi publishes `/digit_prediction`, then `/strokes`.
3. Sim draws the strokes.
4. Sim publishes `/turn_done`. The Pi waits for this before starting the next turn.

## Stroke format (`/strokes`)
- One message = one full drawing, a list of poses in drawing order.
- `header.frame_id` = "canvas"
- `x`, `y` = position on the canvas, normalised 0.0 to 1.0
  (origin top-left, x to the right, y downward)
- `z` = pen state: 0.0 pen down (drawing), 1.0 pen up (moving)
- Orientation fields are unused (set `w = 1.0`)

## Latency timestamps
- Pi stamps `header.stamp` on every message at the moment of publishing.
- Clocks must be synced across machines (chrony), or latency is measured
  as round-trip on the Pi's clock only.

## Open questions
- (add anything undecided here)