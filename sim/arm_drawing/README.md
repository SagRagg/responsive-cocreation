# arm_drawing

Last stage of the drawing pipeline. When `/strokes` arrives it draws that
digit on the simulated Gen3, then publishes `/turn_done` so `sketch_capture`
sends the next sketch.

No motion planning happens during a trial. Each digit has a fixed joint
trajectory, computed once offline from the stroke templates and stored in
`config/digit_poses.json`. The node looks up the digit and sends that
trajectory to the arm's `joint_trajectory_controller`.

- Subscribes to `/strokes` (`std_msgs/String`, JSON) and `/digit_prediction`
  (`std_msgs/Int32`, only for its receive time). Reliable QoS.
- Sends the trajectory as a `FollowJointTrajectory` goal to
  `/joint_trajectory_controller/follow_joint_trajectory`.
- Publishes `/turn_done` (`std_msgs/Bool`, `true`) when the arm finishes. It
  publishes it on failure too (bad message, no controller, rejected or failed
  trajectory), so a run never stalls; the `status` column records what
  happened.
- If `/strokes` arrives while a digit is still being drawn, it is ignored
  with a warning.
- Publishes `/drawing_markers` (`visualization_msgs/MarkerArray`) with the
  paper outline and the digit's pen-down path, for RViz.
- At start-up it waits for the controller, then moves the arm to the ready
  pose above the paper centre. Every digit starts and ends there.

The topic contract is in [`docs/interfaces.md`](../../docs/interfaces.md).

## Layout

| File | Job |
|---|---|
| `arm_drawing/templates.py` | Copy of the perception side's stroke templates |
| `arm_drawing/kinematics.py` | Gen3 forward kinematics (from the URDF) and IK |
| `arm_drawing/joint_poses.py` | Builds `config/digit_poses.json` (`make_joint_poses`) |
| `arm_drawing/strokes_msg.py` | Decodes the `/strokes` JSON |
| `arm_drawing/turn_log.py` | CSV timing log |
| `arm_drawing/drawing_node.py` | The ROS node |
| `launch/arm_drawing.launch.py` | Launch file |
| `config/digit_poses.json` | Precomputed joint trajectories, generated |
| `test/` | Unit tests for the non-ROS modules |

## Where the arm draws

The 0-1 canvas maps onto a 0.20 m paper square lying flat at the base's
mounting height (z = 0), centred 0.45 m in front of the base. The top of the
canvas is the far edge and canvas right is the robot's -y, so the digit reads
upright when you look along +x from behind the arm. The pen is 0.10 m long,
points straight down, lifts 0.03 m between strokes and moves at 0.05 m/s while
drawing. One digit takes 8-16 s.

These values are in `DEFAULTS` in `joint_poses.py`. After changing them, or
after copying new templates into `templates.py`, regenerate the table and
commit it:

```bash
cd sim/arm_drawing
python3 -m arm_drawing.joint_poses
```

A unit test fails if the committed table is out of date.

## CSV log

One row per turn. All times are ROS time in integer nanoseconds.

| Column | Meaning |
|---|---|
| `trial_number`, `digit`, `confidence` | From the `/strokes` JSON |
| `source_stamp_ns` | The sketch's `header.stamp`, carried back in `/strokes` |
| `digit_rx_ns` | When `/digit_prediction` arrived |
| `strokes_rx_ns` | When `/strokes` arrived |
| `goal_sent_ns`, `goal_done_ns` | Trajectory sent to the arm, and finished |
| `turn_done_ns` | When `/turn_done` was published |
| `strokes_latency_ms` | `strokes_rx_ns - source_stamp_ns`: the latency of the stage under test |
| `status` | `ok`, `bad_message`, `no_controller`, `rejected` or `error_<code>` |

Join it with the `sketch_capture` CSV on `trial_number`. Across machines the
latency is only valid if the clocks are synced (chrony).

## Run it in the VM

1. Build (the repo's `sim/` folder is already symlinked into the workspace for
   `sketch_capture`):

   ```bash
   cd ~/ros2_kortex_ws
   MAKEFLAGS=-j1 colcon build --packages-select arm_drawing --executor sequential
   source install/setup.bash
   ```

2. Terminal 1: bring up the arm (see the root README).

   ```bash
   ros2 launch kortex_bringup gen3.launch.py robot_ip:=192.168.1.10 \
     use_fake_hardware:=true dof:=7 launch_rviz:=true
   ```

3. Terminal 2: start the drawing node. The arm moves to the ready pose.

   ```bash
   export ROS_DOMAIN_ID=30
   ros2 launch arm_drawing arm_drawing.launch.py
   # optional: csv_path:=~/runs/edge_01_arm.csv
   ```

4. In RViz: **Add** > **By topic** > `/drawing_markers` > MarkerArray to see the
   paper and the ink.

## Test without perception

Send a `/strokes` message by hand (Terminal 3). The arm draws a 7 and
`/turn_done` is published:

```bash
export ROS_DOMAIN_ID=30
ros2 topic pub --once /strokes std_msgs/msg/String "{data: '{\"trial\": 1, \"digit\": 7, \"confidence\": 1.0, \"source_stamp\": {\"sec\": 0, \"nanosec\": 0}, \"frame_id\": \"canvas\", \"strokes\": [[[0.2, 0.1], [0.8, 0.1], [0.55, 0.45], [0.4, 0.9]]]}'}"
```

`source_stamp` is 0 here, so the logged latency is meaningless. Watch the
release with `ros2 topic echo /turn_done`.

## Unit tests

The non-ROS modules need only Python, numpy and pytest:

```bash
cd sim/arm_drawing
python3 -m pytest
```
