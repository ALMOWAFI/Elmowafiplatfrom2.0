"""narrator — the referee's voice.

Subscribes to /game/events, renders each public event into Arabic or
English (phrases.py), optionally asks a local Ollama model to punch the
line up, then speaks it. Every spoken line is also published on
/narrator/utterances so screens can subtitle it.

TTS engines:
  piper       (default) neural voices via the `piper` CLI + paplay/aplay.
              ar_JO-kareem-medium for Arabic, en_US-lessac-medium for
              English by default (paths are parameters, swap for better
              voices freely — e.g. an Egyptian-dialect voice if one shows
              up in rhasspy/piper-voices later).
  elevenlabs  cloud TTS, noticeably better voice quality, needs internet
              and an API key (env var ELEVENLABS_API_KEY — deliberately
              NOT a ROS parameter, so it never shows up in `ros2 param
              list` or launch logs). Falls back to piper automatically
              on any failure: no key set, no internet, quota exceeded,
              timeout, bad response. Free-tier ElevenLabs accounts get
              10,000 characters/month — plenty for actual game nights
              (a full game is roughly 500-3000 characters) but don't
              leave this on as the default for casual dev/test loops;
              use piper or none for that and switch to elevenlabs for
              the real thing.
  espeak      formant synthesis fallback (always available via apt,
              noticeably more robotic — kept for environments without
              piper installed or as a sanity-check baseline).
  none        no audio, /narrator/utterances still published. (Deliberately
              not called "off" — that's a reserved YAML 1.1 boolean literal,
              so `tts:=off` on a `ros2 launch` command line silently becomes
              the boolean False instead of the string "off" and crashes the
              node with a type error. "none" isn't a YAML keyword.)

Parameters
  language        'ar' | 'en'          (default 'ar')
  use_llm         bool                 rewrite lines via local Ollama (default False)
  ollama_url      str                  default http://127.0.0.1:11434
  ollama_model    str                  default 'qwen2.5:3b'
  ollama_timeout_s double              default 12.0 (measured warm ~3.3s,
                                        cold-load ~13.6s on this dev box;
                                        node warms the model at startup so
                                        real gameplay should see the warm
                                        number, not the cold one)
  tts                   'piper' | 'elevenlabs' | 'espeak' | 'none'   (default 'piper')
  piper_bin             str            path to the piper executable
  ar_voice_model / en_voice_model      str, path to a piper .onnx voice
  player_bin            str            'paplay' (PulseAudio, needed under WSLg)
                                        or 'aplay' (plain ALSA) — default 'paplay'
  elevenlabs_voice_id   str            default 'JBFqnCBsd6RMkjVDRZzb'
                                        ("George — Warm, Captivating
                                        Storyteller"; fits a dramatic
                                        game host. All voices on a fresh
                                        account are English-labeled, but
                                        the multilingual model speaks
                                        Arabic through any of them.)
  elevenlabs_model_id   str            default 'eleven_multilingual_v2'
  elevenlabs_timeout_s  double         default 15.0
  mpg123_bin            str            default 'mpg123' (decodes the
                                        MP3 ElevenLabs returns; piped
                                        into player_bin rather than
                                        trusting mpg123's own audio
                                        backend, which was unreliable
                                        under WSLg during testing)
"""

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from elmowafi_msgs.msg import GameEvent

from narrator.phrases import render

DEFAULT_MODELS = Path.home() / 'models/piper'

# Observed failure modes from a real qwen2.5:3b run (2026-08-03): a stray
# U+FFFD replacement char, and Arabic/Latin scripts glued together with no
# space ("thenmafia" written as one token). Names embedded in a template
# on purpose ("hey Ali!") are fine because they're space-separated; only
# the glued-with-no-space case indicates a broken generation.
_MOJIBAKE_RE = re.compile('�')
_GLUED_SCRIPT_RE = re.compile(r'[؀-ۿ][A-Za-z]|[A-Za-z][؀-ۿ]')


def _looks_broken(text: str) -> bool:
    return bool(_MOJIBAKE_RE.search(text) or _GLUED_SCRIPT_RE.search(text))


