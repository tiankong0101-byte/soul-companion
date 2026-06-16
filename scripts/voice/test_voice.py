#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  test_voice.py - v3.2 单元测试
# ============================================================

from __future__ import annotations

import asyncio
import gc
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

# UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from voice import TTS_REGISTRY, ASR_REGISTRY, create_tts, create_asr  # noqa: E402
from voice.tts.base import TTSError, TTSResult  # noqa: E402
from voice.tts.edge_tts import EdgeTTS, FEIFEI_VOICES  # noqa: E402
from voice.asr.base import ASRError, ASRResult  # noqa: E402
from voice.asr.whisper_asr import WhisperASR  # noqa: E402


class TestTTSRegistry(unittest.TestCase):
    def test_registry_has_edge(self):
        self.assertIn("edge", TTS_REGISTRY)

    def test_create_edge(self):
        t = create_tts("test", {"engine": "edge"})
        self.assertIsInstance(t, EdgeTTS)
        self.assertEqual(t.name, "test")

    def test_unknown_engine(self):
        with self.assertRaises(TTSError):
            create_tts("x", {"engine": "nonexistent"})


class TestEdgeTTS(unittest.TestCase):
    def test_voice_alias_mapping(self):
        for alias, neural in FEIFEI_VOICES.items():
            t = EdgeTTS("t", {"engine": "edge", "voice": alias})
            self.assertEqual(t.voice, neural)
            self.assertEqual(t.voice_alias, alias)

    def test_unknown_voice_kept_as_is(self):
        t = EdgeTTS("t", {"engine": "edge", "voice": "zh-CN-XiaoxiaoNeural"})
        self.assertEqual(t.voice, "zh-CN-XiaoxiaoNeural")
        self.assertIsNone(t.voice_alias)

    @patch("voice.tts.edge_tts.asyncio.run")
    def test_synthesize_calls_async(self, mock_run):
        # 直接重写 _async_synth，避免 mock asyncio.run 的复杂性
        t = EdgeTTS("t", {"engine": "edge", "voice": "default", "output_dir": tempfile.mkdtemp()})

        # 让 asyncio.run 直接调 fake coroutine（写文件）
        def fake_run(coro):
            # coroutine.__await__ 完成后取 result
            try:
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(coro)
                finally:
                    loop.close()
            except Exception:
                pass
            return None

        async def fake_async(self, text, voice, output_path):
            Path(output_path).write_bytes(b"fake mp3 data")

        mock_run.side_effect = fake_run
        with patch.object(EdgeTTS, "_async_synth", fake_async):
            result = t.synth("hello")
            self.assertIsInstance(result, TTSResult)
            self.assertEqual(result.engine, "t")
            self.assertTrue(Path(result.audio_path).exists())

    def test_synthesize_empty_text_raises(self):
        t = EdgeTTS("t", {"engine": "edge", "voice": "default"})
        with self.assertRaises(TTSError):
            t.synth("   ")
        with self.assertRaises(TTSError):
            t.synth("")

    def test_synthesize_emoji_only_raises(self):
        t = EdgeTTS("t", {"engine": "edge", "voice": "default"})
        with self.assertRaises(TTSError):
            t.synth("🎉🎊✨")


class TestTTSBase(unittest.TestCase):
    def test_preprocess_removes_emoji(self):
        from voice.tts.base import BaseTTS
        result = BaseTTS._preprocess("你好 🎉 世界")
        # emoji 删除后会留下 2 个空格，再被 \s+ 合并成 1 个
        self.assertEqual(result, "你好 世界")

    def test_preprocess_normalizes_whitespace(self):
        from voice.tts.base import BaseTTS
        result = BaseTTS._preprocess("你好\n\n世界\t\t")
        self.assertEqual(result, "你好 世界")

    def test_preprocess_removes_control_chars(self):
        from voice.tts.base import BaseTTS
        result = BaseTTS._preprocess("hello\x00\x01world")
        self.assertEqual(result, "helloworld")

    def test_default_output_path_deterministic(self):
        from voice.tts.base import BaseTTS
        t = EdgeTTS("t", {"engine": "edge", "voice": "default", "output_dir": "/tmp"})
        p1 = t._default_output_path("hello", "v1")
        p2 = t._default_output_path("hello", "v1")
        self.assertEqual(p1, p2)
        self.assertTrue(p1.endswith(".mp3"))


class TestGPTSoVITSTTS(unittest.TestCase):
    @patch("voice.tts.gpt_sovits.requests.post")
    def test_synthesize_calls_api(self, m_post):
        m_resp = MagicMock()
        m_resp.status_code = 200
        m_resp.content = b"RIFF....WAVE"
        m_post.return_value = m_resp
        from voice.tts.gpt_sovits import GPTSoVITSTTS
        t = GPTSoVITSTTS("t", {
            "engine": "gpt_sovits",
            "base_url": "http://127.0.0.1:9880",
            "ref_audio_path": "ref.wav",
            "prompt_text": "hi",
        })
        with tempfile.TemporaryDirectory() as d:
            out = str(Path(d) / "out.wav")
            result = t.synth("hello", output_path=out)
            self.assertEqual(result.engine, "t")
            self.assertEqual(Path(result.audio_path).read_bytes(), b"RIFF....WAVE")
            payload = m_post.call_args.kwargs["json"]
            self.assertEqual(payload["text"], "hello")
            self.assertEqual(payload["ref_audio_path"], "ref.wav")

    def test_missing_ref_audio_raises(self):
        from voice.tts.gpt_sovits import GPTSoVITSTTS
        t = GPTSoVITSTTS("t", {"engine": "gpt_sovits"})
        with self.assertRaises(TTSError):
            t.synth("hello")


