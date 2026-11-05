# responsive-cocreation

Responsive Co-Creation: Benchmarking Edge and Cloud AI for Human-Robot
Collaborative Drawing. Engineering Project Part A, University of Canberra.

A simulated Kinova Gen3 7-DOF arm takes turns with a "human" sketch: a sketch
(an MNIST digit) is recognised, and the arm draws a clean version of that
digit. The experiment compares where recognition runs: on a Raspberry Pi 5
(edge) or on a Google Cloud VM in Sydney (cloud). Everything else stays the
same between the two, and the measured quantity is latency.

Part A is simulation only. No physical arm is involved.

## Branches

| Branch | Owner | Contents |
|---|---|---|
| `main` | both | The integrated submission. Changes arrive through pull requests from the two branches below |
| `simulation` (this branch) | Nikko | Simulated arm, sketch capture, dashboard, run scripts, interface contract |
| `perception` | Dwayne | Digit recognition model and the GCP cloud predictor |

The `perception/` folder, including the ROS perception node
`mnist_perception_node.py` and the trained model, is not on this branch. It is
on [`main`](https://github.com/SagRagg/responsive-cocreation/tree/main/perception),
merged from the `perception` branch. The run scripts on this branch expect a
checkout of `main` next to it for that node (see
[`scripts/README.md`](scripts/README.md)).

## How it works

```
 Ubuntu VM (VirtualBox)                            Machine under test
                                                   (Pi 5 = edge, GCP VM = cloud)
+---------------------------+                     +---------------------------+
| sketch_capture            | /sketch_image       | perception node           |
|                           | /ground_truth       |   CNN + stroke lookup     |
|                           | ------------------> |                           |
|                           |                     |                           |
| arm_drawing               | /digit_prediction   |                           |
|   ros2_kortex Gen3        | /strokes            |                           |
|   ros2_control mock arm   | <------------------ |                           |
|   RViz2                   |                     |                           |
|                           | /turn_done          | dashboard (subscribes     |
|                           | ------------------> |   to every topic)         |
+---------------------------+                     +---------------------------+
```

1. `sketch_capture` publishes a seeded MNIST test digit on `/sketch_image`
   (and its true label on `/ground_truth`).
2. The perception node recognises it and publishes `/digit_prediction`, then
   `/strokes` (the template strokes for that digit).
3. `arm_drawing` draws the digit from precomputed joint poses and publishes
   `/turn_done`, which releases the next sketch.

Only the location of the perception node changes between the edge and cloud
runs. The dashboard runs next to it and records latency and accuracy.

The message contract (topics, types, stroke format, turn sequence, latency
stamps) lives in [`docs/interfaces.md`](docs/interfaces.md). Both sides must
follow it; change it there first.

### The simulated arm

The arm is not a physics simulation. It is the real Kinova ROS 2 stack
([`ros2_kortex`](https://github.com/Kinovarobotics/ros2_kortex), `jazzy`
branch) run with **fake hardware**:

- `kortex_bringup`'s `gen3.launch.py` starts the normal Gen3 setup, but
  `use_fake_hardware:=true` swaps the real Kortex driver for a `ros2_control`
  mock system. Commands sent to the arm are simply echoed back as joint
  states.
- `robot_state_publisher` loads the Gen3 URDF (`dof:=7`) and publishes the
  transforms for every link.
- The `ros2_control` controllers (joint state broadcaster plus the arm's
  trajectory controller) accept motion commands exactly as they would on a
  real arm.
- RViz2 draws the arm from the joint states, so you see it move.
- `robot_ip` is required by the launch file but is ignored in fake-hardware
  mode, so any value works.

Because it is the same interface a real arm would expose, whatever drives the
simulated arm should work unchanged on hardware later.

### Current status

| Piece | State |
|---|---|
| Simulated Gen3 launches with fake hardware and RViz | Working |
| Arm accepts joint trajectory commands | Working (standard `ros2_control` interface) |
| `sketch_capture`: MNIST sketches on `/sketch_image`, labels on `/ground_truth` | Working ([`sim/sketch_capture`](sim/sketch_capture)) |
| `arm_drawing`: `/strokes` to arm motion, `/turn_done` publisher | Working in the VM; full loop run end to end with perception on the Pi and on the cloud VM ([`sim/arm_drawing`](sim/arm_drawing)) |
| Telemetry dashboard and CSV logging | Working ([`dashboard`](dashboard)) |
| One-command run scripts and CPU sampler | Working ([`scripts`](scripts)) |
| Edge and cloud benchmark runs (30 trials each) | Done, 3 November 2026 (see below) |

## Prerequisites

### Host machine

- Apple Silicon Mac (developed on an 8 GB machine)
- VirtualBox 7.2.x
- About 60 GB free disk for the VM (dynamic disk, 57.7 GB cap)

### VM

| Item | Value |
|---|---|
| Name | `THESIS` |
| Guest OS | Ubuntu 24.04 LTS, arm64 |
| User | `nikko` |
| RAM | 4096 MB |
| 3D acceleration | Enabled in VirtualBox settings |
| ROS 2 | Jazzy Jalisco (desktop install) |
| DDS middleware | Default (Fast DDS). Every machine must use the same one |
| `ROS_DOMAIN_ID` | `30` |
| Workspace | `~/ros2_kortex_ws` |

### Build tools

`git`, `colcon`, `rosdep`, `vcs` (python3-vcstool) and `tmux` (recommended for
long builds, so a dropped terminal does not kill them).

## One-time setup

Skip this if the VM already has `~/ros2_kortex_ws` built.

1. Install ROS 2 Jazzy desktop following the
   [official instructions](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html),
   then the build tools:

   ```bash
   sudo apt install ros-dev-tools python3-vcstool python3-colcon-common-extensions tmux
   ```

2. Set the domain ID for every new terminal:

   ```bash
   echo 'export ROS_DOMAIN_ID=30' >> ~/.bashrc
   echo 'source /opt/ros/jazzy/setup.bash' >> ~/.bashrc
   source ~/.bashrc
   ```

3. Get the Kinova packages (`jazzy` branch):

   ```bash
   mkdir -p ~/ros2_kortex_ws/src && cd ~/ros2_kortex_ws/src
   git clone -b jazzy https://github.com/Kinovarobotics/ros2_kortex.git
   cd ~/ros2_kortex_ws
   vcs import src --skip-existing --input src/ros2_kortex/ros2_kortex.jazzy.repos
   rosdep install --ignore-src --from-paths src -y -r
   ```

4. Build. The VM is small, so build one package at a time and inside `tmux`:

   ```bash
   tmux new -s build
   cd ~/ros2_kortex_ws
   MAKEFLAGS=-j1 colcon build --executor sequential \
     --packages-ignore kortex_api kortex_driver gz_ros2_control \
       gz_ros2_control_demos ackermann_steering_controller \
       bicycle_steering_controller tricycle_steering_controller
   ```

   Why those packages are skipped:
   - `kortex_api` and `kortex_driver` talk to a real arm and only build on
     Linux x86_64, not this arm64 VM.
   - The Gazebo and steering-controller packages are not needed. Gazebo is
     skipped on purpose because VirtualBox 3D on Apple Silicon is
     experimental; fake hardware plus RViz is enough.

   Expect the build to take a long time. If it runs out of memory, close
   other apps on the Mac and re-run the same command; colcon resumes.

## Bring the arm up

1. Start the VM and log in as `nikko`.
2. Open a terminal and load the environment:

   ```bash
   source /opt/ros/jazzy/setup.bash
   source ~/ros2_kortex_ws/install/setup.bash
   echo $ROS_DOMAIN_ID   # should print 30
   ```

3. Launch the simulated arm with RViz:

   ```bash
   ros2 launch kortex_bringup gen3.launch.py \
     robot_ip:=192.168.1.10 \
     use_fake_hardware:=true \
     dof:=7 \
     launch_rviz:=true
   ```

   An RViz window opens showing the Gen3 arm.

### Check that it is healthy

In a second terminal (source both setup files again first):

```bash
ros2 control list_controllers      # controllers should be "active"
ros2 topic echo /joint_states --once
ros2 topic list                    # see what the arm exposes
```

If you see the arm in RViz and `/joint_states` prints values, the arm side is
up.

## Troubleshooting

| Symptom | Fix |
|---|---|
| RViz crashes or the window is blank (OpenGL errors) | Use software rendering: `export LIBGL_ALWAYS_SOFTWARE=1`, then relaunch. RViz2 needs OpenGL 3.3+ |
| Build is killed or the VM freezes | Out of RAM. Close other Mac apps, keep `-j1` and `--executor sequential`, build in `tmux` |
| `package 'kortex_bringup' not found` | Workspace not sourced: `source ~/ros2_kortex_ws/install/setup.bash` |
| Controllers stay `inactive` | Wait about 10 seconds after launch; otherwise check the launch terminal for errors |
| VM and Pi (or cloud VM) cannot see each other's topics | See "Talking to the machine under test" below |

## Talking to the machine under test

For the VM and the perception machine to exchange the topics in the interface
contract:

1. **Edge (Pi on the LAN):** the VM defaults to NAT, which blocks DDS
   discovery. In VirtualBox, set the VM's network adapter to **Bridged** on
   the Mac's Wi-Fi interface (`en0`) and set Promiscuous Mode to **Allow
   All**. Reboot the VM, then confirm it has an address on the same subnet as
   the Pi.
2. **Cloud (GCP VM):** the VM and the cloud VM are joined over Tailscale, and
   DDS discovery uses `ROS_STATIC_PEERS` set to the other machine's Tailscale
   address. The run scripts pass `ROS_STATIC_PEERS` (and the other discovery
   variables) through to every node. No GCP firewall port is opened; the
   dashboard binds to the Tailscale address.
3. **Same settings on every machine:** `ROS_DOMAIN_ID=30` and the same RMW
   implementation (Fast DDS by default).
4. **Clocks:** sync every machine with chrony so latency timestamps
   (`header.stamp`) are comparable. See the "Latency timestamps" section of
   the interface contract, and the clock caveat under the experiment below.
5. **Check discovery:** on the VM run `ros2 topic list` while perception is
   running; `/digit_prediction` and `/strokes` should appear.

## Running a benchmark

[`scripts/README.md`](scripts/README.md) has the full procedure. In short, one
script per machine, started in this order:

1. Pi or cloud VM: `scripts/perception_side.sh edge` (or `cloud`) starts
   perception, then the dashboard, then the CPU sampler.
2. VM: `scripts/sim_side.sh` starts the arm and `arm_drawing`.
3. VM: `scripts/capture.sh <run-name>` starts `sketch_capture` once the
   other nodes are visible.

Do a 10-trial warm-up run first, then `scripts/perception_side.sh new-run
edge|cloud` to restart the dashboard (fresh CSV, perception kept warm) before
the measured run.

## Edge vs cloud experiment

### Setup

| | Edge | Cloud |
|---|---|---|
| Perception + strokes | Raspberry Pi 5 on the LAN | GCP VM, Sydney region, 2 vCPU, over Tailscale |
| Model and libraries | Same CNN, TensorFlow 2.21 / Keras 3.15.1 | Same |
| Capture and arm | VirtualBox VM on the Mac | Same |

- 30 trials per placement: `per_digit` 3, `seed` 42, so both runs saw the
  same 30 MNIST test digits in the same order.
- Start order: perception, then dashboard, then capture. The dashboard was
  restarted (`new-run`) before each measured run, after a 10-trial warm-up
  that is not counted (the first inference after start-up is slow).
- Runs done on 3 November 2026.

### Metrics

Recorded per trial by the dashboard on the perception machine (column names as
in its CSV; definitions in [`dashboard/README.md`](dashboard/README.md)):

| Column | Meaning | Clocks |
|---|---|---|
| `compute_ms` | `/strokes` receive time minus `/sketch_image` receive time, both on the perception machine. Inference plus local DDS | One |
| `e2e_ms` | `/strokes` receive time on the perception machine minus the sketch's `header.stamp` (set on the VM) | Two |
| `network_ms` | `e2e_ms - compute_ms`: the sketch's trip from the VM, plus any clock offset | Two |
| `turn_ms` | `/turn_done` receive time minus the sketch stamp: the whole turn including drawing | Two |

The sampler also logs CPU and resident memory of the perception node and the
dashboard every 2 s.

### Headline results

| | Edge (Pi 5) | Cloud (GCP Sydney) |
|---|---|---|
| Trials completed (`status` ok) | 30/30 | 30/30 |
| Correctly classified | 30/30 | 30/30 |
| `compute_ms`, median (mean) | 83.4 (84.1) | 91.0 (91.6) |
| `e2e_ms`, median (range) | 105.9 (89.5-139.4) | 105.3 (89.6-133.6) |
| `turn_ms`, median (range) | about 13.7 s (8.7-22.7 s) | about 13.7 s (8.7-15.9 s) |
| Perception node CPU, mean (% of one core) | 0.7 | 0.8 |
| Perception node memory, max RSS | 555 MB | 628 MB |

- Compute was about 7-8 ms faster on the Pi than on the 2-vCPU cloud VM.
- `e2e_ms` on the edge drifted upward over the run (about 90 ms at the start,
  about 120 ms at the end). On the cloud 26 of 30 trials fell between 95 and
  115 ms, drifting slightly downward.
- The turn time is dominated by arm motion (8-16 s per digit) and does not
  depend on placement.

**Caveat.** `e2e_ms`, `network_ms` and `turn_ms` compare a VM timestamp with a
perception-machine clock. The VM clock (chrony over the internet) was accurate
only to roughly 10-25 ms, and `network_ms` drifted in opposite directions in
the two runs (rising on edge, falling on cloud), which points to clock drift
rather than real network change. Treat `e2e_ms` and `network_ms` as indicative
only, and do not compare `network_ms` between placements. `compute_ms`, CPU,
memory and accuracy are measured on a single machine and are reliable. With
n = 30, percentiles above the median rest on one or two trials.

The full analysis is in the thesis report.

## Known limits

- The real arm cannot be driven from this VM: `kortex_api` only builds on
  Linux x86_64.
- No physics or collision simulation (no Gazebo). Motion is kinematic only.
- Performance is bound by the 4 GB VM on an 8 GB host; keep other apps closed
  while running RViz.

## Repository layout

On this branch:

- [`docs/interfaces.md`](docs/interfaces.md): topic and message contract
- [`sim/sketch_capture`](sim/sketch_capture): replays MNIST digits as the
  human's sketch and publishes the ground truth
- [`sim/arm_drawing`](sim/arm_drawing): draws the recognised digit on the arm
  and publishes `/turn_done`
- [`dashboard`](dashboard): live telemetry page and per-run CSV logs, run on
  the perception machine ([README](dashboard/README.md))
- [`scripts`](scripts): one-command run scripts for each machine
  ([README](scripts/README.md))

On `main` only:

- [`perception`](https://github.com/SagRagg/responsive-cocreation/tree/main/perception):
  digit recognition model, the ROS perception node and the GCP cloud predictor

## Licence

All rights reserved. Submitted as university coursework; not licensed for
reuse.