class NarratorNode(Node):
    def __init__(self):
        super().__init__('narrator')
        self.declare_parameter('language', 'ar')
        self.declare_parameter('use_llm', False)
        self.declare_parameter('ollama_url', 'http://127.0.0.1:11434')
        self.declare_parameter('ollama_model', 'qwen2.5:3b')
        self.declare_parameter('ollama_timeout_s', 12.0)
        self.declare_parameter('tts', 'piper')
        self.declare_parameter('piper_bin',
                               str(Path.home() / '.local/bin/piper'))
        self.declare_parameter('ar_voice_model',
                               str(DEFAULT_MODELS / 'ar_JO-kareem-medium.onnx'))
        self.declare_parameter('en_voice_model',
                               str(DEFAULT_MODELS / 'en_US-lessac-medium.onnx'))
        self.declare_parameter('player_bin', 'paplay')
        self.declare_parameter('elevenlabs_voice_id', 'JBFqnCBsd6RMkjVDRZzb')
        self.declare_parameter('elevenlabs_model_id', 'eleven_multilingual_v2')
        self.declare_parameter('elevenlabs_timeout_s', 15.0)
        self.declare_parameter('mpg123_bin', 'mpg123')

        self.names: dict[str, str] = {}
        self.utter_pub = self.create_publisher(String, '/narrator/utterances', 10)
        self.create_subscription(GameEvent, '/game/events', self.on_event, 50)

        self._piper_rates: dict[str, int] = {}
        self._speech_q: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._speaker_loop, daemon=True).start()

        if bool(self.get_parameter('use_llm').value):
            threading.Thread(target=self._warm_up_llm, daemon=True).start()

        self.get_logger().info(
            f"narrator ready (tts={self.get_parameter('tts').value})")

    # ---------- events ----------

    def on_event(self, msg: GameEvent):
        data = json.loads(msg.data_json) if msg.data_json else {}
        if msg.type == 'roles_assigned':
            self.names.update(data.get('names', {}))
            return
        lang = str(self.get_parameter('language').value)
        line = render(msg.type, data, self.names, lang)
        if not line:
            return
        if bool(self.get_parameter('use_llm').value):
            line = self._flavor(line, lang)
        out = String()
        out.data = line
        self.utter_pub.publish(out)
        self.get_logger().info(f'🗣 {line}')
        self._speech_q.put(line)

    # ---------- optional LLM flavor ----------

    def _warm_up_llm(self):
        """Load the model into Ollama's memory at startup (~13s cold on
        this dev box) so the first real narration line doesn't eat that
        cost mid-game."""
        try:
            self._ollama_generate('hi', timeout=30.0)
            self.get_logger().info('LLM flavor model warmed up')
        except Exception as e:  # noqa: BLE001
            self.get_logger().warning(f'LLM warm-up failed: {e}')

    def _ollama_generate(self, prompt: str, timeout: float) -> str:
        url = str(self.get_parameter('ollama_url').value)
        model = str(self.get_parameter('ollama_model').value)
        body = json.dumps({'model': model, 'prompt': prompt,
                           'stream': False,
                           'options': {'temperature': 0.6,
                                       'num_predict': 60}}).encode()
        req = urllib.request.Request(f'{url}/api/generate', body,
                                     {'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()).get('response', '').strip()

    def _flavor(self, line: str, lang: str) -> str:
        lang_name = 'Egyptian Arabic' if lang == 'ar' else 'English'
        prompt = (f'You are a dramatic mafia-game narrator. Rewrite this line '
                  f'in {lang_name} only — do not mix in English words or '
                  f'switch scripts mid-word. Keep it under 25 words, keep '
                  f'all names exactly as written, no explanations:\n{line}')
        timeout = float(self.get_parameter('ollama_timeout_s').value)
        try:
            text = self._ollama_generate(prompt, timeout=timeout)
        except Exception as e:  # noqa: BLE001 — any LLM failure -> template
            self.get_logger().warning(
                f'llm flavor failed ({e}); using template',
                throttle_duration_sec=30)
            return line
        if not text or _looks_broken(text):
            self.get_logger().warning(
                f'llm flavor output looked broken ({text!r}); using template',
                throttle_duration_sec=30)
            return line
        return text

    # ---------- speech ----------

    def _speaker_loop(self):
        while True:
            line = self._speech_q.get()
            mode = str(self.get_parameter('tts').value)
            if mode == 'piper':
                self._speak_piper(line)
            elif mode == 'elevenlabs':
                self._speak_elevenlabs(line)
            elif mode == 'espeak':
                self._speak_espeak(line)
            # mode == 'none' (or anything else): utterance already
            # published on /narrator/utterances, nothing more to do

    def _voice_model(self, lang: str) -> Path:
        key = 'ar_voice_model' if lang == 'ar' else 'en_voice_model'
        return Path(str(self.get_parameter(key).value))

    def _sample_rate(self, model: Path) -> int:
        cached = self._piper_rates.get(str(model))
        if cached is not None:
            return cached
        try:
            cfg = json.loads(Path(str(model) + '.json').read_text())
            rate = int(cfg['audio']['sample_rate'])
        except Exception:  # noqa: BLE001
            rate = 22050  # standard piper default
        self._piper_rates[str(model)] = rate
        return rate

    def _speak_piper(self, line: str):
        piper_bin = str(self.get_parameter('piper_bin').value)
        lang = str(self.get_parameter('language').value)
        model = self._voice_model(lang)
        player_bin = str(self.get_parameter('player_bin').value)

        if not Path(piper_bin).is_file() and shutil.which(piper_bin) is None:
            self.get_logger().warning(f'piper binary not found: {piper_bin}',
                                      throttle_duration_sec=30)
            return
        if not model.exists():
            self.get_logger().warning(f'voice model not found: {model}',
                                      throttle_duration_sec=30)
            return
        if shutil.which(player_bin) is None:
            self.get_logger().warning(f'audio player not found: {player_bin}',
                                      throttle_duration_sec=30)
            return

        try:
            synth = subprocess.run(
                [piper_bin, '-m', str(model), '--output-raw'],
                input=line.encode('utf-8'), capture_output=True, timeout=30)
            if synth.returncode != 0 or not synth.stdout:
                self.get_logger().warning(
                    f'piper synth failed: {synth.stderr[:200]!r}',
                    throttle_duration_sec=30)
                return
            rate = self._sample_rate(model)
            subprocess.run(self._player_args(player_bin, rate),
                           input=synth.stdout, timeout=30)
        except Exception as e:  # noqa: BLE001
            self.get_logger().warning(f'piper speak failed: {e}',
                                      throttle_duration_sec=30)

    @staticmethod
    def _player_args(player_bin: str, rate: int) -> list[str]:
        """Piper --output-raw is mono 16-bit signed little-endian PCM at
        the voice's native rate; paplay and aplay need it spelled out
        with different flag conventions, and the stream is on stdin."""
        name = Path(player_bin).name
        if name == 'paplay':
            return [player_bin, '--raw', f'--rate={rate}',
                   '--format=s16le', '--channels=1']
        return [player_bin, '-r', str(rate), '-f', 'S16_LE', '-t', 'raw',
               '-q', '-']

    def _speak_elevenlabs(self, line: str):
        api_key = os.environ.get('ELEVENLABS_API_KEY', '')
        if not api_key:
            self.get_logger().warning(
                'ELEVENLABS_API_KEY not set; falling back to piper',
                throttle_duration_sec=60)
            self._speak_piper(line)
            return

        voice_id = str(self.get_parameter('elevenlabs_voice_id').value)
        model_id = str(self.get_parameter('elevenlabs_model_id').value)
        timeout = float(self.get_parameter('elevenlabs_timeout_s').value)
        url = f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}'
        body = json.dumps({'text': line, 'model_id': model_id}).encode('utf-8')
        req = urllib.request.Request(
            url, body,
            {'xi-api-key': api_key, 'Content-Type': 'application/json',
             'Accept': 'audio/mpeg'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                mp3_bytes = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read()[:200] if hasattr(e, 'read') else b''
            self.get_logger().warning(
                f'elevenlabs http {e.code}: {detail!r}; falling back to piper',
                throttle_duration_sec=30)
            self._speak_piper(line)
            return
        except Exception as e:  # noqa: BLE001 — any failure -> piper
            self.get_logger().warning(
                f'elevenlabs request failed ({e}); falling back to piper',
                throttle_duration_sec=30)
            self._speak_piper(line)
            return

        if not self._play_mp3(mp3_bytes):
            self._speak_piper(line)

    def _play_mp3(self, mp3_bytes: bytes) -> bool:
        """Decode via mpg123 and play via player_bin, rather than trust
        mpg123's own audio backend (unreliable under WSLg in testing:
        it tried jack/ALSA and produced dozens of error lines even
        though it happened to still exit 0). Returns False on any
        failure so the caller can fall back."""
        mpg123_bin = str(self.get_parameter('mpg123_bin').value)
        player_bin = str(self.get_parameter('player_bin').value)
        if shutil.which(mpg123_bin) is None:
            self.get_logger().warning(f'mpg123 not found: {mpg123_bin}',
                                      throttle_duration_sec=30)
            return False
        if shutil.which(player_bin) is None:
            self.get_logger().warning(f'audio player not found: {player_bin}',
                                      throttle_duration_sec=30)
            return False
        try:
            decoded = subprocess.run(
                [mpg123_bin, '-q', '-s', '-'],
                input=mp3_bytes, capture_output=True, timeout=30)
            if decoded.returncode != 0 or not decoded.stdout:
                self.get_logger().warning(
                    f'mpg123 decode failed: {decoded.stderr[:200]!r}',
                    throttle_duration_sec=30)
                return False
            # ElevenLabs MP3 output observed at 44.1kHz mono (confirmed
            # via `file` on a real response, 2026-08-03); mpg123 decodes
            # at the source rate by default.
            subprocess.run(self._player_args(player_bin, 44100),
                           input=decoded.stdout, timeout=30)
            return True
        except Exception as e:  # noqa: BLE001
            self.get_logger().warning(f'mp3 playback failed: {e}',
                                      throttle_duration_sec=30)
            return False

    def _speak_espeak(self, line: str):
        if shutil.which('espeak-ng') is None:
            return
        voice = 'ar' if str(self.get_parameter('language').value) == 'ar' else 'en'
        try:
            subprocess.run(['espeak-ng', '-v', voice, '-s', '150', line],
                           timeout=30, capture_output=True)
        except Exception:  # noqa: BLE001
            pass


def main(args=None):
    rclpy.init(args=args)
    node = NarratorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
