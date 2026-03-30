# v_agent/permissions.py
import json

AUTO_APPROVE = {"read_file", "list_dir", "load_skill", "rag_query"}
NEEDS_CONFIRM = {"bash", "write_file", "edit_file", "http_request"}

_session_approved: set = set()  # 预留，暂不启用

def grant_session_permission(tool_name: str):
    """预留接口，后续可扩展"""
    _session_approved.add(tool_name)

def confirm_action(tool_name: str, params: dict) -> bool:
    """交互式确认，返回 True 执行，False 跳过"""
    if tool_name in AUTO_APPROVE or tool_name in _session_approved:
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

def show_permissions():
    """显示当前权限配置"""
    print("\n自动执行:", ", ".join(sorted(AUTO_APPROVE)))
    print("需要确认:", ", ".join(sorted(NEEDS_CONFIRM)))
    if _session_approved:
        print("会话授权:", ", ".join(sorted(_session_approved)))
