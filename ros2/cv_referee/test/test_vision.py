from dataclasses import dataclass

from cv_referee.vision import BoolSmoother, EyeSmoother, assign_seats, hand_raised


def test_smoother_majority_and_window():
    s = BoolSmoother(n=5)
    # single blink frame doesn't flip the state
    assert s.update(0, False) is False
    assert s.update(0, True) is False
    assert s.update(0, False) is False
    # sustained closure does
    for _ in range(3):
        result = s.update(0, True)
    assert result is True


def test_smoother_per_face_isolation():
    s = BoolSmoother(n=3)
    s.update(0, True); s.update(0, True)
    assert s.update(1, False) is False   # face 1 unaffected by face 0


def test_forget_missing():
    s = BoolSmoother(n=3)
    s.update(0, True); s.update(1, True)
    s.forget_missing({0})
    assert 1 not in s._hist and 0 in s._hist


def test_eyesmoother_alias_is_the_same_class():
    assert EyeSmoother is BoolSmoother


def test_assign_seats_left_to_right():
    # faces detected out of order: x=0.8, 0.1, 0.5
    got = assign_seats([0.8, 0.1, 0.5], ['p_left', 'p_mid', 'p_right'])
    assert got == ['p_right', 'p_left', 'p_mid']


def test_assign_seats_extra_faces_and_short_map():
    got = assign_seats([0.2, 0.6, 0.9], ['p1', 'p2'])
    assert got == ['p1', 'p2', '']
    assert assign_seats([], ['p1']) == []


@dataclass
class _Point:
    x: float
    y: float


def test_hand_raised_left_wrist_above_shoulder():
    # image y grows downward; wrist.y=0.2 is ABOVE shoulder.y=0.5
    ls, rs = _Point(0.3, 0.5), _Point(0.7, 0.5)
    lw, rw = _Point(0.3, 0.2), _Point(0.7, 0.6)  # left raised, right resting
    assert hand_raised(ls, rs, lw, rw) is True


def test_hand_raised_right_wrist_above_shoulder():
    ls, rs = _Point(0.3, 0.5), _Point(0.7, 0.5)
    lw, rw = _Point(0.3, 0.6), _Point(0.7, 0.1)  # left resting, right raised
    assert hand_raised(ls, rs, lw, rw) is True


def test_hand_raised_neither_wrist_up():
    ls, rs = _Point(0.3, 0.5), _Point(0.7, 0.5)
    lw, rw = _Point(0.3, 0.6), _Point(0.7, 0.6)  # both wrists below shoulders
    assert hand_raised(ls, rs, lw, rw) is False


def test_hand_raised_exactly_level_is_not_raised():
    # boundary case: wrist exactly at shoulder height doesn't count
    ls, rs = _Point(0.3, 0.5), _Point(0.7, 0.5)
    lw, rw = _Point(0.3, 0.5), _Point(0.7, 0.5)
    assert hand_raised(ls, rs, lw, rw) is False
