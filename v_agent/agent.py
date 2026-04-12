#!/usr/bin/env python3
"""V-Agent: 安全的命令行编程助手"""

import json
import logging
import os
import sys
import time
from pathlib import Path

# Add v_agent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)

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
from permissions import confirm_action, show_permissions, sanitize_content, load_redact_config, handle_redact_command, handle_permissions_command
from context import ContextManager
from rag import RAG
from tools import TOOLS, TOOL_HANDLERS, SkillLoader, _registry, _init_api_loader
from api import call_with_retry, RetryConfig
from logging_config import get_logger

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
_logger = None  # 全局日志实例

# 命令补全定义
COMMANDS = [
    ("/help", "显示帮助"),
    ("/model", "切换模型 (/model <id>)"),
    ("/models", "列出已配置的模型"),
    ("/compact", "手动压缩上下文"),
    ("/skills", "列出可用 skill"),
    ("/permissions", "查看/管理权限配置"),
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


def _log_request(system_prompt: str, messages: list, model: str,
                  tools: list, max_tokens: int):
    """将发送给模型的完整参数写入调试日志，格式化便于查看"""
    if not _debug_enabled:
        return
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    hour_tag = time.strftime("%Y%m%d_%H")
    log_file = DEBUG_DIR / f"request_{hour_tag}.log"

    sep = "=" * 72
    sub_sep = "-" * 72
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    msg_count = len(messages)
    token_est = len(json.dumps(messages, default=str)) // 4

    lines = [
        "",
        sep,
        f"  LLM Request  |  {ts}",
        sep,
        "",
        f"[参数]",
        f"  model:      {model}",
        f"  max_tokens: {max_tokens}",
        f"  tools:      {len(tools)} 个 ({', '.join(t['name'] for t in tools)})",
        f"  messages:   {msg_count} 条 (约 {token_est} tokens)",
        "",
        f"[System Prompt]",
        sub_sep,
        system_prompt,
        sub_sep,
        "",
        f"[Messages]",
    ]

    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        content = msg.get("content")
        lines.append(f"  [{i}] {role}")

        if isinstance(content, str):
            preview = content if len(content) <= 500 else content[:500] + f"\n    ... ({len(content)} chars total)"
            for line in preview.splitlines():
                lines.append(f"    {line}")

        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    ptype = part.get("type", "?")
                    tid = part.get("tool_use_id", "")
                    pcontent = str(part.get("content", ""))
                    preview = pcontent if len(pcontent) <= 300 else pcontent[:300] + f"... ({len(pcontent)} chars)"
                    lines.append(f"    [{ptype}] id={tid}")
                    for line in preview.splitlines():
                        lines.append(f"      {line}")
                elif hasattr(part, "type"):
                    if part.type == "tool_use":
                        input_str = json.dumps(part.input, ensure_ascii=False, default=str)
                        if len(input_str) > 300:
                            input_str = input_str[:300] + f"... ({len(input_str)} chars)"
                        lines.append(f"    [tool_use] {part.name} id={part.id}")
                        lines.append(f"      input: {input_str}")
                    elif part.type == "text":
                        text = part.text
                        preview = text if len(text) <= 500 else text[:500] + f"\n      ... ({len(text)} chars total)"
                        lines.append(f"    [text]")
                        for line in preview.splitlines():
                            lines.append(f"      {line}")
                    else:
                        lines.append(f"    [{part.type}] {str(part)[:200]}")

        lines.append("")

    lines.append(sep)
    lines.append("")

    with open(log_file, "a") as f:
        f.write("\n".join(lines))
    if _logger:
        _logger._main.debug(f"[debug] 请求已记录: {log_file} ({msg_count} msgs, ~{token_est} tokens)")
    else:
        print(f"\033[90m[debug] 请求已记录: {log_file} ({msg_count} msgs, ~{token_est} tokens)\033[0m")


GLOSSARY_PATH = V_AGENT_HOME / "glossary.json"


def _load_glossary() -> str:
    """加载业务术语表，返回格式化文本"""
    if not GLOSSARY_PATH.exists():
        return ""
    try:
        data = json.loads(GLOSSARY_PATH.read_text())
        lines = [f"  {en} → {zh}" for en, zh in data.items()]
        return "业务术语表 (回复时使用中文术语):\n" + "\n".join(lines)
    except Exception:
        return ""


def build_system_prompt(skill_loader: SkillLoader) -> str:
    glossary = _load_glossary()
    glossary_section = f"\n{glossary}" if glossary else ""
    return f"""你是一个专注于业务的编程助手，工作目录: {WORKDIR}。
所有回复必须使用中文。回答简洁，执行操作前先说明计划。

你的职责范围:
- 使用工具 (bash, read_file, write_file, edit_file, list_dir, http_request) 帮助用户完成编程和业务任务
- 通过已注册的接口工具 (apis) 查询和操作业务数据
- 加载技能 (skills) 获取专业知识: {skill_loader.descriptions()}
- 通过 RAG 知识库检索业务相关信息

重要规则:
- 只回答与上述职责相关的问题
- 对于闲聊、天气、新闻、娱乐等与业务无关的问题，礼貌拒绝，例如: "抱歉，这个问题超出了我的业务范围，我只能帮你处理编程和业务相关的任务。"
- 不要编造业务数据，如果不确定请使用工具查询{glossary_section}"""


def _sanitize_messages(messages: list) -> list:
    """构建脱敏副本，用于发送给 LLM。原始 messages 不变。"""
    sanitized = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            sanitized.append({**msg, "content": sanitize_content(content)})
        elif isinstance(content, list):
            new_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    new_parts.append({**part, "content": sanitize_content(str(part.get("content", "")))})
                else:
                    # ContentBlock 对象 (tool_use/text) 原样保留
                    new_parts.append(part)
            sanitized.append({**msg, "content": new_parts})
        else:
            sanitized.append(msg)
    return sanitized


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

        # 发送前统一脱敏: 构建脱敏副本，原始 messages 不变
        sanitized = _sanitize_messages(messages)

        # LLM 调用 (使用脱敏副本 + 重试机制)
        _log_request(system_prompt, sanitized, model, TOOLS, 8000)
        try:
            response = call_with_retry(
                client,
                {
                    "model": model,
                    "system": system_prompt,
                    "messages": sanitized,
                    "tools": TOOLS,
                    "max_tokens": 8000,
                },
                RetryConfig()
            )
        except Exception as e:
            # API 调用失败，返回错误信息给用户
            print(f"\n\033[31mAPI 调用失败: {e}\033[0m")
            return
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # 输出文本
            for block in response.content:
                if hasattr(block, "text"):
                    print(f"\n{block.text}")
            return

        # 工具执行（支持并行）
        results = _execute_tools(response.content, TOOL_HANDLERS, _registry)
        messages.append({"role": "user", "content": results})


def _execute_tools(content_blocks, tool_handlers, tool_registry):
    """执行工具，只读工具并行，写操作串行"""
    import time

    # 收集所有工具调用
    tool_calls = []
    for block in content_blocks:
        if block.type == "tool_use":
            tool_calls.append(block)

    if not tool_calls:
        return []

    # 单个工具：直接执行
    if len(tool_calls) == 1:
        return [_execute_one_tool(tool_calls[0], tool_handlers)]

    # 多个工具：分类执行
    read_only_calls = []
    write_calls = []

    for tc in tool_calls:
        # 从注册表获取工具检查是否只读
        tool = tool_registry.get(tc.name) if tool_registry else None
        if tool and tool.is_read_only(tc.input):
            read_only_calls.append(tc)
        else:
            write_calls.append(tc)

    results = []

    # 只读工具：并行执行
    if read_only_calls:
        start = time.time()
        parallel_results = _execute_parallel(read_only_calls, tool_handlers)
        results.extend(parallel_results)
        duration = time.time() - start
        if _logger:
            _logger._main.debug(f"并行执行 {len(read_only_calls)} 个只读工具 ({duration:.2f}s)")

    # 写操作：串行执行
    for tc in write_calls:
        results.append(_execute_one_tool(tc, tool_handlers))

    return results


def _execute_parallel(tool_calls, tool_handlers):
    """并行执行多个工具"""
    results = []
    for tc in tool_calls:
        result = _execute_one_tool(tc, tool_handlers)
        results.append(result)
    return results


def _execute_one_tool(tool_call, tool_handlers):
    """执行单个工具"""
    tool_name = tool_call.name
    tool_input = tool_call.input

    # 权限检查
    if not confirm_action(tool_name, tool_input):
        output = "[用户拒绝执行]"
    else:
        handler = tool_handlers.get(tool_name)
        try:
            output = handler(**tool_input) if handler else f"Unknown tool: {tool_name}"
        except Exception as e:
            output = f"Error: {e}"

    print(f"\033[90m> {tool_name}: {str(output)[:200]}\033[0m")

    return {
        "type": "tool_result",
        "tool_use_id": tool_call.id,
        "content": str(output)
    }


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

    if cmd == "/permissions" or cmd.startswith("/permissions "):
        permissions_args = cmd[12:].strip()
        handle_permissions_command(permissions_args)
        return True

    if cmd == "/debug":
        global _debug_enabled
        _debug_enabled = not _debug_enabled
        status = "开启" if _debug_enabled else "关闭"
        if _logger:
            _logger._main.info(f"调试日志已{status}")
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
    global _logger
    model_mgr = ModelManager()
    ctx_mgr = ContextManager()
    _logger = get_logger(V_AGENT_HOME)

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
    ApiLoader = _init_api_loader()
    _api_loader = ApiLoader(APIS_DIR)
    api_handlers, api_tools = _api_loader.load_all()
    TOOL_HANDLERS.update(api_handlers)
    TOOLS.extend(api_tools)
    # API 工具全部需要确认
    from permissions import NEEDS_CONFIRM
    for name in api_handlers:
        NEEDS_CONFIRM.add(name)
    if api_handlers:
        if _logger:
            _logger._main.info(f"已加载 {len(api_handlers)} 个接口工具")
        else:
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
