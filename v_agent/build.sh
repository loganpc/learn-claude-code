#!/bin/bash
# V-Agent 打包脚本
# 用法: ./build.sh

set -e
cd "$(dirname "$0")"

echo "=== V-Agent 打包 ==="

# 清理旧产物
rm -rf build dist

# 激活虚拟环境
source .venv/bin/activate

# 打包
echo "正在打包..."
pyinstaller --onedir --name v-agent --add-data "skills:skills" agent.py 2>&1 | grep -E "(INFO: Build complete|ERROR|WARNING.*import)"

# 结果
SIZE=$(du -sh dist/v-agent/ | cut -f1)
echo ""
echo "=== 打包完成 ==="
echo "输出目录: dist/v-agent/"
echo "可执行文件: dist/v-agent/v-agent"
echo "总大小: $SIZE"
echo ""
echo "运行: ./dist/v-agent/v-agent"
