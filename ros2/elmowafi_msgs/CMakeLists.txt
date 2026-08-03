cmake_minimum_required(VERSION 3.8)
project(elmowafi_msgs)

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/GameState.msg"
  "msg/GameEvent.msg"
  "msg/EyeState.msg"
  "msg/EyeStateArray.msg"
  "msg/Violation.msg"
  "srv/SubmitAction.srv"
  DEPENDENCIES builtin_interfaces
)

ament_package()
