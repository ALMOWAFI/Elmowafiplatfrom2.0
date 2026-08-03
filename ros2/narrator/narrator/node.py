"""narrator — the referee's voice.

Subscribes to /game/events, renders each public event into Arabic or
English (phrases.py), optionally asks a local Ollama model to punch the
line up, then speaks it. Every spoken line is also published on
/narrator/utterances so screens can subtitle it.

TTS engines:
  piper   (default) neural voices via the `piper` CLI + aplay.
          ar_JO-kareem-medium for Arabic, en_US-lessac-medium for
          English by default (paths are parameters, swap for better
          voices freely — e.g. an Egyptian-dialect voice if one shows
          up in rhasspy/piper-voices later).
  espeak  formant synthesis fallback (always available via apt,
          noticeably more robotic — kept for environments without
          piper installed or as a sanity-check baseline).
  off     no audio, /narrator/utterances still published.

Parameters
  language      'ar' | 'en'          (default 'ar')
  use_llm       bool                 rewrite lines via local Ollama (default False)
  ollama_url    str                  default http://127.0.0.1:11434
  ollama_model  str                  default 'qwen2.5:3b'
  tts           'piper' | 'espeak' | 'off'   (default 'piper')
  piper_bin     str                  path to the piper executable
  ar_voice_model / en_voice_model    str, path to a piper .onnx voice
  player_bin    str                  'paplay' (PulseAudio, needed under WSLg)
                                      or 'aplay' (plain ALSA) — default 'paplay'
"""

import json
import queue
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from elmowafi_msgs.msg import GameEvent

from narrator.phrases import render

DEFAULT_MODELS = Path.home() / 'models/piper'


class NarratorNode(Node):
    def __init__(self):
        super().__init__('narrator')
        self.declare_parameter('language', 'ar')
        self.declare_parameter('use_llm', False)
        self.declare_parameter('ollama_url', 'http://127.0.0.1:11434')
        self.declare_parameter('ollama_model', 'qwen2.5:3b')
        self.declare_parameter('tts', 'piper')
        self.declare_parameter('piper_bin',
                               str(Path.home() / '.local/bin/piper'))
        self.declare_parameter('ar_voice_model',
                               str(DEFAULT_MODELS / 'ar_JO-kareem-medium.onnx'))
        self.declare_parameter('en_voice_model',
                               str(DEFAULT_MODELS / 'en_US-lessac-medium.onnx'))
        self.declare_parameter('player_bin', 'paplay')

        self.names: dict[str, str] = {}
        self.utter_pub = self.create_publisher(String, '/narrator/utterances', 10)
        self.create_subscription(GameEvent, '/game/events', self.on_event, 50)

        self._piper_rates: dict[str, int] = {}
        self._speech_q: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._speaker_loop, daemon=True).start()
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

    def _flavor(self, line: str, lang: str) -> str:
        url = str(self.get_parameter('ollama_url').value)
        model = str(self.get_parameter('ollama_model').value)
        lang_name = 'Egyptian Arabic' if lang == 'ar' else 'English'
        prompt = (f'You are a dramatic mafia-game narrator. Rewrite this line '
                  f'in {lang_name}, keep it under 25 words, keep all names '
                  f'exactly as written, no explanations:\n{line}')
        body = json.dumps({'model': model, 'prompt': prompt,
                           'stream': False,
                           'options': {'temperature': 0.9,
                                       'num_predict': 60}}).encode()
        try:
            req = urllib.request.Request(f'{url}/api/generate', body,
                                         {'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=6) as r:
                text = json.loads(r.read()).get('response', '').strip()
            return text or line
        except Exception as e:  # noqa: BLE001 — any LLM failure -> template
            self.get_logger().warning(
                f'llm flavor failed ({e}); using template',
                throttle_duration_sec=30)
            return line

    # ---------- speech ----------

    def _speaker_loop(self):
        while True:
            line = self._speech_q.get()
            mode = str(self.get_parameter('tts').value)
            if mode == 'piper':
                self._speak_piper(line)
            elif mode == 'espeak':
                self._speak_espeak(line)
            # mode == 'off': utterance already published, nothing to do

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
