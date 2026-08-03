from game_master.engine import MafiaEngine, Phase, Role
from game_master.referee import peek_violations

PLAYERS = [("p1", "Ali"), ("p2", "Marwa"), ("p3", "Omar"),
           ("p4", "Sara"), ("p5", "Hani")]


def game():
    eng = MafiaEngine(PLAYERS, mafia_count=1, seed=7)
    eng.start()
    return eng


def role_pid(eng, role):
    return next(p.id for p in eng.players.values() if p.role is role)


def test_civilian_peek_flagged_mafia_allowed():
    eng = game()
    assert eng.phase is Phase.NIGHT_MAFIA
    mafia = role_pid(eng, Role.MAFIA)
    civ = role_pid(eng, Role.CIVILIAN)
    states = [(mafia, True, 0.9), (civ, True, 0.9)]
    out = peek_violations(eng, states, {}, now=100.0)
    assert out == [civ]


def test_cooldown_blocks_repeat_callouts():
    eng = game()
    civ = role_pid(eng, Role.CIVILIAN)
    last = {}
    assert peek_violations(eng, [(civ, True, 0.9)], last, now=100.0) == [civ]
    assert peek_violations(eng, [(civ, True, 0.9)], last, now=103.0) == []
    assert peek_violations(eng, [(civ, True, 0.9)], last, now=109.0) == [civ]


def test_day_and_low_confidence_and_unknown_ignored():
    eng = game()
    civ = role_pid(eng, Role.CIVILIAN)
    # low confidence ignored
    assert peek_violations(eng, [(civ, True, 0.3)], {}, now=1.0) == []
    # unidentified face ignored
    assert peek_violations(eng, [('', True, 0.9)], {}, now=1.0) == []
    # day phases: eyes open is fine
    mafia = role_pid(eng, Role.MAFIA)
    doctor = role_pid(eng, Role.DOCTOR)
    det = role_pid(eng, Role.DETECTIVE)
    eng.mafia_kill(mafia, civ)
    eng.doctor_protect(doctor, civ)
    eng.detective_ask(det, mafia)
    assert eng.phase is Phase.DAY_DISCUSSION
    assert peek_violations(eng, [(civ, True, 0.9)], {}, now=1.0) == []


def test_doctor_phase_allows_only_doctor():
    eng = game()
    mafia = role_pid(eng, Role.MAFIA)
    doctor = role_pid(eng, Role.DOCTOR)
    civ = role_pid(eng, Role.CIVILIAN)
    eng.mafia_kill(mafia, civ)
    assert eng.phase is Phase.NIGHT_DOCTOR
    states = [(doctor, True, 0.9), (mafia, True, 0.9)]
    assert peek_violations(eng, states, {}, now=5.0) == [mafia]


def test_dead_players_ignored():
    eng = game()
    mafia = role_pid(eng, Role.MAFIA)
    doctor = role_pid(eng, Role.DOCTOR)
    det = role_pid(eng, Role.DETECTIVE)
    civ = role_pid(eng, Role.CIVILIAN)
    eng.mafia_kill(mafia, civ)
    eng.doctor_protect(doctor, doctor)  # protect self
    eng.detective_ask(det, mafia)
    assert not eng.players[civ].alive
    # next night: dead civilian watching is not a violation
    eng.begin_vote()
    alive = eng.alive_ids
    other_civ = [p for p in alive if eng.players[p].role is Role.CIVILIAN]
    target = other_civ[0] if other_civ else alive[0]
    for pid in list(eng.alive_ids):
        eng.cast_vote(pid, target)
    if eng.phase is Phase.NIGHT_MAFIA:
        assert peek_violations(eng, [(civ, True, 0.9)], {}, now=50.0) == []
