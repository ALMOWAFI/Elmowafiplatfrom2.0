"""cv_referee — camera -> per-player eye states on /cv/eye_states.

Role-blind by design: it reports WHO has eyes open, never why that
matters; game_master owns the rules. Identity v1 is seat mapping
(seat_map parameter: player ids left-to-right as the camera sees them).
Face-recognition identity comes later via seeds/facial_recognition_trainer.py.

Parameters
  camera_index   int    webcam index (default 0)
  video_path     str    play a recorded clip instead of the camera
  model_path     str    face_landmarker.task location
  seat_map       str[]  player ids left-to-right ('' entries allowed)
  closed_threshold  double  blink score above this = closed (default 0.5)
  smooth_frames  int    majority window (default 5)
"""

import time
from pathlib import Path

import rclpy
from rclpy.node import Node

from elmowafi_msgs.msg import EyeState, EyeStateArray

from cv_referee.vision import EyeSmoother, assign_seats

MODEL_URL = ('https://storage.googleapis.com/mediapipe-models/face_landmarker/'
             'face_landmarker/float16/latest/face_landmarker.task')


class CvRefereeNode(Node):
    def __init__(self):
        super().__init__('cv_referee')
        self.declare_parameter('camera_index', 0)
        self.declare_parameter('video_path', '')
        self.declare_parameter('model_path',
                               str(Path.home() / 'models/face_landmarker.task'))
        self.declare_parameter('seat_map', [''])
        self.declare_parameter('closed_threshold', 0.5)
        self.declare_parameter('smooth_frames', 5)

        self.pub = self.create_publisher(EyeStateArray, '/cv/eye_states', 10)
        self.smoother = EyeSmoother(
            int(self.get_parameter('smooth_frames').value))
        self._cap = None
        self._landmarker = None
        self.timer = self.create_timer(0.05, self.tick)  # ~20 Hz
        self.get_logger().info('cv_referee starting')

    # ---------- lazy pipeline setup ----------

    def _ensure_pipeline(self) -> bool:
        if self._landmarker is not None:
            return True
        model = Path(str(self.get_parameter('model_path').value)).expanduser()
        if not model.exists():
            self.get_logger().error(
                f'model not found: {model}\ndownload it from {MODEL_URL}',
                throttle_duration_sec=30)
            return False
        try:
            import cv2  # noqa: F401
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as e:
            self.get_logger().error(f'missing dependency: {e}',
                                    throttle_duration_sec=30)
            return False

        video_path = str(self.get_parameter('video_path').value)
        import cv2
        if video_path:
            self._cap = cv2.VideoCapture(video_path)
        else:
            self._cap = cv2.VideoCapture(
                int(self.get_parameter('camera_index').value))
        if not self._cap.isOpened():
            self.get_logger().error('cannot open camera/video',
                                    throttle_duration_sec=30)
            self._cap = None
            return False

        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=8,
            output_face_blendshapes=True)
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._mp = mp
        self._cv2 = cv2
        self.get_logger().info('camera + model ready')
        return True

    # ---------- main loop ----------

    def tick(self):
        if not self._ensure_pipeline():
            return
        ok, frame = self._cap.read()
        if not ok:
            self.get_logger().warn('frame read failed',
                                   throttle_duration_sec=10)
            return
        rgb = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
        mp_img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                                data=rgb)
        res = self._landmarker.detect_for_video(mp_img,
                                                int(time.time() * 1000))
        threshold = float(self.get_parameter('closed_threshold').value)
        seat_map = [s for s in self.get_parameter('seat_map').value]

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
            # distance from the ambiguous middle = confidence
            confidences.append(min(1.0, abs(blink - threshold) * 2 + 0.5))

        players = assign_seats(faces_x, seat_map)
        self.smoother.forget_missing(set(range(len(faces_x))))

        msg = EyeStateArray()
        msg.stamp = self.get_clock().now().to_msg()
        for i in range(len(faces_x)):
            st = EyeState()
            st.player_id = players[i]
            st.face_index = i
            st.eyes_open = not self.smoother.update(i, closed_flags[i])
            st.confidence = float(confidences[i])
            msg.states.append(st)
        self.pub.publish(msg)


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
