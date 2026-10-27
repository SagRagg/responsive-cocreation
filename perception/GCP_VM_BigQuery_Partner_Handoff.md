# Google Cloud CNN + BigQuery — Partner / Agent Handoff

## Purpose

Instructions for a project partner and their coding agent to use **existing** Google Cloud infrastructure to run a trained MNIST CNN and read its results. **Do not create a second project, VM, dataset or table.**

### Existing resources (already tested)

| Item | Value |
|---|---|
| GCP project ID | `responsive-cocreation` |
| Project number | `1042594693205` |
| Region / zone | Sydney, `australia-southeast1-a` |
| VM | `ros2-perception-vm` (Ubuntu 24.04, `e2-standard-2`, CPU only) |
| BigQuery dataset | `cnn_experiments` |
| BigQuery table | `responsive-cocreation.cnn_experiments.cnn_trials` |
| Model | `mnist_cnn_baseline.keras` |
| Running script | `cloud_mnist_predictor_bigquery.py` |
| Owner's project directory on VM | `~/responsive-cocreation/perception` (under the owner's Linux account) |

**Verified:** The VM loads TensorFlow and the `.keras` model, predicts MNIST digits, and prints `BigQuery upload: SUCCESS` after writing experiment metrics to BigQuery. ROS 2 installation and a VPN are **not necessary** to run this standalone MNIST demo.

## 1. Owner: authorise partner's own Google account

The partner must use **their own Google identity**. Do not share passwords, SSH private keys, service-account keys or JSON credentials.

### BigQuery read-only access (recommended minimum)

