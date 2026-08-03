"""ROS2 wrapper around MafiaEngine.

Topics
  /game/state   elmowafi_msgs/GameState   (transient_local, latest state)
  /game/events  elmowafi_msgs/GameEvent   (stream; private events carry recipient_id)
Subscriptions
  /cv/violations  elmowafi_msgs/Violation (peeks caught by cv_referee ->
                                           instant callout event for narrator)
Services
  /game/submit_action  elmowafi_msgs/SubmitAction (lobby + all player actions,
                                                   called by web_bridge)
"""

import json
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, HistoryPolicy

from elmowafi_msgs.msg import EyeStateArray, GameEvent, GameState, Violation
from elmowafi_msgs.srv import SubmitAction

from game_master.engine import MafiaEngine, Phase, Role, RuleError
from game_master.referee import peek_violations


class GameMasterNode(Node):
    def __init__(self):
        super().__init__('game_master')
        latched = QoSProfile(depth=1,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             history=HistoryPolicy.KEEP_LAST)
        self.state_pub = self.create_publisher(GameState, '/game/state', latched)
        self.event_pub = self.create_publisher(GameEvent, '/game/events', 10)
        self.create_subscription(Violation, '/cv/violations',
                                 self.on_violation, 10)
        self.create_subscription(EyeStateArray, '/cv/eye_states',
                                 self.on_eye_states, 10)
        self._last_callout: dict[str, float] = {}
        self.create_service(SubmitAction, '/game/submit_action',
                            self.on_action)

        self.lobby: list[tuple[str, str]] = []   # (player_id, name)
        self.engine: MafiaEngine | None = None
        self._emitted = 0
        self.publish_state()
        self.get_logger().info('game_master ready — waiting for players')

    # ---------- publishing ----------

    def publish_state(self):
        msg = GameState()
        if self.engine is None:
            msg.phase = 'lobby'
            msg.round = 0
            msg.alive_ids = [pid for pid, _ in self.lobby]
            msg.winner = ''
        else:
            msg.phase = self.engine.phase.value
            msg.round = self.engine.round
            msg.alive_ids = self.engine.alive_ids
            msg.winner = self.engine.winner.value if self.engine.winner else ''
        self.state_pub.publish(msg)

    def flush_events(self):
        """Publish engine events created since the last flush."""
        if self.engine is None:
            return
        for ev in self.engine.events[self._emitted:]:
            msg = GameEvent()
            msg.stamp = self.get_clock().now().to_msg()
            msg.type = ev.type
            data = dict(ev.data)
            # private events go only to their recipient via web_bridge
            if ev.type == 'detective_answer':
                msg.recipient_id = data.get('detective', '')
            elif ev.type == 'roles_assigned':
                # web_bridge fans this out per player; mafia_ids only to mafia
                msg.recipient_id = '__per_player__'
            msg.data_json = json.dumps(data)
            self.event_pub.publish(msg)
        self._emitted = len(self.engine.events)

    # ---------- CV violations ----------

    def on_violation(self, msg: Violation):
        # Instant callout: relayed to narrator as a broadcast event
        ev = GameEvent()
        ev.stamp = msg.stamp
        ev.type = 'peek_callout'
        ev.data_json = json.dumps({'player': msg.player_id,
                                   'phase': msg.phase,
                                   'confidence': round(msg.confidence, 3)})
        self.event_pub.publish(ev)
        self.get_logger().warning(f'PEEK: {msg.player_id} during {msg.phase}')

    def on_eye_states(self, msg: EyeStateArray):
        """Role-blind eye states from cv_referee -> phase-aware callouts."""
        if self.engine is None:
            return
        states = [(s.player_id, s.eyes_open, s.confidence)
                  for s in msg.states]
        for pid in peek_violations(self.engine, states,
                                   self._last_callout, time.time()):
            ev = GameEvent()
            ev.stamp = self.get_clock().now().to_msg()
            ev.type = 'peek_callout'
            ev.data_json = json.dumps({'player': pid,
                                       'phase': self.engine.phase.value})
            self.event_pub.publish(ev)
            self.get_logger().warning(
                f'PEEK: {pid} during {self.engine.phase.value}')

    # ---------- player actions ----------

    def on_action(self, req: SubmitAction.Request, res: SubmitAction.Response):
        res.accepted = True
        res.message = ''
        res.result_json = ''
        try:
            handler = getattr(self, f'_act_{req.action_type}', None)
            if handler is None:
                raise RuleError(f'unknown action {req.action_type!r}')
            result = handler(req)
            if result is not None:
                res.result_json = json.dumps(result)
        except RuleError as e:
            res.accepted = False
            res.message = str(e)
        self.flush_events()
        self.publish_state()
        return res

    def _act_join(self, req):
        if self.engine is not None:
            # reconnect of a known player is fine; new players can't join mid-game
            if req.player_id in self.engine.players:
                return {'joined': req.player_id, 'rejoined': True,
                        'players': len(self.engine.players)}
            raise RuleError('game already running')
        name = json.loads(req.data_json or '{}').get('name', req.player_id)
        if any(pid == req.player_id for pid, _ in self.lobby):
            return {'joined': req.player_id, 'rejoined': True,
                    'players': len(self.lobby)}
        self.lobby.append((req.player_id, name))
        return {'joined': req.player_id, 'players': len(self.lobby)}

    def _act_start(self, req):
        if self.engine is not None:
            raise RuleError('game already running')
        data = json.loads(req.data_json or '{}')
        mafia_count = int(data.get('mafia_count', max(1, len(self.lobby) // 4)))
        self.engine = MafiaEngine(self.lobby, mafia_count=mafia_count)
        self.engine.start()
        return {'started': True, 'players': len(self.lobby),
                'mafia_count': mafia_count}

    def _need_engine(self) -> MafiaEngine:
        if self.engine is None:
            raise RuleError('no game running')
        return self.engine

    def _act_kill(self, req):
        self._need_engine().mafia_kill(req.player_id, req.target_id)

    def _act_protect(self, req):
        self._need_engine().doctor_protect(req.player_id, req.target_id)

    def _act_ask(self, req):
        is_mafia = self._need_engine().detective_ask(req.player_id, req.target_id)
        return {'target': req.target_id, 'is_mafia': is_mafia}

    def _act_begin_vote(self, req):
        self._need_engine().begin_vote()

    def _act_vote(self, req):
        self._need_engine().cast_vote(req.player_id, req.target_id)

    def _act_skip(self, req):
        eng = self._need_engine()
        if eng.phase is Phase.NIGHT_DOCTOR:
            eng.skip_doctor()
        elif eng.phase is Phase.NIGHT_DETECTIVE:
            eng.skip_detective()
        else:
            raise RuleError('nothing to skip in this phase')

    def _act_reset(self, req):
        self.engine = None
        self.lobby = []
        self._emitted = 0
        return {'reset': True}


def main(args=None):
    rclpy.init(args=args)
    node = GameMasterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
