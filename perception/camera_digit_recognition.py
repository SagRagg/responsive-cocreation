import argparse
from pathlib import Path

import cv2
import numpy as np
import tensorflow as tf


# -------------------------------------------------------
# Configuration
# -------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = SCRIPT_DIR / "mnist_cnn_baseline.keras"


# -------------------------------------------------------
# Preprocess camera image to look like MNIST
# -------------------------------------------------------

def preprocess_digit(roi):
    """
    Convert a camera ROI into the same general format as an MNIST image:
    white digit on a black 28x28 background.

    Returns:
        model_input: shape (1, 28, 28, 1), float32 in [0, 1]
        preview:      28x28 uint8 image for display
    """

    # Convert to grayscale
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    # Reduce camera noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Black writing on white paper -> white digit on black background
    _, threshold = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
    )

    # Find connected shapes
    contours, _ = cv2.findContours(
        threshold,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    if not contours:
        return None, threshold

    # Use largest contour as the handwritten digit
    largest_contour = max(contours, key=cv2.contourArea)

    # Ignore small noise
    if cv2.contourArea(largest_contour) < 500:
        return None, threshold

    x, y, w, h = cv2.boundingRect(largest_contour)
    digit = threshold[y:y + h, x:x + w]

    # Resize to fit inside a 20x20 area while preserving aspect ratio
    target_size = 20

    if h > w:
        new_h = target_size
        new_w = max(1, int(w * target_size / h))
    else:
        new_w = target_size
        new_h = max(1, int(h * target_size / w))

    digit = cv2.resize(
        digit,
        (new_w, new_h),
        interpolation=cv2.INTER_AREA,
    )

    # Centre digit on a 28x28 MNIST-style canvas
    canvas = np.zeros((28, 28), dtype=np.uint8)

    x_offset = (28 - new_w) // 2
    y_offset = (28 - new_h) // 2

    canvas[
        y_offset:y_offset + new_h,
        x_offset:x_offset + new_w,
    ] = digit

    # Normalise 0-255 -> 0-1
    canvas_float = canvas.astype("float32") / 255.0

    # CNN expects: (batch, height, width, channels)
    model_input = canvas_float.reshape(1, 28, 28, 1)

    return model_input, canvas


def main():
    parser = argparse.ArgumentParser(
        description="Live handwritten digit recognition using the attached MNIST CNN."
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL_PATH,
        help="Path to the .keras model file.",
    )
    parser.add_argument(
        "--camera",
        type=int,
        default=0,
        help="Camera index to use (default: 0).",
    )
    parser.add_argument(
        "--box-size",
        type=int,
        default=300,
        help="Size of the centre digit detection box in pixels.",
    )
    args = parser.parse_args()

    # -------------------------------------------------------
    # Load trained model
    # -------------------------------------------------------

    model_path = args.model.expanduser().resolve()

    if not model_path.exists():
        raise FileNotFoundError(
            f"Model not found: {model_path}\n"
            "Put mnist_cnn_baseline.keras in the same folder as this script "
            "or use --model /path/to/model.keras"
        )

    print(f"Loading model: {model_path}")
    model = tf.keras.models.load_model(model_path)
    print("Model loaded successfully.")

    # -------------------------------------------------------
    # Open camera
    # -------------------------------------------------------

    print(f"Opening camera index {args.camera}...")
    camera = cv2.VideoCapture(args.camera)

    if not camera.isOpened():
        raise RuntimeError(
            f"Could not open camera index {args.camera}.\n"
            "Try another index, for example:\n"
            "  python camera_digit_recognition.py --camera 1"
        )

    print("Camera opened successfully.")
    print("Place one handwritten digit inside the green box.")
    print("Press Q to quit.")

    # -------------------------------------------------------
    # Live camera loop
    # -------------------------------------------------------

    try:
        while True:
            ret, frame = camera.read()

            if not ret or frame is None:
                continue

            # Mirror camera view
            frame = cv2.flip(frame, 1)

            height, width, _ = frame.shape

            # Keep box inside frame dimensions
            box_size = min(args.box_size, width - 20, height - 20)

            x1 = width // 2 - box_size // 2
            y1 = height // 2 - box_size // 2
            x2 = x1 + box_size
            y2 = y1 + box_size

            # Region of Interest
            roi = frame[y1:y2, x1:x2]

            # Preprocess
            processed, preview = preprocess_digit(roi)

            prediction_text = "No digit detected"

            # CNN prediction
            if processed is not None:
                predictions = model.predict(processed, verbose=0)

                predicted_digit = int(np.argmax(predictions[0]))
                confidence = float(np.max(predictions[0]))

                prediction_text = (
                    f"Digit: {predicted_digit}  "
                    f"Confidence: {confidence * 100:.1f}%"
                )

            # Detection box
            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2,
            )

            # Prediction text
            cv2.putText(
                frame,
                prediction_text,
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )

            cv2.putText(
                frame,
                "Place one handwritten digit inside box",
                (30, height - 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )

            # Live camera
            cv2.imshow(
                "Handwritten Digit Recognition",
                frame,
            )

            # Show exactly what the CNN receives
            if processed is not None:
                preview_large = cv2.resize(
                    preview,
                    (280, 280),
                    interpolation=cv2.INTER_NEAREST,
                )

                cv2.imshow(
                    "CNN Input",
                    preview_large,
                )

            # Press Q to quit
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        camera.release()
        cv2.destroyAllWindows()
        print("Program closed.")


if __name__ == "__main__":
    main()
