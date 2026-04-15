#!/usr/bin/env python3
"""
feifei-tts.py - 菲菲语音合成器
使用微软 Edge TTS 生成菲菲的声音，配合 ffplay 播放

用法:
    python feifei-tts.py "你好呀，我是菲菲~"
    python feifei-tts.py "这是一段比较长的文字内容..." --voice zh-CN-XiaoyiNeural
"""

import argparse
import asyncio
import os
import sys
import tempfile
import subprocess
import shutil

try:
    import edge_tts
except ImportError:
    print("❌ 请先安装 edge-tts: pip install edge-tts")
    sys.exit(1)


# 菲菲的语音配置
FEIFEI_VOICES = {
    "default": {
        "voice": "zh-CN-XiaoxiaoNeural",
        "rate": "-10%",  # 稍慢，温柔
        "pitch": "+5Hz",  # 略高，少女感
        "desc": "晓晓 - 活泼温柔少女音",
    },
    "gentle": {
        "voice": "zh-CN-XiaoyiNeural",
        "rate": "-15%",
        "pitch": "+3Hz",
        "desc": "晓伊 - 温暖柔和少女音",
    },
    "mature": {
        "voice": "zh-CN-XiaobeiNeural",
        "rate": "-10%",
        "pitch": "0Hz",
        "desc": "晓北 - 知性温柔姐姐音",
    },
    "night": {
        "voice": "zh-CN-XiaoxiaoNeural",
        "rate": "-25%",      # 更慢，低沉
        "pitch": "-8Hz",     # 略低，夜晚氛围
        "desc": "晓晓 - 低沉夜话音"
    }

# 备用播放器
FFPLAY_PATH = None
if shutil.which("ffplay"):
    FFPLAY_PATH = "ffplay"
else:
    for base in [
        os.environ.get("ProgramData", ""),
        "C:\\Program Files",
        "C:\\Program Files (x86)",
    ]:
        candidate = os.path.join(base, "chocolatey", "bin", "ffplay.exe")
        if os.path.exists(candidate):
            FFPLAY_PATH = candidate
            break


def find_ffplay():
    """找到 ffplay 可执行文件"""
    # 先尝试 shutil.which
    path = shutil.which("ffplay")
    if path:
        return path
    # 再试 chocolatey 默认安装路径
    paths = [
        r"C:\ProgramData\chocolatey\bin\ffplay.exe",
        r"C:\ffmpeg\bin\ffplay.exe",
        r"C:\Program Files\ffmpeg\bin\ffplay.exe",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def play_audio(filepath: str):
    """使用 ffplay 播放音频，自动关闭"""
    ffplay = find_ffplay()
    if not ffplay:
        print("⚠️ 未找到 ffplay，跳过播放（音频已保存）")
        print(f"   文件位置: {filepath}")
        return

    try:
        subprocess.run(
            [ffplay, "-autoexit", "-nodisp", "-loglevel", "quiet", filepath],
            timeout=60,
            check=True,
        )
    except subprocess.TimeoutExpired:
        print("⚠️ 播放超时，已终止")
    except FileNotFoundError:
        print("⚠️ ffplay 未找到，跳过播放")
    except Exception as e:
        print(f"⚠️ 播放出错: {e}")


def split_text(text: str, max_len: int = 400) -> list:
    """
    将长文本分割为句子，避免 TTS 截断
    按句子分割，保持语气完整性
    """
    import re

    # 分割句子：按中文句号、感叹号、问号、英文句号分割
    sentences = re.split(r"(?<=[。！？.!?])", text)
    chunks = []
    current = ""

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(current) + len(sent) <= max_len:
            current += sent
        else:
            if current:
                chunks.append(current)
            # 如果单句超过 max_len，进一步按逗号分割
            while len(sent) > max_len:
                # 找到合适的中断点
                for i in range(max_len - 1, 0, -1):
                    if sent[i] in "，,；;：:":
                        chunks.append(sent[: i + 1])
                        sent = sent[i + 1 :]
                        break
                else:
                    chunks.append(sent[:max_len])
                    sent = sent[max_len:]
            current = sent

    if current:
        chunks.append(current)

    return [c for c in chunks if c.strip()]


async def generate_tts(
    text: str,
    voice: str = "zh-CN-XiaoxiaoNeural",
    rate: str = "-10%",
    pitch: str = "+5Hz",
    output_path: str = None,
    volume: str = "+0%",
) -> str:
    """
    使用 Edge TTS 生成语音

    Args:
        text: 要转换的文本
        voice: 语音名称
        rate: 语速 (如 "-10%", "+5%")
        pitch: 音调 (如 "+5Hz", "-10Hz")
        output_path: 输出文件路径，None 则自动生成
        volume: 音量

    Returns:
        生成的文件路径
    """
    if not text or not text.strip():
        raise ValueError("文本不能为空")

    # 确定输出路径
    if output_path is None:
        temp_dir = os.environ.get("TEMP", "/tmp")
        fd, output_path = tempfile.mkstemp(suffix=".mp3", dir=temp_dir)
        os.close(fd)
    else:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 分割长文本
    chunks = split_text(text)

    if len(chunks) == 1:
        # 单段，直接生成
        communicate = edge_tts.Communicate(
            text, voice=voice, rate=rate, pitch=pitch, volume=volume
        )
        await communicate.save(output_path)
    else:
        sub_audio_files = []

        for i, chunk in enumerate(chunks):
            sub_file = output_path.replace(".mp3", f"_part{i}.mp3")
            communicate = edge_tts.Communicate(
                chunk, voice=voice, rate=rate, pitch=pitch, volume=volume
            )
            await communicate.save(sub_file)
            sub_audio_files.append(sub_file)

        # 用 ffmpeg 合并音频
        concat_list = output_path.replace(".mp3", "_concat.txt")
        with open(concat_list, "w", encoding="utf-8") as f:
            for af in sub_audio_files:
                f.write(f"file '{af}'\n")

        try:
            ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
            result = subprocess.run(
                [
                    ffmpeg_path,
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    concat_list,
                    "-c",
                    "copy",
                    output_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                print(f"⚠️ 合并警告: {result.stderr[:200]}")
        finally:
            # 清理临时文件
            for af in sub_audio_files:
                try:
                    os.remove(af)
                except Exception:
                    pass
            try:
                os.remove(concat_list)
            except Exception:
                pass

    return output_path


async def main_async(args):
    """异步主函数"""
    import sys

    # 修复 Windows GBK 控制台输出
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    # 选择语音配置
    if args.voice_name and args.voice_name in FEIFEI_VOICES:
        cfg = FEIFEI_VOICES[args.voice_name]
    elif args.voice:
        cfg = {
            "voice": args.voice,
            "rate": args.rate or "-10%",
            "pitch": args.pitch or "+5Hz",
            "desc": "自定义",
        }
    else:
        cfg = FEIFEI_VOICES["default"]

    # 读取文本
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = args.text

    if not text.strip():
        print("❌ 文本为空")
        sys.exit(1)

    # 显示信息
    print(f"🔊 菲菲语音合成")
    print(f"   文本: {text[:50]}{'...' if len(text) > 50 else ''}")
    print(f"   语音: {cfg.get('desc', cfg['voice'])}")
    print(f"   语速: {cfg['rate']}  音调: {cfg['pitch']}")

    # 生成
    output = await generate_tts(
        text, voice=cfg["voice"], rate=cfg["rate"], pitch=cfg["pitch"]
    )

    size = os.path.getsize(output)
    print(f"✅ 生成完成: {output} ({size} bytes)")

    # 播放
    if args.no_play:
        print(f"📁 音频文件: {output}")
    else:
        print(f"🔊 正在播放...")
        play_audio(output)
        print("✅ 播放完毕")


def main():
    parser = argparse.ArgumentParser(
        description="菲菲 TTS - 微软 Edge 语音合成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
语音配置:
  --voice-name default  晓晓(活泼温柔少女音) - 适合日常
  --voice-name gentle   晓伊(温暖柔和少女音) - 适合安慰
  --voice-name night    云希(磁性低沉夜话音) - 适合深夜
  --voice-name mature   晓北(知性温柔姐姐音) - 适合治愈

示例:
  python feifei-tts.py "你好呀，我是菲菲~今天过得怎么样？"
  python feifei-tts.py --voice-name night "夜深了..."
  python feifei-tts.py -f speech.txt --no-play
        """,
    )
    parser.add_argument("text", nargs="?", help="要转换的文本（可省略，配合 -f 使用）")
    parser.add_argument("-f", "--file", help="从文件读取文本")
    parser.add_argument("-o", "--output", help="输出文件路径（默认临时目录）")
    parser.add_argument("--voice", help="直接指定 Edge TTS 语音名称")
    parser.add_argument(
        "--voice-name",
        choices=list(FEIFEI_VOICES.keys()),
        default="default",
        help="使用预设语音配置",
    )
    parser.add_argument("--rate", help="语速，如 '-10%%' '+5%%'")
    parser.add_argument("--pitch", help="音调，如 '+5Hz' '-10Hz'")
    parser.add_argument("--no-play", action="store_true", help="只生成文件，不播放")

    args = parser.parse_args()

    if not args.text and not args.file:
        parser.print_help()
        sys.exit(1)

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
