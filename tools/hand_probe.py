"""Hand-raise probe — validates the core trick for day-vote CV before
wiring it into cv_referee: MediaPipe Pose, wrist-above-shoulder per
person, live-labeled with a short reliability summary at the end.

Pose (not Hand landmarks) is used deliberately: a family circle sits at
2-3m from the camera, and Pose tracks wrists+shoulders reliably at that
range from a whole-body view, where finger-level Hand landmarks would
need a much closer, hands-in-frame shot.

Usage: python hand_probe.py [seconds]
Model: pose_landmarker_lite.task next to this script.
Download: https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
"""

import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

MODEL = Path(__file__).resolve().parent / 'pose_landmarker_lite.task'
# BlazePose landmark indices
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_WRIST, RIGHT_WRIST = 15, 16
SMOOTH_N = 4


def hand_raised(landmarks) -> bool:
    """True if either wrist is above (smaller y than) its shoulder."""
    ls, rs = landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER]
    lw, rw = landmarks[LEFT_WRIST], landmarks[RIGHT_WRIST]
    return lw.y < ls.y or rw.y < rs.y


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    if not MODEL.exists():
        print(f'model missing: {MODEL}\nsee URL in this script header')
        sys.exit(1)
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print('ERROR: cannot open webcam')
        sys.exit(1)

    landmarker = vision.PoseLandmarker.create_from_options(
        vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(MODEL)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=6))

    history: dict[int, list[bool]] = {}
    stats = {'frames': 0, 'pose_frames': 0, 'raised_frames': 0,
             'transitions': 0, 'last': None}
    t0 = time.time()
    fps_t, fps_n, fps = time.time(), 0, 0.0

    while time.time() - t0 < seconds:
        ok, frame = cap.read()
        if not ok:
            break
        stats['frames'] += 1
        h, w = frame.shape[:2]
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB,
                          data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        res = landmarker.detect_for_video(mp_img, int(time.time() * 1000))

        if res.pose_landmarks:
            stats['pose_frames'] += 1
            for pi, lm in enumerate(res.pose_landmarks):
                raised_now = hand_raised(lm)
                hist = history.setdefault(pi, [])
                hist.append(raised_now)
                if len(hist) > SMOOTH_N:
                    hist.pop(0)
                raised = sum(hist) > len(hist) // 2

                if pi == 0:
                    if stats['last'] is not None and stats['last'] != raised:
                        stats['transitions'] += 1
                    stats['last'] = raised
                    if raised:
                        stats['raised_frames'] += 1

                xs = [p.x for p in lm]; ys = [p.y for p in lm]
                x1, y1 = int(min(xs) * w), int(min(ys) * h)
                x2, y2 = int(max(xs) * w), int(max(ys) * h)
                color = (0, 200, 0) if raised else (0, 0, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, 'HAND UP' if raised else 'down',
                            (x1, max(20, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        fps_n += 1
        if time.time() - fps_t >= 1.0:
            fps = fps_n / (time.time() - fps_t)
            fps_t, fps_n = time.time(), 0
        cv2.putText(frame, f'{fps:.1f} fps  (q quits)', (10, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1)
        cv2.imshow('Hand-raise probe', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    f, pf = stats['frames'], stats['pose_frames']
    print('--- hand-raise probe summary ---')
    print(f'frames: {f}, with pose: {pf} ({100 * pf / max(1, f):.0f}%)')
    print(f'raised frames (person 0): {stats["raised_frames"]}')
    print(f'raised/lowered transitions: {stats["transitions"]}')
    print(f'approx fps: {fps:.1f}')


if __name__ == '__main__':
    main()
