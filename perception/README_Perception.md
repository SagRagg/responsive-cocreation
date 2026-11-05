# Perception Stream — Responsive Co-Creation

The perception stream recognises handwritten digits using a trained TensorFlow/Keras convolutional neural network (CNN). In the ROS workflow, the predicted digit selects a predefined stroke template for the simulated Kinova Gen3 drawing stream.

The project compares perception on a Raspberry Pi 5 and a Google Compute Engine VM. Capture and arm execution remain on the simulation VM. The current task uses controlled MNIST images and standard digit templates; it does not reproduce the exact handwriting or generate original artwork.

> **Documentation basis:** This guide describes the supplied `main` code snapshot and the separately updated local/cloud predictor scripts. Live GitHub access was unavailable during preparation. Check the commands against the final submission checkout. Code presence does not establish successful execution or measured benchmark results.

## 1. Choose a workflow

| Workflow | Entry point | What it does |
|---|---|---|
| Local standalone test | `local_mnist_predictor.py` | Select an MNIST image, print prediction and class scores, and display the image |
| Cloud standalone test | `cloud_mnist_predictor_bigquery.py` | Run interactive predictions, time the prediction call and upload metrics to BigQuery |
| Integrated ROS perception | `mnist_perception_node.py` | Receive `/sketch_image`, predict the digit and publish `/digit_prediction` and `/strokes` |

The standalone BigQuery script is not the ROS perception node. Starting it does not publish drawing instructions or launch the arm.

## 2. Files

Paths below are relative to `perception/` in the supplied repository snapshot.

| File | Purpose |
|---|---|
| `mnist_cnn_baseline.keras` | Trained CNN used for both edge and cloud placements; keep this artifact available |
| `ENGPROJ.ipynb` | Model-development notebook; inspect its cells for training and evaluation details |
| `local_mnist_predictor.py` | Interactive local recognition demo; no inference timing or persistent logging |
| `cloud_mnist_predictor_bigquery.py` | Interactive cloud recognition and BigQuery metrics |
| `mnist_perception_node.py` | Native ROS 2 perception and stroke-template publication |
| `prediction_listener_node.py` | Native ROS listener for digit predictions |
| `mnist_source_node.py` | Older native ROS source; incompatible completion-message type in the reviewed snapshot |
| `README_GCP_CNN.md` | Detailed standalone GCP setup and logging guide |
| `GCP_VM_BigQuery_Partner_Handoff.md` | Partner permissions, VM access and BigQuery handoff |

The integrated capture and actuation packages live outside this folder:

- `sim/sketch_capture/`: repeatable MNIST input and capture CSVs.
- `sim/arm_drawing/`: trajectories, completion feedback and arm CSVs.
- `docs/interfaces.md`: shared ROS interface specification. Some timing/joining notes in the reviewed version are outdated; use the source timestamp procedure below.

## 3. Model and preprocessing

Keep `mnist_cnn_baseline.keras` beside the predictor scripts. Their default model paths are relative to the script location, not the terminal's working directory. Use the same model artifact for comparable placements; record its checksum and the code commit used for each experiment.

For controlled MNIST input:

1. Use a 28 × 28 grayscale image with a white digit on a black background.
2. Convert pixels to `float32` and divide by `255.0`.
3. Reshape to `(1, 28, 28, 1)` for batch, height, width and channel dimensions.
4. Run the CNN and select the digit with the highest class score.
5. In ROS mode, select that digit's fixed stroke template.

Ground-truth labels are used to check correctness, not passed into the CNN. Confidence is the largest model score and does not guarantee a correct prediction.

## 4. Standalone local setup

