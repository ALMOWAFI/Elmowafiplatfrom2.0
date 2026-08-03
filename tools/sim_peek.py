#!/usr/bin/env python3
"""Live integration check for the CV -> callout -> narration loop.

Starts a 5-player game via /game/submit_action, then publishes a fake
/cv/eye_states frame where a civilian has eyes open during night_mafia.
Passes when game_master emits peek_callout naming that civilian AND the
narrator speaks a line containing the player's name.

Run with game_master + narrator already up:  python3 sim_peek.py
"""

import json
import sys
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from elmowafi_msgs.msg import EyeState, EyeStateArray, GameEvent
from elmowafi_msgs.srv import SubmitAction

PLAYERS = {f'p{i}': n for i, n in
           enumerate(['Ali', 'Marwa', 'Omar', 'Sara', 'Hani'], 1)}


class Sim(Node):
    def __init__(self):
        super().__init__('sim_peek')
        self.client = self.create_client(SubmitAction, '/game/submit_action')
        self.eye_pub = self.create_publisher(EyeStateArray, '/cv/eye_states', 10)
        self.callouts = []
        self.utterances = []
        self.roles = {}
        self.create_subscription(GameEvent, '/game/events', self.on_event, 50)
        self.create_subscription(String, '/narrator/utterances',
                                 lambda m: self.utterances.append(m.data), 50)

    def on_event(self, msg):
        data = json.loads(msg.data_json) if msg.data_json else {}
        if msg.type == 'peek_callout':
            self.callouts.append(data)
        if msg.type == 'roles_assigned':
            self.roles = data.get('roles', {})

    def act(self, pid, action, target='', data=None):
        req = SubmitAction.Request()
        req.player_id, req.action_type, req.target_id = pid, action, target
        req.data_json = json.dumps(data or {})
        fut = self.client.call_async(req)
        rclpy.spin_until_future_complete(self, fut, timeout_sec=5)
        res = fut.result()
        assert res is not None and res.accepted, f'{action} failed: {res and res.message}'
        return res


def main():
    rclpy.init()
    sim = Sim()
    assert sim.client.wait_for_service(timeout_sec=5), 'game_master not running'

    sim.act('p1', 'reset')
    for pid, name in PLAYERS.items():
        sim.act(pid, 'join', data={'name': name})
    sim.act('p1', 'start', data={'mafia_count': 1})

    t0 = time.time()
    while not sim.roles and time.time() - t0 < 5:
        rclpy.spin_once(sim, timeout_sec=0.1)
    civ = next(p for p, r in sim.roles.items() if r == 'civilian')
    print(f'game started; guilty civilian will be {civ} ({PLAYERS[civ]})')

    # fake camera: civilian peeking during night_mafia, twice in a row
    # (single frames shouldn't be enough for cv_referee smoothing, but
    #  game_master trusts the already-smoothed eyes_open flag)
    frame = EyeStateArray()
    st = EyeState()
    st.player_id = civ
    st.face_index = 0
    st.eyes_open = True
    st.confidence = 0.95
    frame.states.append(st)
    sim.eye_pub.publish(frame)

    def named_utterance():
        return any(PLAYERS[civ] in u for u in sim.utterances)

    t0 = time.time()
    while time.time() - t0 < 8 and not (sim.callouts and named_utterance()):
        rclpy.spin_once(sim, timeout_sec=0.1)

    assert sim.callouts, 'no peek_callout emitted'
    assert sim.callouts[0]['player'] == civ, f'wrong player: {sim.callouts[0]}'
    named = [u for u in sim.utterances if PLAYERS[civ] in u]
    assert named, f'narrator never named the cheater; got {sim.utterances}'
    print('callout:', sim.callouts[0])
    print('narration:', named[-1])

    # cooldown: immediate second frame must NOT produce a second callout
    sim.eye_pub.publish(frame)
    t0 = time.time()
    while time.time() - t0 < 2:
        rclpy.spin_once(sim, timeout_sec=0.1)
    assert len(sim.callouts) == 1, 'cooldown failed, duplicate callout'

    print('SIM PEEK OK')
    rclpy.shutdown()


if __name__ == '__main__':
    try:
        main()
    except AssertionError as e:
        print('SIM PEEK FAILED:', e)
        sys.exit(1)
