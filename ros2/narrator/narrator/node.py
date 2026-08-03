"""narrator — the referee's voice.

Subscribes to /game/events, renders each public event into Arabic or
English (phrases.py), optionally asks a local Ollama model to punch the
line up, then speaks it with espeak-ng. Every spoken line is also
published on /narrator/utterances so screens can subtitle it.

Parameters
  language     'ar' | 'en'          (default 'ar')
  use_llm      bool                 rewrite lines via local Ollama (default False)
  ollama_url   str                  default http://127.0.0.1:11434
  ollama_model str                  default 'qwen2.5:3b'
  tts          'espeak' | 'off'     (default 'espeak')
"""

import json
import queue
import shutil
import subprocess
import threading
import urllib.request

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from elmowafi_msgs.msg import GameEvent

from narrator.phrases import render


class NarratorNode(Node):
    def __init__(self):
        super().__init__('narrator')
        self.declare_parameter('language', 'ar')
        self.declare_parameter('use_llm', False)
        self.declare_parameter('ollama_url', 'http://127.0.0.1:11434')
        self.declare_parameter('ollama_model', 'qwen2.5:3b')
        self.declare_parameter('tts', 'espeak')

        self.names: dict[str, str] = {}
        self.utter_pub = self.create_publisher(String, '/narrator/utterances', 10)
        self.create_subscription(GameEvent, '/game/events', self.on_event, 50)

        self._speech_q: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._speaker_loop, daemon=True).start()
        self.get_logger().info('narrator ready')

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
            if mode != 'espeak' or shutil.which('espeak-ng') is None:
                continue
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
