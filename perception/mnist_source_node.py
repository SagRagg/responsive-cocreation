#!/usr/bin/env python3
import random
import numpy as np
import tensorflow as tf
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Int32, Empty

class MnistSourceNode(Node):
    def __init__(self):
        super().__init__('mnist_source')
        qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1, reliability=ReliabilityPolicy.RELIABLE)
        self.image_pub = self.create_publisher(Image, '/sketch_image', qos)
        self.label_pub = self.create_publisher(Int32, '/mnist_ground_truth', 10)
        self.turn_done_sub = self.create_subscription(Empty, '/turn_done', self.turn_done_callback, 10)
        self.trial_counter = 0
        (_, _), (self.x_test, self.y_test) = tf.keras.datasets.mnist.load_data()
        self.get_logger().info(f'Loaded MNIST test set with {len(self.x_test)} images.')
        self.start_timer = self.create_timer(1.0, self.publish_first_sample)

    def publish_first_sample(self):
        self.start_timer.cancel()
        self.publish_next_sample()

    def publish_next_sample(self):
        index = random.randrange(len(self.x_test))
        image = self.x_test[index].astype(np.uint8)
        label = int(self.y_test[index])
        self.trial_counter += 1

        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'mnist'
        msg.height = 28
        msg.width = 28
        msg.encoding = 'mono8'
        msg.is_bigendian = 0
        msg.step = 28
        msg.data = image.tobytes()

        label_msg = Int32()
        label_msg.data = label

        self.image_pub.publish(msg)
        self.label_pub.publish(label_msg)
        stamp = msg.header.stamp
        self.get_logger().info(
            f'Trial {self.trial_counter}: published MNIST index={index}, ground_truth={label}, '
            f'stamp={stamp.sec}.{stamp.nanosec:09d}'
        )
        self.get_logger().info('Waiting for /turn_done before publishing the next MNIST image.')

    def turn_done_callback(self, _msg):
        self.get_logger().info('Received /turn_done. Publishing next MNIST image.')
        self.publish_next_sample()

def main(args=None):
    rclpy.init(args=args)
    node = MnistSourceNode()
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
