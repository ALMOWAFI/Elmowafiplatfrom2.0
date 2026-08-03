import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { useLanguage } from '@/context/LanguageContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';

// ---- protocol types (mirror web_bridge) ----
type GameState = {
  phase: string; round: number; alive_ids: string[];
  winner: string; names: Record<string, string>; host: string;
};
type WsMsg =
  | ({ type: 'state' } & GameState)
  | { type: 'role'; role: string; partners?: string[] }
  | { type: 'event'; event: string; data: Record<string, unknown> };

const pidKey = 'mafia_pid';
const getPid = () => {
  let pid = sessionStorage.getItem(pidKey);
  if (!pid) {
    pid = 'p_' + Math.random().toString(36).slice(2, 8);
    sessionStorage.setItem(pidKey, pid);
  }
  return pid;
};

const L = {
  en: {
    title: 'Mafia Night', join: 'Join the game', name: 'Your name', enter: 'Join',
    lobby: 'Waiting for players…', you: 'you', start: 'Start game',
    needMore: (n: number) => `Need ${n} more to start`, mafiaN: (n: number) => `Mafia: ${n}`,
    dead: '☠️ You are out — watch quietly', win: 'You win! 🎉', lose: 'You lose 😢',
    roles: {
      mafia: ['🔪', 'Mafia', 'Stay hidden. Partners:'],
      doctor: ['🩺', 'Doctor', 'Each night, protect one person'],
      detective: ['🕵️', 'Detective', 'Each night, ask about one person'],
      civilian: ['👤', 'Civilian', 'Find the mafia'],
    } as Record<string, [string, string, string]>,
    phases: {
      night_mafia: ['🌙 Mafia is choosing…', 'Eyes closed unless you are mafia'],
      night_doctor: ['🌙 Doctor is working…', 'Eyes closed unless you are the doctor'],
      night_detective: ['🌙 Detective is asking…', 'Eyes closed unless you are the detective'],
      day_discussion: ['☀️ Discussion', 'Accuse, debate, then vote'],
      day_vote: ['🗳️ Voting', 'Pick your suspect'],
      game_over: ['🏁 Game over', ''],
    } as Record<string, [string, string]>,
    act: { kill: 'Assassinate', protect: 'Protect', ask: 'Ask', vote: 'Vote', beginVote: 'Start the vote' },
  },
  ar: {
    title: 'ليلة المافيا', join: 'انضم للعبة', name: 'اسمك', enter: 'دخول',
    lobby: 'في انتظار اللاعبين…', you: 'أنت', start: 'ابدأ اللعبة',
    needMore: (n: number) => `محتاجين ${n} كمان للبدء`, mafiaN: (n: number) => `المافيا: ${n}`,
    dead: '☠️ خرجت من اللعبة — تابع بصمت', win: 'فزت! 🎉', lose: 'خسرت 😢',
    roles: {
      mafia: ['🔪', 'مافيا', 'لا تكشف نفسك. شركاؤك:'],
      doctor: ['🩺', 'الدكتور', 'كل ليلة تحمي شخصًا واحدًا'],
      detective: ['🕵️', 'الشايب', 'كل ليلة تسأل عن شخص'],
      civilian: ['👤', 'مواطن', 'اكتشف المافيا'],
    } as Record<string, [string, string, string]>,
    phases: {
      night_mafia: ['🌙 المافيا تختار…', 'أغمض عينيك إن لم تكن مافيا'],
      night_doctor: ['🌙 الدكتور يعالج…', 'أغمض عينيك إن لم تكن الدكتور'],
      night_detective: ['🌙 الشايب يسأل…', 'أغمض عينيك إن لم تكن الشايب'],
      day_discussion: ['☀️ وقت النقاش', 'اتهموا وناقشوا ثم صوّتوا'],
      day_vote: ['🗳️ التصويت', 'اختر من تتهمه'],
      game_over: ['🏁 انتهت اللعبة', ''],
    } as Record<string, [string, string]>,
    act: { kill: 'اغتيال', protect: 'حماية', ask: 'اسأل عنه', vote: 'صوّت', beginVote: 'ابدأ التصويت' },
  },
};

