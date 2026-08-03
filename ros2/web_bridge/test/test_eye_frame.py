"""Unit tests for the own-camera eye-frame endpoint logic (process_eye_frame
/ publish_own_camera_eye_state). mediapipe/cv2 detection is mocked so
these run fast and don't need a real camera, model file, or ROS graph
beyond the single Bridge node — but they pin down the exact behavior:
no-face vs found-face, missing-model handling, and per-player smoothing
isolation (one phone's frames shouldn't affect another's smoothed state).
"""

from unittest.mock import MagicMock, patch

import pytest
import rclpy

from web_bridge.node import EYE_CLOSED_THRESHOLD, Bridge


@pytest.fixture
def bridge():
    rclpy.init()
    b = Bridge(port=0)
    yield b
    b.node.destroy_node()
    rclpy.shutdown()


def _fake_landmarker(blink_score: float, has_face: bool = True):
    """Build a mock matching the real FaceLandmarker.detect() result
    shape: .face_landmarks (list of landmark lists) and
    .face_blendshapes (list of category lists)."""
    result = MagicMock()
    if not has_face:
        result.face_landmarks = []
        result.face_blendshapes = []
        return result
    result.face_landmarks = [[MagicMock()]]
    cat_left = MagicMock(category_name='eyeBlinkLeft', score=blink_score)
    cat_right = MagicMock(category_name='eyeBlinkRight', score=blink_score)
    result.face_blendshapes = [[cat_left, cat_right]]
    return result


def test_process_eye_frame_no_model_returns_none(bridge, tmp_path):
    with patch('web_bridge.node.Path.home', return_value=tmp_path):
        result = bridge.process_eye_frame('p1', b'fake-jpeg-bytes')
    assert result is None


def test_process_eye_frame_bad_image_returns_none(bridge):
    bridge._face_landmarker = MagicMock()  # skip real model loading
    bridge._cv2 = MagicMock()
    bridge._cv2.imdecode.return_value = None  # cv2 failed to decode
    bridge._mp = MagicMock()
    result = bridge.process_eye_frame('p1', b'not-a-real-jpeg')
    assert result is None


def test_process_eye_frame_no_face_found(bridge):
    bridge._face_landmarker = MagicMock()
    bridge._face_landmarker.detect.return_value = _fake_landmarker(0, has_face=False)
    bridge._cv2 = MagicMock()
    bridge._cv2.imdecode.return_value = MagicMock()
    bridge._cv2.cvtColor.return_value = MagicMock()
    bridge._cv2.COLOR_BGR2RGB = 4
    bridge._mp = MagicMock()

    result = bridge.process_eye_frame('p1', b'jpeg-bytes')
    assert result == {'found_face': False}


def test_process_eye_frame_eyes_open(bridge):
    bridge._face_landmarker = MagicMock()
    bridge._face_landmarker.detect.return_value = _fake_landmarker(0.1)  # low blink = open
    bridge._cv2 = MagicMock()
    bridge._cv2.imdecode.return_value = MagicMock()
    bridge._cv2.cvtColor.return_value = MagicMock()
    bridge._mp = MagicMock()

    result = bridge.process_eye_frame('p1', b'jpeg-bytes')
    assert result['found_face'] is True
    assert result['eyes_open'] is True


def test_process_eye_frame_sustained_closure_reports_closed(bridge):
    bridge._face_landmarker = MagicMock()
    bridge._face_landmarker.detect.return_value = _fake_landmarker(0.9)  # high blink = closed
    bridge._cv2 = MagicMock()
    bridge._cv2.imdecode.return_value = MagicMock()
    bridge._cv2.cvtColor.return_value = MagicMock()
    bridge._mp = MagicMock()

    # BoolSmoother has no prior history for a brand-new player, so even
    # the very first closed frame reports closed (sum=1 > len//2=0) --
    # this is existing, accepted behavior shared with cv_referee's
    # smoother, not something new here. What matters for THIS test is
    # that sustained closure over several frames stays reported closed.
    for _ in range(3):
        result = bridge.process_eye_frame('p1', b'jpeg-bytes')
    assert result['eyes_open'] is False


def test_process_eye_frame_single_blink_does_not_flip_from_open(bridge):
    bridge._face_landmarker = MagicMock()
    bridge._cv2 = MagicMock()
    bridge._cv2.imdecode.return_value = MagicMock()
    bridge._cv2.cvtColor.return_value = MagicMock()
    bridge._mp = MagicMock()

    bridge._face_landmarker.detect.return_value = _fake_landmarker(0.1)  # open
    bridge.process_eye_frame('p1', b'jpeg-bytes')
    bridge._face_landmarker.detect.return_value = _fake_landmarker(0.9)  # one closed blip
    result = bridge.process_eye_frame('p1', b'jpeg-bytes')
    assert result['eyes_open'] is True  # one blip among an open history doesn't flip it


def test_process_eye_frame_smoothing_is_per_player(bridge):
    bridge._face_landmarker = MagicMock()
    bridge._cv2 = MagicMock()
    bridge._cv2.imdecode.return_value = MagicMock()
    bridge._cv2.cvtColor.return_value = MagicMock()
    bridge._mp = MagicMock()

    # p1 gets 3 sustained-closed frames; p2's single frame is wide-open.
    # If state leaked between players, p2 would inherit p1's closed
    # history and read closed too -- it must not.
    bridge._face_landmarker.detect.side_effect = [
        _fake_landmarker(0.9), _fake_landmarker(0.9), _fake_landmarker(0.9),
        _fake_landmarker(0.05),
    ]
    for _ in range(3):
        bridge.process_eye_frame('p1', b'jpeg-bytes')
    r_p2_first = bridge.process_eye_frame('p2', b'jpeg-bytes')
    assert r_p2_first['eyes_open'] is True


def test_publish_own_camera_eye_state_publishes_single_state(bridge):
    with patch.object(bridge.node, 'eye_pub') as pub:
        bridge.publish_own_camera_eye_state('p1', True, 0.9)
    pub.publish.assert_called_once()
    msg = pub.publish.call_args.args[0]
    assert len(msg.states) == 1
    assert msg.states[0].player_id == 'p1'
    assert msg.states[0].eyes_open is True


def test_eye_closed_threshold_matches_cv_referee_default():
    assert EYE_CLOSED_THRESHOLD == 0.5
