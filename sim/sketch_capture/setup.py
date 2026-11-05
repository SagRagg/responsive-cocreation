"""Package setup for the sketch_capture ROS 2 package (ament_python).

Installs the capture_node executable and its launch file.
"""

import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'sketch_capture'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
         ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
         glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Nikko',
    maintainer_email='nikkoboy2011@yahoo.com',
    description='Simulated image capture: replays MNIST test digits as the '
                "human's sketch, one per turn.",
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'capture_node = sketch_capture.capture_node:main',
        ],
    },
)
