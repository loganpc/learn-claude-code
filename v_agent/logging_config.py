"""结构化日志系统"""

import logging
import sys
from pathlib import Path
from typing import Any


class VAgentLogger:
    """结构化日志系统"""

    def __init__(self, home: Path):
        self._home = home
        self._setup_loggers()

    def _setup_loggers(self):
        """配置多个日志输出"""
        # 主日志
        self._main = logging.getLogger("v_agent")
        self._main.setLevel(logging.DEBUG)

        # 清除现有 handlers
        self._main.handlers.clear()

        # 文件处理器
        log_file = self._home / "v_agent.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)

        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # 格式化
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        self._main.addHandler(file_handler)
        self._main.addHandler(console_handler)

        # API 请求日志 (单独文件)
        self._api = logging.getLogger("v_agent.api")
        self._api.setLevel(logging.DEBUG)
        self._api.handlers.clear()

        api_file = self._home / "api_requests.log"
        api_handler = logging.FileHandler(api_file, encoding="utf-8")
        api_handler.setFormatter(formatter)
        self._api.addHandler(api_handler)

    def log_request(self, model: str, messages: list, tools: list, **kwargs):
        """记录 API 请求"""
        self._api.info("Request: model=%s messages=%d tools=%d",
                      model, len(messages), len(tools))

    def log_response(self, model: str, input_tokens: int, output_tokens: int):
        """记录 API 响应"""
        self._api.info("Response: model=%s input=%d output=%d",
                      model, input_tokens, output_tokens)

    def log_tool_exec(self, tool_name: str, success: bool, duration: float = None):
        """记录工具执行"""
        if success:
            msg = f"✓ {tool_name}"
            if duration:
                msg += f" ({duration:.2f}s)"
            self._main.debug(msg)
        else:
            self._main.warning(f"✗ {tool_name} failed")

    def log_compact(self, before: int, after: int, method: str):
        """记录上下文压缩"""
        self._main.info(f"Compact: {before}→{after} tokens ({method})")


# 全局单例
_logger: VAgentLogger | None = None


def get_logger(home: Path = None) -> VAgentLogger:
    global _logger
    if _logger is None and home:
        _logger = VAgentLogger(home)
    return _logger
