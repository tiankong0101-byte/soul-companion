"""
Soul Companion v4.0 — 主入口
菲菲的灵魂伴侣系统

启动命令：
  python app.py                    # 默认启动
  python app.py --port 8080        # 指定端口
  python app.py --debug            # 调试模式
  python app.py --config other.yaml  # 指定配置文件

架构：
  app.py (入口) → core/ (业务逻辑) → scripts/ (基础设施)
"""
import os
import sys
import json
import argparse
import asyncio
from pathlib import Path

import yaml
from loguru import logger
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO

from core.agent import FeiFeiAgent
from core.chat_manager import ChatManager
from core.live2d_controller import Live2DController
from core.tools import ToolManager
from core.image_generator import ImageGenerator
from core.scheduler import Scheduler
from core.vision_manager import VisionManager


def load_config(config_path: str = None) -> dict:
    """加载配置文件"""
    if config_path is None:
        config_path = Path(__file__).parent / "config" / "config.yaml"
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        logger.error(f"配置文件不存在: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 加载 LLM 子配置
    llm_config_path = Path(config_path).parent / "llm.yaml"
    if llm_config_path.exists():
        with open(llm_config_path, "r", encoding="utf-8") as f:
            llm_config = yaml.safe_load(f)
            config["llm"] = {**config.get("llm", {}), **llm_config}

    # 记录基础路径
    config["_base_dir"] = str(Path(__file__).parent)

    return config


def create_app(config: dict) -> tuple:
    """创建 Flask 应用"""
    app_config = config.get("app", {})
    server_config = config.get("server", {})

    app = Flask(
        __name__,
        static_folder=str(Path(config["_base_dir"]) / "web"),
        static_url_path="/static",
    )
    app.secret_key = server_config.get("secret_key", "soul-companion-v4")

    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode="threading",
    )

    # ===== 初始化核心模块 =====
    agent = FeiFeiAgent(config)
    chat_manager = ChatManager(config)
    live2d = Live2DController(config)

    # 初始化新模块
    tool_manager = ToolManager(config)
    image_generator = ImageGenerator(config)
    scheduler = Scheduler(config)
    vision_manager = VisionManager(config)

    # 注入模块到 ChatManager
    chat_manager.tool_manager = tool_manager
    chat_manager.image_generator = image_generator
    chat_manager.scheduler = scheduler

    # 注册日程到期回调
    async def on_reminder_due(reminder):
        """日程到期时推送到前端"""
        title = reminder.get("title", "提醒")
        socketio.emit("reminder_alert", {
            "title": title,
            "message": f"⏰ 天哥，该「{title}」啦~",
        })

    scheduler.register_callback(on_reminder_due)

    logger.info("="*50)
    logger.info("菲菲 Soul Companion v5.0 启动中...")
    logger.info(f"  📦 工具: {tool_manager.list_tools()}")
    logger.info(f"  🖼️ 图片生成: {image_generator.get_info()['provider']}")
    logger.info(f"  📅 日程提醒: 就绪")
    logger.info("="*50)

    # ===== 路由定义 =====

    @app.route("/")
    def index():
        """主页"""
        return app.send_static_file("index.html")

    @app.route("/api/config")
    def get_config():
        """获取前端配置"""
        return jsonify({
            "app_name": app_config.get("name", "菲菲"),
            "version": app_config.get("version", "4.0.0"),
            "live2d_enabled": config.get("live2d", {}).get("enabled", True),
            "voice_enabled": config.get("voice", {}).get("tts", {}).get("provider") is not None,
            "vision_enabled": config.get("vision", {}).get("enabled", True),
            "memory_enabled": config.get("memory", {}).get("enabled", True),
        })

    @app.route("/api/chat", methods=["POST"])
    async def chat():
        """HTTP 聊天接口"""
        data = request.get_json()
        user_text = data.get("message", "").strip()

        if not user_text:
            return jsonify({"error": "消息不能为空"}), 400

        response = await chat_manager.process_message(user_text, agent)
        live2d_event = live2d.get_emotion_event(
            response.get("emotion", "neutral"),
            response.get("mode", "default"),
        )

        result = {
            "response": response.get("content", ""),
            "emotion": response.get("emotion", "neutral"),
            "mode": response.get("mode", "default"),
            "live2d_event": live2d_event,
        }

        # 图片路径
        if response.get("image_path"):
            result["image_path"] = response["image_path"]

        # 提醒列表
        if response.get("reminders"):
            result["reminders"] = response["reminders"]

        return jsonify(result)

    @app.route("/api/stats")
    def stats():
        """获取统计信息"""
        return jsonify(chat_manager.get_stats())

    @app.route("/api/vision", methods=["POST"])
    async def vision():
        """图片识图接口"""
        # 支持两种方式：URL 和 base64
        data = request.get_json()
        image_url = data.get("image_url", "")
        image_base64 = data.get("image_base64", "")
        prompt = data.get("prompt", "")

        image_source = image_url or image_base64
        if not image_source:
            return jsonify({"error": "请提供图片 URL 或 base64 数据"}), 400

        result = await vision_manager.analyze_image(image_source, prompt or None)
        return jsonify({
            "response": result,
            "status": "ok",
        })

    @app.route("/api/vision/upload", methods=["POST"])
    async def vision_upload():
        """上传图片识图接口"""
        if "image" not in request.files:
            return jsonify({"error": "请上传图片"}), 400

        file = request.files["image"]
        if not file.filename:
            return jsonify({"error": "文件名为空"}), 400

        # 读取图片并转为 base64
        import base64
        image_data = file.read()
        b64 = base64.b64encode(image_data).decode()

        # 确定 MIME 类型
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif",
            ".webp": "image/webp",
        }
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpeg"
        mime = mime_map.get(f".{ext}", "image/jpeg")
        data_uri = f"data:{mime};base64,{b64}"

        prompt = request.form.get("prompt", "")
        result = await vision_manager.analyze_image(data_uri, prompt or None)
        return jsonify({
            "response": result,
            "filename": file.filename,
            "status": "ok",
        })

    @app.route("/api/health")
    def health():
        """健康检查"""
        return jsonify({
            "status": "ok",
            "version": "5.0.0",
            "name": "菲菲 Soul Companion",
            "tools": tool_manager.list_tools(),
            "image_generator": image_generator.get_info(),
            "scheduler": scheduler.get_info(),
        })

    # 启动日程后台检查
    import threading
    scheduler_loop = asyncio.new_event_loop()

    def run_scheduler():
        asyncio.set_event_loop(scheduler_loop)
        scheduler_loop.run_until_complete(scheduler.start_check_loop())

    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("日程后台检查已启动")

    # ===== WebSocket 事件 =====

    @socketio.on("connect")
    def handle_connect():
        logger.info(f"客户端连接: {request.sid}")

    @socketio.on("disconnect")
    def handle_disconnect():
        logger.info(f"客户端断开: {request.sid}")

    @socketio.on("chat_message")
    async def handle_chat_message(data):
        """WebSocket 聊天消息处理"""
        user_text = data.get("message", "").strip()
        if not user_text:
            socketio.emit("chat_response", {
                "error": "消息不能为空",
            })
            return

        # 生成回复
        response = await chat_manager.process_message(user_text, agent)

        # 生成 Live2D 事件
        live2d_event = live2d.get_emotion_event(
            response.get("emotion", "neutral"),
            response.get("mode", "default"),
        )

        # 发送回复
        result = {
            "response": response.get("content", ""),
            "emotion": response.get("emotion", "neutral"),
            "mode": response.get("mode", "default"),
            "live2d_event": live2d_event,
        }
        if response.get("image_path"):
            result["image_path"] = response["image_path"]
        if response.get("reminders"):
            result["reminders"] = response["reminders"]

        socketio.emit("chat_response", result)

    @socketio.on("typing")
    def handle_typing(data):
        """用户正在输入"""
        socketio.emit("user_typing", {"typing": True})

    @socketio.on("analyze_image")
    async def handle_analyze_image(data):
        """WebSocket 图片识图"""
        image_source = data.get("image_url") or data.get("image_base64", "")
        prompt = data.get("prompt", "")

        if not image_source:
            socketio.emit("vision_response", {"error": "请提供图片"})
            return

        # 先发"正在看图"状态
        socketio.emit("vision_status", {"status": "analyzing"})

        result = await vision_manager.analyze_image(image_source, prompt or None)
        socketio.emit("vision_response", {
            "response": result,
            "status": "ok",
        })

    return app, socketio


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="菲菲 Soul Companion v4.0")
    parser.add_argument("--host", default=None, help="监听地址")
    parser.add_argument("--port", type=int, default=None, help="监听端口")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--config", default=None, help="配置文件路径")
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)
    app_config = config.get("app", {})

    # 命令行参数覆盖配置
    host = args.host or app_config.get("host", "0.0.0.0")
    port = args.port or app_config.get("port", 5000)
    debug = args.debug or app_config.get("debug", False)

    # 配置日志
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(
        str(log_dir / "soul_companion_{time:YYYY-MM-DD}.log"),
        rotation="1 day",
        retention="30 days",
        level="INFO",
    )

    # 创建应用
    app, socketio = create_app(config)

    logger.info(f"启动服务: http://{host}:{port}")
    logger.info(f"调试模式: {'开启' if debug else '关闭'}")

    socketio.run(app, host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
