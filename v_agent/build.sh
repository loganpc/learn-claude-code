#!/bin/bash
# V-Agent 打包脚本
# 用法: ./build.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== V-Agent 打包 ==="

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "❌ 虚拟环境不存在"
    echo "请先运行: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# 激活虚拟环境
source .venv/bin/activate

# 检查 PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo "📦 安装 PyInstaller..."
    pip install pyinstaller
fi

# 清理旧产物和旧 spec 文件
echo "🧹 清理旧产物..."
rm -rf build dist v-agent.spec

# 构建打包参数
PYINSTALLER_ARGS="--onedir --name v-agent"
PYINSTALLER_ARGS="$PYINSTALLER_ARGS --hidden-import anthropic"
PYINSTALLER_ARGS="$PYINSTALLER_ARGS --hidden-import requests"
PYINSTALLER_ARGS="$PYINSTALLER_ARGS --hidden-import prompt_toolkit"
PYINSTALLER_ARGS="$PYINSTALLER_ARGS --exclude-module tkinter"
PYINSTALLER_ARGS="$PYINSTALLER_ARGS --exclude-module matplotlib"
PYINSTALLER_ARGS="$PYINSTALLER_ARGS --exclude-module numpy"
PYINSTALLER_ARGS="$PYINSTALLER_ARGS --exclude-module pandas"

# 检查 skills 目录是否存在
if [ -d "skills" ]; then
    echo "📁 包含 skills 目录"
    PYINSTALLER_ARGS="$PYINSTALLER_ARGS --add-data skills:skills"
else
    echo "⚠️  skills 目录不存在，跳过"
    echo "   (skills 是可选的，用于内置技能)"
fi

# 打包
echo "🔨 正在打包..."
echo ""
echo "包含模块:"
echo "  - api/ (API 重试机制)"
echo "  - tools/ (工具系统)"
echo "  - logging_config.py (结构化日志)"
echo "  - permissions.py (权限系统)"
echo "  - context.py (上下文管理)"
echo "  - rag.py (知识检索)"
echo ""

# 使用 PyInstaller 打包
eval pyinstaller $PYINSTALLER_ARGS agent.py

# 检查打包结果
if [ ! -d "dist/v-agent" ]; then
    echo ""
    echo "❌ 打包失败"
    exit 1
fi

# 结果
SIZE=$(du -sh dist/v-agent/ | cut -f1)
echo ""
echo "=== ✅ 打包完成 ==="
echo ""
echo "📦 输出目录: dist/v-agent/"
echo "🚀 可执行文件: dist/v-agent/v-agent"
echo "📏 总大小: $SIZE"
echo ""
echo "📝 使用说明:"
echo "  1. 复制整个 dist/v-agent/ 目录到目标机器"
echo "  2. 运行: ./dist/v-agent/v-agent"
echo "  3. 首次运行会自动创建 ~/.v-agent/ 目录和配置文件"
echo ""
echo "⚠️  注意:"
echo "  - 目标机器需要 macOS 系统"
echo "  - 首次运行需要配置 API Key"
echo "  - 如有 skills/ 目录，会自动包含"
echo "  - 用户自定义的 API 工具需要手动配置到 ~/.v-agent/apis/"


