#!/bin/bash
# Deployment setup for the mafia-game stack on a fresh Ubuntu box
# (the eventual "old PC"). Installs exactly what was proven to work
# during development (2026-08-03, WSL2 Ubuntu 26.04 + ROS 2 Lyrical
# Luth) — nothing speculative added for "just in case".
#
# Idempotent: safe to re-run. Run as a normal user with sudo access,
# NOT as root directly (some steps intentionally use sudo per-command).
#
# What this does NOT do, on purpose:
#   - Configure a camera device (hardware-specific, do it manually first
#     and confirm with `cv2.VideoCapture(0).isOpened()` before running
#     cv_referee for real)
#   - Set up autostart/systemd (add that once the hardware is real and
#     you know it should survive reboots unattended)
set -euo pipefail

UBUNTU_CODENAME=$(. /etc/os-release && echo "$UBUNTU_CODENAME")
if [ "$UBUNTU_CODENAME" != "resolute" ]; then
  echo "WARNING: this was only ever tested on Ubuntu 26.04 (resolute)."
  echo "Detected: $UBUNTU_CODENAME. Continuing anyway, watch for errors."
fi

echo "==> ROS 2 Lyrical Luth"
if [ ! -d /opt/ros/lyrical ]; then
  sudo apt-get update
  sudo apt-get install -y curl software-properties-common locales
  sudo locale-gen en_US en_US.UTF-8
  sudo add-apt-repository -y universe
  sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    -o /usr/share/keyrings/ros-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu ${UBUNTU_CODENAME} main" \
    | sudo tee /etc/apt/sources.list.d/ros2.list
  sudo apt-get update
  sudo apt-get install -y ros-lyrical-desktop ros-dev-tools \
    python3-colcon-common-extensions python3-rosdep python3-pip python3-venv
  sudo rosdep init || true
else
  echo "already installed, skipping"
fi

echo "==> Node.js (to build the web/ frontend)"
sudo apt-get install -y nodejs npm

echo "==> Python packages for the ROS nodes"
sudo apt-get install -y python3-fastapi python3-uvicorn python3-websockets
pip3 install --break-system-packages piper-tts mediapipe opencv-python

echo "==> Audio (paplay under PulseAudio/PipeWire; aplay as a plain-ALSA fallback)"
sudo apt-get install -y alsa-utils pulseaudio-utils espeak-ng

echo "==> Ollama (optional: only needed if you run narrator with use_llm:=true)"
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sudo sh
else
  echo "already installed, skipping"
fi

echo "==> Voice + vision models"
mkdir -p ~/models/piper
cd ~/models
PIPER_BASE=https://huggingface.co/rhasspy/piper-voices/resolve/main
MP_BASE=https://storage.googleapis.com/mediapipe-models
get() { [ -f "$2" ] || curl -sSL "$1" -o "$2"; }
get "$MP_BASE/face_landmarker/face_landmarker/float16/latest/face_landmarker.task" \
  face_landmarker.task
get "$MP_BASE/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task" \
  pose_landmarker_lite.task
get "$PIPER_BASE/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx" \
  piper/ar_JO-kareem-medium.onnx
get "$PIPER_BASE/ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx.json" \
  piper/ar_JO-kareem-medium.onnx.json
get "$PIPER_BASE/en/en_US/lessac/medium/en_US-lessac-medium.onnx" \
  piper/en_US-lessac-medium.onnx
get "$PIPER_BASE/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" \
  piper/en_US-lessac-medium.onnx.json
ls -la ~/models ~/models/piper

echo "==> Building the workspace"
cd ~/elmowafi_ws  # adjust if the workspace lives elsewhere on this machine
source /opt/ros/lyrical/setup.bash
colcon build --symlink-install
source install/setup.bash

echo "==> Building the web frontend"
cd src/elmowafiplatform/web
npm install --legacy-peer-deps
npm run build

echo
echo "Setup done. Sanity-check before family night:"
echo "  1. Camera:  python3 -c \"import cv2; print(cv2.VideoCapture(0).isOpened())\""
echo "  2. Test suite:  cd ~/elmowafi_ws/src/elmowafiplatform && for p in game_master cv_referee narrator; do (cd ros2/\$p && python3 -m pytest test/ -q); done"
echo "  3. Launch everything:  ros2 launch elmowafi_bringup game_night.launch.py"
echo "  4. Open http://<this-machine-ip>:8080/ from a phone on the same network"
