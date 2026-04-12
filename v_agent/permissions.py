# v_agent/permissions.py
import json
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from config import V_AGENT_HOME

# === 权限配置 ===
PERMISSIONS_CONFIG_PATH = V_AGENT_HOME / "permissions.json"

# 默认权限配置
DEFAULT_PERMISSIONS = {
    "auto_approve": ["read_file", "list_dir", "load_skill", "rag_query"],
    "needs_confirm": ["bash", "write_file", "edit_file", "http_request"],
    "denied_tools": [],
    "path_rules": [
        {"pattern": "/etc/*", "allow": False},
        {"pattern": "*/.ssh/*", "allow": False}
    ],
    "denied_commands": ["rm -rf /*", "sudo rm *", "dd if=* of=/dev/*"]
}

# 加载权限配置
def _load_permissions_config() -> dict:
    """加载权限配置"""
    if not PERMISSIONS_CONFIG_PATH.exists():
        return DEFAULT_PERMISSIONS.copy()

    try:
        with open(PERMISSIONS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"\033[31m[permissions] 配置加载失败: {e}\033[0m")
        return DEFAULT_PERMISSIONS.copy()

# 创建默认权限配置
def _create_default_permissions():
    """创建默认权限配置文件"""
    if PERMISSIONS_CONFIG_PATH.exists():
        return

    PERMISSIONS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PERMISSIONS_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(DEFAULT_PERMISSIONS, f, indent=2, ensure_ascii=False)
    print(f"\033[32m[permissions] 已创建默认配置: {PERMISSIONS_CONFIG_PATH}\033[0m")

# 加载配置
_permissions_config = _load_permissions_config()
AUTO_APPROVE = set(_permissions_config.get("auto_approve", []))
NEEDS_CONFIRM = set(_permissions_config.get("needs_confirm", []))
DENIED_TOOLS = set(_permissions_config.get("denied_tools", []))
PATH_RULES = _permissions_config.get("path_rules", [])
DENIED_COMMANDS = _permissions_config.get("denied_commands", [])

_session_approved: set = set()  # 预留，暂不启用


# === 方向1: 敏感文件拦截 ===
SENSITIVE_FILE_PATTERNS = [
    ".env", ".env.*",
    "config.json",
    "*.pem", "*.key", "*.p12", "*.pfx",
    "id_rsa", "id_rsa.*", "id_ed25519", "id_ed25519.*",
    "*credential*", "*secret*",
]

def _is_sensitive_file(path: str) -> bool:
    """检查文件名是否匹配敏感文件模式"""
    name = Path(path).name.lower()
    for pattern in SENSITIVE_FILE_PATTERNS:
        regex = pattern.replace(".", r"\.").replace("*", ".*")
        if re.fullmatch(regex, name):
            return True
    return False


# === 方向2: 出口脱敏 ===

REDACT_CONFIG_PATH = V_AGENT_HOME / "redact.json"

# --- 角色模板 ---
_ROLE_TEMPLATES = {
    "dba": {
        "name": "DBA (SQL、用户数据)",
        "config": {
            "keywords": ["user_id", "phone", "email", "id_card", "password"],
            "patterns": [
                {"name": "手机号", "pattern": r"(?<!\d)1[3-9]\d{9}(?!\d)"},
                {"name": "身份证", "pattern": r"(?<![a-zA-Z0-9])\d{17}[\dXx](?!\d)"},
            ]
        }
    },
    "finance": {
        "name": "财务 (金额、银行卡)",
        "config": {
            "keywords": ["salary", "balance", "revenue", "profit", "amount", "price"],
            "patterns": [
                {"name": "银行卡号", "pattern": r"(?<!\d)\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}(?!\d)"},
                {"name": "手机号", "pattern": r"(?<!\d)1[3-9]\d{9}(?!\d)"},
            ]
        }
    },
    "product": {
        "name": "产品 (用户信息、业务数据)",
        "config": {
            "keywords": ["username", "phone", "email", "address", "id_card"],
            "patterns": [
                {"name": "手机号", "pattern": r"(?<!\d)1[3-9]\d{9}(?!\d)"},
                {"name": "身份证", "pattern": r"(?<![a-zA-Z0-9])\d{17}[\dXx](?!\d)"},
            ]
        }
    },
    "empty": {
        "name": "空白 (从零开始)",
        "config": {
            "keywords": [],
            "patterns": []
        }
    },
}

