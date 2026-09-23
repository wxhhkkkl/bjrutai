#!/usr/bin/env bash

# 鲁泰后端一键部署脚本
#
# 默认用法（在服务器上传 backend 代码后执行）：
#   cd /home/ubuntu/backend
#   bash deploy_backend.sh
#
# 可选环境变量：
#   BACKEND_DIR       后端目录，默认是本脚本所在目录
#   VENV_DIR          Python 虚拟环境目录，默认是 $BACKEND_DIR/venv
#   BACKUP_ROOT       代码备份目录，默认是 $BACKEND_DIR/.deploy-backups
#   PORT              uvicorn 端口，默认 8000
#   HEALTH_URL        健康检查地址，默认 http://127.0.0.1:$PORT/api/v1/health
#   HEALTH_TIMEOUT    健康检查最长等待秒数，默认 60
#   INSTALL_DEPS      是否安装 requirements，默认 1；设为 0 可跳过
#   SKIP_MIGRATIONS   是否跳过 Alembic 迁移，默认 0；设为 1 可跳过

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${BACKEND_DIR:-$SCRIPT_DIR}"
VENV_DIR="${VENV_DIR:-$BACKEND_DIR/venv}"
BACKUP_ROOT="${BACKUP_ROOT:-$BACKEND_DIR/.deploy-backups}"
PID_FILE="${PID_FILE:-$BACKEND_DIR/app.pid}"
LOG_FILE="${LOG_FILE:-$BACKEND_DIR/app.log}"
PORT="${PORT:-8000}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:${PORT}/api/v1/health}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"
INSTALL_DEPS="${INSTALL_DEPS:-1}"
SKIP_MIGRATIONS="${SKIP_MIGRATIONS:-0}"

PYTHON_BIN="$VENV_DIR/bin/python"
UVICORN_BIN="$VENV_DIR/bin/uvicorn"

log() {
  printf '[deploy] %s\n' "$*"
}

fail() {
  printf '[deploy][错误] %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
用法：
  bash deploy_backend.sh [选项]

选项：
  --skip-deps        跳过 requirements.txt 依赖安装
  --skip-migrations  跳过 Alembic 数据库迁移
  --help             显示帮助

也可以使用环境变量覆盖默认配置，例如：
  INSTALL_DEPS=0 bash deploy_backend.sh
  SKIP_MIGRATIONS=1 bash deploy_backend.sh
EOF
}

parse_args() {
  while (($# > 0)); do
    case "$1" in
      --skip-deps)
        INSTALL_DEPS=0
        ;;
      --skip-migrations)
        SKIP_MIGRATIONS=1
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        fail "未知参数：$1（使用 --help 查看用法）"
        ;;
    esac
    shift
  done
}

check_command() {
  command -v "$1" >/dev/null 2>&1 || fail "服务器缺少命令：$1"
}

check_environment() {
  [[ -d "$BACKEND_DIR" ]] || fail "后端目录不存在：$BACKEND_DIR"
  [[ -f "$BACKEND_DIR/.env" ]] || fail "未找到 $BACKEND_DIR/.env；请保留服务器上的生产配置，不要用 .env.example 覆盖它"
  [[ -x "$PYTHON_BIN" ]] || fail "Python 虚拟环境不存在或不可执行：$PYTHON_BIN"
  [[ -x "$UVICORN_BIN" ]] || fail "虚拟环境中未找到 uvicorn：$UVICORN_BIN"
  [[ -f "$BACKEND_DIR/requirements.txt" ]] || fail "未找到 requirements.txt"
  [[ -f "$BACKEND_DIR/alembic.ini" ]] || fail "未找到 alembic.ini"

  check_command curl
  check_command tar
  check_command ps
  check_command kill

  if [[ ! "$PORT" =~ ^[0-9]+$ ]] || ((PORT < 1 || PORT > 65535)); then
    fail "PORT 必须是 1 到 65535 之间的端口号，当前为：$PORT"
  fi
  if [[ ! "$HEALTH_TIMEOUT" =~ ^[0-9]+$ ]] || ((HEALTH_TIMEOUT < 1)); then
    fail "HEALTH_TIMEOUT 必须是正整数，当前为：$HEALTH_TIMEOUT"
  fi
}

