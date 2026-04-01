#!/usr/bin/env python3
"""V-Agent: 安全的命令行编程助手"""

import json
import os
import sys
import time
from pathlib import Path

# Add v_agent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.styles import Style

PROMPT_STYLE = Style.from_dict({
    'completion-menu':                    'bg:default #888888',
    'completion-menu.completion':         'bg:default #888888',
    'completion-menu.completion.current': 'bg:default #888888 bold',
    'desc':                              '#888888',
    'scrollbar.background':              'bg:default',
    'scrollbar.button':                  'bg:default #888888',
})

from config import ModelManager, V_AGENT_HOME
from permissions import confirm_action, show_permissions, sanitize_content, load_redact_config, handle_redact_command
from context import ContextManager
from rag import RAG
from tools import TOOLS, TOOL_HANDLERS, SkillLoader, ApiLoader

WORKDIR = Path.cwd()

# PyInstaller 打包后，数据文件在 sys._MEIPASS 下
if getattr(sys, 'frozen', False):
    _BUNDLE_DIR = Path(sys._MEIPASS)
else:
    _BUNDLE_DIR = Path(__file__).parent

SKILLS_DIR = _BUNDLE_DIR / "skills"
APIS_DIR = V_AGENT_HOME / "apis"
DEBUG_DIR = V_AGENT_HOME / "debug"
_debug_enabled = False
_api_loader = None

# 命令补全定义
COMMANDS = [
    ("/help", "显示帮助"),
    ("/model", "切换模型 (/model <id>)"),
    ("/models", "列出已配置的模型"),
    ("/compact", "手动压缩上下文"),
    ("/skills", "列出可用 skill"),
    ("/permissions", "查看权限配置"),
    ("/redact", "查看脱敏规则"),
    ("/redact init", "交互式初始化脱敏规则"),
    ("/redact add keyword", "添加关键字脱敏"),
    ("/redact add pattern", "添加正则脱敏"),
    ("/redact rm keyword", "移除关键字"),
    ("/redact rm pattern", "移除正则"),
    ("/debug", "开关调试日志"),
    ("/apis", "查看已注册的接口工具"),
]


class CommandCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        for cmd, desc in COMMANDS:
            if cmd.startswith(text) and cmd != text:
                display = [('', cmd), ('class:desc', f'  {desc}')]
                yield Completion(cmd, start_position=-len(text), display=display)


def _log_request(system_prompt: str, messages: list, model: str):
    """将发送给模型的完整内容写入调试日志，按小时切割"""
    if not _debug_enabled:
        return
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    hour_tag = time.strftime("%Y%m%d_%H")
    log_file = DEBUG_DIR / f"request_{hour_tag}.jsonl"
    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": model,
        "system": system_prompt,
        "messages": messages,
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
    print(f"\033[90m[debug] 请求已记录: {log_file}\033[0m")


def build_system_prompt(skill_loader: SkillLoader) -> str:
    return f"""你是一个编程助手，工作目录: {WORKDIR}。使用工具帮助用户解决问题。
所有回复必须使用中文。
可用技能 (使用 load_skill 加载): {skill_loader.descriptions()}
执行操作前先说明计划。回答简洁。"""


def agent_loop(messages: list, model_mgr: ModelManager,
               ctx_mgr: ContextManager, system_prompt: str):
    """核心代理循环"""
    client = model_mgr.get_client()
    model = model_mgr.get_model_id()

    while True:
        # Layer 1: micro_compact
        ctx_mgr.micro_compact(messages)
        # Layer 2: auto_compact
        ctx_mgr.auto_compact(messages)

        # LLM 调用
        _log_request(system_prompt, messages, model)
        response = client.messages.create(
            model=model, system=system_prompt, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # 输出文本
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\n{block.text}")
            return

        # 工具执行
        results = []
        for block in response.content:
            if block.type == "tool_use":
                # 权限检查
                if not confirm_action(block.name, block.input):
                    output = "[用户拒绝执行]"
                else:
                    handler = TOOL_HANDLERS.get(block.name)
                    try:
                        output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                    except Exception as e:
                        output = f"Error: {e}"
                print(f"\033[90m> {block.name}: {str(output)[:200]}\033[0m")
                # 方向2: 出口脱敏，敏感信息不回传给模型
                safe_output = sanitize_content(str(output))
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": safe_output
                })

        messages.append({"role": "user", "content": results})


