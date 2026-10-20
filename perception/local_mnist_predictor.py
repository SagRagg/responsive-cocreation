#!/usr/bin/env python3

from pathlib import Path
import random

import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf


MODEL_PATH = Path(__file__).resolve().parent / "mnist_cnn_baseline.keras"


def load_data():
    (_, _), (x_test, y_test) = tf.keras.datasets.mnist.load_data()
    return x_test, y_test


def preprocess(image):
    # Same preprocessing used during training.
    image = image.astype("float32") / 255.0
    return image.reshape(1, 28, 28, 1)


def predict_digit(model, image):
    model_input = preprocess(image)
    predictions = model.predict(model_input, verbose=0)[0]

    predicted_digit = int(np.argmax(predictions))
    confidence = float(np.max(predictions))

    return predicted_digit, confidence, predictions


def show_result(image, true_digit, predicted_digit, confidence):
    plt.figure(figsize=(4, 4))
    plt.imshow(image, cmap="gray")
    plt.title(
        f"True: {true_digit} | Predicted: {predicted_digit}\n"
        f"Confidence: {confidence * 100:.2f}%"
    )
    plt.axis("off")
    plt.show()


def main():
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
