#!/usr/bin/env python3

import argparse
import base64
import random
import threading
import time

import numpy as np
import tensorflow as tf
import roslibpy


class MacMnistSource:
    def __init__(self, host, port):
        self.host = host
        self.port = port

        self.ros = roslibpy.Ros(
            host=self.host,
            port=self.port,
        )

        self.image_topic = roslibpy.Topic(
            self.ros,
            "/sketch_image",
            "sensor_msgs/msg/Image",
        )

        self.truth_topic = roslibpy.Topic(
            self.ros,
            "/mnist_ground_truth",
            "std_msgs/msg/Int32",
        )

        self.turn_done_topic = roslibpy.Topic(
            self.ros,
            "/turn_done",
            "std_msgs/msg/Empty",
        )

        (_, _), (self.x_test, self.y_test) = tf.keras.datasets.mnist.load_data()

        self.trial_counter = 0
        self.waiting_for_turn_done = False
        self.lock = threading.Lock()

    @staticmethod
    def now_stamp():
        now = time.time()
        sec = int(now)
        nanosec = int((now - sec) * 1_000_000_000)
        return {
            "sec": sec,
            "nanosec": nanosec,
        }

    def publish_next(self):
        with self.lock:
            if self.waiting_for_turn_done:
                return

            index = random.randrange(len(self.x_test))
            image = self.x_test[index].astype(np.uint8)
            label = int(self.y_test[index])

            self.trial_counter += 1
            stamp = self.now_stamp()

            image_bytes_b64 = base64.b64encode(
                image.tobytes()
            ).decode("ascii")

            image_msg = {
                "header": {
                    "stamp": stamp,
                    "frame_id": "mnist",
                },
                "height": 28,
                "width": 28,
                "encoding": "mono8",
                "is_bigendian": 0,
                "step": 28,
                "data": image_bytes_b64,
            }

            self.image_topic.publish(
                roslibpy.Message(image_msg)
            )

            self.truth_topic.publish(
                roslibpy.Message({
                    "data": label
                })
            )

            self.waiting_for_turn_done = True

            print(
                f"Trial {self.trial_counter}: "
                f"published MNIST index={index}, "
                f"ground_truth={label}, "
                f"stamp={stamp['sec']}.{stamp['nanosec']:09d}"
            )

            print(
                "Waiting for /turn_done before publishing "
                "the next MNIST image."
            )

    def turn_done_callback(self, _message):
        print("Received /turn_done.")

        with self.lock:
            self.waiting_for_turn_done = False

        time.sleep(0.1)
        self.publish_next()

    def run(self):
        print(
            f"Connecting to rosbridge at "
            f"ws://{self.host}:{self.port}"
        )

        self.ros.run()

        if not self.ros.is_connected:
            raise RuntimeError(
                f"Could not connect to rosbridge at "
                f"{self.host}:{self.port}"
            )

        print("Connected to rosbridge.")

        self.turn_done_topic.subscribe(
            self.turn_done_callback
        )

        # Give other nodes a moment to connect.
        time.sleep(1.0)

        self.publish_next()

        try:
            while self.ros.is_connected:
                time.sleep(0.5)

        except KeyboardInterrupt:
            print("\nStopping MNIST source node.")

        finally:
            try:
                self.turn_done_topic.unsubscribe()
            except Exception:
                pass

            try:
                self.image_topic.unadvertise()
            except Exception:
                pass

            try:
                self.truth_topic.unadvertise()
            except Exception:
                pass

            self.ros.terminate()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Publish MNIST test images from macOS "
            "to ROS 2 through rosbridge."
        )
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help=(
            "IP address or hostname of the Ubuntu VM "
            "running rosbridge."
        ),
    )

    parser.add_argument(
        "--port",
        type=int,
        default=9090,
        help="rosbridge WebSocket port. Default: 9090",
    )

    args = parser.parse_args()

    node = MacMnistSource(
        host=args.host,
        port=args.port,
    )

    node.run()


if __name__ == "__main__":
    main()
