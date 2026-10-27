import os
from glob import glob

from setuptools import find_packages, setup

package_name = 'arm_drawing'

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
        (os.path.join('share', package_name, 'config'),
         glob('config/*.json')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Nikko',
    maintainer_email='nikkoboy2011@yahoo.com',
    description='Draws the recognised digit on the simulated Gen3 from '
                'precomputed joint poses and publishes /turn_done.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'drawing_node = arm_drawing.drawing_node:main',
            'make_joint_poses = arm_drawing.joint_poses:main',
        ],
    },
)
