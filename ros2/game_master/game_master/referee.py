"""Phase-aware peek detection — pure logic, no ROS.

cv_referee reports who has eyes open; this module decides who is
cheating given the current phase and roles. Dead players are ignored
(they're allowed to watch), and the acting role of each night sub-phase
is allowed to look.
"""

from __future__ import annotations

from game_master.engine import MafiaEngine, Phase, Role

# Which role is allowed eyes-open in each night sub-phase
ALLOWED = {
    Phase.NIGHT_MAFIA: {Role.MAFIA},
    Phase.NIGHT_DOCTOR: {Role.DOCTOR},
    Phase.NIGHT_DETECTIVE: {Role.DETECTIVE},
}

PEEK_COOLDOWN_S = 8.0   # min seconds between callouts for the same player
MIN_CONFIDENCE = 0.6    # ignore low-confidence eye states


def peek_violations(engine: MafiaEngine,
                    eye_states: list[tuple[str, bool, float]],
                    last_callout: dict[str, float],
                    now: float,
                    cooldown: float = PEEK_COOLDOWN_S) -> list[str]:
    """Return player_ids to call out. Mutates last_callout for those returned.

    eye_states: (player_id, eyes_open, confidence) triples; player_id may
    be '' for unidentified faces, which are skipped.
    """
    allowed = ALLOWED.get(engine.phase)
    if allowed is None:
        return []
    offenders = []
    for player_id, eyes_open, confidence in eye_states:
        if not player_id or not eyes_open or confidence < MIN_CONFIDENCE:
            continue
        player = engine.players.get(player_id)
        if player is None or not player.alive:
            continue
        if player.role in allowed:
            continue
        if now - last_callout.get(player_id, -1e9) < cooldown:
            continue
        last_callout[player_id] = now
        offenders.append(player_id)
    return offenders
