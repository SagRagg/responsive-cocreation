#!/usr/bin/env python3

import argparse
import base64
import json
import time
from pathlib import Path

import numpy as np
import tensorflow as tf
import roslibpy


STROKE_TEMPLATES = {
    0: [[[0.5,0.1],[0.3,0.15],[0.2,0.35],[0.2,0.65],[0.3,0.85],
         [0.5,0.9],[0.7,0.85],[0.8,0.65],[0.8,0.35],[0.7,0.15],[0.5,0.1]]],
    1: [[[0.4,0.25],[0.5,0.1],[0.5,0.9]]],
    2: [[[0.2,0.25],[0.35,0.1],[0.6,0.1],[0.8,0.3],
         [0.65,0.5],[0.2,0.9],[0.8,0.9]]],
    3: [[[0.2,0.15],[0.5,0.1],[0.75,0.25],[0.5,0.5],
         [0.75,0.75],[0.5,0.9],[0.2,0.85]]],
    4: [[[0.7,0.9],[0.7,0.1]],
        [[0.7,0.1],[0.2,0.6],[0.85,0.6]]],
    5: [[[0.8,0.1],[0.3,0.1],[0.25,0.45],[0.55,0.45],
         [0.8,0.6],[0.7,0.85],[0.45,0.9],[0.2,0.8]]],
    6: [[[0.7,0.15],[0.45,0.1],[0.25,0.35],[0.2,0.65],
         [0.35,0.9],[0.65,0.85],[0.8,0.65],[0.65,0.45],
         [0.35,0.45],[0.2,0.6]]],
    7: [[[0.2,0.1],[0.8,0.1],[0.55,0.45],[0.4,0.9]]],
    8: [[[0.5,0.5],[0.3,0.4],[0.25,0.2],[0.5,0.1],
         [0.75,0.2],[0.7,0.4],[0.5,0.5],[0.3,0.6],
         [0.25,0.8],[0.5,0.9],[0.75,0.8],[0.7,0.6],[0.5,0.5]]],
    9: [[[0.8,0.45],[0.65,0.55],[0.4,0.55],[0.25,0.4],
         [0.25,0.2],[0.45,0.1],[0.7,0.2],[0.8,0.45],
         [0.7,0.7],[0.5,0.9]]],
}


class MacMnistPerception:
    def __init__(self, host, port, model_path):
        self.host = host
        self.port = port

        self.ros = roslibpy.Ros(host=host, port=port)

        self.image_topic = roslibpy.Topic(
            self.ros,
            "/sketch_image",
            "sensor_msgs/msg/Image"
        )

        self.prediction_topic = roslibpy.Topic(
            self.ros,
            "/digit_prediction",
            "std_msgs/msg/Int32"
        )

        self.strokes_topic = roslibpy.Topic(
            self.ros,
            "/strokes",
            "std_msgs/msg/String"
        )

        self.model = tf.keras.models.load_model(model_path)
        self.trial_counter = 0

    @staticmethod
    def decode_rosbridge_image(message):
        if int(message["height"]) != 28 or int(message["width"]) != 28:
            raise ValueError(
                f"Expected 28x28 image, got "
                f"{message['width']}x{message['height']}"
            )

        if message["encoding"] != "mono8":
            raise ValueError(
                f"Expected mono8, got {message['encoding']}"
            )

        data = message["data"]

        if isinstance(data, str):
            raw = base64.b64decode(data)
            arr = np.frombuffer(raw, dtype=np.uint8)
        else:
            arr = np.asarray(data, dtype=np.uint8)

        step = int(message["step"])
        rows = arr.reshape(int(message["height"]), step)
        image = rows[:, :int(message["width"])]

        normalised = image.astype(np.float32) / 255.0
        return normalised.reshape(1, 28, 28, 1)

    def image_callback(self, message):
        self.trial_counter += 1
        trial = self.trial_counter

        header = message.get("header", {})
        stamp = header.get("stamp", {"sec": 0, "nanosec": 0})
        frame_id = header.get("frame_id", "")

        sec = int(stamp.get("sec", 0))
        nsec = int(stamp.get("nanosec", 0))

        print(
            f"Trial {trial}: received /sketch_image "
            f"stamp={sec}.{nsec:09d}, "
            f"frame_id='{frame_id}'"
        )

        try:
            model_input = self.decode_rosbridge_image(message)
        except Exception as exc:
            print(f"Trial {trial}: preprocessing failed: {exc}")
            return

        predictions = self.model.predict(
            model_input,
            verbose=0
        )[0]

        digit = int(np.argmax(predictions))
        confidence = float(np.max(predictions))

        print(
            f"Trial {trial}: predicted digit={digit}, "
            f"confidence={confidence:.4f}"
        )

        # Publish digit first.
        self.prediction_topic.publish(
            roslibpy.Message({"data": digit})
        )

        # Then publish demo strokes.
        payload = {
            "trial": trial,
            "digit": digit,
            "confidence": confidence,
            "source_stamp": {
                "sec": sec,
                "nanosec": nsec
            },
            "frame_id": frame_id,
            "strokes": STROKE_TEMPLATES[digit]
        }

        self.strokes_topic.publish(
            roslibpy.Message({
                "data": json.dumps(payload)
            })
        )

        print(
            f"Trial {trial}: published "
            f"/digit_prediction={digit}, then /strokes."
        )

        # IMPORTANT: never publish /turn_done.

    def run(self):
        print(
            f"Connecting to rosbridge at "
            f"ws://{self.host}:{self.port}"
        )

        self.ros.run()
        print("Connected.")
        print("CNN model loaded. Waiting for /sketch_image...")

        self.image_topic.subscribe(self.image_callback)

        try:
            while self.ros.is_connected:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.image_topic.unsubscribe()
            self.prediction_topic.unadvertise()
            self.strokes_topic.unadvertise()
            self.ros.terminate()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Ubuntu VM IP/hostname running rosbridge"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9090,
        help="rosbridge websocket port"
    )
    parser.add_argument(
        "--model",
        default=str(
            Path(__file__).resolve().parent /
            "mnist_cnn_baseline.keras"
        )
    )
    args = parser.parse_args()

    MacMnistPerception(
        args.host,
        args.port,
        args.model
    ).run()


if __name__ == "__main__":
    main()

