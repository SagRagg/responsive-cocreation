from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
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
            parameters=[{
                'csv_path': ParameterValue(LaunchConfiguration('csv_path'), value_type=str),
                'poses_file': ParameterValue(LaunchConfiguration('poses_file'), value_type=str),
            }],
        ),
    ])