backup_code() {
  local timestamp archive item
  local -a items=()

  timestamp="$(date '+%Y%m%d-%H%M%S')"
  mkdir -p "$BACKUP_ROOT"
  chmod 700 "$BACKUP_ROOT"
  archive="$BACKUP_ROOT/backend-${timestamp}.tar.gz"

  # 只备份代码和部署配置，不备份 .env、venv、日志、PID 等运行时内容。
  # .env 会被原样保留，避免生产密钥出现在代码备份包中。
  for item in src migrations requirements.txt pyproject.toml alembic.ini Dockerfile start.sh deploy_backend.sh; do
    if [[ -e "$BACKEND_DIR/$item" ]]; then
      items+=("$item")
    fi
  done

  ((${#items[@]} > 0)) || fail "没有找到可备份的后端代码文件"
  tar -czf "$archive" -C "$BACKEND_DIR" "${items[@]}"
  chmod 600 "$archive"
  log "代码备份完成：$archive"
}

install_dependencies() {
  if [[ "$INSTALL_DEPS" == "0" ]]; then
    log "已跳过依赖安装（INSTALL_DEPS=0）"
    return
  fi

  log "安装/校验 Python 依赖……"
  (
    cd "$BACKEND_DIR"
    "$PYTHON_BIN" -m pip install --disable-pip-version-check -r requirements.txt
  )
}

run_migrations() {
  if [[ "$SKIP_MIGRATIONS" == "1" ]]; then
    log "已跳过数据库迁移（SKIP_MIGRATIONS=1）"
    return
  fi

  log "执行 Alembic 数据库迁移……"
  (
    cd "$BACKEND_DIR"
    "$PYTHON_BIN" -m alembic upgrade head
  )
}

stop_existing_service() {
  local pid command_line attempt

  if [[ ! -f "$PID_FILE" ]]; then
    log "未找到旧的 PID 文件，将直接启动服务"
    return
  fi

  pid="$(tr -d '[:space:]' < "$PID_FILE")"
  if [[ ! "$pid" =~ ^[0-9]+$ ]]; then
    fail "PID 文件内容无效：$PID_FILE"
  fi

  if ! kill -0 "$pid" 2>/dev/null; then
    log "PID $pid 对应的旧进程已不存在，将重新启动"
    return
  fi

  command_line="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  if [[ "$command_line" != *uvicorn* || "$command_line" != *src.main:app* ]]; then
    fail "拒绝停止 PID $pid：该进程不是当前后端的 uvicorn（$command_line）"
  fi

  log "停止旧服务（PID $pid）……"
  kill "$pid"
  for ((attempt = 1; attempt <= 20; attempt++)); do
    if ! kill -0 "$pid" 2>/dev/null; then
      log "旧服务已停止"
      return
    fi
    sleep 1
  done

  fail "旧服务在 20 秒内未停止；未强制 kill，请先检查：$LOG_FILE"
}

start_service() {
  local pid

  log "启动 uvicorn（端口 $PORT）……"
  cd "$BACKEND_DIR"
  printf '\n===== deploy %s =====\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
  nohup "$UVICORN_BIN" src.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    >> "$LOG_FILE" 2>&1 < /dev/null &
  pid=$!
  printf '%s\n' "$pid" > "$PID_FILE"
  chmod 600 "$PID_FILE"
  log "新服务已启动，PID：$pid"
}

wait_for_health() {
  local attempt response

  log "等待健康检查：$HEALTH_URL（最长 ${HEALTH_TIMEOUT}s）"
  for ((attempt = 1; attempt <= HEALTH_TIMEOUT; attempt++)); do
    if response="$(curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null)" \
      && printf '%s' "$response" | "$PYTHON_BIN" -c \
        'import json, sys; body = json.load(sys.stdin); raise SystemExit(0 if body.get("data", {}).get("status") == "ok" else 1)'; then
      log "健康检查通过：$response"
      return
    fi
    sleep 1
  done

  printf '[deploy][错误] 健康检查失败，最近日志如下：\n' >&2
  if [[ -f "$LOG_FILE" ]]; then
    tail -n 80 "$LOG_FILE" >&2 || true
  fi
  fail "服务未通过健康检查，请先检查 $LOG_FILE；代码备份位于 $BACKUP_ROOT"
}

main() {
  parse_args "$@"
  log "部署目录：$BACKEND_DIR"
  check_environment
  backup_code
  install_dependencies
  run_migrations
  stop_existing_service
  start_service
  wait_for_health
  log "后端部署完成"
}

main "$@"
