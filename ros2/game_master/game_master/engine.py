"""Mafia game engine — the family ruleset as a pure state machine.

No ROS imports here: the engine must be unit-testable with plain pytest.
The rclpy node in node.py wraps this class and translates its events
into topics/services.

Family ruleset (confirmed 2026-08-03):
- Roles: mafia (count chosen at setup), one doctor, one detective
  ("el-shayeb"), rest civilians.
- Night order: mafia kill -> doctor protect -> detective ask.
- Day: announce death -> discussion -> vote -> eliminate.
- Mafia win when non-mafia count equals mafia count; civilians win
  when all mafia are dead.
- Dead doctor/detective still get their night sub-phase announced so
  the group can't infer who died from the narration; input is ignored.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Role(str, Enum):
    MAFIA = "mafia"
    DOCTOR = "doctor"
    DETECTIVE = "detective"
    CIVILIAN = "civilian"


class Phase(str, Enum):
    LOBBY = "lobby"
    NIGHT_MAFIA = "night_mafia"
    NIGHT_DOCTOR = "night_doctor"
    NIGHT_DETECTIVE = "night_detective"
    DAY_ANNOUNCE = "day_announce"
    DAY_DISCUSSION = "day_discussion"
    DAY_VOTE = "day_vote"
    GAME_OVER = "game_over"


class Team(str, Enum):
    MAFIA = "mafia"
    CIVILIANS = "civilians"


@dataclass
class Player:
    id: str
    name: str
    role: Optional[Role] = None
    alive: bool = True


@dataclass
class GameEvent:
    """Structured event for the narrator / web bridge to render."""
    type: str
    data: dict = field(default_factory=dict)


class RuleError(Exception):
    """An action that the current phase or role does not allow."""


class MafiaEngine:
    def __init__(self, players: list[tuple[str, str]], mafia_count: int,
                 seed: Optional[int] = None):
        if len(players) < 4:
            raise RuleError("need at least 4 players (mafia, doctor, detective, civilian)")
        # mafia + doctor + detective must leave at least one civilian
        if mafia_count < 1 or mafia_count + 2 >= len(players):
            raise RuleError(f"mafia_count {mafia_count} impossible for {len(players)} players")
        self.players: dict[str, Player] = {
            pid: Player(id=pid, name=name) for pid, name in players
        }
        self.mafia_count = mafia_count
        self.phase = Phase.LOBBY
        self.round = 0
        self.winner: Optional[Team] = None
        self.events: list[GameEvent] = []
        self._rng = random.Random(seed)
        self._night_kill: Optional[str] = None
        self._night_protect: Optional[str] = None
        self._last_death: Optional[str] = None
        self._votes: dict[str, str] = {}
        self._revote_done = False
        self._revote_candidates: Optional[set[str]] = None

    # ---------- helpers ----------

    def _emit(self, type_: str, **data) -> GameEvent:
        ev = GameEvent(type=type_, data=data)
        self.events.append(ev)
        return ev

    def _require(self, phase: Phase):
        if self.phase is not phase:
            raise RuleError(f"action not allowed in phase {self.phase.value}")

    def _alive(self, role: Optional[Role] = None) -> list[Player]:
        return [p for p in self.players.values()
                if p.alive and (role is None or p.role is role)]

    def _alive_player(self, pid: str) -> Player:
        p = self.players.get(pid)
        if p is None or not p.alive:
            raise RuleError(f"no living player {pid!r}")
        return p

    def role_of(self, pid: str) -> Role:
        return self.players[pid].role

    @property
    def alive_ids(self) -> list[str]:
        return [p.id for p in self.players.values() if p.alive]

    # ---------- setup ----------

    def start(self):
        """Assign roles and enter the first night."""
        self._require(Phase.LOBBY)
        roles = ([Role.MAFIA] * self.mafia_count
                 + [Role.DOCTOR, Role.DETECTIVE]
                 + [Role.CIVILIAN] * (len(self.players) - self.mafia_count - 2))
        self._rng.shuffle(roles)
        for player, role in zip(self.players.values(), roles):
            player.role = role
        mafia = [p.id for p in self.players.values() if p.role is Role.MAFIA]
        self._emit("roles_assigned",
                   roles={p.id: p.role.value for p in self.players.values()},
                   mafia_ids=mafia)
        self._begin_night()

    # ---------- night ----------

    def _begin_night(self):
        self.round += 1
        self._night_kill = None
        self._night_protect = None
        self.phase = Phase.NIGHT_MAFIA
        self._emit("night_begins", round=self.round)

    def mafia_kill(self, actor: str, target: str):
        self._require(Phase.NIGHT_MAFIA)
        if self._alive_player(actor).role is not Role.MAFIA:
            raise RuleError("only mafia act in this phase")
        self._night_kill = self._alive_player(target).id
        self.phase = Phase.NIGHT_DOCTOR
        self._emit("mafia_chose", requires_input=self._role_alive(Role.DOCTOR))

    def doctor_protect(self, actor: str, target: str):
        self._require(Phase.NIGHT_DOCTOR)
        if self._alive_player(actor).role is not Role.DOCTOR:
            raise RuleError("only the doctor acts in this phase")
        self._night_protect = self._alive_player(target).id
        self._advance_to_detective()

    def skip_doctor(self):
        """Called by the moderator flow when the doctor is dead —
        the sub-phase is still narrated, but nobody acts."""
        self._require(Phase.NIGHT_DOCTOR)
        if self._role_alive(Role.DOCTOR):
            raise RuleError("doctor is alive and must act")
        self._advance_to_detective()

    def _advance_to_detective(self):
        self.phase = Phase.NIGHT_DETECTIVE
        self._emit("doctor_done", requires_input=self._role_alive(Role.DETECTIVE))

    def detective_ask(self, actor: str, target: str) -> bool:
        self._require(Phase.NIGHT_DETECTIVE)
        if self._alive_player(actor).role is not Role.DETECTIVE:
            raise RuleError("only the detective acts in this phase")
        is_mafia = self._alive_player(target).role is Role.MAFIA
        self._emit("detective_answer", detective=actor, target=target,
                   is_mafia=is_mafia, private=True)
        self._resolve_night()
        return is_mafia

    def skip_detective(self):
        self._require(Phase.NIGHT_DETECTIVE)
        if self._role_alive(Role.DETECTIVE):
            raise RuleError("detective is alive and must act")
        self._resolve_night()

    def _role_alive(self, role: Role) -> bool:
        return bool(self._alive(role))

    def _resolve_night(self):
        saved = (self._night_kill is not None
                 and self._night_kill == self._night_protect)
        if self._night_kill and not saved:
            self.players[self._night_kill].alive = False
            self._last_death = self._night_kill
        else:
            self._last_death = None
        self.phase = Phase.DAY_ANNOUNCE
        self._emit("day_begins", round=self.round,
                   death=self._last_death, saved=saved)
        if not self._check_win():
            self.phase = Phase.DAY_DISCUSSION
            self._emit("discussion_begins", alive=self.alive_ids)

    # ---------- day ----------

    def begin_vote(self):
        self._require(Phase.DAY_DISCUSSION)
        self.phase = Phase.DAY_VOTE
        self._votes = {}
        self._revote_done = False
        self._revote_candidates = None
        self._emit("vote_begins", candidates=self.alive_ids)

    def cast_vote(self, voter: str, target: str):
        self._require(Phase.DAY_VOTE)
        self._alive_player(voter)
        target_p = self._alive_player(target)
        if self._revote_candidates is not None and target_p.id not in self._revote_candidates:
            raise RuleError("revote is restricted to the tied players")
        self._votes[voter] = target_p.id
        if len(self._votes) == len(self.alive_ids):
            self._tally()

    def _tally(self):
        counts: dict[str, int] = {}
        for target in self._votes.values():
            counts[target] = counts.get(target, 0) + 1
        top = max(counts.values())
        leaders = [pid for pid, n in counts.items() if n == top]
        if len(leaders) > 1:
            if not self._revote_done:
                # one revote restricted to the tied players
                self._revote_done = True
                self._revote_candidates = set(leaders)
                self._votes = {}
                self._emit("vote_tied", candidates=leaders, revote=True)
                return
            self._emit("vote_tied", candidates=leaders, revote=False)
            self._end_day(eliminated=None)
            return
        self._end_day(eliminated=leaders[0])

    def _end_day(self, eliminated: Optional[str]):
        if eliminated is not None:
            p = self.players[eliminated]
            p.alive = False
            self._emit("player_eliminated", player=eliminated,
                       role=p.role.value)
        else:
            self._emit("no_elimination")
        if not self._check_win():
            self._begin_night()

    # ---------- win ----------

    def _check_win(self) -> bool:
        mafia = len(self._alive(Role.MAFIA))
        others = len(self.alive_ids) - mafia
        if mafia == 0:
            self.winner = Team.CIVILIANS
        elif others <= mafia:
            self.winner = Team.MAFIA
        if self.winner:
            self.phase = Phase.GAME_OVER
            self._emit("game_over", winner=self.winner.value,
                       roles={p.id: p.role.value for p in self.players.values()})
            return True
        return False
