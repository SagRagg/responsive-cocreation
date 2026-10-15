# sim: simulated Kinova Gen3 arm

This folder is the simulation stream of the project: a simulated Kinova Gen3
7-DOF arm running in ROS 2 Jazzy inside an Ubuntu VM. It is the "robot" side of
the drawing loop; the perception side runs on a Raspberry Pi 5 (see
[`../perception`](../perception)).

Part A of the project is simulation only. No physical arm is involved.

## How it works

```
 Raspberry Pi 5                              Ubuntu VM (this folder)
+--------------------+   /digit_prediction  +-----------------------------+
| digit recognition  | -------------------> |                             |
| (perception/)      |   /strokes           |  ROS 2 Jazzy                |
|                    | -------------------> |  + ros2_kortex (Gen3)       |
|                    |   /turn_done         |  + ros2_control mock arm    |
|                    | <------------------- |  + RViz2 visualisation      |
+--------------------+                      +-----------------------------+
```

The message contract between the two machines (topics, types, stroke format,
turn sequence) lives in [`../docs/interfaces.md`](../docs/interfaces.md). Both
sides must follow it; change it there first.

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
| `/strokes` to arm motion (drawing node) | Not in this folder yet |
| `/turn_done` publisher | Not in this folder yet |

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
| Pi and VM cannot see each other's topics | See "Talking to the Pi" below |

## Talking to the Pi

For the VM and the Pi to exchange the topics in the interface contract:

1. **Networking:** the VM defaults to NAT, which blocks DDS discovery. In
   VirtualBox, set the VM's network adapter to **Bridged** on the Mac's Wi-Fi
   interface (`en0`) and set Promiscuous Mode to **Allow All**. Reboot the
   VM, then confirm it has an address on the same subnet as the Pi.
2. **Same settings on both machines:** `ROS_DOMAIN_ID=30` and the same RMW
   implementation (Fast DDS by default).
3. **Clocks:** sync both machines with chrony so latency timestamps
   (`header.stamp`) are comparable. See the "Latency timestamps" section of
   the interface contract.
4. **Check discovery:** on the VM run `ros2 topic list` while the Pi is
   publishing; `/digit_prediction` and `/strokes` should appear.

## Known limits

- The real arm cannot be driven from this VM: `kortex_api` only builds on
  Linux x86_64.
- No physics or collision simulation (no Gazebo). Motion is kinematic only.
- Performance is bound by the 4 GB VM on an 8 GB host; keep other apps closed
  while running RViz.

## Related files

- [`../docs/interfaces.md`](../docs/interfaces.md): topic and message contract
- [`../perception`](../perception): digit recognition on the Pi
