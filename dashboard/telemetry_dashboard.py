#!/usr/bin/env python3
"""Live telemetry dashboard: subscribes to the pipeline topics and serves a page.

Run it on the machine that runs the perception node. It only subscribes; it
never publishes and never changes anything the other nodes use.
"""

import json
import os
import threading
import time
from datetime import datetime

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, Int32, String

from clock_sync import ClockSyncPoller
from trial_tracker import CsvLog, TOPICS, TrialTracker, perception_health
from web_server import Hub, make_server

UI_PERIOD_S = 0.2          # 5 Hz: the most often the browser is updated
MAX_IMAGE_BYTES = 28 * 28  # the perception node only takes 28x28 sketches


def _qos(depth):
    return QoSProfile(reliability=QoSReliabilityPolicy.RELIABLE,
                      history=QoSHistoryPolicy.KEEP_LAST, depth=depth)


class TelemetryDashboard(Node):
    def __init__(self):
        super().__init__('telemetry_dashboard')
        self.declare_parameter('placement', 'edge')
        self.declare_parameter('port', 8080)
        self.declare_parameter('bind', '0.0.0.0')
        self.declare_parameter('csv_dir', '~/dashboard_logs')
        self.declare_parameter('trial_timeout_s', 30.0)

        self.placement = self.get_parameter('placement').value
        if self.placement not in ('edge', 'cloud'):
            raise ValueError(
                f"placement must be 'edge' or 'cloud', got {self.placement!r}")
        port = self.get_parameter('port').value
        bind = self.get_parameter('bind').value
        csv_dir = self.get_parameter('csv_dir').value
        timeout_s = float(self.get_parameter('trial_timeout_s').value)

        self.run_id = f"{self.placement}_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.csv = CsvLog(csv_dir, self.run_id)
        self.tracker = TrialTracker(self.placement, timeout_s, self._on_finish)
        self.last_seen_ns = {topic: None for topic in TOPICS}
        self.sent_seq = -1
        self._csv_failed = False

        self.create_subscription(Image, '/sketch_image', self._on_sketch, _qos(1))
        self.create_subscription(String, '/ground_truth', self._on_truth, _qos(10))
        self.create_subscription(Int32, '/digit_prediction', self._on_prediction, _qos(10))
        self.create_subscription(String, '/strokes', self._on_strokes, _qos(10))
        self.create_subscription(Bool, '/turn_done', self._on_turn_done, _qos(10))

        self.hub = Hub()
        self.clock = ClockSyncPoller()
        self.clock.start()
        static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
        self.server = make_server(bind, port, static_dir, self.hub,
                                  self._history, csv_dir)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.create_timer(UI_PERIOD_S, self._publish_update)

        self.get_logger().info(
            f'{self.placement} dashboard on http://{bind}:{port}, '
            f'logging to {self.csv.dir}/{self.run_id}.csv')

    # ---- subscriptions: stamp the arrival first, then do the work ----------

    def _seen(self, topic):
        now_ns = time.time_ns()
        self.last_seen_ns[topic] = now_ns
        return now_ns

    def _on_sketch(self, msg):
        now_ns = self._seen('/sketch_image')
        image = None
        if (msg.encoding == 'mono8' and msg.width * msg.height <= MAX_IMAGE_BYTES
                and msg.step >= msg.width):
            data = bytes(msg.data)
            image = b''.join(data[r * msg.step:r * msg.step + msg.width]
                             for r in range(msg.height))
        self.tracker.on_sketch(
            (msg.header.stamp.sec, msg.header.stamp.nanosec), now_ns,
            image, msg.width, msg.height)

    def _on_truth(self, msg):
        self.tracker.on_ground_truth(msg.data, self._seen('/ground_truth'))

    def _on_prediction(self, msg):
        self.tracker.on_prediction(msg.data, self._seen('/digit_prediction'))

    def _on_strokes(self, msg):
        self.tracker.on_strokes(msg.data, self._seen('/strokes'))

    def _on_turn_done(self, msg):
        now_ns = self._seen('/turn_done')
        if msg.data:
            self.tracker.on_turn_done(now_ns)

    def _on_finish(self, row):
        try:
            self.csv.write(row)
        except OSError as exc:
            if not self._csv_failed:
                self._csv_failed = True
                self.get_logger().error(f'cannot write CSV: {exc}')
            return
        self.get_logger().info(
            f"trial {row['trial']}: true={row['true_digit']} pred={row['pred_digit']} "
            f"e2e={row['e2e_ms']} ms compute={row['compute_ms']} ms "
            f"turn={row['turn_ms']} ms [{row['status']}]")

    # ---- browser updates ---------------------------------------------------

    def _health(self, now_ns):
        health = {}
        for topic in TOPICS:
            seen = self.last_seen_ns[topic]
            try:
                pubs = self.count_publishers(topic)
            except Exception:
                pubs = None
            health[topic] = {
                'age_s': None if seen is None else round((now_ns - seen) / 1e9, 1),
                'publishers': pubs}
        return health

    def _publish_update(self):
        now_ns = time.time_ns()
        self.tracker.tick(now_ns)
        health = self._health(now_ns)
        strokes = health['/strokes']
        colour, reason = perception_health(strokes['publishers'], strokes['age_s'])
        rows = self.tracker.rows_since(self.sent_seq)
        if rows:
            self.sent_seq = rows[-1]['seq']
        update = {
            't': now_ns / 1e9,
            'placement': self.placement,
            'run_id': self.run_id,
            'csv_file': self.csv.path,
            'total': len(self.tracker.rows),
            'rows': rows,
            'current': self.tracker.current(now_ns),
            'health': health,
            'perception': {'status': colour, 'reason': reason},
            'chrony': self.clock.status(),
        }
        self.hub.publish(json.dumps(update))

    def _history(self):
        now_ns = time.time_ns()
        return {
            'placement': self.placement,
            'run_id': self.run_id,
            'csv_file': self.csv.path,
            'total': len(self.tracker.rows),
            'rows': self.tracker.snapshot_rows(),
            'current': self.tracker.current(now_ns),
        }

    def close(self):
        self.clock.stop()
        self.server.shutdown()
        self.server.server_close()
        self.csv.close()


def main(args=None):
    rclpy.init(args=args)
    node = TelemetryDashboard()
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
