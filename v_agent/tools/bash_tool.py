"""Bash 工具"""

import re
import shlex
import subprocess
from pathlib import Path
from typing import Optional

from .base_new import BaseTool, ToolContext, ToolResult

WORKDIR = Path.cwd()

# 完全禁止的命令
BLOCKED_COMMANDS: list[str] = ["sudo", "shutdown", "reboot", "> /dev/", "mkfs", "dd if="]


def safe_path(p: str) -> Path:
    """检查路径是否在工作目录内"""
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def _check_rm_command(command: str) -> Optional[str]:
    """检查 rm 命令安全性，返回错误信息或 None（安全）"""
    # 检测 rm 命令（支持 rm / rm -rf / rm -f 等变体）
    rm_match = re.search(r'\brm\s+', command)
    if not rm_match:
        return None

    # 提取 rm 后面的参数
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = command.split()

    # 找到 rm 的位置，提取目标路径
    rm_idx: Optional[int] = None
    for i, p in enumerate(parts):
        if p == "rm":
            rm_idx = i
            break
    if rm_idx is None:
        return None

    targets = []
    for p in parts[rm_idx + 1:]:
        if p.startswith("-"):
            continue  # 跳过选项如 -rf, -f, -r
        targets.append(p)

    if not targets:
        return "Error: rm 命令缺少目标文件"

    # 检查每个目标路径是否在安全路径内
    for target in targets:
        try:
            safe_path(target)
        except ValueError:
            return f"Error: 禁止删除工作目录外的文件: {target}"

    # 列出将要删除的文件，要求用户二次确认
    print(f"\n\033[31m[删除确认] 将删除以下目标:\033[0m")
    for t in targets:
        resolved = (WORKDIR / t).resolve()
        kind = "目录" if resolved.is_dir() else "文件"
        print(f"  {kind}: {resolved}")

    while True:
        try:
            ans = input("\033[31m确认删除? [y/n]: \033[0m").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "Error: 用户取消删除"
        if ans == "y":
            return None  # 允许执行
        elif ans == "n":
            return "Error: 用户取消删除"

    return None


class BashTool(BaseTool):
    """Bash 命令执行工具"""

    name: str = "bash"
    description: str = "Run a shell command."

    def get_input_schema(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run"
                }
            },
            "required": ["command"]
        }

    def is_read_only(self, arguments: dict[str, object]) -> bool:
        """检测是否为只读命令"""
        command = arguments.get("command", "")
        if not isinstance(command, str):
            return False
        readonly_prefixes = ["ls", "cat", "grep", "find", "echo", "pwd", "head", "tail", "wc"]
        return any(command.startswith(prefix) for prefix in readonly_prefixes)

    def execute(self, arguments: dict[str, object], context: ToolContext) -> ToolResult:
        command = arguments.get("command", "")
        if not isinstance(command, str):
            return ToolResult(content="Error: command must be a string", is_error=True)

        # 完全禁止的命令
        if any(d in command for d in BLOCKED_COMMANDS):
            return ToolResult(content="Error: Dangerous command blocked", is_error=True)

        # rm 命令特殊处理
        rm_error = _check_rm_command(command)
        if rm_error:
            return ToolResult(content=rm_error, is_error=True)

        try:
            r = subprocess.run(
                command,
                shell=True,
                cwd=context.cwd,
                capture_output=True,
                text=True,
                timeout=120
            )
            out = (r.stdout + r.stderr).strip()
            content = out[:50000] if out else "(no output)"
            return ToolResult(content=content)
        except subprocess.TimeoutExpired:
            return ToolResult(content="Error: Timeout (120s)", is_error=True)
        except Exception as e:
            return ToolResult(content=f"Error: {e}", is_error=True)
