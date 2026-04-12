#!/bin/bash
# V-Agent 启动脚本

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 检查虚拟环境是否存在
if [ ! -d ".venv" ]; then
    echo "❌ 虚拟环境不存在"
    echo ""
    echo "请先创建虚拟环境："
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# 检查 Python 版本
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "🐍 Python $PYTHON_VERSION"
echo "📂 工作目录: $SCRIPT_DIR"
echo ""

# 激活虚拟环境
source .venv/bin/activate

# 检查关键依赖
if ! python -c "import anthropic" 2>/dev/null; then
    echo "❌ 缺少依赖包"
    echo ""
    echo "正在安装依赖..."
    pip install -q -r requirements.txt
    echo "✅ 依赖安装完成"
    echo ""
fi

# 运行 v_agent
echo "🚀 启动 V-Agent..."
echo ""
python agent.py
