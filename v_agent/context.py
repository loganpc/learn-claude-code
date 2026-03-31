# v_agent/context.py
import json
import os
import time
from datetime import date
from pathlib import Path

from config import V_AGENT_HOME

THRESHOLD = 50_000
KEEP_RECENT_RESULTS = 3
KEEP_RECENT_MESSAGES = 10
TRANSCRIPT_DIR = V_AGENT_HOME / "transcripts"


class ContextManager:
    def __init__(self):
        TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
        self.transcript_path = TRANSCRIPT_DIR / f"{date.today().isoformat()}_session_{int(time.time())}.jsonl"

    def _append_transcript(self, messages: list):
        """追加写入本地 transcript 文件"""
        with open(self.transcript_path, "a") as f:
            for msg in messages:
                f.write(json.dumps(msg, default=str, ensure_ascii=False) + "\n")

    def _collect_tool_results(self, messages: list) -> list:
        """收集所有 tool_result"""
        results = []
        for msg in messages:
            if msg["role"] == "user" and isinstance(msg.get("content"), list):
                for part in msg["content"]:
                    if isinstance(part, dict) and part.get("type") == "tool_result":
                        results.append(part)
        return results

    def _build_tool_name_map(self, messages: list) -> dict:
        """从 assistant 消息中提取 tool_use_id -> tool_name 映射"""
        name_map = {}
        for msg in messages:
            if msg["role"] == "assistant":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if hasattr(block, "type") and block.type == "tool_use":
                            name_map[block.id] = block.name
        return name_map

    def micro_compact(self, messages: list):
        """Layer 1: 替换旧 tool_result 为占位符，替换前先存本地"""
        results = self._collect_tool_results(messages)
        if len(results) <= KEEP_RECENT_RESULTS:
            return

        name_map = self._build_tool_name_map(messages)
        to_clear = results[:-KEEP_RECENT_RESULTS]

        # 先存后清
        saved = []
        for part in to_clear:
            if isinstance(part.get("content"), str) and len(part["content"]) > 100:
                tool_id = part.get("tool_use_id", "")
                tool_name = name_map.get(tool_id, "unknown")
                saved.append({
                    "type": "micro_compact_cleared",
                    "tool_name": tool_name,
                    "tool_use_id": tool_id,
                    "content": part["content"]
                })
                part["content"] = f"[Previous: used {tool_name}]"

        if saved:
            self._append_transcript(saved)

    def auto_compact(self, messages: list):
        """Layer 2: 滑动窗口截断，不做 AI 摘要"""
        if self.estimate_tokens(messages) <= THRESHOLD:
            return False

        print(f"\033[33m[auto_compact] 上下文过长，执行压缩...\033[0m")

        to_remove = messages[:-KEEP_RECENT_MESSAGES]
        self._append_transcript(to_remove)

        kept = messages[-KEEP_RECENT_MESSAGES:]
        messages.clear()

        messages.append({
            "role": "user",
            "content": f"[对话已压缩，共移除 {len(to_remove)} 条消息。完整记录: {self.transcript_path}]"
        })
        messages.append({
            "role": "assistant",
            "content": "好的，之前的上下文已压缩保存。请继续。"
        })
        messages.extend(kept)

        print(f"[已保存 {len(to_remove)} 条消息到 {self.transcript_path}]")
        os.system("clear")
        print("\033[33m[上下文已压缩，历史对话已保存到本地]\033[0m\n")
        return True

    def manual_compact(self, messages: list):
        """Layer 3: 手动触发，强制执行不检查阈值"""
        if len(messages) <= KEEP_RECENT_MESSAGES:
            print("[compact] 消息数量较少，无需压缩")
            return

        to_remove = messages[:-KEEP_RECENT_MESSAGES]
        self._append_transcript(to_remove)

        kept = messages[-KEEP_RECENT_MESSAGES:]
        messages.clear()

        messages.append({
            "role": "user",
            "content": f"[手动压缩，共移除 {len(to_remove)} 条消息。完整记录: {self.transcript_path}]"
        })
        messages.append({
            "role": "assistant",
            "content": "好的，已手动压缩。请继续。"
        })
        messages.extend(kept)

        print(f"[已保存 {len(to_remove)} 条消息到 {self.transcript_path}]")
        os.system("clear")
        print("\033[33m[上下文已手动压缩，历史对话已保存到本地]\033[0m\n")

    def estimate_tokens(self, messages: list) -> int:
        return len(json.dumps(messages, default=str)) // 4
