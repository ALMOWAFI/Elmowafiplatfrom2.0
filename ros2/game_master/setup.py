from setuptools import find_packages, setup

package_name = 'game_master'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Ali Elmowafi',
    maintainer_email='aelmowafi@constructor.university',
    description='Mafia game state machine and referee node for Elmowafiplatform',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'game_master_node = game_master.node:main',
        ],
    },
)
