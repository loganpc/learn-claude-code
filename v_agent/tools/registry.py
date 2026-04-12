"""工具注册表"""

from typing import Dict, List, Any

from .base_new import BaseTool


class ToolRegistry:
    """工具注册表"""

    def __init__(self) -> None:
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> List[BaseTool]:
        """列出所有工具"""
        return list(self._tools.values())

    def to_api_schema(self) -> List[dict[str, Any]]:
        """转换为 API 格式"""
        return [tool.to_api_schema() for tool in self._tools.values()]

    def create_handler_map(self) -> dict[str, Any]:
        """创建处理器映射（兼容旧代码）"""
        def make_handler(tool: BaseTool):
            def handler(**kw: Any) -> str:
                from .base_new import ToolContext
                from pathlib import Path
                result = tool.execute(kw, ToolContext(cwd=Path.cwd(), metadata={}))
                return result.content
            return handler

        return {tool.name: make_handler(tool) for tool in self._tools.values()}