# --- 内置规则 (始终生效) ---
_SENSITIVE_KEYS = (
    r'(?:api[_-]?key|secret[_-]?key|access[_-]?key|auth[_-]?token'
    r'|password|passwd|token|secret|credential)'
)
_CODE_NEGATIVE = (
    r'(?!(?:input|os\.|getpass|environ|config|model_|None|True|False|null|\{|\(|self\.))'
)
_SECRET_VALUE = r'([a-zA-Z0-9\-_\.+/]{8,})'

_BUILTIN_PATTERNS = [
    # 规则1: key=value 或 key: value
    (re.compile(_SENSITIVE_KEYS + r'\s*[=:]\s*["\x27]?' + _CODE_NEGATIVE + _SECRET_VALUE, re.I),
     r'[REDACTED]'),
    # 规则2: JSON "key": "value"
    (re.compile(r'"' + _SENSITIVE_KEYS + r'"\s*:\s*"' + _CODE_NEGATIVE + _SECRET_VALUE, re.I),
     r'"\1": "[REDACTED]'),
    # sk-xxx 前缀密钥
    (re.compile(r'\b(sk-[a-zA-Z0-9]{8})[a-zA-Z0-9]{20,}'), r'\1...[REDACTED]'),
    # Bearer token
    (re.compile(r'(Bearer\s+)[^\s"\x27]{20,}'), r'\1[REDACTED]'),
    # hex.base64 (GLM key 格式)
    (re.compile(r'\b([a-f0-9]{32,})\.[a-zA-Z0-9]{10,}\b'), r'[REDACTED:api_key]'),
]

# --- 用户自定义规则 (从 redact.json 加载) ---
_custom_patterns: list = []  # [(compiled_regex, replacement)]
_custom_config: dict = {}    # 原始配置，用于 show_redact


def _build_keyword_pattern(keyword: str):
    """从关键字构建 key=value 和 JSON 两种匹配规则"""
    kw = re.escape(keyword)
    rules = []
    # key=value / key: value
    rules.append((
        re.compile(kw + r'\s*[=:]\s*["\x27]?' + _CODE_NEGATIVE + r'([^\s"\x27,;\n]{1,})', re.I),
        f'[REDACTED:{keyword}]'
    ))
    # JSON "key": "value"
    rules.append((
        re.compile(r'"' + kw + r'"\s*:\s*"' + _CODE_NEGATIVE + r'([^"]{1,})', re.I),
        f'"{keyword}": "[REDACTED:{keyword}]'
    ))
    return rules


def load_redact_config():
    """加载用户自定义脱敏配置"""
    global _custom_patterns, _custom_config
    _custom_patterns = []
    _custom_config = {}

    if not REDACT_CONFIG_PATH.exists():
        return

    try:
        _custom_config = json.loads(REDACT_CONFIG_PATH.read_text())
    except Exception as e:
        print(f"\033[31m[redact] 配置加载失败: {e}\033[0m")
        return

    # keywords → 自动生成 key=value 匹配规则
    for kw in _custom_config.get("keywords", []):
        _custom_patterns.extend(_build_keyword_pattern(kw))

    # patterns → 用户自定义正则
    for item in _custom_config.get("patterns", []):
        try:
            name = item.get("name", "unknown")
            compiled = re.compile(item["pattern"])
            replacement = f'[REDACTED:{name}]'
            _custom_patterns.append((compiled, replacement))
        except Exception as e:
            print(f"\033[31m[redact] 正则编译失败 '{item.get('name', '?')}': {e}\033[0m")


def _save_redact_config(config: dict):
    """保存脱敏配置并重新加载"""
    V_AGENT_HOME.mkdir(parents=True, exist_ok=True)
    REDACT_CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    load_redact_config()


def sanitize_content(text: str) -> str:
    """脱敏处理: 内置规则 + 用户自定义规则"""
    # 内置规则
    for pattern, replacement in _BUILTIN_PATTERNS:
        text = pattern.sub(replacement, text)
    # 用户自定义规则
    for pattern, replacement in _custom_patterns:
        text = pattern.sub(replacement, text)
    return text


# === /permissions 子命令 ===

def show_permissions():
    """显示当前权限配置"""
    print("\n\033[36m[权限配置]\033[0m")
    print(f"  自动执行: {', '.join(sorted(AUTO_APPROVE))}")
    print(f"  需要确认: {', '.join(sorted(NEEDS_CONFIRM))}")
    print(f"  已禁用工具: {', '.join(sorted(DENIED_TOOLS)) or '(无)'}")

    if PATH_RULES:
        print(f"  路径规则:")
        for rule in PATH_RULES:
            status = "\033[32m允许\033[0m" if rule.get("allow") else "\033[31m拒绝\033[0m"
            print(f"    - {rule['pattern']}: {status}")
    else:
        print(f"  路径规则: (无)")

    if DENIED_COMMANDS:
        print(f"  命令拒绝规则: {', '.join(DENIED_COMMANDS)}")
    else:
        print(f"  命令拒绝规则: (无)")

    print(f"\n配置文件: {PERMISSIONS_CONFIG_PATH}")


