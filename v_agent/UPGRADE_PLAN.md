# V-Agent 升级计划

> 基于 OpenHarness 架构的渐进式升级方案
>
> **设计原则**: 保持 v_agent 的核心理念 (脱敏安全、内置 skills、手动 APIs)，引入生产级架构

---

## 📋 目录

- [当前架构分析](#当前架构分析)
- [设计理念 (需保留)](#设计理念-需保留)
- [升级点概览](#升级点概览)
- [详细升级方案](#详细升级方案)
- [实施计划](#实施计划)
- [升级后结构](#升级后结构)

---

## 当前架构分析

### 文件结构

```
v_agent/
├── agent.py          # 主入口，REPL 循环
├── config.py         # 模型配置管理
├── permissions.py    # 权限控制 + 脱敏 (特色功能)
├── context.py        # 上下文压缩管理
├── rag.py            # 知识检索
├── tools/            # 工具系统
│   ├── __init__.py   # 工具注册 + SkillLoader
│   ├── base.py       # 基础工具实现
│   ├── http.py       # HTTP 工具
│   ├── api_loader.py # API 工具动态加载
│   └── custom.py     # 自定义工具
└── skills/           # 内置技能
```

### 当前工具系统

```python
# 当前：函数式工具定义
TOOL_HANDLERS = {
    "bash": lambda **kw: run_bash(kw["command"]),
    "read_file": lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    ...
}

TOOLS = [
    {"name": "bash", "description": "...", "input_schema": {...}},
    {"name": "read_file", "description": "...", "input_schema": {...}},
    ...
]
```

### 当前权限系统

```python
# 三层检查
1. 敏感文件匹配 — SENSITIVE_FILE_PATTERNS
2. 工具审批列表 — AUTO_APPROVE / NEEDS_CONFIRM
3. 用户确认对话框 — confirm_action()

# 出口脱敏 (v_agent 独有特性)
- 内置规则: API key, secret, token, password
- 用户自定义: keywords + patterns
```

---

## 设计理念 (需保留)

| 理念 | 说明 | 升级策略 |
|------|------|----------|
| **脱敏安全** | 出口脱敏是 v_agent 独有特性 | ✅ 完全保留 `sanitize_content()` |
| **内置 skills** | 不支持随意安装外部 MCP | ✅ SkillLoader 保持现有逻辑 |
| **手动 APIs** | APIs 目录需要用户手动配置 | ✅ ApiLoader 保持不变 |
| **简洁 CLI** | prompt_toolkit 命令补全 | ✅ 保持交互模式 |

---

## 升级点概览

| 优先级 | 升级点 | 影响 | 复杂度 | 保持理念 |
|--------|--------|------|--------|----------|
| **P0** | 工具系统重构为类式架构 | 可扩展性 ⭐⭐⭐ | 中 | ✅ |
| **P0** | API 调用重试机制 | 稳定性 ⭐⭐⭐ | 低 | ✅ |
| **P1** | 权限系统增加路径规则 | 安全性 ⭐⭐ | 中 | ✅ |
| **P1** | 上下文压缩改进 | 性能 ⭐⭐ | 中 | ✅ |
| **P1** | 结构化日志系统 | 可维护性 ⭐⭐ | 低 | ✅ |
| **P2** | 工具并行执行 | 性能 ⭐ | 中 | ✅ |
| **P2** | 完整类型注解 | 代码质量 ⭐ | 低 | ✅ |
| **P3** | 会话持久化 | 功能增强 ⭐⭐ | 中 | ✅ |
| **P3** | 成本追踪 | 功能增强 ⭐ | 低 | ✅ |

---

## 详细升级方案

### P0-1: 工具系统重构为类式架构

**目标**: 提高可扩展性，便于添加新工具

**当前问题**:
```python
# 函数式定义，难以扩展
TOOL_HANDLERS = {
    "bash": lambda **kw: run_bash(kw["command"]),
    ...
}
```

**升级方案**:

```python
# tools/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from pathlib import Path

@dataclass
class ToolContext:
    """工具执行上下文"""
    cwd: Path
    metadata: dict[str, Any]

@dataclass
class ToolResult:
    """工具执行结果"""
    output: str
    is_error: bool = False
    metadata: dict[str, Any] = None

class BaseTool(ABC):
    """工具基类"""

    name: str
    description: str

    @abstractmethod
    def get_input_schema(self) -> dict:
        """返回输入参数的 JSON Schema"""
        pass

    @abstractmethod
    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        """执行工具"""
        pass

    def is_read_only(self, arguments: dict) -> bool:
        """是否为只读工具"""
        return False

    def to_api_schema(self) -> dict:
        """转换为 API 格式"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.get_input_schema()
        }

# tools/bash_tool.py
class BashTool(BaseTool):
    name = "bash"
    description = "Run a shell command"

    def get_input_schema(self) -> dict:
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

    async def execute(self, arguments: dict, context: ToolContext) -> ToolResult:
        # 实现逻辑
        ...

# tools/registry.py
class ToolRegistry:
    """工具注册表"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def to_api_schema(self) -> list[dict]:
        return [tool.to_api_schema() for tool in self._tools.values()]
```

---

### P0-2: API 调用重试机制

**目标**: 提高网络不稳定时的可靠性

**当前问题**: API 调用失败直接报错

**升级方案**:

```python
# api/client.py
import asyncio
import logging
from anthropic import APIError, APIStatusError
from dataclasses import dataclass

log = logging.getLogger(__name__)

@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    retryable_status_codes = {429, 500, 502, 503, 529}

async def call_with_retry(
    client,
    request: dict,
    config: RetryConfig = None
):
    """带重试的 API 调用"""
    config = config or RetryConfig()
    last_error = None

    for attempt in range(config.max_retries):
        try:
            return await client.messages.create(**request)
        except (APIError, APIStatusError) as e:
            last_error = e
            status_code = getattr(e, 'status_code', None)

            if status_code not in config.retryable_status_codes:
                log.error(f"API error (非重试类型): {e}")
                raise

            if attempt == config.max_retries - 1:
                log.error(f"达到最大重试次数: {config.max_retries}")
                raise

            delay = min(config.base_delay * (2 ** attempt), config.max_delay)
            log.warning(f"请求失败，{delay:.1f}秒后重试 ({attempt + 1}/{config.max_retries}): {e}")
            await asyncio.sleep(delay)

    raise last_error
```

---

### P1-1: 权限系统增强

**目标**: 增加路径级和命令级控制

**升级方案**:

```python
# permissions.py 增强
from dataclasses import dataclass
from fnmatch import fnmatch

@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    requires_confirmation: bool = False
    reason: str = ""

@dataclass(frozen=True)
class PathRule:
    pattern: str
    allow: bool

class PermissionChecker:
    """权限检查器"""

    def __init__(self, config: dict):
        self._config = config
        self._path_rules = self._load_path_rules()
        self._denied_commands = self._load_denied_commands()

    def _load_path_rules(self) -> list[PathRule]:
        rules = []
        for rule in self._config.get("path_rules", []):
            rules.append(PathRule(
                pattern=rule["pattern"],
                allow=rule.get("allow", True)
            ))
        return rules

    def _load_denied_commands(self) -> list[str]:
        return self._config.get("denied_commands", [])

    def evaluate(self, tool_name: str, args: dict, is_read_only: bool) -> PermissionDecision:
        """评估权限 (7 层检查)"""

        # 1. 敏感文件检查 (保留现有)
        if _is_sensitive_file(args.get("path", "")):
            return PermissionDecision(allowed=False, reason="敏感文件")

        # 2. 工具黑名单 (保留现有)
        if tool_name in self._config.get("denied_tools", []):
            return PermissionDecision(allowed=False, reason=f"{tool_name} 已被禁用")

        # 3. 路径规则 (新增)
        file_path = args.get("path")
        if file_path:
            for rule in self._path_rules:
                if fnmatch.fnmatch(file_path, rule.pattern):
                    if not rule.allow:
                        return PermissionDecision(
                            allowed=False,
                            reason=f"路径匹配拒绝规则: {rule.pattern}"
                        )

        # 4. 命令拒绝模式 (新增)
        if tool_name == "bash":
            command = args.get("command", "")
            for pattern in self._denied_commands:
                if fnmatch.fnmatch(command, pattern):
                    return PermissionDecision(
                        allowed=False,
                        reason=f"命令匹配拒绝规则: {pattern}"
                    )

        # 5. 只读工具自动允许 (保留现有)
        if is_read_only:
            return PermissionDecision(allowed=True)

        # 6. 自动批准列表 (保留现有)
        if tool_name in AUTO_APPROVE:
            return PermissionDecision(allowed=True)

        # 7. 需要确认 (保留现有)
        if tool_name in NEEDS_CONFIRM:
            return PermissionDecision(
                allowed=False,
                requires_confirmation=True
            )

        return PermissionDecision(allowed=True)
```

**配置示例**:

```json
// ~/.v-agent/config.json
{
  "permissions": {
    "denied_tools": [],
    "path_rules": [
      {"pattern": "/etc/*", "allow": false},
      {"pattern": "/tmp/*", "allow": true},
      {"pattern": "*/.ssh/*", "allow": false}
    ],
    "denied_commands": ["rm -rf /*", "sudo rm *", "dd if=* of=/dev/*"]
  }
}
```

---

### P1-2: 上下文压缩改进

**目标**: 支持可选的 LLM 驱动摘要

**当前问题**: 只有简单的滑动窗口截断

**升级方案**:

```python
# context.py 改进
from dataclasses import dataclass

@dataclass
class CompactStrategy:
    """压缩策略配置"""
    micro_compact_keep: int = 3
    auto_compact_threshold: int = 50000
    auto_compact_keep: int = 10
    enable_llm_summary: bool = False  # 可选启用 LLM 摘要

class ContextManager:
    """上下文管理器"""

    def __init__(self, strategy: CompactStrategy = None):
        self._strategy = strategy or CompactStrategy()
        # ... 现有初始化

    async def smart_compact(self, messages: list, client=None) -> bool:
        """智能压缩"""
        # 1. 先执行 micro compact
        self.micro_compact(messages)

        # 2. 检查是否需要进一步压缩
        if self.estimate_tokens(messages) <= self._strategy.auto_compact_threshold:
            return False

        # 3. 如果启用 LLM 摘要且有 client，使用 LLM 摘要
        if self._strategy.enable_llm_summary and client:
            return await self._llm_compact(messages, client)

        # 4. 否则使用滑动窗口
        return self.auto_compact(messages)

    async def _llm_compact(self, messages: list, client) -> bool:
        """使用 LLM 生成旧消息的摘要"""
        to_summarize = messages[:-self._strategy.auto_compact_keep]
        recent = messages[-self._strategy.auto_compact_keep:]

        # 提取需要摘要的文本
        summary_text = self._extract_text(to_summarize)

        # 调用 LLM 生成摘要
        summary_prompt = f"""请将以下对话历史压缩为简洁的摘要，保留关键信息：

{summary_text[:10000]}

摘要："""

        try:
            response = client.messages.create(
                model=self._model,
                max_tokens=2000,
                messages=[{"role": "user", "content": summary_prompt}]
            )
            summary = response.content[0].text
        except Exception as e:
            log.warning(f"LLM 摘要失败，回退到滑动窗口: {e}")
            return self.auto_compact(messages)

        # 替换为摘要
        messages.clear()
        messages.append({
            "role": "user",
            "content": f"[历史对话摘要]\n{summary}"
        })
        messages.append({
            "role": "assistant",
            "content": "已阅读历史摘要。"
        })
        messages.extend(recent)
        return True

    def _extract_text(self, messages: list) -> str:
        """从消息中提取文本内容"""
        texts = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            texts.append(part.get("content", ""))
                    elif hasattr(part, "type"):
                        if part.type == "text":
                            texts.append(part.text)
        return "\n\n".join(texts)
```

---

### P1-3: 结构化日志系统

**目标**: 替换 print 语句，便于调试和监控

**升级方案**:

```python
# logging_config.py
import logging
import sys
from pathlib import Path
from typing import Any

class VAgentLogger:
    """结构化日志系统"""

    def __init__(self, home: Path):
        self._home = home
        self._setup_loggers()

    def _setup_loggers(self):
        """配置多个日志输出"""
        # 主日志
        self._main = logging.getLogger("v_agent")
        self._main.setLevel(logging.DEBUG)

        # 清除现有 handlers
        self._main.handlers.clear()

        # 文件处理器
        log_file = self._home / "v_agent.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)

        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # 格式化
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        self._main.addHandler(file_handler)
        self._main.addHandler(console_handler)

        # API 请求日志 (单独文件)
        self._api = logging.getLogger("v_agent.api")
        self._api.setLevel(logging.DEBUG)
        self._api.handlers.clear()

        api_file = self._home / "api_requests.log"
        api_handler = logging.FileHandler(api_file, encoding="utf-8")
        api_handler.setFormatter(formatter)
        self._api.addHandler(api_handler)

    def log_request(self, model: str, messages: list, tools: list, **kwargs):
        """记录 API 请求"""
        self._api.info("Request: model=%s messages=%d tools=%d",
                      model, len(messages), len(tools))

    def log_response(self, model: str, input_tokens: int, output_tokens: int):
        """记录 API 响应"""
        self._api.info("Response: model=%s input=%d output=%d",
                      model, input_tokens, output_tokens)

    def log_tool_exec(self, tool_name: str, success: bool, duration: float = None):
        """记录工具执行"""
        if success:
            msg = f"✓ {tool_name}"
            if duration:
                msg += f" ({duration:.2f}s)"
            self._main.debug(msg)
        else:
            self._main.warning(f"✗ {tool_name} failed")

    def log_compact(self, before: int, after: int, method: str):
        """记录上下文压缩"""
        self._main.info(f"Compact: {before}→{after} tokens ({method})")

# 全局单例
_logger: VAgentLogger | None = None

def get_logger(home: Path = None) -> VAgentLogger:
    global _logger
    if _logger is None and home:
        _logger = VAgentLogger(home)
    return _logger
```

---

### P2-1: 工具并行执行

**目标**: 多个工具调用时并行执行

**升级方案**:

```python
# agent.py 中的工具执行逻辑
import asyncio

async def execute_tools(
    tool_calls: list,
    registry: ToolRegistry,
    permission_checker: PermissionChecker,
    sanitize_fn: callable
) -> list:
    """并行或串行执行工具"""

    async def execute_one(tc) -> dict:
        """执行单个工具"""
        tool_name = tc.name
        args = tc.input

        # 获取工具
        tool = registry.get(tool_name)
        if not tool:
            return {
                "tool_use_id": tc.id,
                "content": f"未知工具: {tool_name}",
                "is_error": True
            }

        # 权限检查
        decision = permission_checker.evaluate(
            tool_name,
            args,
            tool.is_read_only(args)
        )

        if not decision.allowed:
            if decision.requires_confirmation:
                # 显示确认对话框
                confirmed = confirm_action(tool_name, args)
                if not confirmed:
                    return {
                        "tool_use_id": tc.id,
                        "content": "用户拒绝执行",
                        "is_error": True
                    }
            else:
                return {
                    "tool_use_id": tc.id,
                    "content": decision.reason,
                    "is_error": True
                }

        # 执行工具
        try:
            result = await tool.execute(
                args,
                ToolContext(cwd=Path.cwd(), metadata={})
            )
            # 脱敏
            result.content = sanitize_fn(result.content)
            return {
                "tool_use_id": tc.id,
                "content": result.content,
                "is_error": result.is_error
            }
        except Exception as e:
            return {
                "tool_use_id": tc.id,
                "content": f"工具执行失败: {e}",
                "is_error": True
            }

    # 单个工具：直接执行
    if len(tool_calls) == 1:
        result = await execute_one(tool_calls[0])
        return [result]

    # 多个工具：并行执行
    results = await asyncio.gather(
        *[execute_one(tc) for tc in tool_calls],
        return_exceptions=True
    )

    # 处理异常
    formatted_results = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            formatted_results.append({
                "tool_use_id": tool_calls[i].id,
                "content": f"执行异常: {r}",
                "is_error": True
            })
        else:
            formatted_results.append(r)

    return formatted_results
```

---

### P2-2: 完整类型注解

**目标**: 提高代码可维护性

**升级方案** 在所有文件中添加类型注解:

```python
# config.py
from typing import Optional
from anthropic import Anthropic

class ModelManager:
    def _load_or_create(self) -> dict[str, any]: ...
    def switch_model(self, model_id: str) -> None: ...
    def get_client(self) -> Anthropic: ...
    def get_model_id(self) -> str: ...

# permissions.py
def confirm_action(tool_name: str, params: dict) -> bool: ...
def sanitize_content(text: str) -> str: ...
def _is_sensitive_file(path: str) -> bool: ...
def load_redact_config() -> None: ...

# context.py
def estimate_tokens(self, messages: list) -> int: ...
def micro_compact(self, messages: list) -> None: ...
def auto_compact(self, messages: list) -> bool: ...
```

---

### P3-1: 会话持久化

**目标**: 支持会话保存和恢复

**升级方案**:

```python
# session.py
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import json

@dataclass
class SessionState:
    """会话状态"""
    session_id: str
    created_at: str
    model: str
    messages: list
    total_tokens: int = 0
    last_compact: str = None

class SessionManager:
    """会话持久化管理"""

    def __init__(self, home: Path):
        self._home = home
        self._session_dir = home / "sessions"
        self._session_dir.mkdir(parents=True, exist_ok=True)
        self._current: SessionState | None = None

    def new_session(self, model: str) -> SessionState:
        """创建新会话"""
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._current = SessionState(
            session_id=session_id,
            created_at=datetime.now().isoformat(),
            model=model,
            messages=[]
        )
        self._save_session()
        return self._current

    def _save_session(self) -> None:
        """保存当前会话"""
        if not self._current:
            return
        session_file = self._session_dir / f"{self._current.session_id}.json"
        session_file.write_text(
            json.dumps(asdict(self._current), indent=2, ensure_ascii=False)
        )

    def update_messages(self, messages: list) -> None:
        """更新会话消息"""
        if self._current:
            self._current.messages = messages
            self._save_session()

    def list_sessions(self) -> list[SessionState]:
        """列出所有会话"""
        sessions = []
        for f in self._session_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                sessions.append(SessionState(**data))
            except Exception:
                continue
        return sorted(sessions, key=lambda s: s.created_at, reverse=True)

    def load_session(self, session_id: str) -> SessionState | None:
        """加载指定会话"""
        session_file = self._session_dir / f"{session_id}.json"
        if not session_file.exists():
            return None
        data = json.loads(session_file.read_text())
        self._current = SessionState(**data)
        return self._current

    def get_current(self) -> SessionState | None:
        """获取当前会话"""
        return self._current
```

---

### P3-2: 成本追踪

**目标**: 追踪 API 调用成本

**升级方案**:

```python
# cost_tracker.py
from dataclasses import dataclass
from collections import defaultdict

@dataclass
class UsageSnapshot:
    """使用量快照"""
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

class CostTracker:
    """成本追踪"""

    # 模型定价 (元/百万 tokens)
    PRICING = {
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
        "claude-opus-4-6": {"input": 15.0, "output": 75.0},
        "claude-haiku-4-5": {"input": 0.8, "output": 4.0},
        "deepseek-chat": {"input": 0.1, "output": 0.1},
        "glm-4-plus": {"input": 1.0, "output": 1.0},
    }

    def __init__(self):
        self._total: dict[str, UsageSnapshot] = defaultdict(
            lambda: UsageSnapshot(0, 0)
        )

    def add(self, model: str, usage: UsageSnapshot) -> None:
        """添加使用量"""
        current = self._total[model]
        self._total[model] = UsageSnapshot(
            input_tokens=current.input_tokens + usage.input_tokens,
            output_tokens=current.output_tokens + usage.output_tokens,
            cache_read_tokens=current.cache_read_tokens + usage.cache_read_tokens,
            cache_write_tokens=current.cache_write_tokens + usage.cache_write_tokens,
        )

    def get_total_cost(self) -> float:
        """计算总成本"""
        total = 0.0
        for model, usage in self._total.items():
            pricing = self.PRICING.get(model, {"input": 0, "output": 0})
            total += (
                usage.input_tokens * pricing["input"] / 1_000_000 +
                usage.output_tokens * pricing["output"] / 1_000_000
            )
        return total

    def format_summary(self) -> str:
        """格式化输出摘要"""
        lines = ["\n📊 使用量统计:"]
        for model, usage in self._total.items():
            total = usage.input_tokens + usage.output_tokens
            lines.append(f"  {model}:")
            lines.append(f"    输入: {usage.input_tokens:,} tokens")
            lines.append(f"    输出: {usage.output_tokens:,} tokens")
            lines.append(f"    总计: {total:,} tokens")

        cost = self.get_total_cost()
        lines.append(f"\n  预估成本: ¥{cost:.4f}")
        return "\n".join(lines)
```

---

## 实施计划

| 阶段 | 升级点 | 预计工作量 | 依赖 |
|------|--------|------------|------|
| **Phase 1** | P0-1: 工具系统重构 | 2-3 小时 | - |
| | P0-2: API 重试机制 | 1 小时 | - |
| **Phase 2** | P1-1: 权限系统增强 | 1-2 小时 | Phase 1 |
| | P1-2: 上下文压缩改进 | 1-2 小时 | - |
| | P1-3: 结构化日志 | 1 小时 | - |
| **Phase 3** | P2-1: 工具并行执行 | 1 小时 | Phase 1 |
| | P2-2: 类型注解 | 1 小时 | - |
| **Phase 4** | P3-1: 会话持久化 | 1-2 小时 | - |
| | P3-2: 成本追踪 | 1 小时 | - |

**总工作量**: 约 12-16 小时

---

## 升级后结构

```
v_agent/
├── agent.py              # 主入口 (增强版)
├── config.py             # 配置管理 (增强)
├── permissions.py        # 权限 + 脱敏 (保留脱敏，增强权限)
├── context.py            # 上下文管理 (改进压缩策略)
├── rag.py                # 知识检索 (保持)
├── session.py            # [新增] 会话持久化
├── cost_tracker.py       # [新增] 成本追踪
├── logging_config.py     # [新增] 结构化日志
│
├── api/
│   └── client.py         # [新增] API 客户端 + 重试
│
├── tools/
│   ├── __init__.py       # 工具注册 (重构)
│   ├── base.py           # [新增] 工具基类
│   ├── bash_tool.py      # [拆分] bash 工具
│   ├── file_tool.py      # [拆分] 文件操作工具
│   ├── http_tool.py      # [拆分] HTTP 工具
│   ├── registry.py       # [新增] 工具注册表
│   ├── api_loader.py     # API 加载器 (保持)
│   └── custom.py         # 自定义工具 (保持)
│
├── skills/               # 内置技能 (保持)
│   ├── agent-builder/
│   ├── code-review/
│   └── ...
│
└── UPGRADE_PLAN.md       # 本文档
```

---

## 保持的设计理念

| 理念 | 说明 | 升级中的体现 |
|------|------|--------------|
| **脱敏安全** | 出口脱敏是 v_agent 独有特性 | `sanitize_content()` 保持不变，在所有工具输出后调用 |
| **内置 skills** | 不支持随意安装外部 MCP | `SkillLoader` 保持现有逻辑，仅从 `skills/` 目录加载 |
| **手动 APIs** | APIs 目录需要用户手动配置 | `ApiLoader` 保持不变，从 `~/.v-agent/apis/` 加载 |
| **简洁 CLI** | prompt_toolkit 命令补全 | 命令补全和交互模式完全保持 |

---

## 与 OpenHarness 的差异

| 特性 | OpenHarness | v_agent (升级后) | 说明 |
|------|-------------|------------------|------|
| 工具系统 | 类式架构 | 类式架构 | ✅ 对齐 |
| API 重试 | 指数退避 | 指数退避 | ✅ 对齐 |
| 权限系统 | 7 层检查 | 7 层检查 | ✅ 对齐 |
| 上下文压缩 | LLM 驱动 | 可选 LLM | ⚠️ v_agent 保留本地优先 |
| 脱敏系统 | 无 | **保留** | ⭐ v_agent 特色 |
| MCP 支持 | 完整支持 | **不支持** | ⭐ v_agent 设计理念 |
| Skills | 插件式 | 内置 | ⭐ v_agent 设计理念 |
| UI | React Ink | prompt_toolkit | ⭐ v_agent 保持简洁 |

---

## 验收标准

每个 Phase 完成后需要验证：

1. **功能完整性**: 所有现有功能正常工作
2. **脱敏正确性**: `sanitize_content()` 仍然正确执行
3. **向后兼容**: 现有配置文件无需修改
4. **日志质量**: 关键操作有日志记录
5. **错误处理**: 网络错误有适当的重试

---

## 参考资料

- OpenHarness: https://github.com/HKUDS/OpenHarness
- 当前 v_agent 代码: `~/Work/python/learn-claude-code/v_agent/`
- 学习教程: `~/Work/python/learn-claude-code/agents/`

---

*文档版本: 1.0*
*创建时间: 2026-04-09*
