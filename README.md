# Elmowafiplatform

Family platform: family tree, memories, travel planning — and an AI game
master that referees family games (Mafia first) with on-device AI.

Runs self-hosted on a home server. AI inference defaults to local: no
cloud calls at game time out of the box. The narrator's voice can
optionally use ElevenLabs (cloud TTS, needs internet + an API key)
for better quality than the offline voice — opt-in, not the default,
and it falls back to the offline voice automatically if unavailable.

**Status (2026-08-03):** the mafia game is fully playable from phones,
end to end, with a talking bilingual referee (Piper neural TTS by
default, optional ElevenLabs cloud TTS for better quality) and a
camera that catches players peeking during the night phase — all
verified live against a real webcam and real gameplay, not just unit
tests. What's *not* yet proven: multi-person accuracy (only tested with
one face so far) and hand-raise vote detection's real-world gesture
accuracy (the pipeline runs, but nobody has actually raised a hand on
camera to confirm it). See "Known gaps" below.

## Architecture

ROS 2 (Lyrical Luth) node graph:

```
/camera (usb_cam) ──→ cv_referee ──→ /cv/eye_states, /cv/hand_raises
                                          ↓ (eye_states)
phones ←→ web_bridge ←──────────────→ game_master  (phase state machine,
   ↑                                    phase/role-aware peek judging)
   └── dev-only relay: tools/win_cam_relay.py posts real webcam eye        
       states to web_bridge's /api/cv/eye_states when the ROS host          
       can't see a USB camera directly (true for WSL2)                    
                                          ↓
                              narrator ←─ /game/events
              (Piper TTS default / optional ElevenLabs, ar/en, optional LLM flavor)
```

| Directory | What it is |
|---|---|
| `ros2/elmowafi_msgs` | Message/service definitions shared by all nodes |
| `ros2/game_master` | Mafia rules engine (pure Python, unit-tested) + phase/role-aware peek judging + ROS node |
| `ros2/cv_referee` | Camera → eye state (MediaPipe FaceLandmarker) + hand-raise (PoseLandmarker), role-blind |
| `ros2/narrator` | Bilingual narration (Piper TTS default, optional ElevenLabs cloud TTS, espeak-ng fallback, optional local-LLM flavor) |
| `ros2/web_bridge` | FastAPI/WebSocket bridge: serves the phone UI, routes actions to game_master, relays camera POSTs |
| `ros2/elmowafi_bringup` | `ros2 launch` file to start everything together |
| `web/` | React/TS frontend — the mafia game lives at `/game`, alongside the rest of the family platform |
| `seeds/` | Working code inherited from the previous repo generation (facial recognition trainer) |
| `tools/` | Dev/test scripts: `e2e_test.py`, `sim_peek.py`, `eye_probe.py`, `hand_probe.py`, `win_cam_relay.py` |
| `scripts/setup_deploy.sh` | Idempotent setup for a fresh Ubuntu box (the eventual "old PC") |

## Running it

```bash
source /opt/ros/lyrical/setup.bash
colcon build --symlink-install
source install/setup.bash

# everything at once:
ros2 launch elmowafi_bringup game_night.launch.py
# useful overrides:
ros2 launch elmowafi_bringup game_night.launch.py language:=en with_camera:=false
```

Open `http://<this-machine>:8080/game` from a phone on the same network.

### Narrator voice: Piper (default) or ElevenLabs (better, needs internet)

```bash
ros2 launch elmowafi_bringup game_night.launch.py            # Piper (offline)
ros2 launch elmowafi_bringup game_night.launch.py tts:=elevenlabs
```

ElevenLabs needs `ELEVENLABS_API_KEY` set in the environment before
launch (NOT a ROS parameter — deliberately kept out of `ros2 param
list` and launch logs; store it outside the repo, e.g. in
`~/.elevenlabs_env` sourced from `.bashrc`, chmod 600). Falls back to
Piper automatically on any failure — no key, no internet, expired key,
quota exceeded, timeout. Free-tier ElevenLabs accounts get 10,000
characters/month; a full game is roughly 500-3000 characters, so real
game nights are comfortably covered, but leaving `tts:=elevenlabs` on
for casual dev/test loops will burn through it — use the default
(Piper) or `tts:=none` for that instead.

### If your ROS host can't see a USB camera (true for WSL2)

`cv_referee` will idle, retrying camera open every 5s and logging an
error — that's expected, not broken. For real camera testing under
WSL, run the camera pipeline on the Windows side instead:

```powershell
python tools/win_cam_relay.py <seat1_id>,<seat2_id>,... [max_seconds]
```

It posts real eye states to `web_bridge`'s `/api/cv/eye_states`, which
republishes them to `/cv/eye_states` for `game_master` — this is how
the live peek-detection demo (webcam → callout → spoken narration) was
actually validated this session. There is no equivalent relay for hand
states yet (only `/api/cv/eye_states` has a Windows-side test path).

## Testing

```bash
# pure-logic unit tests (no ROS needed to run these), 46 total:
for pkg in game_master cv_referee narrator; do
  (cd ros2/$pkg && python3 -m pytest test/ -v)
done

# live integration tests (need game_master + web_bridge/narrator running):
python3 tools/e2e_test.py   # full 5-player game over real WebSockets
python3 tools/sim_peek.py   # fake camera frame -> callout -> narration

# frontend
cd web && npm install --legacy-peer-deps && npm run build
```

## Game rules (house rules, fixed 2026-08-03)

Mafia (count agreed at setup), one Doctor, one Detective (el-shayeb),
rest civilians. Night: mafia kill → doctor protect → detective ask.
Day: announce → discussion → vote. Mafia win at numeric parity;
civilians win when all mafia are out. CV referee calls out peeking
instantly, by name, in the narrator's voice.

## Known gaps (honest, not hidden)

- **Multi-person CV accuracy**: everything camera-related has only ever
  been tested with one face in frame. A real family circle (multiple
  people, distance, evening lighting) is genuinely untested.
- **Hand-raise vote detection**: the geometry (`hand_raised()` in
  `cv_referee/vision.py`) is unit tested, and the live MediaPipe Pose
  pipeline runs at ~15fps with 100% pose detection — but nobody has
  actually raised and lowered a hand on camera to confirm the gesture
  itself is classified correctly. It also isn't wired into any vote
  logic yet: `/cv/hand_raises` is published but unconsumed. How a
  raised hand should become an actual accusation (simultaneous show of
  hands per suspect? sequential nomination? tie handling?) is a real
  game-design decision that hasn't been made.
- **LLM narration flavor** (`use_llm:=true`): mechanically solid
  (warm-up avoids the ~13s cold-load stall, guards catch mojibake and
  glued-script garbage) but `qwen2.5:3b`'s actual Arabic creative
  writing quality is inconsistent — sometimes clean, sometimes
  hallucinates non-words. Defaults to off; the hand-written templates
  in `narrator/phrases.py` are the reliable path.
- **Old-PC deployment**: `scripts/setup_deploy.sh` exists and lists
  exactly what this session installed, but has never run against the
  actual target hardware — untested until that machine exists.
- **Family tree / memories / rest of the platform**: deliberately
  deferred until the game is solid, per the original plan.

Previous generation of the project (reference only):
https://github.com/ALMOWAFI/Elmowafiplatform