def handle_permissions_command(args: str) -> bool:
    """处理 /permissions 子命令，返回 True 表示已处理"""
    args = args.strip()

    if args == "" or args == "show":
        show_permissions()
        return True

    print("用法:")
    print("  /permissions              查看当前配置")
    print("  /permissions show         同上")
    # 更多子命令可以后续添加
    return True


# === /redact 子命令 (保持不变) ===

def redact_init():
    """交互式初始化脱敏配置"""
    if REDACT_CONFIG_PATH.exists():
        print(f"\n\033[33m已存在配置: {REDACT_CONFIG_PATH}\033[0m")
        try:
            ans = input("覆盖现有配置? [y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return
        if ans != "y":
            print("已取消")
            return

    roles = list(_ROLE_TEMPLATES.items())
    print("\n选择角色模板:")
    for i, (key, tmpl) in enumerate(roles, 1):
        print(f"  {i}. {tmpl['name']}")

    while True:
        try:
            choice = int(input("\n选择 (数字): ")) - 1
            if 0 <= choice < len(roles):
                break
        except (ValueError, EOFError, KeyboardInterrupt):
            print("已取消")
            return
        print("无效选择，请重试")

    role_key, role = roles[choice]
    config = role["config"].copy()
    _save_redact_config(config)

    print(f"\n\033[32m已生成 {REDACT_CONFIG_PATH} (基于 {role['name']} 模板)\033[0m")
    print("可以继续使用以下命令调整:")
    print("  /redact add keyword <字段名>")
    print("  /redact add pattern <名称> <正则>")
    print("  /redact show")


def redact_add(args: str):
    """添加脱敏规则"""
    parts = args.split(None, 2)
    if len(parts) < 2:
        print("用法:")
        print("  /redact add keyword <字段名>")
        print("  /redact add pattern <名称> <正则>")
        return

    # 加载现有配置或创建新的
    if REDACT_CONFIG_PATH.exists():
        try:
            config = json.loads(REDACT_CONFIG_PATH.read_text())
        except Exception:
            config = {"keywords": [], "patterns": []}
    else:
        config = {"keywords": [], "patterns": []}

    kind = parts[0]
    if kind == "keyword":
        kw = parts[1]
        if kw in config.get("keywords", []):
            print(f"关键字 '{kw}' 已存在")
            return
        config.setdefault("keywords", []).append(kw)
        _save_redact_config(config)
        print(f"\033[32m已添加关键字: {kw}\033[0m")

    elif kind == "pattern":
        if len(parts) < 3:
            print("用法: /redact add pattern <名称> <正则>")
            return
        name = parts[1]
        regex = parts[2]
        # 验证正则
        try:
            re.compile(regex)
        except re.error as e:
            print(f"\033[31m正则语法错误: {e}\033[0m")
            return
        config.setdefault("patterns", []).append({"name": name, "pattern": regex})
        _save_redact_config(config)
        print(f"\033[32m已添加正则: {name} -> {regex}\033[0m")

    else:
        print(f"未知类型: {kind}，支持 keyword 或 pattern")


def redact_remove(args: str):
    """移除脱敏规则"""
    parts = args.split(None, 1)
    if len(parts) < 2:
        print("用法:")
        print("  /redact rm keyword <字段名>")
        print("  /redact rm pattern <名称>")
        return

    if not REDACT_CONFIG_PATH.exists():
        print("尚未配置脱敏规则")
        return

    try:
        config = json.loads(REDACT_CONFIG_PATH.read_text())
    except Exception:
        print("配置文件损坏")
        return

    kind = parts[0]
    name = parts[1]

    if kind == "keyword":
        keywords = config.get("keywords", [])
        if name not in keywords:
            print(f"关键字 '{name}' 不存在")
            return
        keywords.remove(name)
        _save_redact_config(config)
        print(f"\033[32m已移除关键字: {name}\033[0m")

    elif kind == "pattern":
        patterns = config.get("patterns", [])
        found = [p for p in patterns if p.get("name") == name]
        if not found:
            print(f"正则 '{name}' 不存在")
            return
        patterns.remove(found[0])
        _save_redact_config(config)
        print(f"\033[32m已移除正则: {name}\033[0m")

    else:
        print(f"未知类型: {kind}，支持 keyword 或 pattern")


def show_redact():
    """显示当前脱敏规则"""
    print("\n\033[36m[内置规则]\033[0m (始终生效)")
    print("  API key / secret / token / password 等字段值")
    print("  sk-xxx 前缀密钥 / Bearer token / hex.base64 格式密钥")

    if not _custom_config:
        print(f"\n\033[36m[自定义规则]\033[0m 未配置")
        print(f"  使用 /redact init 初始化，或 /redact add 添加规则")
    else:
        keywords = _custom_config.get("keywords", [])
        patterns = _custom_config.get("patterns", [])
        print(f"\n\033[36m[自定义规则]\033[0m 来源: {REDACT_CONFIG_PATH}")
        if keywords:
            print(f"  关键字 ({len(keywords)}): {', '.join(keywords)}")
        if patterns:
            print(f"  正则 ({len(patterns)}):")
            for p in patterns:
                print(f"    - {p.get('name', '?')}: {p.get('pattern', '?')}")

    print(f"\n配置文件: {REDACT_CONFIG_PATH}")


def handle_redact_command(args: str) -> bool:
    """处理 /redact 子命令，返回 True 表示已处理"""
    args = args.strip()

    if args == "" or args == "show":
        show_redact()
        return True

    if args == "init":
        redact_init()
        return True

    if args.startswith("add "):
        redact_add(args[4:])
        return True

    if args.startswith("rm "):
        redact_remove(args[3:])
        return True

    print("用法:")
    print("  /redact              查看当前规则")
    print("  /redact init         交互式初始化 (选择角色模板)")
    print("  /redact add keyword <字段名>")
    print("  /redact add pattern <名称> <正则>")
    print("  /redact rm keyword <字段名>")
    print("  /redact rm pattern <名称>")
    return True


# === 权限检查 ===

def grant_session_permission(tool_name: str):
    """预留接口，后续可扩展"""
    _session_approved.add(tool_name)


def confirm_action(tool_name: str, params: dict) -> bool:
    """交互式确认，返回 True 执行，False 跳过"""
    # 检查是否被禁用
    if tool_name in DENIED_TOOLS:
        print(f"\033[31m[权限拒绝] {tool_name} 已被禁用\033[0m")
        return False

    # 检查路径规则
    if "path" in params:
        file_path = params["path"]
        for rule in PATH_RULES:
            if fnmatch.fnmatch(file_path, rule["pattern"]):
                if not rule.get("allow", True):
                    print(f"\033[31m[权限拒绝] 路径匹配拒绝规则: {rule['pattern']}\033[0m")
                    return False

    # 检查命令拒绝规则
    if tool_name == "bash":
        command = params.get("command", "")
        for pattern in DENIED_COMMANDS:
            if fnmatch.fnmatch(command, pattern):
                print(f"\033[31m[权限拒绝] 命令匹配拒绝规则: {pattern}\033[0m")
                return False

    # 方向1: read_file 遇到敏感文件，降级为需要确认
    if tool_name == "read_file" and _is_sensitive_file(params.get("path", "")):
        print(f"\n\033[31m[敏感文件] {params['path']}\033[0m")
        print("该文件可能包含密钥等敏感信息，读取内容将发送给模型。")
    elif tool_name in AUTO_APPROVE or tool_name in _session_approved:
        return True
    if tool_name not in NEEDS_CONFIRM:
        # 未知工具默认需要确认
        pass

    print(f"\n\033[33m[权限请求] {tool_name}\033[0m")
    # 参数预览: 截断过长内容
    preview = json.dumps(params, ensure_ascii=False, indent=2)
    if len(preview) > 500:
        preview = preview[:500] + "\n... (truncated)"
    print(f"参数: {preview}")

    while True:
        try:
            ans = input("\033[33m执行? [y/n]: \033[0m").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if ans == 'y':
            return True
        elif ans == 'n':
            return False


def _reload_permissions():
    """重新加载权限配置"""
    global _permissions_config, AUTO_APPROVE, NEEDS_CONFIRM, DENIED_TOOLS, PATH_RULES, DENIED_COMMANDS
    _permissions_config = _load_permissions_config()
    AUTO_APPROVE = set(_permissions_config.get("auto_approve", []))
    NEEDS_CONFIRM = set(_permissions_config.get("needs_confirm", []))
    DENIED_TOOLS = set(_permissions_config.get("denied_tools", []))
    PATH_RULES = _permissions_config.get("path_rules", [])
    DENIED_COMMANDS = _permissions_config.get("denied_commands", [])
