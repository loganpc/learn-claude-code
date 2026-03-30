#!/usr/bin/env python3
"""V-Agent: 安全的命令行编程助手"""

import json
import sys
from pathlib import Path

# Add v_agent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import ModelManager
from permissions import confirm_action, show_permissions
from context import ContextManager
from rag import RAG
from tools import TOOLS, TOOL_HANDLERS, SkillLoader

WORKDIR = Path.cwd()
SKILLS_DIR = Path(__file__).parent / "skills"


def build_system_prompt(skill_loader: SkillLoader) -> str:
    return f"""You are a coding assistant at {WORKDIR}. Use tools to help the user.
Available skills (use load_skill to load): {skill_loader.descriptions()}
Always explain your plan before executing. Be concise."""


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
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output)
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

    return False


def main():
    # 初始化
    model_mgr = ModelManager()
    ctx_mgr = ContextManager()
    skill_loader = SkillLoader(SKILLS_DIR)

    # RAG 配置
    rag_config = model_mgr.get_rag_config()
    rag = RAG(rag_config.get("endpoint") if rag_config.get("enabled") else None)

    # 注册 skill 和 rag 的 handler (动态注入)
    TOOL_HANDLERS["load_skill"] = lambda **kw: skill_loader.load(kw["name"])
    TOOL_HANDLERS["rag_query"] = lambda **kw: rag.query(kw["question"], kw.get("top_k", 3))

    system_prompt = build_system_prompt(skill_loader)

    print(f"\033[36mV-Agent | Model: {model_mgr.get_model_id()} | /help for commands\033[0m\n")

    history = []
    while True:
        try:
            query = input("\033[36mv-agent >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if query.strip().lower() in ("q", "exit", ""):
            break

        if query.startswith("/"):
            if handle_repl_command(query, model_mgr, ctx_mgr, history, skill_loader):
                continue

        history.append({"role": "user", "content": query})
        agent_loop(history, model_mgr, ctx_mgr, system_prompt)
        print()


if __name__ == "__main__":
    main()
