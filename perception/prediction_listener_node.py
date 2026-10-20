#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32

class PredictionListener(Node):
    def __init__(self):
        super().__init__('prediction_listener')
        self.create_subscription(Int32, '/digit_prediction', self.callback, 10)
        self.get_logger().info('Listening on /digit_prediction ...')

    def callback(self, msg):
        self.get_logger().info(f'Received CNN prediction: {msg.data}')

def main(args=None):
    rclpy.init(args=args)
    node = PredictionListener()
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
