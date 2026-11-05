"""ROS node: draw the digit from /strokes on the arm, then publish /turn_done.

This is the robot's half of a turn in the simulated co-creation loop:

1. sketch_capture publishes a sketch on /sketch_image (edge side).
2. Perception recognises it and publishes /digit_prediction (std_msgs/Int32),
   then /strokes (std_msgs/String holding JSON, see docs/interfaces.md).
3. This node receives /strokes, sends the precomputed joint trajectory for
   that digit to the Gen3's FollowJointTrajectory action (fake hardware in
   simulation), and shows the pen path in RViz on /drawing_markers.
4. When the trajectory finishes, or the turn fails, it publishes
   /turn_done (std_msgs/Bool), which tells sketch_capture to send the next
   sketch.

No planning happens during a trial: the joint poses for every digit are
generated offline by `make_joint_poses` (arm_drawing.joint_poses) and loaded
from config/digit_poses.json at start-up, so drawing time does not vary with
solver time and the measured latency is the perception round trip.

Every turn is written as one row of a CSV timing log (arm_drawing.turn_log).
All times in that log are this node's ROS clock in integer nanoseconds.
"""

from datetime import datetime
import json
import os

from ament_index_python.packages import get_package_share_directory
from builtin_interfaces.msg import Duration
from control_msgs.action import FollowJointTrajectory
from geometry_msgs.msg import Point
import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from std_msgs.msg import Bool, ColorRGBA, Int32, String
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from visualization_msgs.msg import Marker, MarkerArray

from arm_drawing.strokes_msg import parse_strokes
from arm_drawing.templates import matches_template
from arm_drawing.turn_log import TurnLog


def _duration(seconds):
    """Convert float seconds to a builtin_interfaces/Duration.

    Args:
        seconds: Non-negative time offset in seconds.

    Returns:
        Duration with whole seconds in `sec` and the rest in `nanosec`.
    """
    sec = int(seconds)
    return Duration(sec=sec, nanosec=int(round((seconds - sec) * 1e9)))


