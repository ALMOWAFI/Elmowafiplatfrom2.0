"""Windows camera relay — real webcam driving the WSL game.

Runs the validated MediaPipe blendshape pipeline on the Windows webcam
(WSL can't see USB cameras) and POSTs smoothed per-player eye states to
web_bridge, which republishes them on /cv/eye_states for game_master.

Usage:
  python win_cam_relay.py p_ab12,p_cd34,p_ef56   # seat map, left-to-right
  python win_cam_relay.py                        # preview only, no ids

Get the ids from the lobby (each phone shows its id in the URL bar
after joining) or from  http://localhost:8080/health  names map.
Model: face_landmarker.task next to this script (URL in tools/eye_probe.py).
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

BRIDGE = 'http://localhost:8080/api/cv/eye_states'
MODEL = Path(__file__).resolve().parent / 'face_landmarker.task'
CLOSED_T = 0.5
SMOOTH_N = 5
SEND_HZ = 10.0


def post_states(states):
    body = json.dumps({'states': states}).encode()
    req = urllib.request.Request(BRIDGE, body,
                                 {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=2) as r:
        return json.loads(r.read())


def main():
    seat_map = sys.argv[1].split(',') if len(sys.argv) > 1 else []
    if not MODEL.exists():
        print(f'model missing: {MODEL} — see tools/eye_probe.py for URL')
        sys.exit(1)
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print('ERROR: cannot open webcam')
        sys.exit(1)

    landmarker = vision.FaceLandmarker.create_from_options(
        vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(MODEL)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=8, output_face_blendshapes=True))

    history: dict[int, list[bool]] = {}
    last_send = 0.0
    send_err = ''
    print(f'relay running -> {BRIDGE}  seat_map={seat_map or "(none)"}  q quits')

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB,
                          data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        res = landmarker.detect_for_video(mp_img, int(time.time() * 1000))

        faces = []
        for lm, bs in zip(res.face_landmarks, res.face_blendshapes):
            xs = [p.x for p in lm]; ys = [p.y for p in lm]
            scores = {c.category_name: c.score for c in bs}
            blink = (scores.get('eyeBlinkLeft', 0.0)
                     + scores.get('eyeBlinkRight', 0.0)) / 2
            faces.append({'cx': (min(xs) + max(xs)) / 2,
                          'box': (int(min(xs) * w), int(min(ys) * h),
                                  int(max(xs) * w), int(max(ys) * h)),
                          'blink': blink})

        # seat mapping: faces sorted left-to-right take seat_map slots
        order = sorted(range(len(faces)), key=lambda i: faces[i]['cx'])
        for seat, fi in enumerate(order):
            faces[fi]['player_id'] = (seat_map[seat]
                                      if seat < len(seat_map) else '')

        states = []
        for fi, f in enumerate(faces):
            hist = history.setdefault(fi, [])
            hist.append(f['blink'] > CLOSED_T)
            if len(hist) > SMOOTH_N:
                hist.pop(0)
            closed = sum(hist) > len(hist) // 2
            f['closed'] = closed
            states.append({'player_id': f['player_id'], 'face_index': fi,
                           'eyes_open': not closed,
                           'confidence': min(1.0, abs(f['blink'] - CLOSED_T) * 2 + 0.5)})
        for fi in list(history):
            if fi >= len(faces):
                del history[fi]

        now = time.time()
        if states and now - last_send >= 1.0 / SEND_HZ:
            last_send = now
            try:
                post_states(states)
                send_err = ''
            except Exception as e:  # noqa: BLE001
                send_err = str(e)

        for f in faces:
            x1, y1, x2, y2 = f['box']
            color = (0, 0, 255) if f['closed'] else (0, 200, 0)
            tag = f['player_id'] or '?'
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame,
                        f'{tag} {"CLOSED" if f["closed"] else "OPEN"}',
                        (x1, max(20, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        status = f'sending {len(faces)} faces' if not send_err else f'SEND ERR: {send_err[:40]}'
        cv2.putText(frame, status + '  (q quits)', (10, h - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1)
        cv2.imshow('Mafia camera relay', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
