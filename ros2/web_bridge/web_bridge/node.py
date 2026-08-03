"""web_bridge — phones <-> ROS graph.

FastAPI serves the phone UI and a WebSocket per player; a background
thread spins rclpy. Private game events (roles, detective answers) are
delivered only to their recipient, everything else is broadcast.

Run:  ros2 run web_bridge web_bridge_node
Phones connect to  http://<server>:8080/

Own-camera eye monitoring (added after a real user tried the game and
expected a camera permission prompt on the page itself — a room-camera
+ separate relay script was the wrong mental model): each phone can
opt in to watching ITS OWN holder via getUserMedia() in the browser,
periodically POSTing a JPEG frame to /api/cv/eye_frame?player_id=...
This runs face detection SERVER-SIDE (mediapipe can process an
uploaded image fine even though WSL2 can't open a live camera device —
that limitation is specific to cv2.VideoCapture(), not image
processing) and republishes on the same /cv/eye_states topic
game_master already consumes, so it's indistinguishable downstream
from the room-camera path (cv_referee / win_cam_relay.py) — both can
run at once if useful.
"""

import asyncio
import json
import os
import threading
from pathlib import Path

import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, HistoryPolicy

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

from elmowafi_msgs.msg import (EyeState, EyeStateArray, GameEvent, GameState,
                               HandRaise, HandRaiseArray)
from elmowafi_msgs.srv import SubmitAction

from cv_referee.vision import BoolSmoother

STATIC_DIR = Path(__file__).resolve().parent / 'static'
# Built React app (vite build output). If present it is served as the UI,
# with SPA fallback; the plain static page stays available at /simple.
DIST_DIR = Path(os.environ.get(
    'ELMOWAFI_WEB_DIST',
    Path.home() / 'elmowafi_ws/src/elmowafiplatform/web/dist'))

EYE_CLOSED_THRESHOLD = 0.5  # matches cv_referee's default closed_threshold
EYE_SMOOTH_FRAMES = 3       # shorter than cv_referee's 5: own-camera frames
                            # arrive slower (~2/s) than a live 20Hz feed,
                            # so a smaller window still debounces without
                            # feeling laggy


class BridgeNode(Node):
    """ROS side: subscribes to game topics, exposes the action service client."""

    def __init__(self, on_event, on_state):
        super().__init__('web_bridge')
        latched = QoSProfile(depth=1,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             history=HistoryPolicy.KEEP_LAST)
        self.create_subscription(GameEvent, '/game/events', on_event, 50)
        self.create_subscription(GameState, '/game/state', on_state, latched)
        self.action_client = self.create_client(SubmitAction, '/game/submit_action')
        # dev relay: a camera process outside ROS (e.g. Windows webcam)
        # can POST eye/hand states which we republish for the ROS graph
        self.eye_pub = self.create_publisher(EyeStateArray, '/cv/eye_states', 10)
        self.hand_pub = self.create_publisher(HandRaiseArray, '/cv/hand_raises', 10)


