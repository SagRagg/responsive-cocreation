"""Launch arm_drawing: draw each recognised digit on the simulated Gen3.

Starts drawing_node only. The Gen3 with fake hardware, its
joint_trajectory_controller and RViz must be started separately
(kortex_bringup's gen3.launch.py with use_fake_hardware:=true). The node
waits for the controller's action server and then parks the arm at the
ready pose.

Example:
    ros2 launch arm_drawing arm_drawing.launch.py csv_path:=~/runs/turns_edge.csv
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    """Declare the launch arguments and the drawing node.

    Returns:
        LaunchDescription with the csv_path and poses_file arguments.
    """
    return LaunchDescription([
        DeclareLaunchArgument('csv_path', default_value='',
                              description='Turn log CSV; empty = timestamped file '
                                          'in ~/arm_drawing/'),
        DeclareLaunchArgument('poses_file', default_value='',
                              description='Joint pose table; empty = the one '
                                          'installed with the package'),
        Node(
            package='arm_drawing',
            executable='drawing_node',
            name='arm_drawing',
            output='screen',
            emulate_tty=True,
            # Launch arguments are strings; ParameterValue keeps an empty
            # value as '' so the node falls back to its defaults.
            parameters=[{
                'csv_path': ParameterValue(LaunchConfiguration('csv_path'), value_type=str),
                'poses_file': ParameterValue(LaunchConfiguration('poses_file'), value_type=str),
            }],
        ),
    ])
