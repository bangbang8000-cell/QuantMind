#!/bin/bash
# OPENBB-CN 启动脚本

cd /root/OPENBB-CN

echo "=========================================="
echo "  OPENBB-CN 金融数据平台"
echo "=========================================="
echo ""

# 检查依赖
echo "[1/4] 检查依赖..."
python3 -c "from openbb_core import OpenBB; print('✅ OpenBB-CN 已安装')" 2>/dev/null || {
    echo "❌ 依赖未安装，正在安装..."
    pip3 install --break-system-packages -i https://pypi.tuna.tsinghua.edu.cn/simple \
        akshare easyquotation pandas numpy fastapi uvicorn httpx pydantic \
        langchain langchain-community redis sqlalchemy python-dotenv tenacity plotly pyarrow 2>/dev/null
}

# 启动服务
echo "[2/4] 启动 API 服务..."
echo ""

# 后台启动
nohup python3 -m uvicorn openbb_core.api:app --host 0.0.0.0 --port 8000 > /tmp/openbb-cn.log 2>&1 &
SERVER_PID=$!

sleep 3

# 检查服务状态
if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "✅ 服务启动成功！"
else
    echo "❌ 服务启动失败，请检查日志: /tmp/openbb-cn.log"
    exit 1
fi

echo "[3/4] 配置信息..."
echo ""
echo "  API 地址:     http://localhost:8000"
echo "  文档地址:     http://localhost:8000/docs"
echo "  健康检查:     http://localhost:8000/health"
echo ""

echo "[4/4] 测试 API..."
echo ""

# 测试几个端点
echo "  测试健康检查..."
curl -s http://localhost:8000/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'    ✅ {d}')" 2>/dev/null || echo "    ⚠️  检查失败"

echo ""
echo "=========================================="
echo "  🎉 OPENBB-CN 已启动！"
echo "=========================================="
echo ""
echo "  访问文档: http://localhost:8000/docs"
echo "  停止服务: kill $SERVER_PID"
echo ""