function eventText(lang: 'en' | 'ar', ev: string, d: Record<string, unknown>,
                   name: (p: string) => string): string {
  const roleName = (r: string) => L[lang].roles[r]?.[1] ?? r;
  const m: Record<string, () => string> = lang === 'ar' ? {
    night_begins: () => `🌙 الليلة ${d.round} بدأت — الكل ينام`,
    day_begins: () => d.death ? `☀️ صباح الخير… ${name(String(d.death))} قُتل الليلة 💀`
      : d.saved ? '☀️ الدكتور أنقذ الضحية! 🩺' : '☀️ صباح الخير — لا ضحايا',
    player_eliminated: () => `⚖️ تم إعدام ${name(String(d.player))} — كان ${roleName(String(d.role))}`,
    no_elimination: () => '⚖️ تعادل — لا إعدام اليوم',
    vote_tied: () => d.revote ? '🔁 تعادل! إعادة التصويت' : '',
    vote_begins: () => '🗳️ بدأ التصويت',
    game_over: () => d.winner === 'mafia' ? '🔪 المافيا فازت!' : '🎉 المواطنون فازوا!',
    peek_callout: () => `🚨 ${name(String(d.player))} فتح عينه وهو نايم! عيب يا معلم!`,
    detective_answer: () => d.is_mafia ? `🕵️ نعم — ${name(String(d.target))} مافيا!`
      : `🕵️ لا — ${name(String(d.target))} بريء`,
  } : {
    night_begins: () => `🌙 Night ${d.round} — everyone sleeps`,
    day_begins: () => d.death ? `☀️ Morning… ${name(String(d.death))} was killed 💀`
      : d.saved ? '☀️ The doctor saved the victim! 🩺' : '☀️ Morning — nobody died',
    player_eliminated: () => `⚖️ ${name(String(d.player))} voted out — was ${roleName(String(d.role))}`,
    no_elimination: () => '⚖️ Tie — nobody eliminated',
    vote_tied: () => d.revote ? '🔁 Tie! Revote' : '',
    vote_begins: () => '🗳️ Voting started',
    game_over: () => d.winner === 'mafia' ? '🔪 Mafia wins!' : '🎉 Civilians win!',
    peek_callout: () => `🚨 ${name(String(d.player))} peeked during the night! Busted!`,
    detective_answer: () => d.is_mafia ? `🕵️ Yes — ${name(String(d.target))} is mafia!`
      : `🕵️ No — ${name(String(d.target))} is innocent`,
  };
  return m[ev]?.() ?? '';
}

