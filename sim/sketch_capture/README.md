# sketch_capture

First stage of the drawing pipeline ("Image Capture"). It simulates a camera
filming the human's sketch by replaying MNIST **test** digits, one per turn.

- Publishes each digit on `/sketch_image` (`sensor_msgs/Image`, `mono8`,
  `frame_id` = `canvas`), QoS reliable / keep last 1. The default is the raw
  28x28 MNIST digit, white on black (784 bytes), which is what the perception
  model takes. `image_format:=canvas` sends a 280x280 black-on-white render
  instead (78,400 bytes), like a photo of paper.
- Waits for a subscriber, publishes trial 1, then publishes the next trial
  every time it receives `true` on `/turn_done` (`std_msgs/Bool`). There is no
  timeout, so no trial is skipped. `false` is ignored.
- Publishes the true label on `/ground_truth` (`std_msgs/String`, JSON) straight
  after each image, carrying the image's `header.stamp` as the join key. Format
  in [`docs/interfaces.md`](../../docs/interfaces.md).
- `header.stamp` is set to the current ROS time at the moment of publishing.
  This is the "Done" instant that starts the latency clock.
- After the last trial's `/turn_done` it logs completion and exits.
- Writes a CSV with one row per trial (see below).

The topic contract is in [`docs/interfaces.md`](../../docs/interfaces.md).

## Layout

| File | Job |
|---|---|
| `sketch_capture/mnist_loader.py` | Read MNIST test IDX files (plain or `.gz`) with numpy |
| `sketch_capture/trial_plan.py` | Seeded, class-balanced, shuffled trial selection |
| `sketch_capture/canvas.py` | Builds the published image in either format |
| `sketch_capture/trial_log.py` | CSV ground-truth log |
| `sketch_capture/ground_truth.py` | JSON payload for `/ground_truth` |
| `sketch_capture/preview.py` | Text preview and PNG writer for the sent image |
| `sketch_capture/capture_node.py` | The ROS node (calls the modules above) |
| `launch/sketch_capture.launch.py` | Launch file with the parameters below |
| `scripts/fetch_mnist.sh` | One-time MNIST test download |
| `test/` | Unit tests for the non-ROS modules |

Only `rclpy` and `numpy` are used (no cv_bridge, OpenCV or ML frameworks).

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `dataset_dir` | `~/datasets/mnist` | Folder with `t10k-images-idx3-ubyte` and `t10k-labels-idx1-ubyte` (`.gz` also accepted) |
| `seed` | `42` | Seed for selection and order. Same seed = identical sequence, so use the same one for edge and cloud runs |
| `per_digit` | `10` | Trials per digit (10 gives 100 trials) |
| `csv_path` | empty | Trial log. Empty = new file `~/sketch_capture/trials_seed<seed>_<timestamp>.csv`. A path you set is overwritten |
| `image_dir` | empty | If set, each sent image is also saved there as `trial_NNN_digitD.png` |
| `print_ascii` | `false` | If `true`, a text picture of each sent image is printed in the launch terminal |
| `image_format` | `mnist` | `mnist` = 28x28 white digit on black; `canvas` = 280x280 black ink on white |

CSV columns: `trial_number, mnist_index, true_label, publish_stamp_sec,
publish_stamp_nanosec`. `mnist_index` is the position in the MNIST test set.
The stamp is the same one carried in the image `header.stamp`.

## Run it in the VM

1. Dependencies (numpy is probably already installed):

   ```bash
   sudo apt install python3-numpy
   ```

2. Download MNIST once (about 2 MB, goes to `~/datasets/mnist/`):

   ```bash
   ./scripts/fetch_mnist.sh
   ```

   (run from this folder, `sim/sketch_capture`)

3. Build. The workspace must contain this repo's `sim/` folder, for example
   by symlinking it into `~/ros2_kortex_ws/src`:

   ```bash
   ln -s <path-to-repo>/sim ~/ros2_kortex_ws/src/sim
   cd ~/ros2_kortex_ws
   MAKEFLAGS=-j1 colcon build --packages-select sketch_capture --executor sequential
   source install/setup.bash
   ```

4. Launch (every terminal needs `ROS_DOMAIN_ID=30` and both setup files
   sourced):

   ```bash
   export ROS_DOMAIN_ID=30
   ros2 launch sketch_capture sketch_capture.launch.py
   # optional: seed:=7 per_digit:=3 csv_path:=~/runs/edge_01.csv image_format:=canvas
   ```

   The node prints `waiting for a subscriber on /sketch_image` until
   something subscribes.

## Test without the Pi

Terminal 2: watch the images arrive (this is also the subscriber the node
waits for).

```bash
export ROS_DOMAIN_ID=30
ros2 topic echo /sketch_image --no-arr
```

Terminal 3: finish a turn, which releases the next trial.

```bash
export ROS_DOMAIN_ID=30
ros2 topic pub --once /turn_done std_msgs/msg/Bool "{data: true}"
```

Repeat the publish once per turn. After the last trial's `/turn_done` the node
exits and the CSV is complete.

## Unit tests

The non-ROS modules need only Python, numpy and pytest, so they run anywhere:

```bash
cd sim/sketch_capture
python3 -m pytest
```
