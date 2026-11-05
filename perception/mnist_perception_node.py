#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np
import tensorflow as tf
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Int32, String

STROKE_TEMPLATES = {
    0: [[[0.5,0.1],[0.3,0.15],[0.2,0.35],[0.2,0.65],[0.3,0.85],[0.5,0.9],[0.7,0.85],[0.8,0.65],[0.8,0.35],[0.7,0.15],[0.5,0.1]]],
    1: [[[0.4,0.25],[0.5,0.1],[0.5,0.9]]],
    2: [[[0.2,0.25],[0.35,0.1],[0.6,0.1],[0.8,0.3],[0.65,0.5],[0.2,0.9],[0.8,0.9]]],
    3: [[[0.2,0.15],[0.5,0.1],[0.75,0.25],[0.5,0.5],[0.75,0.75],[0.5,0.9],[0.2,0.85]]],
    4: [[[0.7,0.9],[0.7,0.1]], [[0.7,0.1],[0.2,0.6],[0.85,0.6]]],
    5: [[[0.8,0.1],[0.3,0.1],[0.25,0.45],[0.55,0.45],[0.8,0.6],[0.7,0.85],[0.45,0.9],[0.2,0.8]]],
    6: [[[0.7,0.15],[0.45,0.1],[0.25,0.35],[0.2,0.65],[0.35,0.9],[0.65,0.85],[0.8,0.65],[0.65,0.45],[0.35,0.45],[0.2,0.6]]],
    7: [[[0.2,0.1],[0.8,0.1],[0.55,0.45],[0.4,0.9]]],
    8: [[[0.5,0.5],[0.3,0.4],[0.25,0.2],[0.5,0.1],[0.75,0.2],[0.7,0.4],[0.5,0.5],[0.3,0.6],[0.25,0.8],[0.5,0.9],[0.75,0.8],[0.7,0.6],[0.5,0.5]]],
    9: [[[0.8,0.45],[0.65,0.55],[0.4,0.55],[0.25,0.4],[0.25,0.2],[0.45,0.1],[0.7,0.2],[0.8,0.45],[0.7,0.7],[0.5,0.9]]],
}

class MnistPerceptionNode(Node):
    def __init__(self):
        super().__init__('mnist_perception')
        qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1, reliability=ReliabilityPolicy.RELIABLE)
        self.create_subscription(Image, '/sketch_image', self.image_callback, qos)
        self.digit_pub = self.create_publisher(Int32, '/digit_prediction', 10)
        self.strokes_pub = self.create_publisher(String, '/strokes', 10)
        self.trial_counter = 0

        model_path = Path(__file__).resolve().parent / 'mnist_cnn_baseline.keras'
        if not model_path.exists():
            raise FileNotFoundError(f'Model not found: {model_path}')
        self.model = tf.keras.models.load_model(model_path)
        self.get_logger().info('CNN model loaded. Waiting for /sketch_image (28x28 mono8 MNIST image).')

    @staticmethod
    def preprocess_image(msg: Image) -> np.ndarray:
        if msg.height != 28 or msg.width != 28:
            raise ValueError(f'Expected 28x28 image, got {msg.width}x{msg.height}.')
        if msg.encoding != 'mono8':
            raise ValueError(f"Expected mono8 encoding, got '{msg.encoding}'.")

        raw = np.frombuffer(msg.data, dtype=np.uint8)
        expected = msg.height * msg.step
        if raw.size < expected:
            raise ValueError(f'Image buffer too small: got {raw.size}, expected {expected}.')
        rows = raw[:expected].reshape(msg.height, msg.step)
        image = rows[:, :msg.width]

        normalised = image.astype(np.float32) / 255.0
        return normalised.reshape(1, 28, 28, 1)

    def image_callback(self, msg: Image):
        self.trial_counter += 1
        trial = self.trial_counter
        sec = msg.header.stamp.sec
        nsec = msg.header.stamp.nanosec
        self.get_logger().info(
            f"Trial {trial}: received /sketch_image, stamp={sec}.{nsec:09d}, frame_id='{msg.header.frame_id}'"
        )

        try:
            model_input = self.preprocess_image(msg)
        except Exception as exc:
            self.get_logger().error(f'Trial {trial}: preprocessing failed: {exc}')
            return

        predictions = self.model.predict(model_input, verbose=0)[0]
        digit = int(np.argmax(predictions))
        confidence = float(np.max(predictions))

        self.get_logger().info(
            f'Trial {trial}: predicted digit={digit}, confidence={confidence:.4f}, stamp={sec}.{nsec:09d}'
        )

        digit_msg = Int32()
        digit_msg.data = digit
        self.digit_pub.publish(digit_msg)

        payload = {
            'trial': trial,
            'digit': digit,
            'confidence': confidence,
            'source_stamp': {'sec': sec, 'nanosec': nsec},
            'frame_id': msg.header.frame_id,
            'strokes': STROKE_TEMPLATES[digit],
        }
        strokes_msg = String()
        strokes_msg.data = json.dumps(payload)
        self.strokes_pub.publish(strokes_msg)

        self.get_logger().info(f'Trial {trial}: published /digit_prediction={digit}, then /strokes.')
        # Never publish /turn_done.

def main(args=None):
    rclpy.init(args=args)
    node = MnistPerceptionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == '__main__':
    main()
