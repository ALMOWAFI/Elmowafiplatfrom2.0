# Elmowafiplatform

Family platform: family tree, memories, travel planning — and an AI game
master that referees family games (Mafia first) with on-device AI.

Runs self-hosted on a home server. All AI inference is local: no cloud
calls at game time.

## Architecture

ROS 2 (Lyrical Luth) node graph:

```
/camera (usb_cam) ──→ cv_referee ──→ /cv/eye_states, /cv/violations
                                          ↓
phones ←→ web_bridge ←──────────────→ game_master  (phase state machine)
                                          ↓
                              narrator ←─ /game/events
                         (local LLM + TTS, Arabic/English)
```

| Directory | What it is |
|---|---|
| `ros2/elmowafi_msgs` | Message/service definitions shared by all nodes |
| `ros2/game_master` | Mafia rules engine (pure Python, unit-tested) + ROS node |
| `ros2/cv_referee` | Camera → face ID, eye state, peek detection, hand votes |
| `ros2/narrator` | Bilingual narration via local LLM + TTS |
| `ros2/web_bridge` | Serves the web UI to phones, bridges ROS ↔ WebSockets |
| `web/` | React/TS frontend (phone + shared screen UI) |
| `seeds/` | Working code inherited from the previous repo generation |

## Development

```bash
# in the colcon workspace containing this repo under src/
source /opt/ros/lyrical/setup.bash
colcon build --symlink-install
source install/setup.bash
ros2 run game_master game_master_node

# engine unit tests (no ROS needed)
cd ros2/game_master && python3 -m pytest test/ -v

# frontend
cd web && npm install --legacy-peer-deps && npm run dev
```

## Game rules (house rules, fixed 2026-08-03)

Mafia (count agreed at setup), one Doctor, one Detective (el-shayeb),
rest civilians. Night: mafia kill → doctor protect → detective ask.
Day: announce → discussion → vote. Mafia win at numeric parity;
civilians win when all mafia are out. CV referee calls out peeking
instantly.

Previous generation of the project (reference only):
https://github.com/ALMOWAFI/Elmowafiplatform