Run from the repository root. Create the environment only if an appropriate one does not already exist:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install tensorflow numpy matplotlib
python perception/local_mnist_predictor.py
```

TensorFlow must support the machine's Python version and architecture. Record the actual working versions for reproducibility. The commands above list dependencies; they do not provide a pinned environment.

MNIST is loaded through Keras and may download on first use. Keep the dataset cached for offline demonstrations.

| Input | Action |
|---|---|
| Enter | Select a random test image |
| `0`–`9999` | Select that MNIST test-image index |
| `q` | Exit |

Close the image window to continue when the plotting backend blocks. The local script prints the predicted digit, confidence and all ten class scores. It does not measure latency or save metrics.

## 5. Standalone cloud workflow

Reuse the existing resources:

| Resource | Value |
|---|---|
| GCP project | `responsive-cocreation` |
| VM | `ros2-perception-vm` |
| Zone | `australia-southeast1-a` |
| BigQuery table | `responsive-cocreation.cnn_experiments.cnn_trials` |
| Original standalone directory | `~/responsive-cocreation/perception` under the owner's Linux account |

From an authorised local terminal:

```bash
gcloud compute ssh ros2-perception-vm \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a
```

Inside the VM, activate the existing standalone environment and run:

```bash
cd ~/responsive-cocreation/perception
source .venv/bin/activate
python cloud_mnist_predictor_bigquery.py
```

A partner's home directory is separate; use the actual accessible location arranged with the owner. If preparing a new environment, dependencies are `tensorflow`, `numpy`, `matplotlib` and `google-cloud-bigquery`. Preserve the existing working `.venv`.

The BigQuery client resolves application default credentials, normally the VM's attached service account. Do not embed credential files in the source. Follow the handoff for IAM, scopes and collaborator access.

The cloud script uses the same interactive controls as the local script. It attempts one upload per valid selection and reports success or failure. Matplotlib display is optional to the recognition/logging logic; for headless execution, a noninteractive backend can be selected:

```bash
MPLBACKEND=Agg python cloud_mnist_predictor_bigquery.py
```

This suppresses an interactive image window; it does not remove the input prompt or save plots automatically.

### Logged metrics

| Field | Meaning |
|---|---|
| `trial_number` | Counter within this script session; resets on restart |
| `mnist_index` | Selected test-image index |
| `ground_truth`, `prediction` | Correct label and predicted digit |
| `confidence` | Highest model score as a fraction |
| `inference_ms` | Elapsed time around `model.predict()` |
| `device` | Script label: `Google Cloud VM` |
| `correct` | Whether prediction equals the label |
| `timestamp` | UTC time when the upload row was prepared |

Timing excludes preprocessing, plotting and BigQuery upload. First-call overhead can affect it. It is not the integrated ROS latency metric. BigQuery stores metrics, not images or stroke messages. An upload failure is printed and the interactive loop continues.

Inspect recent rows in BigQuery:

```sql
SELECT timestamp, device, trial_number, mnist_index,
       ground_truth, prediction, confidence, inference_ms, correct
FROM `responsive-cocreation.cnn_experiments.cnn_trials`
ORDER BY timestamp DESC
LIMIT 20;
```

## 6. Native ROS 2 perception

Use the ROS 2 Jazzy Ubuntu environment, with a Python interpreter that can import `rclpy`, `sensor_msgs`, `std_msgs`, NumPy and TensorFlow. A plain standalone virtual environment may hide ROS packages. Confirm imports before launching:

```bash
python -c "import rclpy, numpy, tensorflow; from sensor_msgs.msg import Image; from std_msgs.msg import Int32, String"
```

Source ROS in every participating terminal. If using the existing `~/venv-ros` environment from the integration setup, activate it; otherwise use your prepared ROS-compatible interpreter:

```bash
source /opt/ros/jazzy/setup.bash
source ~/venv-ros/bin/activate
export ROS_DOMAIN_ID=30
```

Use the agreed default Fast DDS configuration consistently across machines. For cloud deployment, confirm the existing Tailscale and DDS connectivity configuration; a shared domain ID alone does not establish cross-network discovery. Keep DDS ports off the public internet.

From the integration checkout's repository root, run:

```bash
python perception/mnist_perception_node.py
```

The cloud integration handoff uses `~/rc-main` and `~/venv-ros`, separate from the standalone BigQuery directory and `.venv`. Preserve both environments.

The node loads the model and waits for images. An optional listener in another prepared terminal is:

```bash
python perception/prediction_listener_node.py
```

### Topic contract

| Topic | Message type | Direction relative to perception |
|---|---|---|
| `/sketch_image` | `sensor_msgs/msg/Image` | Input from capture |
| `/digit_prediction` | `std_msgs/msg/Int32` | Output digit, 0–9 |
| `/strokes` | `std_msgs/msg/String` containing JSON | Output template, prediction and source identity |
| `/turn_done` | `std_msgs/msg/Bool` | Arm-to-capture feedback; the perception node does not publish it |

The image must be 28 × 28, `mono8`, normally `step=28` and `frame_id=canvas`. The input subscription is reliable, keep last 1. The output publishers use depth 10. The node validates dimensions, encoding and buffer length, accounting for row stride.

A stroke message contains:

| JSON field | Meaning |
|---|---|
| `trial` | Perception's received-image counter |
| `digit`, `confidence` | Predicted class and highest score |
| `source_stamp.sec`, `source_stamp.nanosec` | Original image header timestamp |
| `frame_id` | Original image frame |
| `strokes` | List of strokes, each containing normalised `[x, y]` points |

Coordinates use a top-left origin, with x increasing rightward and y downward. Separate strokes imply pen lifts. Templates must remain consistent with the arm's precomputed trajectories.

The node publishes the digit, then strokes. Do not rely on cross-topic delivery order as a timestamp association mechanism. Use the source timestamp in `/strokes`.

### Capture and arm startup

Build and configure the simulation packages using their own READMEs. Start the Kinova controller environment and arm drawing node, then perception, then capture. On the simulation VM, source ROS and the built workspace before these package commands:

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_kortex_ws/install/setup.bash
export ROS_DOMAIN_ID=30
ros2 launch arm_drawing arm_drawing.launch.py
```