def handle_repl_command(cmd: str, model_mgr: ModelManager,
                        ctx_mgr: ContextManager, messages: list,
                        skill_loader: SkillLoader) -> bool:
    """处理 REPL 命令，返回 True 表示已处理"""
    cmd = cmd.strip()

    if cmd == "/help":
        print("""
命令:
  /model <id>     切换模型
  /models         列出已配置的模型
  /compact        手动压缩上下文
  /skills         列出可用 skill
  /permissions    查看权限配置
  /redact          查看/管理脱敏规则
  /redact init     交互式初始化 (选择角色模板)
  /redact add      添加关键字或正则规则
  /redact rm       移除规则
  /debug          开关调试日志 (记录发送给模型的完整内容)
  /apis           查看已注册的接口工具
  /help           显示帮助
  q / exit        退出
""")
        return True

    if cmd.startswith("/model "):
        model_id = cmd[7:].strip()
        model_mgr.switch_model(model_id)
        return True

    if cmd == "/models":
        model_mgr.list_models()
        return True

    if cmd == "/compact":
        ctx_mgr.manual_compact(messages)
        return True

    if cmd == "/skills":
        names = skill_loader.list_names()
        if names:
            print("可用 skills:")
            for n in names:
                print(f"  - {n}")
        else:
            print("暂无 skill")
        return True

    if cmd == "/permissions":
        show_permissions()
        return True

    if cmd == "/debug":
        global _debug_enabled
        _debug_enabled = not _debug_enabled
        status = "开启" if _debug_enabled else "关闭"
        print(f"\033[33m[调试日志已{status}]\033[0m")
        if _debug_enabled:
            print(f"日志目录: {DEBUG_DIR.resolve()}")
        return True

    if cmd == "/redact" or cmd.startswith("/redact "):
        redact_args = cmd[7:].strip()
        handle_redact_command(redact_args)
        return True

    if cmd == "/apis":
        if not _api_loader or not _api_loader.list_apis():
            print(f"\n暂无接口工具。在 {APIS_DIR}/ 下添加 JSON 配置，重启生效。")
        else:
            print(f"\n已注册的接口工具 (来源: {APIS_DIR}/):")
            for api in _api_loader.list_apis():
                method = api.get("method", "?").upper()
                print(f"  - {api['name']}  {method} {api['url']}")
                desc = api.get("description", "")
                if desc:
                    print(f"    {desc}")
        return True

    return False


def main():
    # 初始化
    model_mgr = ModelManager()
    ctx_mgr = ContextManager()

    # 把 config 中的 ak 同步到环境变量，供 API URL 模板使用
    if "ak" in model_mgr.config:
        os.environ["AK"] = model_mgr.config["ak"]

    skill_loader = SkillLoader(SKILLS_DIR)

    # RAG 配置
    rag_config = model_mgr.get_rag_config()
    rag = RAG(rag_config.get("endpoint") if rag_config.get("enabled") else None)

    # 注册 skill 和 rag 的 handler (动态注入)
    TOOL_HANDLERS["load_skill"] = lambda **kw: skill_loader.load(kw["name"])
    TOOL_HANDLERS["rag_query"] = lambda **kw: rag.query(kw["question"], kw.get("top_k", 3))

    # 加载自定义 API 工具
    global _api_loader
    _api_loader = ApiLoader(APIS_DIR)
    api_handlers, api_tools = _api_loader.load_all()
    TOOL_HANDLERS.update(api_handlers)
    TOOLS.extend(api_tools)
    # API 工具全部需要确认
    from permissions import NEEDS_CONFIRM
    for name in api_handlers:
        NEEDS_CONFIRM.add(name)
    if api_handlers:
        print(f"\033[90m[已加载 {len(api_handlers)} 个接口工具]\033[0m")

    system_prompt = build_system_prompt(skill_loader)

    # 加载用户自定义脱敏配置
    load_redact_config()

    print(f"\033[36mV-Agent | Model: {model_mgr.get_model_id()} | /help for commands\033[0m\n")

    history = []
    while True:
        try:
            query = pt_prompt(HTML('<cyan>v-agent &gt;&gt; </cyan>'),
                              completer=CommandCompleter(),
                              style=PROMPT_STYLE)
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if query.strip().lower() in ("q", "exit"):
            break
        if query.strip() == "":
            continue

        if query.startswith("/"):
            if handle_repl_command(query, model_mgr, ctx_mgr, history, skill_loader):
                continue

        history.append({"role": "user", "content": query})
        agent_loop(history, model_mgr, ctx_mgr, system_prompt)
        print()


if __name__ == "__main__":
    main()
