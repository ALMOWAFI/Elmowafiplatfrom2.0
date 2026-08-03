"""Unit tests for the piper TTS wiring — subprocess is mocked so these
run fast with no real audio hardware or model files, but they pin down
the exact CLI invocation (flag names, sample rate handling) so a typo
there fails CI instead of silently going mute at family night.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import rclpy

from narrator.node import NarratorNode, _looks_broken


@pytest.fixture
def node(tmp_path):
    rclpy.init()
    n = NarratorNode()
    yield n, tmp_path
    n.destroy_node()
    rclpy.shutdown()


def _model_with_config(tmp_path, rate=22050):
    model = tmp_path / 'voice.onnx'
    model.write_bytes(b'fake-onnx-bytes')
    cfg = tmp_path / 'voice.onnx.json'
    cfg.write_text(json.dumps({'audio': {'sample_rate': rate}}))
    return model


def test_sample_rate_parses_and_caches(node):
    n, tmp_path = node
    model = _model_with_config(tmp_path, rate=16000)
    assert n._sample_rate(model) == 16000
    # cache hit: delete the config, must still return cached value
    (tmp_path / 'voice.onnx.json').unlink()
    assert n._sample_rate(model) == 16000


def test_sample_rate_falls_back_when_config_missing(node):
    n, tmp_path = node
    model = tmp_path / 'nowhere.onnx'
    assert n._sample_rate(model) == 22050


def test_speak_piper_invokes_expected_cli_args(node):
    n, tmp_path = node
    model = _model_with_config(tmp_path, rate=22050)
    n.set_parameters([
        rclpy.parameter.Parameter('piper_bin', value=str(tmp_path / 'piper')),
        rclpy.parameter.Parameter('ar_voice_model', value=str(model)),
        rclpy.parameter.Parameter('language', value='ar'),
        rclpy.parameter.Parameter('player_bin', value='aplay'),
    ])
    (tmp_path / 'piper').write_text('#!/bin/sh\n')
    (tmp_path / 'piper').chmod(0o755)

    fake_audio = b'\x00\x01' * 100
    with patch('narrator.node.shutil.which', return_value='/usr/bin/aplay'), \
         patch('narrator.node.subprocess.run') as run:
        run.side_effect = [
            MagicMock(returncode=0, stdout=fake_audio, stderr=b''),
            MagicMock(returncode=0),
        ]
        n._speak_piper('يا Ali! عيب عليك!')

    assert run.call_count == 2
    synth_args = run.call_args_list[0].args[0]
    assert synth_args[0] == str(tmp_path / 'piper')
    assert '-m' in synth_args and str(model) in synth_args
    assert '--output-raw' in synth_args
    assert run.call_args_list[0].kwargs['input'] == 'يا Ali! عيب عليك!'.encode('utf-8')

    play_args = run.call_args_list[1].args[0]
    assert play_args[0] == 'aplay'
    assert '-r' in play_args and '22050' in play_args
    assert play_args[play_args.index('-r') + 1] == '22050'
    assert run.call_args_list[1].kwargs['input'] == fake_audio


def test_speak_piper_missing_model_does_not_call_subprocess(node):
    n, tmp_path = node
    (tmp_path / 'piper').write_text('#!/bin/sh\n')
    (tmp_path / 'piper').chmod(0o755)
    n.set_parameters([
        rclpy.parameter.Parameter('piper_bin', value=str(tmp_path / 'piper')),
        rclpy.parameter.Parameter('ar_voice_model',
                                  value=str(tmp_path / 'missing.onnx')),
        rclpy.parameter.Parameter('language', value='ar'),
    ])
    with patch('narrator.node.subprocess.run') as run:
        n._speak_piper('should not speak')
    run.assert_not_called()


def test_speak_piper_missing_binary_does_not_call_subprocess(node):
    n, tmp_path = node
    model = _model_with_config(tmp_path)
    n.set_parameters([
        rclpy.parameter.Parameter('piper_bin',
                                  value=str(tmp_path / 'nonexistent-piper')),
        rclpy.parameter.Parameter('ar_voice_model', value=str(model)),
        rclpy.parameter.Parameter('language', value='ar'),
    ])
    with patch('narrator.node.subprocess.run') as run:
        n._speak_piper('should not speak')
    run.assert_not_called()


def test_speak_piper_switches_english_model(node):
    n, tmp_path = node
    en_dir = tmp_path
    en_model = en_dir / 'en.onnx'
    en_model.write_bytes(b'x')
    (en_dir / 'en.onnx.json').write_text(json.dumps({'audio': {'sample_rate': 16000}}))
    piper_bin = tmp_path / 'piper'
    piper_bin.write_text('#!/bin/sh\n')
    piper_bin.chmod(0o755)

    n.set_parameters([
        rclpy.parameter.Parameter('piper_bin', value=str(piper_bin)),
        rclpy.parameter.Parameter('en_voice_model', value=str(en_model)),
        rclpy.parameter.Parameter('language', value='en'),
    ])
    with patch('narrator.node.shutil.which', return_value='/usr/bin/aplay'), \
         patch('narrator.node.subprocess.run') as run:
        run.side_effect = [
            MagicMock(returncode=0, stdout=b'\x00\x00', stderr=b''),
            MagicMock(returncode=0),
        ]
        n._speak_piper('Marwa is out')

    synth_args = run.call_args_list[0].args[0]
    assert str(en_model) in synth_args
    play_args = run.call_args_list[1].args[0]
    assert play_args[0] == 'paplay'  # default player_bin
    assert '--rate=16000' in play_args


def test_player_args_paplay_flags():
    args = NarratorNode._player_args('paplay', 22050)
    assert args == ['paplay', '--raw', '--rate=22050', '--format=s16le',
                    '--channels=1']


def test_player_args_aplay_flags():
    args = NarratorNode._player_args('/usr/bin/aplay', 16000)
    assert args == ['/usr/bin/aplay', '-r', '16000', '-f', 'S16_LE',
                    '-t', 'raw', '-q', '-']


# --- real failure modes observed from a live qwen2.5:3b run 2026-08-03 ---

def test_looks_broken_detects_replacement_char():
    assert _looks_broken('�ا غادرت، كانت عصابة يا حميم!')


def test_looks_broken_detects_glued_scripts():
    assert _looks_broken('اليوم الثاني، الجميع ينامون، ثمmafia يستيقظون بشدة.')
    assert _looks_broken('mafiaوصلت')  # glued the other direction too


def test_looks_broken_allows_spaced_names_in_arabic():
    assert not _looks_broken('يا Ali! عينك مفتوحة!')
    assert not _looks_broken('قررت العائلة إعدام Marwa. كان مافيا!')


def test_looks_broken_allows_clean_text():
    assert not _looks_broken('صباح الخير يا عائلة.')
    assert not _looks_broken('Good morning, family.')


def test_flavor_falls_back_when_output_looks_broken(node):
    n, tmp_path = node
    with patch.object(n, '_ollama_generate',
                      return_value='ثمmafia يستيقظون'):
        result = n._flavor('Night falls.', 'ar')
    assert result == 'Night falls.'  # template, not the broken LLM output


def test_flavor_uses_llm_output_when_clean(node):
    n, tmp_path = node
    with patch.object(n, '_ollama_generate', return_value='الليل يهبط.'):
        result = n._flavor('Night falls.', 'ar')
    assert result == 'الليل يهبط.'


def test_flavor_falls_back_on_timeout(node):
    n, tmp_path = node
    with patch.object(n, '_ollama_generate', side_effect=TimeoutError('slow')):
        result = n._flavor('Night falls.', 'ar')
    assert result == 'Night falls.'
