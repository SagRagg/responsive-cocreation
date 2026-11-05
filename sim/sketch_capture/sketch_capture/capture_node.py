"""ROS node: replay one MNIST digit per turn on /sketch_image.

This node stands in for the camera that captures the human's sketch. It is
the start of every turn in the simulated co-creation loop:

1. It publishes one MNIST test digit on /sketch_image (sensor_msgs/Image,
   mono8) and the true label on /ground_truth.
2. Perception (edge or cloud) recognises the digit and publishes /strokes.
3. arm_drawing draws it and publishes /turn_done, which lets this node send
   the next digit.

The image's header.stamp is the start of the latency measurement and the key
that joins all logs (it comes back as `source_stamp` in /strokes). The digits
are chosen by a seeded, class-balanced plan (sketch_capture.trial_plan), so
edge and cloud runs with the same seed see the same inputs in the same order.
Each published trial is written as one row of a CSV log
(sketch_capture.trial_log). The node exits when the plan is finished.
"""

from datetime import datetime

import os

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, String

from sketch_capture.canvas import IMAGE_FORMATS, render_image
from sketch_capture.ground_truth import ground_truth_json
from sketch_capture.mnist_loader import load_mnist_test
from sketch_capture.preview import to_ascii, write_png
from sketch_capture.trial_log import TrialLog
from sketch_capture.trial_plan import build_trial_plan


