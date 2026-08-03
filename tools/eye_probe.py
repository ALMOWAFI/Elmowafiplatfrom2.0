"""Eye-state probe — the core experiment for the mafia CV referee.

MediaPipe 1.0 Tasks API: FaceLandmarker with blendshapes. The model
outputs a trained eyeBlinkLeft/eyeBlinkRight score per face; we treat
mean blink score > 0.5 as CLOSED. Labels every face live and prints a
reliability summary at the end.

Usage:  python eye_probe.py [seconds]   (default 30, or press q)

Model (place face_landmarker.task next to this script):
https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task

Validated 2026-08-03 (laptop webcam, CPU): 100% face detection over
540 frames, ~35ms inference, ~20fps; blinks and deliberate closures
tracked cleanly with blendshape threshold 0.5 + 5-frame smoothing.
"""

import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

MODEL = Path(__file__).resolve().parent / 'face_landmarker.task'
CLOSED_T = 0.5
SMOOTH_N = 5


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print('ERROR: cannot open webcam')
        sys.exit(1)

    options = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(MODEL)),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=6,
        output_face_blendshapes=True)
    landmarker = vision.FaceLandmarker.create_from_options(options)

    history: dict[int, list[bool]] = {}
    stats = {'frames': 0, 'face_frames': 0, 'closed_frames': 0,
             'transitions': 0, 'last': None, 'lat_ms': []}
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
        t_in = time.time()
        res = landmarker.detect_for_video(mp_img, int(t_in * 1000))
        stats['lat_ms'].append((time.time() - t_in) * 1000)

        if res.face_landmarks:
            stats['face_frames'] += 1
            for fi, (lm, bs) in enumerate(zip(res.face_landmarks,
                                              res.face_blendshapes)):
                scores = {c.category_name: c.score for c in bs}
                blink = (scores.get('eyeBlinkLeft', 0)
                         + scores.get('eyeBlinkRight', 0)) / 2
                closed_now = blink > CLOSED_T
                hist = history.setdefault(fi, [])
                hist.append(closed_now)
                if len(hist) > SMOOTH_N:
                    hist.pop(0)
                closed = sum(hist) > len(hist) // 2

                if fi == 0:
                    if stats['last'] is not None and stats['last'] != closed:
                        stats['transitions'] += 1
                    stats['last'] = closed
                    if closed:
                        stats['closed_frames'] += 1

                xs = [p.x for p in lm]; ys = [p.y for p in lm]
                x1, y1 = int(min(xs) * w), int(min(ys) * h)
                x2, y2 = int(max(xs) * w), int(max(ys) * h)
                color = (0, 0, 255) if closed else (0, 200, 0)
                label = f'{"CLOSED" if closed else "OPEN"} blink={blink:.2f}'
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame, label, (x1, max(20, y1 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        fps_n += 1
        if time.time() - fps_t >= 1.0:
            fps = fps_n / (time.time() - fps_t)
            fps_t, fps_n = time.time(), 0
        cv2.putText(frame, f'{fps:.1f} fps  (q quits)', (10, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1)
        cv2.imshow('Mafia eye probe', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    f, ff = stats['frames'], stats['face_frames']
    lat = sorted(stats['lat_ms'])
    print('--- eye probe summary ---')
    print(f'frames: {f}, with face: {ff} ({100 * ff / max(1, f):.0f}%)')
    print(f'closed frames (face 0): {stats["closed_frames"]}')
    print(f'open/closed transitions: {stats["transitions"]}')
    if lat:
        print(f'inference ms  p50={lat[len(lat)//2]:.1f}  p90={lat[int(len(lat)*.9)]:.1f}')
    print(f'approx fps: {fps:.1f}')


if __name__ == '__main__':
    main()
