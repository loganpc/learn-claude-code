"""文件操作工具"""

from pathlib import Path
from typing import Optional

from .base_new import BaseTool, ToolContext, ToolResult

WORKDIR = Path.cwd()


def safe_path(p: str) -> Path:
    """检查路径是否在工作目录内"""
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


class ReadFileTool(BaseTool):
    """读取文件工具"""

    name: str = "read_file"
    description: str = "Read file contents."

    def get_input_schema(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "limit": {"type": "integer", "description": "Max lines to read"}
            },
            "required": ["path"]
        }

    def is_read_only(self, arguments: dict[str, object]) -> bool:
        return True

    def execute(self, arguments: dict[str, object], context: ToolContext) -> ToolResult:
        try:
            path = arguments.get("path", "")
            if not isinstance(path, str):
                return ToolResult(content="Error: path must be a string", is_error=True)

            limit = arguments.get("limit")
            if limit is not None and not isinstance(limit, int):
                return ToolResult(content="Error: limit must be an integer", is_error=True)

            lines = safe_path(path).read_text().splitlines()
            if limit and isinstance(limit, int) and limit < len(lines):
                lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
            content = "\n".join(lines)[:50000]
            return ToolResult(content=content)
        except Exception as e:
            return ToolResult(content=f"Error: {e}", is_error=True)


class WriteFileTool(BaseTool):
    """写入文件工具"""

    name: str = "write_file"
    description: str = "Write content to file."

    def get_input_schema(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }

    def execute(self, arguments: dict[str, object], context: ToolContext) -> ToolResult:
        try:
            path = arguments.get("path", "")
            content = arguments.get("content", "")
            if not isinstance(path, str) or not isinstance(content, str):
                return ToolResult(content="Error: path and content must be strings", is_error=True)

            fp = safe_path(path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content)
            return ToolResult(content=f"Wrote {len(content)} bytes to {path}")
        except Exception as e:
            return ToolResult(content=f"Error: {e}", is_error=True)


class EditFileTool(BaseTool):
    """编辑文件工具"""

    name: str = "edit_file"
    description: str = "Replace exact text in file."

    def get_input_schema(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"}
            },
            "required": ["path", "old_text", "new_text"]
        }

    def execute(self, arguments: dict[str, object], context: ToolContext) -> ToolResult:
        try:
            path = arguments.get("path", "")
            old_text = arguments.get("old_text", "")
            new_text = arguments.get("new_text", "")
            if not all(isinstance(x, str) for x in [path, old_text, new_text]):
                return ToolResult(content="Error: path, old_text, and new_text must be strings", is_error=True)

            fp = safe_path(path)
            c = fp.read_text()
            if old_text not in c:
                return ToolResult(content=f"Error: Text not found in {path}", is_error=True)
            fp.write_text(c.replace(old_text, new_text, 1))
            return ToolResult(content=f"Edited {path}")
        except Exception as e:
            return ToolResult(content=f"Error: {e}", is_error=True)


class ListDirTool(BaseTool):
    """列出目录工具"""

    name: str = "list_dir"
    description: str = "List directory contents."

    def get_input_schema(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path, defaults to current dir"
                }
            }
        }

    def is_read_only(self, arguments: dict[str, object]) -> bool:
        return True

    def execute(self, arguments: dict[str, object], context: ToolContext) -> ToolResult:
        try:
            path = arguments.get("path", ".")
            if not isinstance(path, str):
                return ToolResult(content="Error: path must be a string", is_error=True)

            target = safe_path(path)
            items = sorted(target.iterdir())
            lines = []
            for item in items:
                prefix = "d " if item.is_dir() else "f "
                lines.append(f"{prefix}{item.name}")
            content = "\n".join(lines) if lines else "(empty directory)"
            return ToolResult(content=content)
        except Exception as e:
            return ToolResult(content=f"Error: {e}", is_error=True)