class TestCosyVoiceTTS(unittest.TestCase):
    @patch("voice.tts.cosyvoice.requests.post")
    def test_synthesize_zero_shot(self, m_post):
        m_resp = MagicMock()
        m_resp.status_code = 200
        m_resp.content = b"wav-data"
        m_post.return_value = m_resp
        from voice.tts.cosyvoice import CosyVoiceTTS
        t = CosyVoiceTTS("t", {
            "engine": "cosyvoice",
            "base_url": "http://127.0.0.1:50000",
            "mode": "zero_shot",
            "prompt_text": "ref text",
            "prompt_wav": "ref.wav",
        })
        with tempfile.TemporaryDirectory() as d:
            out = str(Path(d) / "out.wav")
            t.synth("hi", output_path=out)
            self.assertEqual(m_post.call_args.args[0], "http://127.0.0.1:50000/inference_zero_shot")
            payload = m_post.call_args.kwargs["json"]
            self.assertEqual(payload["prompt_wav"], "ref.wav")


class TestFishSpeechTTS(unittest.TestCase):
    @patch("voice.tts.fish_speech.requests.post")
    def test_synthesize(self, m_post):
        m_resp = MagicMock()
        m_resp.status_code = 200
        m_resp.content = b"fish-wav"
        m_post.return_value = m_resp
        from voice.tts.fish_speech import FishSpeechTTS
        t = FishSpeechTTS("t", {"engine": "fish_speech", "base_url": "http://127.0.0.1:8180"})
        with tempfile.TemporaryDirectory() as d:
            t.synth("hi", output_path=str(Path(d) / "out.wav"))
            self.assertIn("/v1/tts", m_post.call_args.args[0])


class TestASRRegistry(unittest.TestCase):
    def test_registry_has_whisper(self):
        self.assertIn("whisper", ASR_REGISTRY)

    def test_create_whisper(self):
        a = create_asr("test", {"engine": "whisper", "model_size": "base"})
        self.assertIsInstance(a, WhisperASR)
        self.assertEqual(a.model_size, "base")

    def test_unknown_engine(self):
        with self.assertRaises(ASRError):
            create_asr("x", {"engine": "unknown"})


class TestWhisperASR(unittest.TestCase):
    def test_default_settings(self):
        a = WhisperASR("a", {"engine": "whisper", "model_size": "base"})
        self.assertEqual(a.model_size, "base")
        self.assertTrue(a.vad_filter)
        self.assertEqual(a.beam_size, 5)

    def test_auto_lang(self):
        a = WhisperASR("a", {"engine": "whisper", "model_size": "base", "language": "auto"})
        # 模拟 _transcribe：lang 是 None
        with patch.object(WhisperASR, "_ensure_loaded", lambda self: None):
            # _transcribe 中 lang = None if language == "auto" else language
            # 直接调 _transcribe 抛错（因为没 _model）
            with self.assertRaises(Exception):
                a._transcribe("nonexistent.wav", "auto")

    def test_transcribe_missing_file(self):
        a = WhisperASR("a", {"engine": "whisper", "model_size": "base"})
        with self.assertRaises(ASRError):
            a.transcribe("nonexistent.wav")

    @patch.object(WhisperASR, "_ensure_loaded")
    def test_transcribe_success(self, m_load):
        a = WhisperASR("a", {"engine": "whisper", "model_size": "base", "language": "zh"})

        # Mock WhisperModel.transcribe
        fake_seg = MagicMock()
        fake_seg.start = 0.0
        fake_seg.end = 1.5
        fake_seg.text = "你好"
        fake_info = MagicMock()
        fake_info.language = "zh"
        fake_info.language_probability = 0.99

        m_model = MagicMock()
        m_model.transcribe.return_value = ([fake_seg], fake_info)
        a._model = m_model

        # 创建一个临时 wav 文件
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF....WAVEfmt ")
            tmp_path = f.name
        try:
            result = a._transcribe(tmp_path, "zh")
            self.assertEqual(result.text, "你好")
            self.assertEqual(result.language, "zh")
            self.assertEqual(len(result.segments), 1)
            self.assertEqual(result.segments[0]["text"], "你好")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class TestCLI(unittest.TestCase):
    def test_tts_list(self):
        from io import StringIO
        from contextlib import redirect_stdout
        import voice.cli as cli_mod
        out = StringIO()
        with redirect_stdout(out):
            cli_mod.main(["tts", "list"])
        self.assertIn("edge-feifei", out.getvalue())

    def test_asr_list(self):
        from io import StringIO
        from contextlib import redirect_stdout
        import voice.cli as cli_mod
        out = StringIO()
        with redirect_stdout(out):
            cli_mod.main(["asr", "list"])
        self.assertIn("whisper-base", out.getvalue())

    def test_tts_voices(self):
        from io import StringIO
        from contextlib import redirect_stdout
        import voice.cli as cli_mod
        out = StringIO()
        with redirect_stdout(out):
            cli_mod.main(["tts", "voices"])
        self.assertIn("default", out.getvalue())
        self.assertIn("zh-CN-XiaoxiaoNeural", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
