#!/usr/bin/env python3
import random, time
from datetime import datetime, timezone
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from google.cloud import bigquery

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "mnist_cnn_baseline.keras"
PROJECT_ID = "responsive-cocreation"
FULL_TABLE_ID = f"{PROJECT_ID}.cnn_experiments.cnn_trials"

bq = bigquery.Client(project=PROJECT_ID)

def preprocess(image):
    return (image.astype("float32") / 255.0).reshape(1, 28, 28, 1)

def predict_digit(model, image):
    x = preprocess(image)
    start = time.perf_counter()
    probs = model.predict(x, verbose=0)[0]
    ms = (time.perf_counter() - start) * 1000.0
    return int(np.argmax(probs)), float(np.max(probs)), probs, ms

def upload_trial(trial, index, truth, pred, conf, ms):
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
    errors = bq.insert_rows_json(FULL_TABLE_ID, [row])
    if errors:
        raise RuntimeError(errors)

def main():
    model = tf.keras.models.load_model(MODEL_PATH)
    (_, _), (x_test, y_test) = tf.keras.datasets.mnist.load_data()
    print(f"BigQuery table: {FULL_TABLE_ID}")
    print("ENTER=random | 0-9999=specific | q=quit")
    trial = 0

    while True:
        choice = input("\nChoose test image: ").strip().lower()
        if choice == "q":
            break
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

        try:
            upload_trial(trial, index, truth, pred, conf, ms)
            print("BigQuery upload: SUCCESS")
        except Exception as exc:
            print(f"BigQuery upload: FAILED - {exc}")

        plt.figure(figsize=(4,4))
        plt.imshow(image, cmap="gray")
        plt.title(f"True: {truth} | Pred: {pred}\n{conf*100:.2f}% | {ms:.2f} ms")
        plt.axis("off")
        plt.show()

if __name__ == "__main__":
    main()
