#!/bin/bash
# OPENBB-CN Web UI 启动脚本

echo "=========================================="
echo "  OPENBB-CN Web UI 启动"
echo "=========================================="

# 启动目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WEB_UI_DIR="$PROJECT_DIR/web_ui"

cd "$WEB_UI_DIR"

echo "[1/2] 启动 API 后端服务..."
# 启动后端 (如果未运行)
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    cd "$PROJECT_DIR"
    nohup python3 -m uvicorn openbb_core.api:app --host 0.0.0.0 --port 8000 > /tmp/openbb-cn-api.log 2>&1 &
    echo "  API 服务已启动 (PID: $!)"
    sleep 3
else
    echo "  API 服务已运行"
fi

echo "[2/2] 启动前端服务..."
cd "$WEB_UI_DIR"
echo "  前端地址: http://localhost:5173"
echo "  API 地址: http://localhost:8000"
echo ""
echo "=========================================="
echo "  🎉 启动完成！"
echo "=========================================="
echo ""
echo "  访问 Web UI: http://localhost:5173"
echo "  API 文档:    http://localhost:8000/docs"
echo ""
echo "  按 Ctrl+C 停止前端服务"
echo "  停止后端: kill \$(pgrep -f 'uvicorn openbb_core')"
echo ""

# 启动 Vite 开发服务器
npm run dev -- --host 0.0.0.0
