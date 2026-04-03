#!/usr/bin/env python3
"""批量安装 API 工具配置到 .v-agent/apis/"""

import json
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SOURCE_DIR = SCRIPT_DIR / "apis"
TARGET_DIR = SCRIPT_DIR / ".v-agent" / "apis"

REQUIRED_FIELDS = {"name", "method", "url"}
VALID_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}


def validate(file: Path) -> tuple[dict | None, str | None]:
    """校验 JSON 文件，返回 (data, error)"""
    try:
        data = json.loads(file.read_text())
    except json.JSONDecodeError as e:
        return None, f"JSON 格式错误: {e}"

    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        return None, f"缺少必填字段: {', '.join(sorted(missing))}"

    method = data["method"].upper()
    if method not in VALID_METHODS:
        return None, f"无效的 method: {data['method']} (支持: {', '.join(VALID_METHODS)})"

    return data, None


def main():
    if not SOURCE_DIR.exists():
        print(f"源目录不存在: {SOURCE_DIR}")
        print(f"请在 {SOURCE_DIR}/ 下放置 API 配置 JSON 文件")
        sys.exit(1)

    files = sorted(SOURCE_DIR.glob("*.json"))
    if not files:
        print(f"源目录为空: {SOURCE_DIR}/")
        print("请先添加 API 配置 JSON 文件")
        sys.exit(1)

    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    # 阶段1: 扫描校验
    print(f"扫描: {SOURCE_DIR}/")
    valid = []
    fail_count = 0
    for f in files:
        data, err = validate(f)
        if err:
            print(f"  [FAIL] {f.name} - {err}")
            fail_count += 1
        else:
            print(f"  [OK]   {f.name}")
            valid.append(f)

    if not valid:
        print(f"\n无可安装文件 (共 {fail_count} 个校验失败)")
        sys.exit(1)

    # 阶段2: 安装
    print(f"\n安装到 {TARGET_DIR}/:")
    ok_count = 0
    for f in valid:
        target = TARGET_DIR / f.name
        overwrite = ""
        if target.exists():
            try:
                ans = input(f"  {f.name} 已存在，覆盖? [y/n]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消")
                sys.exit(0)
            if ans != "y":
                print(f"  {f.name}  - 跳过")
                continue
            overwrite = " (覆盖)"

        shutil.copy2(f, target)
        print(f"  {f.name}  + 已安装{overwrite}")
        ok_count += 1

    print(f"\n完成: {ok_count} 成功, {fail_count} 失败")
    if ok_count > 0:
        print("重启 v-agent 后生效。")


if __name__ == "__main__":
    main()
