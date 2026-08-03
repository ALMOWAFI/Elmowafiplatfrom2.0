"""cv_referee — camera -> per-player eye states + hand-raise states.

Role-blind AND vote-blind by design: it reports geometric facts only
("this seat's eyes are open", "this seat's hand is up"), never what
those facts mean for the game. game_master owns the eye-state rules
(see game_master/referee.py). Hand-raise consumption is NOT wired up
anywhere yet — how a raised hand becomes an actual day-vote accusation
is a real game-flow design decision that hasn't been made (simultaneous
show-of-hands per accused? one nomination at a time? tie handling?) and
publishing the raw signal here doesn't presume an answer. Phones remain
the real vote mechanism (game_master 'vote' action) until that's
decided.

Identity v1 for both signals is seat mapping (seat_map parameter:
player ids left-to-right as the camera sees them), computed
independently per modality (face center-x vs. pose bounding-box
center-x) — for a person standing/sitting normally these agree, but it
is an approximation, not a true tracked identity. Face-recognition
identity is future work via seeds/facial_recognition_trainer.py.

Runs BOTH MediaPipe models (face + pose) every tick unconditionally.
This is a real, but not yet exercised, cost: cutting it in half by only
running FaceLandmarker during night phases and PoseLandmarker during
day_vote (subscribing to /game/state to pick) is flagged future work,
not done here — better decided against real timing numbers on the
actual deployment hardware than guessed now.

Parameters
  camera_index      int    webcam index (default 0)
  video_path        str    play a recorded clip instead of the camera
  model_path        str    face_landmarker.task location
  pose_model_path   str    pose_landmarker_lite.task location
  seat_map          str[]  player ids left-to-right ('' entries allowed)
  closed_threshold  double blink score above this = closed (default 0.5)
  smooth_frames     int    majority window, both signals (default 5)
  enable_hands      bool   run pose/hand-raise detection (default True)
  camera_retry_s    double seconds between camera-open retries while no
                           camera is available (default 5.0) — without
                           this, a missing camera makes cv2.VideoCapture()
                           get hammered at the ~20Hz tick rate, which is
                           both wasteful and spams OpenCV's own stderr
                           diagnostics (those bypass rclpy's log
                           throttling entirely since they're printed by
                           OpenCV's C++ layer, not through this node's
                           logger)
"""

import time
from pathlib import Path

import rclpy
from rclpy.node import Node

from elmowafi_msgs.msg import EyeState, EyeStateArray, HandRaise, HandRaiseArray

from cv_referee.vision import BoolSmoother, assign_seats, hand_raised

FACE_MODEL_URL = ('https://storage.googleapis.com/mediapipe-models/'
                  'face_landmarker/face_landmarker/float16/latest/'
                  'face_landmarker.task')
POSE_MODEL_URL = ('https://storage.googleapis.com/mediapipe-models/'
                  'pose_landmarker/pose_landmarker_lite/float16/latest/'
                  'pose_landmarker_lite.task')

# BlazePose landmark indices (see hand_probe.py, validated 2026-08-03)
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_WRIST, RIGHT_WRIST = 15, 16


