# MNIST CNN Inference on Google Cloud

This folder contains the perception prototype for the **Responsive Co-Creation** project. A trained convolutional neural network (CNN) recognises handwritten digits from the MNIST test dataset. The cloud version runs inference on a **Google Compute Engine VM** and uploads each trial's prediction and timing metrics to **BigQuery**.

> **Current scope:** MNIST test-image classification and experiment logging. The script does **not** capture a live camera image, control the Kinova robot, or publish ROS 2 topics. Those are separate integration stages.

## How it works

```text
MNIST test image (28 × 28 grayscale)
                |
                v
       TensorFlow/Keras CNN
                |
                v
 Prediction + confidence + inference time
                |
                v
        Google Cloud BigQuery
                |
                v
responsive-cocreation.cnn_experiments.cnn_trials
```

## Files used

| File | Purpose | Required to run cloud predictor? |
| --- | --- | --- |
| `mnist_cnn_baseline.keras` | Trained TensorFlow/Keras CNN model, loaded during inference. | **Yes** |
| `cloud_mnist_predictor_bigquery.py` | Loads MNIST test images, runs the CNN, prints predictions and inference latency, and uploads results to BigQuery. | **Yes** |
| `local_mnist_predictor.py` | Earlier standalone Mac/local predictor. Does not upload to BigQuery. | No |
| `local_mnist_predictor_supabase.py` | Earlier experimental Supabase logger; **not used** for the Google Cloud pipeline. | No |
| `.venv/` | Python virtual environment; create independently on each machine. | Required environment, **do not commit** |

Both required files must be in the **same folder** on the VM. The model must retain the filename `mnist_cnn_baseline.keras`, which is the name the script expects.

The CNN was trained using TensorFlow/Keras on MNIST. Input images are converted to `float32`, normalised to `[0, 1]`, and reshaped to `(1, 28, 28, 1)` before prediction. `ground_truth` is used for evaluation only, not provided as model input.

## Existing Google Cloud resources

| Resource | Value |
| --- | --- |
| Project ID | `responsive-cocreation` |
| Compute Engine VM | `ros2-perception-vm` |
| VM zone | `australia-southeast1-a` (Sydney) |
| VM operating system | Ubuntu 24.04 |
| VM machine type | `e2-standard-2` (CPU only) |
| BigQuery dataset | `cnn_experiments` |
| BigQuery table | `cnn_trials` |
| Full table ID | `responsive-cocreation.cnn_experiments.cnn_trials` |
| VM working folder | `~/responsive-cocreation/perception` for the original VM account |

These resources have already been created. **Do not create duplicate projects, VMs, datasets or tables** when following this README. Google Cloud use can incur charges. Stop the VM when finished.

## Prerequisites

- Google Cloud CLI (`gcloud`) installed on your Mac/workstation.
- Google account authorised for the project. New collaborators require IAM/SSH access granted by the project owner; do not share passwords or private SSH keys.
- The existing VM, model, and script as described above.
- BigQuery API enabled, `cnn_trials` table created, and the VM's attached service account authorised to insert rows. The VM has previously been configured with the `cloud-platform` OAuth scope.

### 1. Select the project on your Mac

Open **VS Code → Terminal → New Terminal** (this is your **Mac** terminal, *not* the VM) and run:

```bash
gcloud auth login
gcloud config set project responsive-cocreation
gcloud config set compute/zone australia-southeast1-a
```

If already logged in, `gcloud auth login` is not needed. Verify:

```bash
gcloud auth list
gcloud config get-value project
```

### 2. Start the VM if it is stopped

**Run on your Mac:**

```bash
gcloud compute instances list --project=responsive-cocreation
```

If `ros2-perception-vm` is `TERMINATED`, start it:

```bash
gcloud compute instances start ros2-perception-vm \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a
```

If it already says `RUNNING`, do not start it again.

### 3. Connect to the VM

**Run on your Mac:**

```bash
gcloud compute ssh ros2-perception-vm \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a
```

Your prompt should now look similar to:

```text
dwaynecruz@ros2-perception-vm:~$
```

A collaborator's prompt or home directory may differ because they should have their own Linux account. They must arrange access to the model and script separately.

### 4. Check the required files

**Run inside the VM:**

```bash
cd ~/responsive-cocreation/perception
ls -lh mnist_cnn_baseline.keras cloud_mnist_predictor_bigquery.py
```

If either file is missing, copy it from your **Mac** (after exiting SSH) using the actual path to your repository:

```bash
gcloud compute scp \
  ./perception/mnist_cnn_baseline.keras \
  ./perception/cloud_mnist_predictor_bigquery.py \
  ros2-perception-vm:~/responsive-cocreation/perception/ \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a
```

The example assumes the Mac terminal is at the **repository root**. If your files are elsewhere, adjust the local paths. The destination path shown assumes you are copying to the original VM Linux account.

### 5. Activate Python and run inference

**Run inside the VM:**

```bash
cd ~/responsive-cocreation/perception
source .venv/bin/activate
python cloud_mnist_predictor_bigquery.py
```