const MafiaGamePage: React.FC = () => {
  const { language } = useLanguage();
  const lang = language === 'ar' ? 'ar' : 'en';
  const t = L[lang];
  const pid = useRef(getPid()).current;

  const [state, setState] = useState<GameState>({
    phase: 'lobby', round: 0, alive_ids: [], winner: '', names: {}, host: '',
  });
  const [role, setRole] = useState<string | null>(null);
  const [partners, setPartners] = useState<string[]>([]);
  const [revealed, setRevealed] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [nameInput, setNameInput] = useState('');
  const [mafiaCount, setMafiaCount] = useState(1);
  const [log, setLog] = useState<{ text: string; hot: boolean }[]>([]);
  const [banner, setBanner] = useState('');
  const bannerTimer = useRef<ReturnType<typeof setTimeout>>();

  const pname = useCallback(
    (p: string) => state.names[p] ?? p, [state.names]);

  const showBanner = useCallback((text: string, ms: number) => {
    setBanner(text);
    clearTimeout(bannerTimer.current);
    bannerTimer.current = setTimeout(() => setBanner(''), ms);
  }, []);

  // websocket with auto-reconnect
  useEffect(() => {
    let ws: WebSocket; let alive = true;
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      ws = new WebSocket(`${proto}://${location.host}/ws/${pid}`);
      ws.onmessage = (e) => {
        const msg: WsMsg = JSON.parse(e.data);
        if (msg.type === 'state') {
          const { type: _t, ...rest } = msg;
          setState((s) => ({ ...s, ...rest }));
          setSelected(null);
        } else if (msg.type === 'role') {
          setRole(msg.role);
          setPartners(msg.partners ?? []);
          setRevealed(false);
        } else if (msg.type === 'event') {
          setState((s) => {
            const text = eventText(lang, msg.event, msg.data,
              (p) => s.names[p] ?? p);
            if (text) {
              setLog((l) => [{ text, hot: msg.event === 'peek_callout' }, ...l].slice(0, 40));
              if (msg.event === 'peek_callout') showBanner(text, 4000);
              if (msg.event === 'detective_answer') showBanner(text, 6000);
            }
            return s;
          });
        }
      };
      ws.onclose = () => { if (alive) setTimeout(connect, 1500); };
    };
    connect();
    return () => { alive = false; ws?.close(); };
  }, [pid, lang, showBanner]);

  const api = useCallback(async (action_type: string, target_id = '',
                                 data: unknown = null) => {
    const r = await fetch('/api/action', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player_id: pid, action_type, target_id, data }),
    });
    const out = await r.json();
    if (!out.accepted && out.message) showBanner('⚠️ ' + out.message, 2500);
    return out;
  }, [pid, showBanner]);

  const joined = pid in state.names;
  const isHost = state.host === pid;
  const amAlive = state.alive_ids.includes(pid);
  const inLobby = state.phase === 'lobby';
  const playerCount = Object.keys(state.names).length;
  const others = state.alive_ids.filter((p) => p !== pid);

  const targetList = (candidates: string[], label: string, action: string) => (
    <div className="space-y-2 mt-4">
      {candidates.map((p) => (
        <button key={p}
          onClick={() => setSelected(p)}
          className={`w-full flex items-center justify-between rounded-xl border px-4 py-3 text-start transition
            ${selected === p ? 'border-primary bg-primary/10' : 'border-border bg-card hover:bg-accent'}`}>
          <span>{pname(p)}</span>
          {selected === p && <Badge>{label}</Badge>}
        </button>
      ))}
      <Button className="w-full" size="lg" disabled={!selected}
        onClick={() => selected && api(action, selected)}>
        {label}
      </Button>
    </div>
  );

  let phaseBody: React.ReactNode = null;
  if (!inLobby) {
    if (!amAlive && state.phase !== 'game_over') {
      phaseBody = <p className="text-muted-foreground text-center mt-4">{t.dead}</p>;
    } else {
      switch (state.phase) {
        case 'night_mafia':
          phaseBody = role === 'mafia'
            ? targetList(others.filter((p) => !partners.includes(p)), t.act.kill, 'kill')
            : null;
          break;
        case 'night_doctor':
          phaseBody = role === 'doctor'
            ? targetList(state.alive_ids, t.act.protect, 'protect') : null;
          break;
        case 'night_detective':
          phaseBody = role === 'detective'
            ? targetList(others, t.act.ask, 'ask') : null;
          break;
        case 'day_discussion':
          phaseBody = (
            <Button className="w-full mt-4" size="lg" onClick={() => api('begin_vote')}>
              {t.act.beginVote}
            </Button>);
          break;
        case 'day_vote':
          phaseBody = targetList(others, t.act.vote, 'vote');
          break;
        case 'game_over': {
          const iWon = (state.winner === 'mafia') === (role === 'mafia');
          phaseBody = (
            <p className="text-2xl font-bold text-center mt-4">
              {iWon ? t.win : t.lose}
            </p>);
          break;
        }
      }
    }
  }

  const phase = t.phases[state.phase] ?? ['', ''];

  return (
    <div dir={lang === 'ar' ? 'rtl' : 'ltr'}
         className="min-h-screen bg-background py-6 px-4">
      <div className="mx-auto w-full max-w-md space-y-4">
        <h1 className="text-2xl font-bold text-center">🎭 {t.title}</h1>

        {banner && (
          <motion.div initial={{ y: -12, opacity: 0 }} animate={{ y: 0, opacity: 1 }}
            className="rounded-xl bg-amber-500/15 border border-amber-500/40 px-4 py-3 text-center font-semibold">
            {banner}
          </motion.div>
        )}

        {inLobby && !joined && (
          <Card>
            <CardHeader><CardTitle className="text-center">{t.join}</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <Input value={nameInput} maxLength={20} placeholder={t.name}
                onChange={(e) => setNameInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && nameInput.trim()
                  && api('join', '', { name: nameInput.trim() })} />
              <Button className="w-full" size="lg" disabled={!nameInput.trim()}
                onClick={() => api('join', '', { name: nameInput.trim() })}>
                {t.enter}
              </Button>
            </CardContent>
          </Card>
        )}

        {inLobby && joined && (
          <Card>
            <CardHeader><CardTitle className="text-center">{t.lobby}</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {Object.entries(state.names).map(([p, n]) => (
                <div key={p} className="rounded-xl border border-border bg-card px-4 py-3 flex justify-between">
                  <span>{p === state.host ? '⭐ ' : ''}{n}</span>
                  {p === pid && <Badge variant="secondary">{t.you}</Badge>}
                </div>
              ))}
              {isHost && (
                <div className="pt-2 space-y-2">
                  {playerCount >= 4 && (
                    <select value={mafiaCount}
                      onChange={(e) => setMafiaCount(Number(e.target.value))}
                      className="w-full rounded-xl border border-border bg-card px-4 py-3">
                      {Array.from({ length: Math.max(1, playerCount - 3) }, (_, i) => i + 1)
                        .map((n) => <option key={n} value={n}>{t.mafiaN(n)}</option>)}
                    </select>
                  )}
                  <Button className="w-full" size="lg" disabled={playerCount < 4}
                    onClick={() => api('start', '', { mafia_count: mafiaCount })}>
                    {playerCount >= 4 ? t.start : t.needMore(4 - playerCount)}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {!inLobby && role && (
          <motion.div layout onClick={() => setRevealed(!revealed)}>
            <Card className="cursor-pointer select-none">
              <CardContent className="py-6 text-center">
                {revealed ? (
                  <>
                    <div className="text-5xl">{t.roles[role]?.[0]}</div>
                    <div className="text-2xl font-extrabold mt-1">{t.roles[role]?.[1]}</div>
                    <div className="text-sm text-muted-foreground mt-1">
                      {t.roles[role]?.[2]}
                      {role === 'mafia' && partners.length > 0 &&
                        ' ' + partners.map(pname).join('، ')}
                    </div>
                  </>
                ) : (
                  <div className="text-4xl">🂠</div>
                )}
              </CardContent>
            </Card>
          </motion.div>
        )}

        {!inLobby && (
          <Card>
            <CardContent className="py-5">
              <div className="text-xl font-bold text-center">{phase[0]}</div>
              {phase[1] && (
                <div className="text-sm text-muted-foreground text-center mt-1">{phase[1]}</div>
              )}
              {phaseBody}
            </CardContent>
          </Card>
        )}

        {log.length > 0 && (
          <Card>
            <CardContent className="py-4 max-h-44 overflow-y-auto space-y-1.5">
              {log.map((l, i) => (
                <div key={i} className={`text-sm ${l.hot ? 'text-amber-500 font-bold' : 'text-muted-foreground'}`}>
                  {l.text}
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
};

export default MafiaGamePage;