In another prepared simulation terminal:

```bash
ros2 launch sketch_capture sketch_capture.launch.py \
  seed:=42 per_digit:=3 image_format:=mnist
```

`per_digit:=3` gives 30 trials; the package default is 10 per digit, or 100 trials. The MNIST IDX test files must already be available; see `sim/sketch_capture/README.md` for download and dataset-path setup. Use a new CSV filename for each run because explicit output paths may be overwritten.

Capture waits for an image subscriber and then for arm completion between turns. A failed arm attempt can also release the next image, so inspect status logs. Do not manually publish completion during measured runs.

Use `sketch_capture` for integration. The older `mnist_source_node.py` subscribes to `/turn_done` as `Empty`, conflicting with the current `Bool` contract. Do not start multiple image sources or multiple perception publishers for the same measured run.

## 7. Verification and experiment records

First establish individual functionality, then one integrated turn, then repeated benchmark runs.

1. Confirm model loading and a selected MNIST prediction in standalone mode.
2. For cloud logging, verify both the upload message and the corresponding table row.
3. In ROS, inspect `/digit_prediction` and `/strokes` and confirm the source timestamp survives.
4. Verify that the arm finishes a valid trajectory, records status `ok`, and releases capture.
5. Compare predicted digits against capture labels separately from arm status.
6. Warm up perception before official measurements and document the warm-up procedure.
7. Use the same code commit, model, seeded sequence and simulation configuration for both placements. Record hardware, package versions, network path and run order.
8. Preserve capture CSVs, arm CSVs, perception logs and run metadata. Report failed turns separately from successful-turn latency.

For the integrated metric:

**Sketch-to-strokes latency = simulation stroke-receipt time − simulation image-publication time.**

Both endpoints originate on the simulation VM. This includes communication and perception up to stroke receipt, and excludes arm motion. Separate timing across different hosts would require clock alignment.

Join capture and arm records by the source timestamp pair `(sec, nanosec)`, using the corresponding column names in each CSV. Do not assume perception's trial counter matches capture trial numbers after warm-up, restarts or invalid images. The reviewed interface document contains older trial-number joining advice.

Useful diagnostics in prepared ROS terminals:

```bash
ros2 topic list
ros2 topic info /sketch_image --verbose
ros2 topic echo /digit_prediction
ros2 topic echo /strokes
```

These checks are procedures, not a statement that the current deployment has passed. No new runtime or benchmark results were generated while writing this README.

## 8. Troubleshooting

| Symptom | Check |
|---|---|
| Model not found | Keep `mnist_cnn_baseline.keras` beside the predictor script |
| TensorFlow import/load failure | Active interpreter, supported platform and recorded working package versions |
| `rclpy` not found | Source Jazzy and use the ROS-compatible interpreter |
| MNIST download fails | Initial network access and dataset cache |
| Image rejected by ROS perception | 28 × 28 `mono8`; use `image_format:=mnist`, not the 280 × 280 canvas mode |
| Capture waits indefinitely | Perception subscriber, ROS domain, DDS/network connectivity and arm completion status |
| Completion type conflict | Use `std_msgs/msg/Bool` and the current capture package |
| Repeated or mixed predictions | Check for duplicate source/perception processes |
| Prediction appears but strokes do not | Perception logs, template lookup and JSON output |
| Plot unavailable over SSH | Use a noninteractive backend for the standalone cloud script |
| BigQuery authentication/permission error | Attached VM service account, dataset access and VM scopes |
| Trials appear misaligned | Join by source timestamp, not independently reset counters |

## 9. Submission and maintenance

Keep source, this README, the trained model and reviewed documentation. Document where the model came from and the evaluation actually performed; do not infer accuracy from a few interactive trials.

Before submission, clear notebook outputs and execution counts, remove personal kernel paths, and document the environment needed to rerun it. Keep the notebook's training code intact.

Do not commit virtual environments, caches, private credentials, SSH keys or downloaded datasets. Keep environment files containing credentials out of version control.

Suggested repository ignore rules:

```gitignore
.venv/
venv-ros/
__pycache__/
*.py[cod]
.ipynb_checkpoints/
.env
*.env
```

The trained model is intentionally retained; do not ignore all `.keras` files for this submission. Review generated logs separately and retain the experiment evidence required for assessment.
