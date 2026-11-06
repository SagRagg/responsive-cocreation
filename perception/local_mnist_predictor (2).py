#!/usr/bin/env python3
"""Run an interactive local demonstration of the trained MNIST digit classifier.

Place mnist_cnn_baseline.keras beside this script. Users can select a test-image
index or request a random image, inspect class scores and view the result.
This script does not measure latency, upload metrics or control a robot."""

from pathlib import Path
import random

import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf


# Locate the model relative to this file rather than the terminal directory.
MODEL_PATH = Path(__file__).resolve().parent / "mnist_cnn_baseline.keras"


def load_data():
    """Return the held-out MNIST test images and labels, discarding training data."""
    (_, _), (x_test, y_test) = tf.keras.datasets.mnist.load_data()
    return x_test, y_test


def preprocess(image):
    """Convert pixel values to float32 in 0–1 and create a (1, 28, 28, 1) input."""
    # Same preprocessing used during training.
    image = image.astype("float32") / 255.0
    # Add one batch dimension and one grayscale channel for the CNN.
    return image.reshape(1, 28, 28, 1)


def predict_digit(model, image):
    """Return the predicted digit, its confidence and all ten class scores.

    Confidence is the largest model score and does not guarantee correctness."""
    model_input = preprocess(image)
    predictions = model.predict(model_input, verbose=0)[0]

    # Model output positions 0–9 map directly to the ten digit classes.
    predicted_digit = int(np.argmax(predictions))
    confidence = float(np.max(predictions))

    return predicted_digit, confidence, predictions


def show_result(image, true_digit, predicted_digit, confidence):
    """Display the input image with its true label, prediction and confidence."""
    plt.figure(figsize=(4, 4))
    plt.imshow(image, cmap="gray")
    plt.title(
        f"True: {true_digit} | Predicted: {predicted_digit}\n"
        f"Confidence: {confidence * 100:.2f}%"
    )
    plt.axis("off")
    # In blocking backends, close the plot window to return to the prompt.
    plt.show()


def main():
    """Validate the model path and run the interactive test-image selection loop."""
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Model not found: {MODEL_PATH}\n"
            "Put mnist_cnn_baseline.keras in the same folder as this script."
        )

    print("Loading CNN model...")
    model = tf.keras.models.load_model(MODEL_PATH)
    print("Model loaded.")

    print("Loading MNIST test dataset...")
    x_test, y_test = load_data()
    print(f"Loaded {len(x_test)} test images.")

    print("\nControls:")
    print("  ENTER = test a random MNIST image")
    print("  number 0-9999 = test that exact MNIST test index")
    print("  q = quit")

    while True:
        choice = input("\nChoose test image: ").strip().lower()

        if choice == "q":
            print("Exiting.")
            break

        # Blank input samples randomly; otherwise validate the requested test index.
        if choice == "":
            index = random.randrange(len(x_test))
        else:
            try:
                index = int(choice)
            except ValueError:
                print("Enter a number from 0-9999, press ENTER, or type q.")
                continue

            if not 0 <= index < len(x_test):
                print(f"Index must be between 0 and {len(x_test) - 1}.")
                continue

        # The test label provides the ground truth for checking recognition.
        image = x_test[index]
        true_digit = int(y_test[index])

        predicted_digit, confidence, predictions = predict_digit(
            model,
            image,
        )

        print("\n------------------------------")
        print(f"MNIST index:     {index}")
        print(f"Ground truth:    {true_digit}")
        print(f"CNN prediction:  {predicted_digit}")
        print(f"Confidence:      {confidence * 100:.2f}%")
        print("------------------------------")

        # Show every class score to help inspect ambiguous model predictions.
        print("Class probabilities:")
        for digit, probability in enumerate(predictions):
            print(f"  {digit}: {probability * 100:.2f}%")

        show_result(
            image,
            true_digit,
            predicted_digit,
            confidence,
        )


if __name__ == "__main__":
    main()
