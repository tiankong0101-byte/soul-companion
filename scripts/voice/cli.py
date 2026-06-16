#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================
#  cli.py - 语音 CLI（v3.2）
# ============================================================
#
#  用法：
#    # TTS
#    python scripts/voice/cli.py tts list
#    python scripts/voice/cli.py tts speak --engine edge-feifei --text "你好，我是菲菲"
#    python scripts/voice/cli.py tts speak -e edge-night -t "夜深了" --play
#    python scripts/voice/cli.py tts speak -e gpt-sovits-feifei -t "你好"
#
#    # ASR
#    python scripts/voice/cli.py asr list
#    python scripts/voice/cli.py asr transcribe --engine whisper-base --audio input.wav
#    python scripts/voice/cli.py asr transcribe -e funasr-zh -a recording.mp3
# ============================================================

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

# UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import yaml

# 路径
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from voice import TTS_REGISTRY, ASR_REGISTRY, create_tts, create_asr  # noqa: E402
from voice.tts.base import TTSError  # noqa: E402
from voice.asr.base import ASRError  # noqa: E402


# ---------- 配置加载 ----------

def _load_config() -> dict:
    cfg_path = Path(__file__).resolve().parent / "config.yaml"
    if not cfg_path.exists():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _create_tts(name: str):
    cfg = _load_config()
    eng_cfg = cfg.get("tts", {}).get("engines", {}).get(name, {})
    if not eng_cfg:
        raise TTSError(f"未知 TTS 配置: {name}")
    return create_tts(name, eng_cfg)


def _create_asr(name: str):
    cfg = _load_config()
    eng_cfg = cfg.get("asr", {}).get("engines", {}).get(name, {})
    if not eng_cfg:
        raise ASRError(f"未知 ASR 配置: {name}")
    return create_asr(name, eng_cfg)


# ---------- TTS 子命令 ----------

def cmd_tts_list(_args):
    cfg = _load_config()
    engines = cfg.get("tts", {}).get("engines", {})
    print("可用 TTS 引擎：\n")
    for n, c in engines.items():
        print(f"  {n:<25} engine={c.get('engine'):<12} voice={c.get('voice', c.get('spk_id', '?'))}")
    print(f"\n已注册 TTS 类别: {list(TTS_REGISTRY.keys())}")


def cmd_tts_speak(args):
    tts = _create_tts(args.engine)
    result = tts.synth(args.text, voice=args.voice, output_path=args.output)
    print(f"[OK] 合成完成")
    print(f"     引擎: {result.engine}")
    print(f"     voice: {result.voice}")
    print(f"     输出: {result.audio_path}")
    print(f"     大小: {result.file_size:,} bytes")
    if args.play:
        if tts.play(result.audio_path):
            print(f"     正在播放...")
        else:
            print(f"     [WARN] 未找到播放器（请安装 ffplay 或 afplay）")


def cmd_tts_voices(_args):
    print("Edge TTS 内置菲菲语音：")
    from voice.tts.edge_tts import FEIFEI_VOICES
    for k, v in FEIFEI_VOICES.items():
        print(f"  {k:<10} → {v}")


# ---------- ASR 子命令 ----------

def cmd_asr_list(_args):
    cfg = _load_config()
    engines = cfg.get("asr", {}).get("engines", {})
    print("可用 ASR 引擎：\n")
    for n, c in engines.items():
        print(f"  {n:<25} engine={c.get('engine'):<13} model={c.get('model_size', c.get('model', '?'))}")
    print(f"\n已注册 ASR 类别: {list(ASR_REGISTRY.keys())}")


def cmd_asr_transcribe(args):
    asr = _create_asr(args.engine)
    result = asr.transcribe(args.audio, language=args.language)
    print(f"[OK] 转写完成")
    print(f"     引擎: {result.engine}")
    print(f"     语言: {result.language}")
    print(f"     时长: {result.duration_sec:.2f}s")
    print(f"     文本: {result.text}")
    if result.segments:
        print(f"\n     段落:")
        for s in result.segments[:10]:
            print(f"        [{s.get('start', 0):.2f}s - {s.get('end', 0):.2f}s] {s.get('text', '').strip()}")
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result.text)
        print(f"\n     已保存到: {args.output}")


# ---------- 解析 ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="feifei-voice", description="soul-companion v3.2 语音 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    # tts
    sp = sub.add_parser("tts", help="TTS 合成")
    tts_sub = sp.add_subparsers(dest="sub", required=True)

    a = tts_sub.add_parser("list")
    a.set_defaults(func=cmd_tts_list)

    a = tts_sub.add_parser("speak")
    a.add_argument("--engine", "-e", required=True)
    a.add_argument("--text", "-t", required=True)
    a.add_argument("--voice", "-v", default=None)
    a.add_argument("--output", "-o", default=None)
    a.add_argument("--play", action="store_true", help="合成后用 ffplay 播放")
    a.set_defaults(func=cmd_tts_speak)

    a = tts_sub.add_parser("voices")
    a.set_defaults(func=cmd_tts_voices)

    # asr
    sp = sub.add_parser("asr", help="ASR 转写")
    asr_sub = sp.add_subparsers(dest="sub", required=True)

    a = asr_sub.add_parser("list")
    a.set_defaults(func=cmd_asr_list)

    a = asr_sub.add_parser("transcribe")
    a.add_argument("--engine", "-e", required=True)
    a.add_argument("--audio", "-a", required=True)
    a.add_argument("--language", "-l", default=None)
    a.add_argument("--output", "-o", default=None, help="把识别文本写到文件")
    a.set_defaults(func=cmd_asr_transcribe)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (TTSError, ASRError) as e:
        print(f"[ERR] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
