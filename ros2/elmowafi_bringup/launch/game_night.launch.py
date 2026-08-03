"""Bring up the full mafia-game stack: game_master, web_bridge, narrator,
and (optionally) cv_referee — one command instead of four terminals.

Usage:
  ros2 launch elmowafi_bringup game_night.launch.py
  ros2 launch elmowafi_bringup game_night.launch.py language:=en use_llm:=true
  ros2 launch elmowafi_bringup game_night.launch.py with_camera:=false

`with_camera` defaults true but cv_referee will simply log an error and
idle if no camera is actually attached/visible (e.g. inside WSL) — see
the package README for the WSL-can't-see-USB-cameras workaround
(tools/win_cam_relay.py posting to web_bridge's /api/cv/eye_states and
/api/cv/hand_raises instead of running cv_referee itself).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    language = LaunchConfiguration('language')
    use_llm = LaunchConfiguration('use_llm')
    tts = LaunchConfiguration('tts')
    with_camera = LaunchConfiguration('with_camera')
    camera_index = LaunchConfiguration('camera_index')
    enable_hands = LaunchConfiguration('enable_hands')

    return LaunchDescription([
        DeclareLaunchArgument('language', default_value='ar',
                              description="narrator language: 'ar' or 'en'"),
        DeclareLaunchArgument('use_llm', default_value='false',
                              description='flavor narration lines via local '
                                          'Ollama (default off: quality is '
                                          'inconsistent, see narrator/node.py)'),
        DeclareLaunchArgument('tts', default_value='piper',
                              description="'piper', 'espeak', or 'none' "
                                          "(NOT 'off' -- that's a YAML "
                                          "boolean literal and will crash "
                                          "the node, see narrator/node.py)"),
        DeclareLaunchArgument('with_camera', default_value='true',
                              description='start cv_referee'),
        DeclareLaunchArgument('camera_index', default_value='0'),
        DeclareLaunchArgument('enable_hands', default_value='true',
                              description='also run pose/hand-raise '
                                          'detection in cv_referee'),

        Node(package='game_master', executable='game_master_node',
             name='game_master', output='screen'),

        Node(package='web_bridge', executable='web_bridge_node',
             name='web_bridge', output='screen'),

        Node(package='narrator', executable='narrator_node',
             name='narrator', output='screen',
             parameters=[{'language': language, 'use_llm': use_llm,
                         'tts': tts}]),

        Node(package='cv_referee', executable='cv_referee_node',
             name='cv_referee', output='screen',
             condition=IfCondition(with_camera),
             parameters=[{'camera_index': camera_index,
                         'enable_hands': enable_hands}]),
    ])
