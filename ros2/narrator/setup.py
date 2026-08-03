from setuptools import find_packages, setup

package_name = 'narrator'

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
    description="The referee's voice: bilingual narration with optional local-LLM flavor",
    license='MIT',
    entry_points={
        'console_scripts': [
            'narrator_node = narrator.node:main',
        ],
    },
)
