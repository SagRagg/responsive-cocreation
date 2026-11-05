# Google Cloud CNN and BigQuery: Partner Handoff

## Purpose and scope

Use the existing Google Cloud setup to run the trained MNIST digit classifier and inspect its recorded metrics. Reuse the project, VM, dataset and table listed below.

This guide covers the **standalone CNN and BigQuery workflow**. It does not launch the distributed ROS 2 drawing pipeline. ROS 2 and a VPN are not required for this standalone demo.

The original handoff reports successful model inference and BigQuery uploads. Those are **historical observations**, not a fresh verification of the current environment.

## Existing resources

| Resource | Value |
|---|---|
| Project ID | `responsive-cocreation` |
| Project number | `1042594693205` |
| Region | `australia-southeast1` (Sydney) |
| Zone | `australia-southeast1-a` |
| VM | `ros2-perception-vm` |
| VM configuration | Ubuntu 24.04, `e2-standard-2`, CPU only |
| BigQuery dataset | `cnn_experiments` |
| BigQuery table | `responsive-cocreation.cnn_experiments.cnn_trials` |
| Trained model | `mnist_cnn_baseline.keras` |
| Prediction script | `cloud_mnist_predictor_bigquery.py` |
| Original owner directory | `~/responsive-cocreation/perception`, under the owner's Linux account |

The model is the trained MNIST CNN retained for the project. Use the same model artifact for comparable edge and cloud runs.

## 1. Arrange access

Each partner must use their own Google account and Linux login. Never share passwords, private SSH keys or service-account credential files.

### View BigQuery results

The owner grants the partner:

| Role | Scope | Purpose |
|---|---|---|
| BigQuery Job User (`roles/bigquery.jobUser`) | Project `responsive-cocreation` | Run query jobs |
| BigQuery Data Viewer (`roles/bigquery.dataViewer`) | Dataset `cnn_experiments` | Read experiment data |

Use the [IAM console](https://console.cloud.google.com/iam-admin/iam?project=responsive-cocreation) for project access and the dataset's sharing settings in the [BigQuery console](https://console.cloud.google.com/bigquery?project=responsive-cocreation) for dataset access.

### Run the model over SSH

SSH access is separate from BigQuery access. Confirm the VM's existing login method with the owner before changing it.

- **Metadata-based SSH:** the original setup used this method. The owner can add the partner's public SSH key.
- **OS Login:** the owner can grant `roles/compute.osLogin`. Use `roles/compute.osAdminLogin` only if administrative access is needed. Access to a VM with an attached service account may also require `roles/iam.serviceAccountUser` on that service account.

Enabling OS Login changes the login mechanism. Before enabling it, the owner must prepare the required permissions and a recovery route, then verify both users can connect afterward. The owner-approved command is:

```bash
# Owner's local terminal: only when an OS Login change is intended.
gcloud compute instances add-metadata ros2-perception-vm \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a \
  --metadata=enable-oslogin=TRUE
```

Restrict SSH to approved source addresses, or use Identity-Aware Proxy with its required IAM and firewall setup. Keep ROS/DDS ports off the public internet. Remember that VM users may be able to use its attached service account's permissions.

### Make project files accessible

Separate Linux accounts have separate home directories. The partner's `~` does not refer to the owner's home.

The owner must provide a partner-accessible copy of the model and script, or an approved shared directory. Record that directory before proceeding. Preserve the owner's working files and existing virtual environment.

## 2. Configure the partner's local terminal

Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) if required. Run these commands in a local terminal, such as the VS Code terminal on the partner's Mac:

```bash
gcloud init
gcloud config set project responsive-cocreation
gcloud config set compute/zone australia-southeast1-a
gcloud auth list
```

Confirm the active account, marked `*`, is the partner's own account with the permissions above.

## 3. Connect to the VM

Check its status from the local terminal:

```bash
gcloud compute instances list --project=responsive-cocreation
```

If it is `TERMINATED`, the owner can start it:

```bash
# Owner's local terminal
gcloud compute instances start ros2-perception-vm \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a
```

SSH and BigQuery viewer permissions do not automatically grant start/stop access. Once the VM is running, connect from the partner's local terminal:

```bash
gcloud compute ssh ros2-perception-vm \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a
```

## 4. Run the standalone predictor

On the VM, change to the directory the owner provided. The example below assumes the files have been copied into the partner's own `~/responsive-cocreation/perception` directory; adjust the path if they are elsewhere.

```bash
# On the VM
cd ~/responsive-cocreation/perception
ls -l mnist_cnn_baseline.keras cloud_mnist_predictor_bigquery.py
source .venv/bin/activate
python cloud_mnist_predictor_bigquery.py
```

