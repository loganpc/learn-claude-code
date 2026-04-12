"""工具基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from pathlib import Path


@dataclass
class ToolContext:
    """工具执行上下文"""
    cwd: Path
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """工具执行结果"""
    content: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    """工具基类"""

    name: str
    description: str

    @abstractmethod
    def get_input_schema(self) -> dict[str, Any]:
        """返回输入参数的 JSON Schema"""
        pass

    @abstractmethod
    def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        """执行工具"""
        pass

    def is_read_only(self, arguments: dict[str, Any]) -> bool:
        """是否为只读工具"""
        return False

    def to_api_schema(self) -> dict[str, Any]:
        """转换为 API 格式"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.get_input_schema()
        }
