from cv_referee.vision import EyeSmoother, assign_seats


def test_smoother_majority_and_window():
    s = EyeSmoother(n=5)
    # single blink frame doesn't flip the state
    assert s.update(0, False) is False
    assert s.update(0, True) is False
    assert s.update(0, False) is False
    # sustained closure does
    for _ in range(3):
        result = s.update(0, True)
    assert result is True


def test_smoother_per_face_isolation():
    s = EyeSmoother(n=3)
    s.update(0, True); s.update(0, True)
    assert s.update(1, False) is False   # face 1 unaffected by face 0


def test_forget_missing():
    s = EyeSmoother(n=3)
    s.update(0, True); s.update(1, True)
    s.forget_missing({0})
    assert 1 not in s._hist and 0 in s._hist


def test_assign_seats_left_to_right():
    # faces detected out of order: x=0.8, 0.1, 0.5
    got = assign_seats([0.8, 0.1, 0.5], ['p_left', 'p_mid', 'p_right'])
    assert got == ['p_right', 'p_left', 'p_mid']


def test_assign_seats_extra_faces_and_short_map():
    got = assign_seats([0.2, 0.6, 0.9], ['p1', 'p2'])
    assert got == ['p1', 'p2', '']
    assert assign_seats([], ['p1']) == []