class CvRefereeNode(Node):
    def __init__(self):
        super().__init__('cv_referee')
        self.declare_parameter('camera_index', 0)
        self.declare_parameter('video_path', '')
        self.declare_parameter('model_path',
                               str(Path.home() / 'models/face_landmarker.task'))
        self.declare_parameter('pose_model_path',
                               str(Path.home() / 'models/pose_landmarker_lite.task'))
        self.declare_parameter('seat_map', [''])
        self.declare_parameter('closed_threshold', 0.5)
        self.declare_parameter('smooth_frames', 5)
        self.declare_parameter('enable_hands', True)
        self.declare_parameter('camera_retry_s', 5.0)

        self.eye_pub = self.create_publisher(EyeStateArray, '/cv/eye_states', 10)
        self.hand_pub = self.create_publisher(HandRaiseArray, '/cv/hand_raises', 10)
        n = int(self.get_parameter('smooth_frames').value)
        self.eye_smoother = BoolSmoother(n)
        self.hand_smoother = BoolSmoother(n)
        self._cap = None
        self._face_landmarker = None
        self._pose_landmarker = None
        self._last_camera_attempt = 0.0
        self._models_ready = False  # models can load even if camera can't open yet
        self.timer = self.create_timer(0.05, self.tick)  # ~20 Hz target
        self.get_logger().info('cv_referee starting')

    # ---------- lazy pipeline setup ----------

    def _load_models(self) -> bool:
        """Import mediapipe/cv2 and construct the landmarkers. Cheap to
        call repeatedly once it has succeeded once (early-returns), so
        it isn't gated behind the camera-retry backoff — no reason to
        delay noticing a fixed missing-model-file once it's fixed."""
        if self._face_landmarker is not None:
            return True
        face_model = Path(str(self.get_parameter('model_path').value)).expanduser()
        if not face_model.exists():
            self.get_logger().error(
                f'face model not found: {face_model}\ndownload from {FACE_MODEL_URL}',
                throttle_duration_sec=30)
            return False
        enable_hands = bool(self.get_parameter('enable_hands').value)
        pose_model = Path(str(self.get_parameter('pose_model_path').value)).expanduser()
        if enable_hands and not pose_model.exists():
            self.get_logger().error(
                f'pose model not found: {pose_model}\ndownload from {POSE_MODEL_URL}',
                throttle_duration_sec=30)
            return False
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as e:
            self.get_logger().error(f'missing dependency: {e}',
                                    throttle_duration_sec=30)
            return False

        face_options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(face_model)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=8,
            output_face_blendshapes=True)
        self._face_landmarker = vision.FaceLandmarker.create_from_options(face_options)

        if enable_hands:
            pose_options = vision.PoseLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(pose_model)),
                running_mode=vision.RunningMode.VIDEO,
                num_poses=8)
            self._pose_landmarker = vision.PoseLandmarker.create_from_options(pose_options)

        self._mp = mp
        self._cv2 = cv2
        self.get_logger().info(
            f'model(s) loaded (hands={"on" if enable_hands else "off"})')
        return True

    def _ensure_pipeline(self) -> bool:
        if self._cap is not None:
            return True

        retry_s = float(self.get_parameter('camera_retry_s').value)
        now = time.time()
        if now - self._last_camera_attempt < retry_s:
            return False  # backing off: don't hammer cv2.VideoCapture()
        self._last_camera_attempt = now

        if not self._load_models():
            return False

        video_path = str(self.get_parameter('video_path').value)
        cv2 = self._cv2
        if video_path:
            cap = cv2.VideoCapture(video_path)
        else:
            cap = cv2.VideoCapture(int(self.get_parameter('camera_index').value))
        if not cap.isOpened():
            self.get_logger().error(
                f'cannot open camera/video, retrying every {retry_s:.0f}s',
                throttle_duration_sec=30)
            return False

        self._cap = cap
        self.get_logger().info('camera ready')
        return True

    # ---------- main loop ----------

    def tick(self):
        if not self._ensure_pipeline():
            return
        ok, frame = self._cap.read()
        if not ok:
            self.get_logger().warning('frame read failed',
                                      throttle_duration_sec=10)
            return
        rgb = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
        mp_img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        now_ms = int(time.time() * 1000)
        seat_map = [s for s in self.get_parameter('seat_map').value]

        self._publish_eyes(mp_img, now_ms, seat_map)
        if self._pose_landmarker is not None:
            self._publish_hands(mp_img, now_ms, seat_map)

    def _publish_eyes(self, mp_img, now_ms: int, seat_map: list[str]):
        res = self._face_landmarker.detect_for_video(mp_img, now_ms)
        threshold = float(self.get_parameter('closed_threshold').value)

        faces_x = []
        closed_flags = []
        confidences = []
        for lm, bs in zip(res.face_landmarks, res.face_blendshapes):
            xs = [p.x for p in lm]
            faces_x.append((min(xs) + max(xs)) / 2)
            scores = {c.category_name: c.score for c in bs}
            blink = (scores.get('eyeBlinkLeft', 0.0)
                     + scores.get('eyeBlinkRight', 0.0)) / 2
            closed_flags.append(blink > threshold)
            confidences.append(min(1.0, abs(blink - threshold) * 2 + 0.5))

        players = assign_seats(faces_x, seat_map)
        self.eye_smoother.forget_missing(set(range(len(faces_x))))

        msg = EyeStateArray()
        msg.stamp = self.get_clock().now().to_msg()
        for i in range(len(faces_x)):
            st = EyeState()
            st.player_id = players[i]
            st.face_index = i
            st.eyes_open = not self.eye_smoother.update(i, closed_flags[i])
            st.confidence = float(confidences[i])
            msg.states.append(st)
        self.eye_pub.publish(msg)

    def _publish_hands(self, mp_img, now_ms: int, seat_map: list[str]):
        res = self._pose_landmarker.detect_for_video(mp_img, now_ms)

        poses_x = []
        raised_flags = []
        for lm in res.pose_landmarks:
            xs = [p.x for p in lm]
            poses_x.append((min(xs) + max(xs)) / 2)
            raised_flags.append(hand_raised(
                lm[LEFT_SHOULDER], lm[RIGHT_SHOULDER],
                lm[LEFT_WRIST], lm[RIGHT_WRIST]))

        players = assign_seats(poses_x, seat_map)
        self.hand_smoother.forget_missing(set(range(len(poses_x))))

        msg = HandRaiseArray()
        msg.stamp = self.get_clock().now().to_msg()
        for i in range(len(poses_x)):
            st = HandRaise()
            st.player_id = players[i]
            st.pose_index = i
            st.hand_raised = self.hand_smoother.update(i, raised_flags[i])
            st.confidence = 0.8  # geometric threshold, not a model score
            msg.states.append(st)
        self.hand_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = CvRefereeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