class CaptureNode(Node):
    """Publishes the trial plan one sketch at a time, paced by /turn_done.

    State: `awaiting_done` is True from a publish until the matching
    /turn_done; `finished` becomes True when the last trial's /turn_done
    arrives, which ends main()'s spin loop.

    Parameters:
        dataset_dir: Folder with the MNIST test IDX files (optionally .gz).
        seed: Seed for the trial selection and order.
        per_digit: Trials per digit; the run has 10 * per_digit trials.
        csv_path: Trial log path. Empty means a timestamped file in
            ~/sketch_capture/ with the seed in its name.
        image_dir: If set, each sent image is also saved there as a PNG.
        print_ascii: Log a text preview of each sent image.
        image_format: 'mnist' (28x28, white on black) or 'canvas'
            (280x280, black on white).

    Publishes:
        /sketch_image (sensor_msgs/Image): the sketch, mono8.
        /ground_truth (std_msgs/String): JSON with trial, mnist_index,
            digit and the sketch's stamp.

    Subscribes:
        /turn_done (std_msgs/Bool): True releases the next trial.
    """

    def __init__(self):
        """Read parameters, load MNIST, build the plan and open the log.

        Raises:
            ValueError: If image_format is not one of IMAGE_FORMATS, or the
                dataset cannot supply per_digit samples of every digit.
            FileNotFoundError: If the MNIST files are not in dataset_dir.
        """
        super().__init__('sketch_capture')
        self.declare_parameter('dataset_dir', '~/datasets/mnist')
        self.declare_parameter('seed', 42)
        self.declare_parameter('per_digit', 10)
        self.declare_parameter('csv_path', '')
        self.declare_parameter('image_dir', '')
        self.declare_parameter('print_ascii', False)
        self.declare_parameter('image_format', 'mnist')

        dataset_dir = self.get_parameter('dataset_dir').value
        seed = self.get_parameter('seed').value
        per_digit = self.get_parameter('per_digit').value
        csv_path = self.get_parameter('csv_path').value
        if not csv_path:
            # Seed in the name so a log can be traced to its trial sequence;
            # wall-clock time so repeated runs never overwrite each other.
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            csv_path = f'~/sketch_capture/trials_seed{seed}_{stamp}.csv'

        image_dir = self.get_parameter('image_dir').value
        self.image_dir = os.path.expanduser(image_dir) if image_dir else ''
        if self.image_dir:
            os.makedirs(self.image_dir, exist_ok=True)
        self.print_ascii = self.get_parameter('print_ascii').value
        self.image_format = self.get_parameter('image_format').value
        if self.image_format not in IMAGE_FORMATS:
            raise ValueError(
                f'image_format must be one of {IMAGE_FORMATS}, '
                f'got {self.image_format!r}')

        self.images, self.labels = load_mnist_test(dataset_dir)
        # Same labels + per_digit + seed always give the same index list.
        self.plan = build_trial_plan(self.labels, per_digit, seed)
        self.log = TrialLog(csv_path)

        # Reliable so a sketch is never silently lost (the loop would wait
        # forever for its /turn_done). Depth 1: only one sketch is ever
        # outstanding, so there is nothing to queue.
        qos = QoSProfile(reliability=QoSReliabilityPolicy.RELIABLE,
                         history=QoSHistoryPolicy.KEEP_LAST, depth=1)
        self.pub = self.create_publisher(Image, '/sketch_image', qos)
        self.truth_pub = self.create_publisher(String, '/ground_truth', 10)
        self.create_subscription(Bool, '/turn_done', self.on_turn_done, 10)

        self.next_trial = 0          # index into self.plan of the next publish
        self.awaiting_done = False   # a trial is out and /turn_done is pending
        self.finished = False
        # 10 Hz poll: the next sketch goes out within 0.1 s of /turn_done,
        # a short gap next to the perception and drawing times.
        self.create_timer(0.1, self.try_publish)

        self.get_logger().info(
            f'{len(self.plan)} trials (seed {seed}, {per_digit} per digit), '
            f'{self.image_format} images, logging to {self.log.path}')

    def try_publish(self):
        """Publish the next trial if the loop is free and someone listens.

        Timer callback. Waiting for a subscriber keeps the first sketch from
        going out before perception is up, which would lose trial 1.
        """
        if self.finished or self.awaiting_done:
            return
        if self.pub.get_subscription_count() == 0:
            self.get_logger().info(
                'waiting for a subscriber on /sketch_image',
                throttle_duration_sec=5.0)
            return
        self.publish_trial()

    def publish_trial(self):
        """Publish the next planned digit and its ground truth, and log it.

        Publishes /sketch_image, then /ground_truth with the same stamp,
        writes the CSV row and optionally an ASCII preview and a PNG.
        Advances `next_trial` (trial numbers in messages and the log are
        1-based) and sets `awaiting_done`.
        """
        index = self.plan[self.next_trial]
        image = render_image(self.images[index], self.image_format)
        size = image.shape[0]

        msg = Image()
        msg.header.frame_id = 'canvas'
        msg.height = size
        msg.width = size
        msg.encoding = 'mono8'
        msg.is_bigendian = 0
        msg.step = size   # bytes per row: one byte per mono8 pixel
        msg.data = image.tobytes()
        # Stamp last: this instant is the "Done" that starts the latency clock.
        msg.header.stamp = self.get_clock().now().to_msg()
        self.pub.publish(msg)

        self.next_trial += 1
        self.awaiting_done = True
        label = int(self.labels[index])
        # Right after the image; the stamp is the join key for listeners.
        truth = String()
        truth.data = ground_truth_json(
            self.next_trial, index, label,
            msg.header.stamp.sec, msg.header.stamp.nanosec)
        self.truth_pub.publish(truth)
        # The CSV keeps the stamp as sec + nanosec, exactly as in the header,
        # so rows match /strokes source_stamp without float rounding.
        self.log.write(self.next_trial, index, label,
                       msg.header.stamp.sec, msg.header.stamp.nanosec)
        self.get_logger().info(
            f'trial {self.next_trial}/{len(self.plan)}: '
            f'mnist index {index}, digit {label}')
        # After the publish and the log row, so previews never delay the stamp.
        if self.print_ascii:
            self.get_logger().info('\n' + to_ascii(image))
        if self.image_dir:
            write_png(os.path.join(
                self.image_dir, f'trial_{self.next_trial:03d}_digit{label}.png'),
                image)

    def on_turn_done(self, msg):
        """Release the next trial, or finish the run after the last one.

        Ignores False and any /turn_done that arrives while no trial is
        out (for example a duplicate), so one turn can never release two
        sketches.

        Args:
            msg: std_msgs/Bool from arm_drawing.
        """
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
        """Close the trial log file."""
        self.log.close()


def main(args=None):
    """Entry point for `ros2 run sketch_capture capture_node`.

    Spins until every trial is done, then exits so a launched run ends by
    itself.
    """
    rclpy.init(args=args)
    node = CaptureNode()
    try:
        # spin_once instead of spin() so the loop can check `finished`.
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
