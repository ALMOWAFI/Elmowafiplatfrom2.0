from setuptools import find_packages, setup

package_name = 'web_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    package_data={package_name: ['static/*.html']},
    include_package_data=True,
    install_requires=['setuptools'],
    zip_safe=False,
    maintainer='Ali Elmowafi',
    maintainer_email='aelmowafi@constructor.university',
    description='FastAPI/WebSocket bridge between family phones and the game ROS graph',
    license='MIT',
    entry_points={
        'console_scripts': [
            'web_bridge_node = web_bridge.node:main',
        ],
    },
)
