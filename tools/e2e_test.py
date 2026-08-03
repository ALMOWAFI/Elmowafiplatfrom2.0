#!/usr/bin/env python3
"""End-to-end test: 5 simulated phones play a full mafia game through
web_bridge (HTTP actions + WebSocket events) against a live game_master.

Assumes both nodes are already running. Exits 0 on success.
"""

import asyncio
import json
import sys
import urllib.request

import websockets

BASE = 'http://127.0.0.1:8080'
WS = 'ws://127.0.0.1:8080/ws'

PLAYERS = {f'p{i}': n for i, n in
           enumerate(['Ali', 'Marwa', 'Omar', 'Sara', 'Hani'], 1)}


def api(player_id, action_type, target_id='', data=None):
    body = json.dumps({'player_id': player_id, 'action_type': action_type,
                       'target_id': target_id, 'data': data}).encode()
    req = urllib.request.Request(BASE + '/api/action', body,
                                 {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


class Phone:
    def __init__(self, pid):
        self.pid = pid
        self.role = None
        self.partners = []
        self.state = {}
        self.private = []          # private events received
        self.leaks = []            # secrecy violations observed
        self.ws = None
        self.task = None

    async def connect(self):
        self.ws = await websockets.connect(f'{WS}/{self.pid}')
        self.task = asyncio.create_task(self.listen())

    async def listen(self):
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if msg['type'] == 'state':
                    self.state = msg
                elif msg['type'] == 'role':
                    self.role = msg['role']
                    self.partners = msg.get('partners', [])
                elif msg['type'] == 'event':
                    data = msg.get('data', {})
                    if msg['event'] == 'detective_answer':
                        self.private.append(msg)
                        if self.role != 'detective':
                            self.leaks.append(('detective_answer', self.pid))
                    if msg['event'] == 'roles_assigned':
                        self.leaks.append(('raw_roles_broadcast', self.pid))
        except websockets.ConnectionClosed:
            pass


async def wait_for(cond, timeout=10.0, what=''):
    for _ in range(int(timeout / 0.1)):
        if cond():
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(f'timeout waiting for {what}')


async def main():
    api('p1', 'reset')
    phones = {pid: Phone(pid) for pid in PLAYERS}
    for pid, ph in phones.items():
        await ph.connect()
        r = api(pid, 'join', data={'name': PLAYERS[pid]})
        assert r['accepted'], f'join failed: {r}'

    r = api('p1', 'start', data={'mafia_count': 1})
    assert r['accepted'], f'start failed: {r}'
    await wait_for(lambda: all(p.role for p in phones.values()),
                   what='role delivery')

    roles = {pid: p.role for pid, p in phones.items()}
    print('roles:', roles)
    assert sorted(roles.values()).count('mafia') == 1
    mafia = next(p for p in phones.values() if p.role == 'mafia')
    doctor = next(p for p in phones.values() if p.role == 'doctor')
    detective = next(p for p in phones.values() if p.role == 'detective')

    rounds = 0
    while phones['p1'].state.get('phase') != 'game_over':
        rounds += 1
        assert rounds < 10, 'game did not converge'
        st = lambda: phones['p1'].state.get('phase')

        await wait_for(lambda: st() == 'night_mafia', what='night_mafia')
        victims = [pid for pid in phones['p1'].state['alive_ids']
                   if pid != mafia.pid]
        api(mafia.pid, 'kill', victims[0])

        await wait_for(lambda: st() in ('night_doctor', 'night_detective',
                                        'day_discussion', 'game_over'),
                       what='post-kill phase')
        if st() == 'night_doctor':
            if doctor.pid in phones['p1'].state['alive_ids']:
                api(doctor.pid, 'protect', doctor.pid)
            else:
                api('p1', 'skip')
        await wait_for(lambda: st() in ('night_detective', 'day_discussion',
                                        'game_over'), what='post-doctor phase')
        if st() == 'night_detective':
            if detective.pid in phones['p1'].state['alive_ids']:
                api(detective.pid, 'ask', mafia.pid)
            else:
                api('p1', 'skip')
        await wait_for(lambda: st() in ('day_discussion', 'game_over'),
                       what='day')
        if st() == 'game_over':
            break

        # everyone votes for a random-but-agreed civilian-side target
        alive = phones['p1'].state['alive_ids']
        target = next(pid for pid in alive
                      if pid != mafia.pid and phones[pid].role != 'detective')
        api('p1' if 'p1' in alive else alive[0], 'begin_vote')
        await wait_for(lambda: st() == 'day_vote', what='vote phase')
        for pid in list(phones['p1'].state['alive_ids']):
            api(pid, 'vote', target)
        await wait_for(lambda: st() in ('night_mafia', 'game_over'),
                       what='post-vote phase')

    winner = phones['p1'].state.get('winner')
    print('winner:', winner, 'after', rounds, 'rounds')
    assert winner == 'mafia', 'mafia should win this scripted game'

    # secrecy checks
    answers = [p for ph in phones.values() for p in ph.private]
    assert detective.private, 'detective never got an answer'
    leaks = [l for ph in phones.values() for l in ph.leaks]
    assert not leaks, f'SECRECY LEAKS: {leaks}'
    non_detective_answers = [ph.pid for ph in phones.values()
                             if ph.private and ph.role != 'detective']
    assert not non_detective_answers, f'answer leaked to {non_detective_answers}'

    for ph in phones.values():
        await ph.ws.close()
    print('E2E OK')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:  # noqa: BLE001
        print('E2E FAILED:', e)
        sys.exit(1)