Reuse an existing working environment. Only if the partner's directory has no environment, create and install one there:

```bash
# On the VM, inside the partner's project directory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install tensorflow numpy matplotlib google-cloud-bigquery
python cloud_mnist_predictor_bigquery.py
```

The script accepts:

| Input | Action |
|---|---|
| Enter | Select a random MNIST test image |
| `0`–`9999` | Select a specific test-image index |
| `q` | Quit |

### Historical example

The original handoff recorded this output for index `1`:

```text
MNIST index:    1
Ground truth:   2
Prediction:     2
Confidence:     100.00%
Inference time: 1044.83 ms
Correct:        True
BigQuery upload: SUCCESS
```

This single observation is not an accuracy evaluation or an edge/cloud benchmark. The first inference can be slower during initialisation. The CPU-only VM may also print CUDA warnings; inspect whether execution actually fails.

BigQuery uploads use the VM's attached service account and permissions. They do not use the partner's local Google login. The original setup reported a `cloud-platform` VM OAuth scope. For upload failures, check the service account's IAM permissions and VM scopes rather than embedding credentials in code.

## 5. Inspect BigQuery results

Open the [BigQuery console](https://console.cloud.google.com/bigquery?project=responsive-cocreation). Confirm the project is exactly `responsive-cocreation`, then open `cnn_experiments` and `cnn_trials`.

### Latest records

```sql
SELECT timestamp, device, trial_number, mnist_index,
       ground_truth, prediction, confidence, inference_ms, correct
FROM `responsive-cocreation.cnn_experiments.cnn_trials`
ORDER BY timestamp DESC
LIMIT 20;
```

### Exploratory summary by device

```sql
SELECT device,
       COUNT(*) AS trials,
       ROUND(AVG(inference_ms), 2) AS average_inference_ms,
       ROUND(AVG(IF(correct, 1, 0)) * 100, 2) AS accuracy_percent
FROM `responsive-cocreation.cnn_experiments.cnn_trials`
GROUP BY device;
```

This summary pools all stored rows per device. For formal comparisons, select comparable runs and account for warm-up and input selection. `inference_ms` measures model inference, not the integrated sketch-to-strokes latency.

The table stores metrics rather than images. `trial_number` resets when the script restarts, so it is not a unique record identifier. Use timestamps to inspect session order; an explicit `run_id` would improve future session grouping. For the integrated ROS experiment, follow its separate log-joining procedure.

### Query from the local terminal

```bash
bq --project_id=responsive-cocreation --location=australia-southeast1 \
  query --use_legacy_sql=false \
  'SELECT * FROM `responsive-cocreation.cnn_experiments.cnn_trials` ORDER BY timestamp DESC LIMIT 20'
```

## 6. End the session

On the VM, enter `q` to quit the predictor, then `exit` to disconnect SSH. When the VM is no longer needed by either partner, the owner can stop it from their local terminal:

```bash
gcloud compute instances stop ros2-perception-vm \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a
```

The original setup did not permit stopping the VM from its own service account. Use the authorised owner's local account. Stopping the VM avoids ongoing running-instance charges, but disks and other provisioned resources may still incur costs.

## 7. Troubleshooting

| Symptom | Check |
|---|---|
| SSH permission denied | Active identity, configured login method, IAM, service-account access and firewall |
| SSH connection refused | VM state, boot completion and SSH service |
| Model or script missing | Partner's directory versus owner's directory; confirm the shared path |
| Missing Python module | Activate the intended `.venv` and install dependencies into that interpreter |
| BigQuery reports insufficient authentication scopes | VM OAuth scope; original setup used `cloud-platform` |
| BigQuery permission denied during upload | Attached VM service account's data-insertion permissions |
| Table absent in the console | Exact project ID, active Google account and dataset access |
| New rows absent | Predictor upload result, table selection and refreshed query |

## Handoff boundaries

1. Reuse the existing infrastructure.
2. Verify the active Google identity and file locations before running commands.
3. Obtain owner approval before changing IAM, SSH, firewall, VM scopes or billing resources.
4. Preserve the working model, predictor and virtual environment.
5. Treat BigQuery viewing and VM execution as separate permissions.
6. Report successful access, inference or uploads only after observing them in the current session.

## Official references

- [Set up OS Login](https://cloud.google.com/compute/docs/oslogin/set-up-oslogin)
- [SSH login security practices](https://cloud.google.com/compute/docs/connect/ssh-best-practices/login-access)
- [BigQuery permissions](https://cloud.google.com/bigquery/docs/access-control)
- [Running BigQuery queries](https://cloud.google.com/bigquery/docs/running-queries)