class Bridge:
    def __init__(self, port: int = 8080):
        self.port = port
        self.loop: asyncio.AbstractEventLoop | None = None
        self.sockets: dict[str, WebSocket] = {}
        self.names: dict[str, str] = {}
        self.host: str = ''
        self.roles: dict[str, str] = {}
        self.mafia_ids: list[str] = []
        self.last_state: dict = {'phase': 'lobby', 'round': 0,
                                 'alive_ids': [], 'winner': ''}
        self.node = BridgeNode(self.on_ros_event, self.on_ros_state)
        self.app = self.make_app()

        self._face_landmarker = None  # lazy-loaded on first uploaded frame
        self._cv2 = None
        self._mp = None
        self._frame_smoothers: dict[str, BoolSmoother] = {}

    # ---------- own-camera eye monitoring (browser -> here) ----------

    def _ensure_frame_pipeline(self) -> bool:
        if self._face_landmarker is not None:
            return True
        model = Path.home() / 'models/face_landmarker.task'
        if not model.exists():
            self.node.get_logger().error(
                f'face model not found: {model}', throttle_duration_sec=30)
            return False
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as e:
            self.node.get_logger().error(f'missing dependency: {e}',
                                         throttle_duration_sec=30)
            return False
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.IMAGE,  # independent frames from
            num_faces=1,                            # possibly-many phones,
            output_face_blendshapes=True)           # not one ordered stream
        self._face_landmarker = vision.FaceLandmarker.create_from_options(options)
        self._cv2 = cv2
        self._mp = mp
        self.node.get_logger().info('own-camera face model loaded')
        return True

    def process_eye_frame(self, player_id: str, jpeg_bytes: bytes) -> dict | None:
        """Decode+detect a single uploaded frame. Returns None on any
        failure (missing model/deps, bad image, no face found) so the
        caller can report that plainly rather than guess."""
        if not self._ensure_frame_pipeline():
            return None
        cv2, mp = self._cv2, self._mp
        arr = cv2.imdecode(np.frombuffer(jpeg_bytes, dtype=np.uint8),
                          cv2.IMREAD_COLOR)
        if arr is None:
            return None
        rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = self._face_landmarker.detect(mp_img)
        if not res.face_landmarks:
            return {'found_face': False}

        scores = {c.category_name: c.score for c in res.face_blendshapes[0]}
        blink = (scores.get('eyeBlinkLeft', 0.0)
                 + scores.get('eyeBlinkRight', 0.0)) / 2
        closed_now = blink > EYE_CLOSED_THRESHOLD
        smoother = self._frame_smoothers.setdefault(
            player_id, BoolSmoother(n=EYE_SMOOTH_FRAMES))
        closed = smoother.update(0, closed_now)
        confidence = min(1.0, abs(blink - EYE_CLOSED_THRESHOLD) * 2 + 0.5)
        return {'found_face': True, 'eyes_open': not closed,
               'confidence': confidence}

    def publish_own_camera_eye_state(self, player_id: str, eyes_open: bool,
                                     confidence: float):
        msg = EyeStateArray()
        msg.stamp = self.node.get_clock().now().to_msg()
        st = EyeState()
        st.player_id = player_id
        st.face_index = 0
        st.eyes_open = eyes_open
        st.confidence = float(confidence)
        msg.states.append(st)
        self.node.eye_pub.publish(msg)

    # ---------- ROS -> phones ----------

    def _submit(self, coro):
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(coro, self.loop)

    def on_ros_state(self, msg: GameState):
        self.last_state = {'phase': msg.phase, 'round': msg.round,
                           'alive_ids': list(msg.alive_ids),
                           'winner': msg.winner}
        self._submit(self.broadcast(self.state_payload()))

    def state_payload(self) -> dict:
        return {'type': 'state', **self.last_state,
                'names': self.names, 'host': self.host}

    def on_ros_event(self, msg: GameEvent):
        data = json.loads(msg.data_json) if msg.data_json else {}
        if msg.type == 'roles_assigned':
            self.roles = data.get('roles', {})
            self.mafia_ids = data.get('mafia_ids', [])
            self._submit(self.send_roles())
            return
        if msg.recipient_id and msg.recipient_id != '__per_player__':
            self._submit(self.send_to(msg.recipient_id,
                                      {'type': 'event', 'event': msg.type,
                                       'data': data, 'private': True}))
            return
        self._submit(self.broadcast({'type': 'event', 'event': msg.type,
                                     'data': data}))

    async def send_roles(self):
        for pid in list(self.roles):
            payload = {'type': 'role', 'role': self.roles[pid]}
            if pid in self.mafia_ids:
                payload['partners'] = [m for m in self.mafia_ids if m != pid]
            await self.send_to(pid, payload)

    async def send_to(self, pid: str, payload: dict):
        ws = self.sockets.get(pid)
        if ws is not None:
            try:
                await ws.send_json(payload)
            except Exception:
                self.sockets.pop(pid, None)

    async def broadcast(self, payload: dict):
        for pid in list(self.sockets):
            await self.send_to(pid, payload)

    # ---------- phones -> ROS ----------

    async def call_action(self, player_id: str, action_type: str,
                          target_id: str = '', data: dict | None = None) -> dict:
        req = SubmitAction.Request()
        req.player_id = player_id
        req.action_type = action_type
        req.target_id = target_id
        req.data_json = json.dumps(data or {})
        if not self.node.action_client.wait_for_service(timeout_sec=2.0):
            return {'accepted': False, 'message': 'game_master not running'}
        ros_future = self.node.action_client.call_async(req)
        aio_future = self.loop.create_future()

        def done(f):
            try:
                res = f.result()
                out = {'accepted': res.accepted, 'message': res.message,
                       'result': json.loads(res.result_json) if res.result_json else None}
            except Exception as e:  # noqa: BLE001
                out = {'accepted': False, 'message': str(e)}
            self.loop.call_soon_threadsafe(aio_future.set_result, out)

        ros_future.add_done_callback(done)
        return await aio_future

    # ---------- web app ----------

    def make_app(self) -> FastAPI:
        app = FastAPI(title='Elmowafi Game Bridge')

        @app.get('/')
        async def index():
            if (DIST_DIR / 'index.html').exists():
                return FileResponse(DIST_DIR / 'index.html')
            return FileResponse(STATIC_DIR / 'index.html')

        @app.get('/simple')
        async def simple():
            return FileResponse(STATIC_DIR / 'index.html')

        @app.get('/health')
        async def health():
            return {'ok': True, 'state': self.last_state}

        @app.post('/api/action')
        async def action(body: dict):
            pid = body.get('player_id', '')
            atype = body.get('action_type', '')
            result = await self.call_action(pid, atype,
                                            body.get('target_id', ''),
                                            body.get('data'))
            if atype == 'join' and result.get('accepted'):
                if not (result.get('result') or {}).get('rejoined'):
                    self.names[pid] = (body.get('data') or {}).get('name', pid)
                if not self.host or self.host not in self.names:
                    self.host = pid
                await self.broadcast(self.state_payload())
            if atype == 'reset' and result.get('accepted'):
                self.roles = {}
                self.mafia_ids = []
                self.names = {}
                self.host = ''
                await self.broadcast(self.state_payload())
            return JSONResponse(result)

        @app.post('/api/cv/eye_states')
        async def cv_eye_states(body: dict):
            msg = EyeStateArray()
            msg.stamp = self.node.get_clock().now().to_msg()
            for s in body.get('states', []):
                st = EyeState()
                st.player_id = str(s.get('player_id', ''))
                st.face_index = int(s.get('face_index', 0))
                st.eyes_open = bool(s.get('eyes_open', False))
                st.confidence = float(s.get('confidence', 0.0))
                msg.states.append(st)
            self.node.eye_pub.publish(msg)
            return {'ok': True, 'n': len(msg.states)}

        @app.post('/api/cv/eye_frame')
        async def cv_eye_frame(request: Request, player_id: str):
            jpeg_bytes = await request.body()
            if not jpeg_bytes:
                return JSONResponse({'ok': False, 'error': 'empty frame'},
                                    status_code=400)
            # mediapipe decode+detect is CPU-bound; run off the event loop
            # so it doesn't stall other players' requests/WebSockets
            result = await asyncio.to_thread(
                self.process_eye_frame, player_id, jpeg_bytes)
            if result is None:
                return JSONResponse(
                    {'ok': False, 'error': 'detector unavailable (see server log)'},
                    status_code=503)
            if not result['found_face']:
                return {'ok': True, 'found_face': False}
            self.publish_own_camera_eye_state(
                player_id, result['eyes_open'], result['confidence'])
            return {'ok': True, 'found_face': True,
                   'eyes_open': result['eyes_open']}

        @app.post('/api/cv/hand_raises')
        async def cv_hand_raises(body: dict):
            msg = HandRaiseArray()
            msg.stamp = self.node.get_clock().now().to_msg()
            for s in body.get('states', []):
                st = HandRaise()
                st.player_id = str(s.get('player_id', ''))
                st.pose_index = int(s.get('pose_index', 0))
                st.hand_raised = bool(s.get('hand_raised', False))
                st.confidence = float(s.get('confidence', 0.0))
                msg.states.append(st)
            self.node.hand_pub.publish(msg)
            return {'ok': True, 'n': len(msg.states)}

        @app.websocket('/ws/{player_id}')
        async def ws_endpoint(ws: WebSocket, player_id: str):
            await ws.accept()
            self.sockets[player_id] = ws
            await ws.send_json(self.state_payload())
            if player_id in self.roles:
                payload = {'type': 'role', 'role': self.roles[player_id]}
                if player_id in self.mafia_ids:
                    payload['partners'] = [m for m in self.mafia_ids
                                           if m != player_id]
                await ws.send_json(payload)
            try:
                while True:
                    await ws.receive_text()  # phones act via POST; WS is downstream
            except WebSocketDisconnect:
                if self.sockets.get(player_id) is ws:
                    self.sockets.pop(player_id, None)

        if DIST_DIR.is_dir():
            from fastapi.staticfiles import StaticFiles
            app.mount('/assets', StaticFiles(directory=DIST_DIR / 'assets'),
                      name='assets')

            @app.get('/{spa_path:path}')
            async def spa_fallback(spa_path: str):
                candidate = DIST_DIR / spa_path
                if candidate.is_file():
                    return FileResponse(candidate)
                return FileResponse(DIST_DIR / 'index.html')

        return app

    # ---------- lifecycle ----------

    def run(self):
        ros_thread = threading.Thread(target=rclpy.spin, args=(self.node,),
                                      daemon=True)
        ros_thread.start()

        config = uvicorn.Config(self.app, host='0.0.0.0', port=self.port,
                                log_level='warning')
        server = uvicorn.Server(config)

        async def serve():
            self.loop = asyncio.get_running_loop()
            await server.serve()

        asyncio.run(serve())


def main(args=None):
    rclpy.init(args=args)
    bridge = Bridge()
    try:
        bridge.run()
    except KeyboardInterrupt:
        pass
    finally:
        bridge.node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
