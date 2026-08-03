"""Pure vision-side logic for the CV referee — no mediapipe, no ROS.

The heavy lifting (face/pose landmarks, blink blendshapes) happens in
node.py with MediaPipe; this module holds the small decisions we want
unit tests on: temporal smoothing, seat-based identity mapping, and the
hand-raise geometry check.
"""

from __future__ import annotations

from typing import Protocol


class BoolSmoother:
    """Majority vote over the last n observations, per tracked key.

    Used for both eye-closed and hand-raised signals — same debounce
    logic either way, one bad frame shouldn't flip the reported state.
    """

    def __init__(self, n: int = 5):
        self.n = n
        self._hist: dict[int, list[bool]] = {}

    def update(self, key: int, value_now: bool) -> bool:
        hist = self._hist.setdefault(key, [])
        hist.append(value_now)
        if len(hist) > self.n:
            hist.pop(0)
        return sum(hist) > len(hist) // 2

    def forget_missing(self, present: set[int]):
        for key in list(self._hist):
            if key not in present:
                del self._hist[key]


# Backwards-compatible alias — EyeSmoother was the original, narrower name.
EyeSmoother = BoolSmoother


class _HasXY(Protocol):
    x: float
    y: float


def hand_raised(left_shoulder: _HasXY, right_shoulder: _HasXY,
                left_wrist: _HasXY, right_wrist: _HasXY) -> bool:
    """True if either wrist is above (smaller y than) its shoulder.

    Image y grows downward, so "above" means a numerically smaller y.
    Takes plain landmark-like objects (just need .y) rather than a
    MediaPipe-specific type, so this stays testable without mediapipe
    installed.
    """
    return left_wrist.y < left_shoulder.y or right_wrist.y < right_shoulder.y


def assign_seats(face_xs: list[float], seat_map: list[str]) -> list[str]:
    """Map detected faces to player ids by seating order.

    face_xs: horizontal center (0..1) of each detected face, in detection
    order. seat_map: player ids left-to-right as the camera sees them.
    Returns a player id (or '') for each detected face, same order as
    face_xs. Extra faces beyond the seat map get ''.
    """
    order = sorted(range(len(face_xs)), key=lambda i: face_xs[i])
    result = [''] * len(face_xs)
    for seat, face_i in enumerate(order):
        if seat < len(seat_map):
            result[face_i] = seat_map[seat]
    return result
