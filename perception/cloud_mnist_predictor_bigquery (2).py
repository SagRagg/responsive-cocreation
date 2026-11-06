#!/usr/bin/env python3
"""Run interactive MNIST CNN predictions and record trial metrics in BigQuery.

Keep mnist_cnn_baseline.keras beside this script. BigQuery uses the credentials
resolved by the Google Cloud client, typically the attached VM service account.
This standalone demo does not run the ROS drawing pipeline."""
import random, time
from datetime import datetime, timezone
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from google.cloud import bigquery

# Resolve the model beside the script, independent of the current working directory.
BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "mnist_cnn_baseline.keras"
# Reuse the existing experiment table rather than creating new cloud resources.
PROJECT_ID = "responsive-cocreation"
FULL_TABLE_ID = f"{PROJECT_ID}.cnn_experiments.cnn_trials"

# Use application default credentials; no service-account key is embedded here.
bq = bigquery.Client(project=PROJECT_ID)

def preprocess(image):
    """Normalise a grayscale digit and add batch and channel dimensions."""
    # Convert 0–255 pixels to 0–1 and form (batch, height, width, channels).
    return (image.astype("float32") / 255.0).reshape(1, 28, 28, 1)

def predict_digit(model, image):
    """Return the predicted digit, confidence, class scores and prediction-call time.

    Timing wraps model.predict only, excluding preprocessing, plotting and upload.
    The first call may include initialisation overhead; this is not ROS latency."""
    x = preprocess(image)
    start = time.perf_counter()
    probs = model.predict(x, verbose=0)[0]
    ms = (time.perf_counter() - start) * 1000.0
    # Class positions correspond to digits 0–9; confidence is the largest score.
    return int(np.argmax(probs)), float(np.max(probs)), probs, ms

def upload_trial(trial, index, truth, pred, conf, ms):
    """Insert one trial record and raise an error if BigQuery rejects the row.

    Confidence is stored as a fraction, and the timestamp records upload-row
    creation in UTC. Trial numbers restart from one in each program session."""
    row = {
        "trial_number": trial,
        "mnist_index": index,
        "ground_truth": truth,
        "prediction": pred,
        "confidence": conf,
        "inference_ms": ms,
        "device": "Google Cloud VM",
        "correct": pred == truth,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    # The API can report row-level errors without raising a Python exception.
    errors = bq.insert_rows_json(FULL_TABLE_ID, [row])
    if errors:
        raise RuntimeError(errors)

def main():
    """Load the model and test set, then predict and log user-selected images."""
    model = tf.keras.models.load_model(MODEL_PATH)
    # Discard the training split and use the held-out MNIST test split.
    (_, _), (x_test, y_test) = tf.keras.datasets.mnist.load_data()
    print(f"BigQuery table: {FULL_TABLE_ID}")
    print("ENTER=random | 0-9999=specific | q=quit")
    # This counter is session-local, not a globally unique trial identifier.
    trial = 0

    while True:
        choice = input("\nChoose test image: ").strip().lower()
        if choice == "q":
            break
        # Blank input samples a test image; numeric input selects a test index.
        if choice == "":
            index = random.randrange(len(x_test))
        else:
            try:
                index = int(choice)
            except ValueError:
                print("Enter 0-9999, ENTER, or q.")
                continue
            if not 0 <= index < len(x_test):
                print("Index must be 0-9999.")
                continue

        # Count only valid selections and convert labels to ordinary Python integers.
        trial += 1
        image = x_test[index]
        truth = int(y_test[index])
        pred, conf, probs, ms = predict_digit(model, image)

        print(f"Trial:          {trial}")
        print(f"MNIST index:    {index}")
        print(f"Ground truth:   {truth}")
        print(f"Prediction:     {pred}")
        print(f"Confidence:     {conf*100:.2f}%")
        print(f"Inference time: {ms:.2f} ms")
        print(f"Correct:        {pred == truth}")

        # Keep the interactive demo usable even if a metric upload fails.
        try:
            upload_trial(trial, index, truth, pred, conf, ms)
            print("BigQuery upload: SUCCESS")
        except Exception as exc:
            print(f"BigQuery upload: FAILED - {exc}")

        # Display the original image; close the plot to continue in blocking backends.
        plt.figure(figsize=(4,4))
        plt.imshow(image, cmap="gray")
        plt.title(f"True: {truth} | Pred: {pred}\n{conf*100:.2f}% | {ms:.2f} ms")
        plt.axis("off")
        plt.show()

if __name__ == "__main__":
    main()
