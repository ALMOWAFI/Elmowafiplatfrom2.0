from setuptools import find_packages, setup

package_name = 'cv_referee'

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
    description='Camera referee: per-player eye states for the mafia game',
    license='MIT',
    entry_points={
        'console_scripts': [
            'cv_referee_node = cv_referee.node:main',
        ],
    },
)
