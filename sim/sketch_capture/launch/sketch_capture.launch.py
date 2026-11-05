"""Launch sketch_capture: replay seeded MNIST digits as the human's sketches.

Starts capture_node, which publishes one digit per turn on /sketch_image and
waits for /turn_done from arm_drawing before sending the next. Use the same
`seed` and `per_digit` for the edge and cloud runs so both see identical
trials in the same order.

Example:
    ros2 launch sketch_capture sketch_capture.launch.py seed:=42 image_format:=canvas
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    """Declare the launch arguments and the capture node.

    Returns:
        LaunchDescription with one argument per node parameter.
    """
    return LaunchDescription([
        DeclareLaunchArgument('dataset_dir', default_value='~/datasets/mnist',
                              description='Folder with the MNIST test IDX files'),
        DeclareLaunchArgument('seed', default_value='42',
                              description='Seed for the trial selection and order'),
        DeclareLaunchArgument('per_digit', default_value='10',
                              description='Trials per digit (10 -> 100 trials)'),
        DeclareLaunchArgument('csv_path', default_value='',
                              description='Trial log CSV; empty = timestamped file '
                                          'in ~/sketch_capture/'),
        DeclareLaunchArgument('image_dir', default_value='',
                              description='If set, save each sent image here as a PNG'),
        DeclareLaunchArgument('print_ascii', default_value='false',
                              description='Print a text preview of each sent image'),
        DeclareLaunchArgument('image_format', default_value='mnist',
                              description='mnist = 28x28 white on black; '
                                          'canvas = 280x280 black on white'),
        Node(
            package='sketch_capture',
            executable='capture_node',
            name='sketch_capture',
            output='screen',
            emulate_tty=True,
            # Launch arguments are strings. ParameterValue casts each to the
            # type the node declares, so an empty path stays '' and
            # 'false' becomes a bool instead of being rejected.
            parameters=[{
                'dataset_dir': ParameterValue(LaunchConfiguration('dataset_dir'), value_type=str),
                'seed': ParameterValue(LaunchConfiguration('seed'), value_type=int),
                'per_digit': ParameterValue(LaunchConfiguration('per_digit'), value_type=int),
                'csv_path': ParameterValue(LaunchConfiguration('csv_path'), value_type=str),
                'image_dir': ParameterValue(LaunchConfiguration('image_dir'), value_type=str),
                'print_ascii': ParameterValue(LaunchConfiguration('print_ascii'), value_type=bool),
                'image_format': ParameterValue(LaunchConfiguration('image_format'), value_type=str),
            }],
        ),
    ])
