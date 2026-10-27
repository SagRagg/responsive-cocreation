"""ROS node: draw the digit from /strokes on the arm, then publish /turn_done."""

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
    sec = int(seconds)
    return Duration(sec=sec, nanosec=int(round((seconds - sec) * 1e9)))


class DrawingNode(Node):
    def __init__(self):
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
            stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            csv_path = f'~/arm_drawing/turns_{stamp}.csv'
        self.log = TurnLog(csv_path)
        self.frame_id = self.get_parameter('frame_id').value

        action = self.get_parameter('controller_action').value
        self.arm = ActionClient(self, FollowJointTrajectory, action)

        qos = QoSProfile(reliability=QoSReliabilityPolicy.RELIABLE,
                         history=QoSHistoryPolicy.KEEP_LAST, depth=10)
        self.create_subscription(String, '/strokes', self.on_strokes, qos)
        self.create_subscription(Int32, '/digit_prediction', self.on_digit, qos)
        self.turn_done_pub = self.create_publisher(Bool, '/turn_done', 10)
        self.marker_pub = self.create_publisher(
            MarkerArray, '/drawing_markers', 10)

        self.last_digit_rx_ns = None
        self.turn = None   # dict of the turn being drawn, None when idle
        self.ready_timer = self.create_timer(1.0, self.go_to_ready)

        self.get_logger().info(
            f'poses from {poses_file}, logging to {self.log.path}, '
            f'arm action {action}')

    def go_to_ready(self):
        """Once the controller is up, park the arm at the ready pose so
        every trial starts from the same place."""
        if not self.arm.server_is_ready():
            self.get_logger().info(
                'waiting for the arm controller', throttle_duration_sec=5.0)
            return
        self.ready_timer.cancel()
        goal = FollowJointTrajectory.Goal()
        goal.trajectory = self.build_trajectory(
            {'time': [5.0], 'joints': [self.poses['ready']]})
        self.arm.send_goal_async(goal)
        self.get_logger().info('moving to the ready pose')

    def now_ns(self):
        return self.get_clock().now().nanoseconds

    def on_digit(self, msg):
        self.last_digit_rx_ns = self.now_ns()

    def on_strokes(self, msg):
        rx_ns = self.now_ns()
        if self.turn is not None:
            self.get_logger().warn(
                f'ignoring /strokes: trial {self.turn["trial_number"]} '
                'is still drawing')
            return
        self.turn = {'strokes_rx_ns': rx_ns,
                     'digit_rx_ns': self.last_digit_rx_ns}
        self.last_digit_rx_ns = None
        try:
            trial, digit, confidence, source_ns, strokes = parse_strokes(msg.data)
        except ValueError as exc:
            self.get_logger().error(str(exc))
            self.finish('bad_message')
            return
        self.turn.update(trial_number=trial, digit=digit,
                         confidence=confidence, source_stamp_ns=source_ns)
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
        traj = self.poses['digits'][str(digit)]
        goal = FollowJointTrajectory.Goal()
        goal.trajectory = self.build_trajectory(traj)
        self.publish_ink(traj)
        self.turn['goal_sent_ns'] = self.now_ns()
        self.arm.send_goal_async(goal).add_done_callback(self.on_goal_response)

    def build_trajectory(self, traj):
        msg = JointTrajectory()
        msg.joint_names = list(self.poses['joint_names'])
        for t, q in zip(traj['time'], traj['joints']):
            point = JointTrajectoryPoint()
            point.positions = [float(a) for a in q]
            point.time_from_start = _duration(t)
            msg.points.append(point)
        return msg

    def on_goal_response(self, future):
        handle = future.result()
        if not handle.accepted:
            self.get_logger().error('arm rejected the trajectory')
            self.finish('rejected')
            return
        handle.get_result_async().add_done_callback(self.on_result)

    def on_result(self, future):
        self.turn['goal_done_ns'] = self.now_ns()
        code = future.result().result.error_code
        if code == FollowJointTrajectory.Result.SUCCESSFUL:
            self.finish('ok')
        else:
            self.get_logger().error(f'trajectory failed, error code {code}')
            self.finish(f'error_{code}')

    def finish(self, status):
        """Always release the next sketch, so a bad turn never stalls a run;
        the status column records what went wrong."""
        self.turn_done_pub.publish(Bool(data=True))
        self.turn['turn_done_ns'] = self.now_ns()
        self.turn['status'] = status
        self.log.write(self.turn)
        self.get_logger().info(
            f'trial {self.turn.get("trial_number", "?")}: {status}, '
            'published /turn_done')
        self.turn = None

    def publish_ink(self, traj):
        """Paper outline plus this digit's pen-down segments, for RViz."""
        s = self.poses['settings']
        half = s['paper_size'] / 2
        cx, cy, z = s['paper_center_x'], s['paper_center_y'], s['paper_z']
        paper = self._marker(0, Marker.LINE_STRIP, 0.6)
        paper.points = [Point(x=cx + dx, y=cy + dy, z=z) for dx, dy in
                        ((half, half), (half, -half), (-half, -half),
                         (-half, half), (half, half))]
        ink = self._marker(1, Marker.LINE_LIST, 0.0)
        xyz, down = traj['xyz'], traj['pen_down']
        for i in range(1, len(xyz)):
            if down[i - 1] and down[i]:
                ink.points += [Point(x=a[0], y=a[1], z=a[2])
                               for a in (xyz[i - 1], xyz[i])]
        self.marker_pub.publish(MarkerArray(markers=[paper, ink]))

    def _marker(self, marker_id, kind, grey):
        m = Marker()
        m.header.frame_id = self.frame_id
        m.header.stamp = self.get_clock().now().to_msg()
        m.ns = 'drawing'
        m.id = marker_id
        m.type = kind
        m.action = Marker.ADD
        m.pose.orientation.w = 1.0
        m.scale.x = 0.003
        m.color = ColorRGBA(r=grey, g=grey, b=grey, a=1.0)
        return m

    def close(self):
        self.log.close()


def main(args=None):
    rclpy.init(args=args)
    node = DrawingNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
