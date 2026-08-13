#!/bin/bash
set -e

echo "========================================"
echo "  北京儒泰分销管理系统 - 后端API"
echo "========================================"
echo ""

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "[1/4] 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "[2/4] 激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "[3/4] 检查依赖..."
pip install -r requirements.txt -q

# 检查配置文件
if [ ! -f ".env" ]; then
    echo ""
    echo "[!] 未找到 .env 配置文件"
    echo "    请复制 .env.example 并填入实际配置:"
    echo "    cp .env.example .env"
    echo ""
    exit 1
fi

# 检查是否已在运行
if pgrep -f "uvicorn src.main:app" > /dev/null; then
    echo "[!] 服务已在运行，无需重复启动"
    echo "    停止服务: pkill -f 'uvicorn src.main:app'"
    exit 1
fi

# 后台启动服务
LOG_FILE="app.log"
PID_FILE="app.pid"
echo "[4/4] 启动服务 (后台运行)..."
nohup uvicorn src.main:app --host 0.0.0.0 --port 8000 </dev/null > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

echo ""
echo "   日志: tail -f $LOG_FILE"
echo "   停止: kill \$(cat $PID_FILE)"
echo "   接口文档: http://localhost:8000/docs"
echo "   健康检查: http://localhost:8000/api/v1/health"
echo "========================================"
echo ""
