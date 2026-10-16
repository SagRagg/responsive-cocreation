"""ROS node: replay one MNIST digit per turn on /sketch_image."""

from datetime import datetime

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Bool

from sketch_capture.canvas import CANVAS_SIZE, render_canvas
from sketch_capture.mnist_loader import load_mnist_test
from sketch_capture.trial_log import TrialLog
from sketch_capture.trial_plan import build_trial_plan


class CaptureNode(Node):
    def __init__(self):
        super().__init__('sketch_capture')
        self.declare_parameter('dataset_dir', '~/datasets/mnist')
        self.declare_parameter('seed', 42)
        self.declare_parameter('per_digit', 10)
        self.declare_parameter('csv_path', '')

        dataset_dir = self.get_parameter('dataset_dir').value
        seed = self.get_parameter('seed').value
        per_digit = self.get_parameter('per_digit').value
        csv_path = self.get_parameter('csv_path').value
        if not csv_path:
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            csv_path = f'~/sketch_capture/trials_seed{seed}_{stamp}.csv'

        self.images, self.labels = load_mnist_test(dataset_dir)
        self.plan = build_trial_plan(self.labels, per_digit, seed)
        self.log = TrialLog(csv_path)

        qos = QoSProfile(reliability=QoSReliabilityPolicy.RELIABLE,
                         history=QoSHistoryPolicy.KEEP_LAST, depth=1)
        self.pub = self.create_publisher(Image, '/sketch_image', qos)
        self.create_subscription(Bool, '/turn_done', self.on_turn_done, 10)

        self.next_trial = 0          # index into self.plan of the next publish
        self.awaiting_done = False   # a trial is out and /turn_done is pending
        self.finished = False
        self.create_timer(0.1, self.try_publish)

        self.get_logger().info(
            f'{len(self.plan)} trials (seed {seed}, {per_digit} per digit), '
            f'logging to {self.log.path}')

    def try_publish(self):
        if self.finished or self.awaiting_done:
            return
        if self.pub.get_subscription_count() == 0:
            self.get_logger().info(
                'waiting for a subscriber on /sketch_image',
                throttle_duration_sec=5.0)
            return
        self.publish_trial()

    def publish_trial(self):
        index = self.plan[self.next_trial]
        canvas = render_canvas(self.images[index])

        msg = Image()
        msg.header.frame_id = 'canvas'
        msg.height = CANVAS_SIZE
        msg.width = CANVAS_SIZE
        msg.encoding = 'mono8'
        msg.is_bigendian = 0
        msg.step = CANVAS_SIZE
        msg.data = canvas.tobytes()
        # Stamp last: this instant is the "Done" that starts the latency clock.
        msg.header.stamp = self.get_clock().now().to_msg()
        self.pub.publish(msg)

        self.next_trial += 1
        self.awaiting_done = True
        label = int(self.labels[index])
        self.log.write(self.next_trial, index, label,
                       msg.header.stamp.sec, msg.header.stamp.nanosec)
        self.get_logger().info(
            f'trial {self.next_trial}/{len(self.plan)}: '
            f'mnist index {index}, digit {label}')

    def on_turn_done(self, msg):
        if not msg.data:
            return
        if not self.awaiting_done:
            self.get_logger().warn('ignoring /turn_done: no trial in progress')
            return
        self.awaiting_done = False
        if self.next_trial >= len(self.plan):
            self.finished = True
            self.get_logger().info(
                f'all {len(self.plan)} trials done, log: {self.log.path}')

    def close(self):
        self.log.close()


def main(args=None):
    rclpy.init(args=args)
    node = CaptureNode()
    try:
        while rclpy.ok() and not node.finished:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
