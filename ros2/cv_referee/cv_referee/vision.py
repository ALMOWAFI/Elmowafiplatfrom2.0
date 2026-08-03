"""Pure vision-side logic for the CV referee — no mediapipe, no ROS.

The heavy lifting (face landmarks, blink blendshapes) happens in node.py
with MediaPipe; this module holds the small decisions we want unit
tests on: temporal smoothing and seat-based identity mapping.
"""

from __future__ import annotations


class EyeSmoother:
    """Majority vote over the last n observations, per face key."""

    def __init__(self, n: int = 5):
        self.n = n
        self._hist: dict[int, list[bool]] = {}

    def update(self, key: int, closed_now: bool) -> bool:
        hist = self._hist.setdefault(key, [])
        hist.append(closed_now)
        if len(hist) > self.n:
            hist.pop(0)
        return sum(hist) > len(hist) // 2

    def forget_missing(self, present: set[int]):
        for key in list(self._hist):
            if key not in present:
                del self._hist[key]


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