class DrawingNode(Node):
    """Plays the stored joint trajectory for each received digit.

    The node handles one turn at a time. `self.turn` is None while idle and
    holds the turn's log row (a dict keyed by turn_log.COLUMNS) while a
    drawing is in progress. The turn moves through these callbacks:

    on_strokes -> on_goal_response -> on_result -> finish

    Any failure along the way jumps straight to finish() with a status
    string, so /turn_done is always published and a run never stalls.

    Parameters:
        poses_file: Joint pose table (JSON). Empty means the
            config/digit_poses.json installed with the package.
        csv_path: Turn log path. Empty means a timestamped file in
            ~/arm_drawing/.
        controller_action: FollowJointTrajectory action of the arm controller.
        frame_id: Frame of the RViz markers (the arm's base_link).

    Subscribes:
        /strokes (std_msgs/String): JSON with trial, digit, confidence,
            source_stamp and strokes. Starts a turn.
        /digit_prediction (std_msgs/Int32): only its arrival time is used,
            as the digit_rx_ns column of the next turn.

    Publishes:
        /turn_done (std_msgs/Bool): True once per turn, whatever the outcome.
        /drawing_markers (visualization_msgs/MarkerArray): paper outline and
            the digit's pen-down segments.
    """

    def __init__(self):
        """Load the pose table, open the turn log and set up ROS interfaces.

        Raises:
            OSError: If the pose table cannot be read or the log cannot be
                created.
        """
        super().__init__('arm_drawing')
        self.declare_parameter('poses_file', '')
        self.declare_parameter('csv_path', '')
        self.declare_parameter(
            'controller_action',
            '/joint_trajectory_controller/follow_joint_trajectory')
        self.declare_parameter('frame_id', 'base_link')

        poses_file = self.get_parameter('poses_file').value or os.path.join(
            get_package_share_directory('arm_drawing'), 'config',
            'digit_poses.json')
        with open(os.path.expanduser(poses_file)) as f:
            self.poses = json.load(f)
        csv_path = self.get_parameter('csv_path').value
        if not csv_path:
            # Wall-clock name so repeated runs never overwrite each other's log.
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            csv_path = f'~/arm_drawing/turns_{stamp}.csv'
        self.log = TurnLog(csv_path)
        self.frame_id = self.get_parameter('frame_id').value

        action = self.get_parameter('controller_action').value
        self.arm = ActionClient(self, FollowJointTrajectory, action)

        # Reliable so no /strokes is silently dropped (a lost one would leave
        # sketch_capture waiting for a /turn_done that never comes); this also
        # matches the reliable publishers on the perception side.
        qos = QoSProfile(reliability=QoSReliabilityPolicy.RELIABLE,
                         history=QoSHistoryPolicy.KEEP_LAST, depth=10)
        self.create_subscription(String, '/strokes', self.on_strokes, qos)
        self.create_subscription(Int32, '/digit_prediction', self.on_digit, qos)
        self.turn_done_pub = self.create_publisher(Bool, '/turn_done', 10)
        self.marker_pub = self.create_publisher(
            MarkerArray, '/drawing_markers', 10)

        # Receive time of the latest /digit_prediction, consumed by the next
        # /strokes. Perception publishes the digit just before the strokes.
        self.last_digit_rx_ns = None
        self.turn = None   # dict of the turn being drawn, None when idle
        # Polls once a second until the controller's action server appears
        # (the controller manager may start after this node), then cancels.
        self.ready_timer = self.create_timer(1.0, self.go_to_ready)

        self.get_logger().info(
            f'poses from {poses_file}, logging to {self.log.path}, '
            f'arm action {action}')

    def go_to_ready(self):
        """Once the controller is up, park the arm at the ready pose so
        every trial starts from the same place.

        Timer callback. Does nothing until the action server is ready, then
        cancels its own timer and sends a single 5 s move to `ready`. The
        result is not awaited. Each digit trajectory is timed on the
        assumption that the arm starts at the ready pose, and ends there
        again for the next turn.
        """
        if not self.arm.server_is_ready():
            self.get_logger().info(
                'waiting for the arm controller', throttle_duration_sec=5.0)
            return
        self.ready_timer.cancel()
        goal = FollowJointTrajectory.Goal()
        # A generous 5 s keeps this first move slow whatever pose the arm
        # starts in; it is sent only once, at start-up.
        goal.trajectory = self.build_trajectory(
            {'time': [5.0], 'joints': [self.poses['ready']]})
        self.arm.send_goal_async(goal)
        self.get_logger().info('moving to the ready pose')

    def now_ns(self):
        """Return the node's current ROS time in integer nanoseconds.

        Uses the same clock as the sketch stamp on the capture side (system
        time, synced across machines), so differences are latencies.
        """
        return self.get_clock().now().nanoseconds

    def on_digit(self, msg):
        """Record when /digit_prediction arrived.

        The value is not used: the digit to draw comes from /strokes. Only
        the receive time is kept, for the digit_rx_ns log column.

        Args:
            msg: std_msgs/Int32 with the recognised digit.
        """
        self.last_digit_rx_ns = self.now_ns()

    def on_strokes(self, msg):
        """Start a turn: decode /strokes and send the digit's trajectory.

        Ignores the message if a turn is already in progress. Otherwise
        logs the receive time, decodes the payload, publishes the RViz
        markers and sends the FollowJointTrajectory goal. A bad payload or a
        missing controller ends the turn at once via finish().

        Args:
            msg: std_msgs/String holding the /strokes JSON.
        """
        # Taken before anything else so parsing and logging do not inflate
        # the measured sketch-to-strokes latency.
        rx_ns = self.now_ns()
        if self.turn is not None:
            # Not logged and no /turn_done: the turn in progress will send
            # it, and capture only has one sketch out at a time.
            self.get_logger().warn(
                f'ignoring /strokes: trial {self.turn["trial_number"]} '
                'is still drawing')
            return
        self.turn = {'strokes_rx_ns': rx_ns,
                     'digit_rx_ns': self.last_digit_rx_ns}
        # Cleared so a stale prediction time is never paired with a later turn.
        self.last_digit_rx_ns = None
        try:
            trial, digit, confidence, source_ns, strokes = parse_strokes(msg.data)
        except ValueError as exc:
            self.get_logger().error(str(exc))
            self.finish('bad_message')
            return
        # source_stamp_ns is the /sketch_image header.stamp echoed back by
        # perception; it is the key that joins this row to the capture log.
        self.turn.update(trial_number=trial, digit=digit,
                         confidence=confidence, source_stamp_ns=source_ns)
        # The arm plays poses precomputed from the local copy of the
        # templates, so a mismatch means the drawing differs from /strokes.
        if not matches_template(digit, strokes):
            self.get_logger().warn(
                f'trial {trial}: /strokes differs from the local template for '
                f'{digit}; drawing the precomputed poses anyway')
        self.get_logger().info(
            f'trial {trial}: drawing {digit}, '
            f'{(rx_ns - source_ns) / 1e6:.1f} ms after the sketch')

        if not self.arm.server_is_ready():
            self.get_logger().error('arm controller action is not available')
            self.finish('no_controller')
            return
        # JSON object keys are strings, hence str(digit).
        traj = self.poses['digits'][str(digit)]
        goal = FollowJointTrajectory.Goal()
        goal.trajectory = self.build_trajectory(traj)
        self.publish_ink(traj)
        self.turn['goal_sent_ns'] = self.now_ns()
        self.arm.send_goal_async(goal).add_done_callback(self.on_goal_response)

    def build_trajectory(self, traj):
        """Build a JointTrajectory from one entry of the pose table.

        The header stamp is left at zero, which the controller reads as
        "start now". Times are offsets from that start.

        Args:
            traj: Dict with 'time' (seconds from start, strictly increasing)
                and 'joints' (one list of joint angles in rad per time).

        Returns:
            trajectory_msgs/JointTrajectory for the joints in the table's
            'joint_names' order.
        """
        msg = JointTrajectory()
        msg.joint_names = list(self.poses['joint_names'])
        for t, q in zip(traj['time'], traj['joints']):
            point = JointTrajectoryPoint()
            point.positions = [float(a) for a in q]
            point.time_from_start = _duration(t)
            msg.points.append(point)
        return msg

    def on_goal_response(self, future):
        """Handle the controller accepting or rejecting the goal.

        Args:
            future: Future of send_goal_async, resolving to a goal handle.
        """
        handle = future.result()
        if not handle.accepted:
            self.get_logger().error('arm rejected the trajectory')
            self.finish('rejected')
            return
        handle.get_result_async().add_done_callback(self.on_result)

    def on_result(self, future):
        """Record when the trajectory finished and end the turn.

        Args:
            future: Future of get_result_async with the action result.
        """
        self.turn['goal_done_ns'] = self.now_ns()
        code = future.result().result.error_code
        if code == FollowJointTrajectory.Result.SUCCESSFUL:
            self.finish('ok')
        else:
            self.get_logger().error(f'trajectory failed, error code {code}')
            self.finish(f'error_{code}')

    def finish(self, status):
        """Always release the next sketch, so a bad turn never stalls a run;
        the status column records what went wrong.

        Publishes /turn_done, writes the turn's CSV row and returns the node
        to idle.

        Args:
            status: 'ok', 'bad_message', 'no_controller', 'rejected' or
                'error_<code>' with the FollowJointTrajectory error code.
        """
        # Publish first, then stamp: turn_done_ns is when the release went
        # out, and the CSV write stays off the critical path.
        self.turn_done_pub.publish(Bool(data=True))
        self.turn['turn_done_ns'] = self.now_ns()
        self.turn['status'] = status
        self.log.write(self.turn)
        self.get_logger().info(
            f'trial {self.turn.get("trial_number", "?")}: {status}, '
            'published /turn_done')
        self.turn = None

    def publish_ink(self, traj):
        """Paper outline plus this digit's pen-down segments, for RViz.

        Publishes one MarkerArray on /drawing_markers. Both markers reuse
        ids 0 and 1 in the 'drawing' namespace, so each turn replaces the
        previous digit instead of drawing over it.

        Args:
            traj: Pose table entry with 'xyz' (tool-tip points in base_link)
                and 'pen_down' (one bool per point).
        """
        s = self.poses['settings']
        half = s['paper_size'] / 2
        cx, cy, z = s['paper_center_x'], s['paper_center_y'], s['paper_z']
        paper = self._marker(0, Marker.LINE_STRIP, 0.6)
        paper.points = [Point(x=cx + dx, y=cy + dy, z=z) for dx, dy in
                        ((half, half), (half, -half), (-half, -half),
                         (-half, half), (half, half))]
        ink = self._marker(1, Marker.LINE_LIST, 0.0)
        xyz, down = traj['xyz'], traj['pen_down']
        # LINE_LIST takes point pairs; only segments with the pen down at
        # both ends are ink, the rest are pen-up travel.
        for i in range(1, len(xyz)):
            if down[i - 1] and down[i]:
                ink.points += [Point(x=a[0], y=a[1], z=a[2])
                               for a in (xyz[i - 1], xyz[i])]
        self.marker_pub.publish(MarkerArray(markers=[paper, ink]))

    def _marker(self, marker_id, kind, grey):
        """Create a grey line marker in the drawing frame.

        Args:
            marker_id: Marker id within the 'drawing' namespace.
            kind: Marker type, e.g. Marker.LINE_STRIP or Marker.LINE_LIST.
            grey: Grey level 0-1 (0 is black ink).

        Returns:
            visualization_msgs/Marker with no points yet.
        """
        m = Marker()
        m.header.frame_id = self.frame_id
        m.header.stamp = self.get_clock().now().to_msg()
        m.ns = 'drawing'
        m.id = marker_id
        m.type = kind
        m.action = Marker.ADD
        m.pose.orientation.w = 1.0
        m.scale.x = 0.003   # line width in metres, about a pen stroke
        m.color = ColorRGBA(r=grey, g=grey, b=grey, a=1.0)
        return m

    def close(self):
        """Close the turn log file."""
        self.log.close()


def main(args=None):
    """Entry point for `ros2 run arm_drawing drawing_node`."""
    rclpy.init(args=args)
    node = DrawingNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        # The launch system may have shut rclpy down already on Ctrl-C.
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
