#!/bin/bash
# OpenBB API Service 启动脚本

echo "🚀 启动 OpenBB API Service..."

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 检查并创建虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv

    echo "📥 安装依赖..."
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "✅ 虚拟环境已存在"
    source venv/bin/activate
fi

# 启动服务
echo "🌐 启动 FastAPI 服务器 (端口: 8001)..."
echo "📖 API 文档: http://localhost:8001/docs"
echo "📊 ReDoc: http://localhost:8001/redoc"
echo ""

uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