In the [Google Cloud IAM console](https://console.cloud.google.com/iam-admin/iam?project=responsive-cocreation), give the partner **BigQuery Job User** (`roles/bigquery.jobUser`) on project `responsive-cocreation`. In the [BigQuery console](https://console.cloud.google.com/bigquery?project=responsive-cocreation), find `cnn_experiments` → **Sharing/Permissions** and grant **BigQuery Data Viewer** (`roles/bigquery.dataViewer`) to the partner on that dataset. This permits queries without broad write access.

### SSH access to execute the model (optional)

Google recommends **OS Login**, which maps the partner's Google identity to a separate Linux account. Owner grants `Compute OS Login` (`roles/compute.osLogin`) with appropriate VM/project permissions. Avoid `Compute OS Admin Login` unless the partner actually needs sudo. If the VM has an attached service account, OS Login may also require `Service Account User` (`roles/iam.serviceAccountUser`) *on that service account*. Beware that SSH users may be able to use the VM's service account permissions; keep them minimal.

**Important:** The VM currently used metadata-based SSH keys for its owner's access. **Enabling OS Login changes that login mechanism**. The owner should check that **both** can still log in before making this change. Once prepared, owner can enable it from their Mac:

```bash
gcloud compute instances add-metadata ros2-perception-vm \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a \
  --metadata=enable-oslogin=TRUE
```

Alternatively, the owner can provision the partner's **public** SSH key in VM metadata without enabling OS Login. Never share private keys. Restrict SSH to approved source addresses (or use Identity-Aware Proxy with its necessary IAM/firewall setup). Do not publicly expose ROS/DDS ports.

**Separate home directories:** After granting SSH access, the partner will not automatically have permission to read files under the owner's `/home/...` directory. The owner must copy the model and script into a partner-accessible directory and set appropriate permissions. Do not assume the `~/responsive-cocreation/perception` path of one user is shared with another.

## 2. Partner: VS Code/Mac setup

Install [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) if needed. In VS Code → Terminal → New Terminal:

```bash
gcloud init
gcloud config set project responsive-cocreation
gcloud config set compute/zone australia-southeast1-a
gcloud auth list
```

Confirm the `*` account is **your own** Google email (the account the owner granted access to).

## 3. Access VM and run the CNN

From the **partner's Mac**, check VM state:

```bash
gcloud compute instances list --project=responsive-cocreation
```

If status is `TERMINATED`, ask the owner to start it (SSH and BigQuery viewer roles don't automatically grant start/stop):

```bash
# Owner runs this from Mac
gcloud compute instances start ros2-perception-vm \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a
```

When running, the partner connects:

```bash
gcloud compute ssh ros2-perception-vm \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a
```

On the VM, locate the shared model and script (ask owner for shared folder path). The original owner's files were in `~/responsive-cocreation/perception` **under the owner's account**. If necessary, owner can locate them:

```bash
find /home -name 'mnist_cnn_baseline.keras' 2>/dev/null
find /home -name 'cloud_mnist_predictor_bigquery.py' 2>/dev/null
```

In your own accessible project directory containing **both files**:

```bash
cd ~/responsive-cocreation/perception
python3 -m venv .venv   # only if needed
source .venv/bin/activate
python -m pip install tensorflow numpy matplotlib google-cloud-bigquery  # only if needed
python cloud_mnist_predictor_bigquery.py
```

The script prompts `ENTER=random | 0-9999=specific | q=quit`. Type `1` to test MNIST index 1; type `q` to exit. Example **previously observed** run:

```text
MNIST index:    1
Ground truth:   2
Prediction:     2
Confidence:     100.00%
Inference time: 1044.83 ms
Correct:        True
BigQuery upload: SUCCESS
```

The first inference can be slower due to model initialisation. The VM has no CUDA GPU; CUDA warnings are expected. BigQuery upload uses the **VM's attached service account** and its IAM access, not the partner's Mac login. The VM OAuth scope was previously updated to `cloud-platform`. If uploads fail, check attached service-account IAM rather than adding secrets to code.

## 4. Read results in the Google Cloud browser

Open: **https://console.cloud.google.com/bigquery?project=responsive-cocreation**

Ensure **project ID** is exactly `responsive-cocreation` (not the unrelated `responsive-cocreation-512712`). In Explorer: project → `cnn_experiments` → `cnn_trials` → **Preview**.

To see the newest data, run:

```sql
SELECT timestamp, device, trial_number, mnist_index,
       ground_truth, prediction, confidence, inference_ms, correct
FROM `responsive-cocreation.cnn_experiments.cnn_trials`
ORDER BY timestamp DESC
LIMIT 20;
```

To summarise results per device:

```sql
SELECT device,
       COUNT(*) AS trials,
       ROUND(AVG(inference_ms), 2) AS average_inference_ms,
       ROUND(AVG(IF(correct, 1, 0)) * 100, 2) AS accuracy_percent
FROM `responsive-cocreation.cnn_experiments.cnn_trials`
GROUP BY device;
```

These are **metrics only**, not the images themselves. The script's `trial_number` resets every time it restarts; use `timestamp` (and later optionally add `run_id`) to distinguish sessions.

### Query from the partner's Mac instead

```bash
bq --project_id=responsive-cocreation --location=australia-southeast1 \
  query --use_legacy_sql=false \
  'SELECT * FROM `responsive-cocreation.cnn_experiments.cnn_trials` ORDER BY timestamp DESC LIMIT 20'
```

## 5. Shut down to control cost

Quit prediction script with `q`, disconnect SSH with `exit`. Owner runs from **Mac**:

```bash
gcloud compute instances stop ros2-perception-vm \
  --project=responsive-cocreation \
  --zone=australia-southeast1-a
```

Don't attempt to stop the VM from **inside** the VM: its service account previously returned insufficient access scopes. Compute charges stop while the VM is stopped, but disk and other provisioned resources may still cost money.

## 6. Troubleshooting

| Error | Action |
|---|---|
| SSH permission denied | Confirm partner IAM, OS Login vs metadata-based keys, attached service account access, firewall |
| SSH connection refused | Check VM state, boot completion, SSH service |
| Model or Python file missing | Check *partner's* home directory versus *owner's* home directory |
| Missing Python module | Activate the right `.venv`; install into that interpreter |
| BigQuery `403 insufficient authentication scopes` | Verify VM OAuth scope (expected `cloud-platform`) |
| BigQuery `403 permission denied` | Check VM's attached service account permissions for data insertion |
| Table absent in browser | Confirm exact project ID, partner Google account, dataset IAM |
| No rows | Confirm `BigQuery upload: SUCCESS`, then refresh/re-run query |

## 7. Instructions to another coding agent

1. Reuse infrastructure; **do not create another project, VM, dataset or table**.
2. Verify which Google identity your user is signed in with.
3. Request owner approval before changing IAM, SSH, firewall, VM scopes or billing resources.
4. Ensure each person has their own login; do not use owner's private SSH key.
5. Confirm model/script are accessible to the partner's Linux account before running.
6. Use BigQuery read-only role for viewing; separate it from VM execution access.
7. Do not claim success before an actual SSH login, model inference or query succeeds.

## Google official references

- [Set up OS Login](https://cloud.google.com/compute/docs/oslogin/set-up-oslogin)
- [SSH login security practices](https://cloud.google.com/compute/docs/connect/ssh-best-practices/login-access)
- [BigQuery permissions](https://cloud.google.com/bigquery/docs/access-control)
- [Running BigQuery queries](https://cloud.google.com/bigquery/docs/running-queries)
