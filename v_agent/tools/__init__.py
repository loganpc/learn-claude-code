# v_agent/tools/__init__.py
"""工具系统 - 类式架构"""

import re
from pathlib import Path

from .base_new import BaseTool, ToolContext, ToolResult
from .registry import ToolRegistry
from .bash_tool import BashTool
from .file_tool import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from .http_tool import HttpRequestTool

# 导出 ApiLoader（延迟导入避免依赖 requests）
ApiLoader = None
def _init_api_loader():
    global ApiLoader
    if ApiLoader is None:
        from .api_loader import ApiLoader as _ApiLoader
        ApiLoader = _ApiLoader
    return ApiLoader


class SkillLoader:
    """内置 Skills 加载器 (保持不变)"""

    def __init__(self, skills_dir: Path):
        self.skills = {}
        if skills_dir.exists():
            for f in sorted(skills_dir.rglob("*.md")):
                text = f.read_text()
                match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
                meta, body = {}, text
                if match:
                    for line in match.group(1).strip().splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            meta[k.strip()] = v.strip()
                    body = match.group(2).strip()
                name = meta.get("name", f.stem)
                self.skills[name] = {"meta": meta, "body": body}

    def descriptions(self) -> str:
        if not self.skills:
            return "(no skills available)"
        return "\n".join(f"  - {n}: {s['meta'].get('description', '-')}"
                         for n, s in self.skills.items())

    def load(self, name: str) -> str:
        s = self.skills.get(name)
        if not s:
            return f"Error: Unknown skill '{name}'. Available: {', '.join(self.skills.keys())}"
        return f"<skill name=\"{name}\">\n{s['body']}\n</skill>"

    def list_names(self) -> list:
        return list(self.skills.keys())


# 创建工具注册表
_registry = ToolRegistry()

# 注册内置工具
_registry.register(BashTool())
_registry.register(ReadFileTool())
_registry.register(WriteFileTool())
_registry.register(EditFileTool())
_registry.register(ListDirTool())
_registry.register(HttpRequestTool())

# 兼容层：生成 TOOL_HANDLERS 和 TOOLS
TOOL_HANDLERS = _registry.create_handler_map()

# 添加 load_skill 和 rag_query 的占位符（运行时注入）
TOOL_HANDLERS["load_skill"] = lambda **kw: f"Error: load_skill not initialized"
TOOL_HANDLERS["rag_query"] = lambda **kw: f"Error: rag_query not initialized"

TOOLS = _registry.to_api_schema()

# 添加 load_skill 和 rag_query 的工具定义
TOOLS.append({
    "name": "load_skill",
    "description": "Load specialized knowledge by skill name.",
    "input_schema": {
        "type": "object",
        "properties": {"name": {"type": "string", "description": "Skill name to load"}},
        "required": ["name"]
    }
})

TOOLS.append({
    "name": "rag_query",
    "description": "Query the RAG knowledge base for relevant information.",
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "The question to search for"},
            "top_k": {"type": "integer", "description": "Number of results, default 3"}
        },
        "required": ["question"]
    }
})


# 导出
__all__ = [
    "BaseTool",
    "ToolContext",
    "ToolResult",
    "ToolRegistry",
    "SkillLoader",
    "ApiLoader",
    "TOOL_HANDLERS",
    "TOOLS",
    "_registry",  # 导出注册表，用于动态添加工具
]
