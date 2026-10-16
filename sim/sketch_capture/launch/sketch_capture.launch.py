from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
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
        Node(
            package='sketch_capture',
            executable='capture_node',
            name='sketch_capture',
            output='screen',
            emulate_tty=True,
            parameters=[{
                'dataset_dir': ParameterValue(LaunchConfiguration('dataset_dir'), value_type=str),
                'seed': ParameterValue(LaunchConfiguration('seed'), value_type=int),
                'per_digit': ParameterValue(LaunchConfiguration('per_digit'), value_type=int),
                'csv_path': ParameterValue(LaunchConfiguration('csv_path'), value_type=str),
                'image_dir': ParameterValue(LaunchConfiguration('image_dir'), value_type=str),
                'print_ascii': ParameterValue(LaunchConfiguration('print_ascii'), value_type=bool),
            }],
        ),
    ])
