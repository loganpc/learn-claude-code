# v_agent/tools/base.py
import re
import shlex
import subprocess
from pathlib import Path

WORKDIR = Path.cwd()

# 完全禁止的命令
BLOCKED_COMMANDS = ["sudo", "shutdown", "reboot", "> /dev/", "mkfs", "dd if="]


def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def _check_rm_command(command: str) -> str | None:
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
    rm_idx = None
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


def run_bash(command: str) -> str:
    # 完全禁止的命令
    if any(d in command for d in BLOCKED_COMMANDS):
        return "Error: Dangerous command blocked"
    # rm 命令特殊处理
    rm_error = _check_rm_command(command)
    if rm_error:
        return rm_error
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"

def run_read(path: str, limit: int = None) -> str:
    try:
        lines = safe_path(path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"

def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(path)
        c = fp.read_text()
        if old_text not in c:
            return f"Error: Text not found in {path}"
        fp.write_text(c.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"

def run_list_dir(path: str = ".") -> str:
    try:
        target = safe_path(path)
        items = sorted(target.iterdir())
        lines = []
        for item in items:
            prefix = "d " if item.is_dir() else "f "
            lines.append(f"{prefix}{item.name}")
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"Error: {e}"