If the VM's `.venv` does not exist, create it and install the dependencies:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
cd ~/responsive-cocreation/perception
python3 -m venv .venv
source .venv/bin/activate
python -m pip install tensorflow numpy matplotlib google-cloud-bigquery
```

For reproducible experiments, record the actual installed package versions (`python -m pip freeze`) and pin them in a project requirements file. The cloud prototype was confirmed working with **TensorFlow 2.21.0**.

### 6. Select a test image and read the output

The interactive script prompts:

```text
BigQuery table: responsive-cocreation.cnn_experiments.cnn_trials
ENTER=random | 0-9999=specific | q=quit
Choose test image:
```

- **Press Enter** to choose a random MNIST test image.
- **Enter an index from 0 to 9999** to choose a specific test image, e.g. `1`.
- **Type `q`** to quit.

Example output from a working trial (timing will vary):

```text
Trial:          1
MNIST index:    1
Ground truth:   2
Prediction:     2
Confidence:     100.00%
Inference time: 1044.83 ms
Correct:        True
BigQuery upload: SUCCESS
```

`BigQuery upload: SUCCESS` means BigQuery accepted the result. CPU-only VMs can print harmless CUDA/GPU warnings. The first inference can be slower than later trials because of TensorFlow initialization; benchmark multiple trials rather than relying on the first one.

> **Headless VM note:** The current script uses Matplotlib to show an image. If `plt.show()` causes display problems over SSH, remove or disable the Matplotlib display block (`plt.figure(...)` through `plt.show()`) before running headlessly; classification and BigQuery logging do not depend on displaying a window.

## Where results are saved

The script writes **one BigQuery row per successful upload** to:

```text
responsive-cocreation.cnn_experiments.cnn_trials
```

| Column | Meaning |
| --- | --- |
| `trial_number` | Trial counter within the current script session; resets when restarted. |
| `mnist_index` | Index in the MNIST test set (0–9999). |
| `ground_truth` | Correct MNIST digit label. |
| `prediction` | CNN's predicted digit. |
| `confidence` | Probability of predicted class, from 0 to 1. |
| `inference_ms` | Time measured around `model.predict()` in milliseconds. |
| `device` | Currently logged as `Google Cloud VM`. |
| `correct` | Whether prediction equals ground truth. |
| `timestamp` | UTC timestamp when result was prepared for upload. |

This table logs **prediction metadata**, not raw images, full probability vectors, or stroke trajectories.

### View results in the Google Cloud website

1. Open [BigQuery in Google Cloud Console](https://console.cloud.google.com/bigquery?project=responsive-cocreation).
2. Check that the **project ID** is exactly `responsive-cocreation` (**not** `responsive-cocreation-512712`, a separate project with a similar name).
3. In **Explorer**, expand `responsive-cocreation` → `cnn_experiments` → `cnn_trials`.
4. Open the **Preview** tab, or run this query:

```sql
SELECT
  timestamp,
  device,
  trial_number,
  mnist_index,
  ground_truth,
  prediction,
  confidence,
  inference_ms,
  correct
FROM `responsive-cocreation.cnn_experiments.cnn_trials`
ORDER BY timestamp DESC
LIMIT 20;
```

To summarise accuracy and inference speed:

```sql
SELECT
  device,
  COUNT(*) AS total_trials,
  ROUND(AVG(inference_ms), 2) AS avg_inference_ms,
  ROUND(100 * AVG(IF(correct, 1, 0)), 2) AS accuracy_percent
FROM `responsive-cocreation.cnn_experiments.cnn_trials`
GROUP BY device;
```

The same queries can also run using the CLI on your **Mac**:

```bash
bq --project_id=responsive-cocreation \
  --location=australia-southeast1 query --use_legacy_sql=false \
  'SELECT * FROM `responsive-cocreation.cnn_experiments.cnn_trials` ORDER BY timestamp DESC LIMIT 20'
```

## Stop the VM when done

Inside the VM, type `q` to quit the predictor, then:

```bash
exit
```

**Back on your Mac**, run:

```bash
gcloud compute instances stop ros2-perception-vm \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a
```

Do **not** try to stop the VM using `gcloud compute instances stop` from inside the VM; its attached service account has previously returned `insufficient authentication scopes` for that operation. Stopping halts VM compute charges, but disk/storage costs can continue.

## Troubleshooting

| Error | Action |
| --- | --- |
| `No such file or directory` for `.keras` | Ensure both required files are in the same VM folder. |
| `No module named tensorflow` or `google.cloud` | Activate the VM's `.venv` and install the missing dependency there. |
| `403 insufficient authentication scopes` during BigQuery upload | Check VM OAuth scopes; this VM needed `cloud-platform`. Changes to service account/scopes require owner/admin access. |
| `403 permission denied` during upload | Check the VM service account's BigQuery permissions on the destination dataset/table. |
| `ssh: Connection refused` | Verify the VM is running, SSH has started, and firewall permissions allow your connection. |
| Predictions work but no new table rows | Check for `BigQuery upload: SUCCESS`, correct project ID and permissions; rerun the query. |
| CUDA/GPU warning | Expected on the CPU-only VM. |
| Image window fails in SSH | Disable the optional Matplotlib display code and keep the prediction/logging steps. |

## GitHub notes and security

- **Commit:** this README, Python source, and your team's reviewed configuration files.
- **Do not commit:** `.venv/`, `__pycache__/`, `.env`, service-account JSON keys, private SSH keys, credentials, or downloaded datasets.
- Decide as a team whether to store `mnist_cnn_baseline.keras` in Git or Git LFS; document how to obtain it if it is excluded.
- Do not use an owner's login credentials for another collaborator. Use individual Google identities and least-privilege IAM/OS Login permissions.
- The `cloud-platform` VM access scope does **not** grant permissions on its own; IAM must separately permit the BigQuery write operation.

Suggested `.gitignore` entries:

```gitignore
.venv/
__pycache__/
.env
*.pyc
*service-account*.json
```

## Notes for integration agents

This cloud script currently runs **interactive inference directly on the VM** and writes metrics to BigQuery. It is **not an HTTP inference endpoint**, scheduled job, ROS 2 perception node, or model-serving API. Do not assume those capabilities are already deployed. To integrate ROS 2 or remote input later, implement a distinct execution interface and preserve the existing model preprocessing and BigQuery logging behavior.
