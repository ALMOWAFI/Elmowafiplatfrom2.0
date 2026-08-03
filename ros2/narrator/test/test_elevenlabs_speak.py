"""Unit tests for the ElevenLabs TTS wiring — network and subprocess
calls are mocked (no real API quota spent, no real audio hardware
needed), but they pin down the exact fallback behavior: every failure
mode must fall back to piper, never go silent or raise.
"""

import urllib.error
from unittest.mock import MagicMock, patch

import pytest
import rclpy


@pytest.fixture
def node(tmp_path, monkeypatch):
    monkeypatch.delenv('ELEVENLABS_API_KEY', raising=False)
    rclpy.init()
    from narrator.node import NarratorNode
    n = NarratorNode()
    yield n, tmp_path
    n.destroy_node()
    rclpy.shutdown()


def test_falls_back_to_piper_when_no_api_key(node, monkeypatch):
    n, _ = node
    monkeypatch.delenv('ELEVENLABS_API_KEY', raising=False)
    with patch.object(n, '_speak_piper') as piper, \
         patch('narrator.node.urllib.request.urlopen') as urlopen:
        n._speak_elevenlabs('hello')
    piper.assert_called_once_with('hello')
    urlopen.assert_not_called()  # never even tries the network without a key


def test_falls_back_to_piper_on_http_error(node, monkeypatch):
    n, _ = node
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'fake-key')
    err = urllib.error.HTTPError('url', 401, 'unauthorized', {}, None)
    err.read = lambda: b'{"detail": "invalid key"}'
    with patch.object(n, '_speak_piper') as piper, \
         patch('narrator.node.urllib.request.urlopen', side_effect=err):
        n._speak_elevenlabs('hello')
    piper.assert_called_once_with('hello')


def test_falls_back_to_piper_on_network_timeout(node, monkeypatch):
    n, _ = node
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'fake-key')
    with patch.object(n, '_speak_piper') as piper, \
         patch('narrator.node.urllib.request.urlopen',
               side_effect=TimeoutError('slow')):
        n._speak_elevenlabs('hello')
    piper.assert_called_once_with('hello')


def test_success_plays_mp3_and_does_not_fall_back(node, monkeypatch):
    n, _ = node
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'fake-key')
    resp = MagicMock()
    resp.read.return_value = b'\xff\xfbfake-mp3-bytes'
    resp.__enter__ = lambda self: resp
    resp.__exit__ = lambda self, *a: False
    with patch.object(n, '_speak_piper') as piper, \
         patch.object(n, '_play_mp3', return_value=True) as play, \
         patch('narrator.node.urllib.request.urlopen', return_value=resp):
        n._speak_elevenlabs('hello')
    play.assert_called_once_with(b'\xff\xfbfake-mp3-bytes')
    piper.assert_not_called()


def test_falls_back_to_piper_when_playback_fails(node, monkeypatch):
    n, _ = node
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'fake-key')
    resp = MagicMock()
    resp.read.return_value = b'\xff\xfbfake-mp3-bytes'
    resp.__enter__ = lambda self: resp
    resp.__exit__ = lambda self, *a: False
    with patch.object(n, '_speak_piper') as piper, \
         patch.object(n, '_play_mp3', return_value=False), \
         patch('narrator.node.urllib.request.urlopen', return_value=resp):
        n._speak_elevenlabs('hello')
    piper.assert_called_once_with('hello')


def test_request_uses_correct_endpoint_and_headers(node, monkeypatch):
    n, _ = node
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'secret-123')
    resp = MagicMock()
    resp.read.return_value = b'mp3data'
    resp.__enter__ = lambda self: resp
    resp.__exit__ = lambda self, *a: False
    with patch.object(n, '_play_mp3', return_value=True), \
         patch('narrator.node.urllib.request.urlopen',
               return_value=resp) as urlopen:
        n._speak_elevenlabs('يا Ali!')
    req = urlopen.call_args.args[0]
    assert req.full_url == 'https://api.elevenlabs.io/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb'
    assert req.get_header('Xi-api-key') == 'secret-123'
    assert req.get_header('Accept') == 'audio/mpeg'
    assert b'"model_id": "eleven_multilingual_v2"' in req.data


def test_play_mp3_missing_mpg123_returns_false(node):
    n, _ = node
    n.set_parameters([
        rclpy.parameter.Parameter('mpg123_bin', value='/no/such/mpg123'),
    ])
    with patch('narrator.node.subprocess.run') as run:
        assert n._play_mp3(b'mp3data') is False
    run.assert_not_called()


def test_play_mp3_decodes_then_plays_at_44100(node, tmp_path):
    n, _ = node
    mpg123 = tmp_path / 'mpg123'
    mpg123.write_text('#!/bin/sh\n')
    mpg123.chmod(0o755)
    n.set_parameters([
        rclpy.parameter.Parameter('mpg123_bin', value=str(mpg123)),
        rclpy.parameter.Parameter('player_bin', value='paplay'),
    ])
    decoded_pcm = b'\x00\x01' * 100
    with patch('narrator.node.shutil.which', return_value='/usr/bin/paplay'), \
         patch('narrator.node.subprocess.run') as run:
        run.side_effect = [
            MagicMock(returncode=0, stdout=decoded_pcm, stderr=b''),
            MagicMock(returncode=0),
        ]
        assert n._play_mp3(b'mp3-input-bytes') is True

    decode_args = run.call_args_list[0].args[0]
    assert decode_args[0] == str(mpg123)
    assert '-s' in decode_args
    assert run.call_args_list[0].kwargs['input'] == b'mp3-input-bytes'

    play_args = run.call_args_list[1].args[0]
    assert play_args[0] == 'paplay'
    assert '--rate=44100' in play_args
    assert run.call_args_list[1].kwargs['input'] == decoded_pcm


def test_play_mp3_decode_failure_returns_false(node, tmp_path):
    n, _ = node
    mpg123 = tmp_path / 'mpg123'
    mpg123.write_text('#!/bin/sh\n')
    mpg123.chmod(0o755)
    n.set_parameters([rclpy.parameter.Parameter('mpg123_bin', value=str(mpg123))])
    with patch('narrator.node.shutil.which', return_value='/usr/bin/paplay'), \
         patch('narrator.node.subprocess.run',
               return_value=MagicMock(returncode=1, stdout=b'', stderr=b'bad mp3')):
        assert n._play_mp3(b'garbage') is False
