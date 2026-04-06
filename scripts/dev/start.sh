#!/usr/bin/env bash
#
# momo-trading 실행 스크립트
#
# 사용법:
#   ./start.sh          — 포그라운드 실행
#   ./start.sh --reload — 포그라운드 실행 (자동 재시작)
#   ./start.sh -d       — 백그라운드(데몬) 실행
#   ./start.sh stop     — 백그라운드 프로세스 종료
#   ./start.sh status   — 실행 상태 확인
#   ./start.sh logs     — 실시간 로그 보기
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV_DIR="${MOMO_VENV_DIR:-$APP_DIR/.venv313}"
PID_FILE="${MOMO_PID_FILE:-$APP_DIR/runtime/pids/momo-trading.pid}"
LOG_FILE="${MOMO_LOG_FILE:-$APP_DIR/runtime/logs/momo-trading.log}"
ENV_FILE="${MOMO_ENV_FILE:-$APP_DIR/.env}"
HOST="${MOMO_HOST:-0.0.0.0}"
PORT="${MOMO_PORT:-9000}"
DOCKER_BIN="${MOMO_DOCKER_BIN:-docker}"
PYTHON_BIN="${MOMO_PYTHON_BIN:-python}"
LSOF_BIN="${MOMO_LSOF_BIN:-lsof}"

has_command() {
    local command_name="$1"

    if [[ "$command_name" == */* ]]; then
        [[ -x "$command_name" ]]
        return
    fi

    command -v "$command_name" >/dev/null 2>&1
}

strip_wrapping_quotes() {
    local value="$1"

    case "$value" in
        \"*\")
            value="${value#\"}"
            value="${value%\"}"
            ;;
        \'*\')
            value="${value#\'}"
            value="${value%\'}"
            ;;
    esac

    printf '%s' "$value"
}

read_env_value() {
    local key="$1"
    local line

    if [ -n "${!key:-}" ]; then
        printf '%s' "${!key}"
        return
    fi

    if [ ! -f "$ENV_FILE" ]; then
        return
    fi

    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ''|\#*)
                continue
                ;;
            "$key="*)
                printf '%s' "${line#*=}"
                return
                ;;
        esac
    done < "$ENV_FILE"
}

get_listening_pids() {
    local port="$1"

    if ! has_command "$LSOF_BIN"; then
        return
    fi

    "$LSOF_BIN" -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true
}

get_child_pids() {
    local parent_pid="$1"

    if ! has_command ps; then
        return
    fi

    ps -o pid= --ppid "$parent_pid" 2>/dev/null | awk '{print $1}' || true
}

get_parent_pid() {
    local pid="$1"

    if ! has_command ps; then
        return
    fi

    ps -o ppid= -p "$pid" 2>/dev/null | awk '{print $1}' || true
}

kill_process_tree() {
    local pid="$1"
    local child

    for child in $(get_child_pids "$pid"); do
        kill_process_tree "$child"
    done

    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
    fi
}

kill_parent_chain() {
    local pid="$1"
    local parent

    parent="$(get_parent_pid "$pid")"
    while [ -n "$parent" ] && [ "$parent" != "1" ] && [ "$parent" != "0" ]; do
        if ! kill -0 "$parent" 2>/dev/null; then
            break
        fi
        if ! is_momo_process "$parent"; then
            break
        fi
        kill "$parent" 2>/dev/null || true
        parent="$(get_parent_pid "$parent")"
    done
}

pid_command_line() {
    local pid="$1"

    if ! has_command ps; then
        return
    fi

    ps -o command= -p "$pid" 2>/dev/null || true
}

is_momo_process() {
    local pid="$1"
    local command_line

    command_line="$(pid_command_line "$pid")"
    if [ -z "$command_line" ]; then
        return 1
    fi

    case "$command_line" in
        *"uvicorn main:app"*|*"scripts/dev/start.sh"*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

stop_momo_processes() {
    local stopped=0
    local pid

    if [ -f "$PID_FILE" ]; then
        pid="$(cat "$PID_FILE")"
        if kill -0 "$pid" 2>/dev/null; then
            echo "🛑 momo-trading 종료 (PID: $pid)"
            kill_process_tree "$pid"
            stopped=1
        else
            echo "프로세스가 이미 종료됨 (stale PID: $pid)"
        fi
        rm -f "$PID_FILE"
    fi

    for pid in $(get_listening_pids "$PORT"); do
        if ! kill -0 "$pid" 2>/dev/null; then
            continue
        fi
        if is_momo_process "$pid"; then
            echo "🧹 포트 점유 잔여 프로세스 정리 (PID: $pid)"
            kill_parent_chain "$pid"
            kill_process_tree "$pid"
            stopped=1
        fi
    done

    if [ "$stopped" -eq 0 ]; then
        echo "실행 중인 프로세스 없음"
    fi
}

port_is_listening() {
    local port="$1"
    [ -n "$(get_listening_pids "$port")" ]
}

ensure_port_available() {
    if port_is_listening "$PORT"; then
        local pids
        pids="$(get_listening_pids "$PORT" | tr '\n' ' ' | xargs)"
        echo "❌ 포트 $PORT 이미 사용 중${pids:+ (PID: $pids)}"
        return 1
    fi
}

sync_broker_sidecar() {
    local broker_provider

    broker_provider="$(read_env_value BROKER_PROVIDER)"
    broker_provider="$(strip_wrapping_quotes "${broker_provider:-KIS}")"
    broker_provider="$(printf '%s' "$broker_provider" | tr '[:lower:]' '[:upper:]')"

    # start.sh의 사이드카 분기 기준은 계좌/키 값이 아니라 BROKER_PROVIDER 하나다.
    if [ "$broker_provider" = "KIS" ]; then
        if ! has_command "$DOCKER_BIN"; then
            echo "❌ BROKER_PROVIDER=KIS 이지만 docker 명령을 찾을 수 없습니다: $DOCKER_BIN"
            exit 1
        fi

        echo "🐳 BROKER_PROVIDER=KIS → kis-mcp 시작"
        if ! "$DOCKER_BIN" compose up -d kis-mcp; then
            echo "❌ kis-mcp 시작 실패"
            exit 1
        fi
        return
    fi

    if has_command "$DOCKER_BIN"; then
        echo "⏭️  BROKER_PROVIDER=$broker_provider → kis-mcp 중지"
        if ! "$DOCKER_BIN" compose stop kis-mcp; then
            echo "⚠️  kis-mcp 중지 실패 또는 이미 중지됨"
        fi
    else
        echo "⏭️  BROKER_PROVIDER=$broker_provider → docker 미감지, kis-mcp 중지 생략"
    fi
}

run_db_migrations() {
    echo "🗂️  DB 마이그레이션 확인"
    if ! "$PYTHON_BIN" -m alembic upgrade head; then
        echo "❌ alembic upgrade head 실패"
        exit 1
    fi
}

if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "❌ venv 없음: $VENV_DIR"
    echo "   python -m venv venv && pip install -r requirements.txt"
    exit 1
fi

cd "$APP_DIR"

mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$(dirname "$PID_FILE")"
mkdir -p "$APP_DIR/runtime/data"

case "${1:-}" in
    stop)
        stop_momo_processes
        ;;

    status)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo "✅ momo-trading 실행 중 (PID: $PID)"
                echo "   http://localhost:$PORT/admin"
                echo "   http://127.0.0.1:$PORT/admin"
            else
                echo "❌ 프로세스 종료됨 (stale PID: $PID)"
                rm -f "$PID_FILE"
                if port_is_listening "$PORT"; then
                    echo "✅ momo-trading 실행 중 (PID 추적 없음)"
                    echo "   http://localhost:$PORT/admin"
                    echo "   http://127.0.0.1:$PORT/admin"
                fi
            fi
        elif port_is_listening "$PORT"; then
            echo "✅ momo-trading 실행 중 (PID 추적 없음)"
            echo "   http://localhost:$PORT/admin"
            echo "   http://127.0.0.1:$PORT/admin"
        else
            echo "❌ 실행 중인 프로세스 없음"
        fi
        ;;

    logs)
        if [ -f "$LOG_FILE" ]; then
            tail -f "$LOG_FILE"
        else
            echo "로그 파일 없음: $LOG_FILE"
        fi
        ;;

    -d|--daemon)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "이미 실행 중 (PID: $(cat "$PID_FILE"))"
            exit 1
        fi
        ensure_port_available || exit 1

        sync_broker_sidecar
        run_db_migrations

        echo "🚀 momo-trading 백그라운드 시작"
        echo "   Host: $HOST:$PORT"
        echo "   Admin: http://localhost:$PORT/admin"
        echo "   Admin: http://127.0.0.1:$PORT/admin"
        echo "   Log: $LOG_FILE"

        nohup "$PYTHON_BIN" -m uvicorn main:app \
            --host "$HOST" --port "$PORT" \
            --log-level info \
            >> "$LOG_FILE" 2>&1 &

        echo $! > "$PID_FILE"
        echo "   PID: $(cat "$PID_FILE")"
        echo ""
        echo "종료: ./start.sh stop"
        ;;

    ""|--foreground|-r|--reload)
        UVICORN_ARGS=(
            -m uvicorn main:app
            --host "$HOST"
            --port "$PORT"
            --log-level info
        )
        if [ "${1:-}" = "-r" ] || [ "${1:-}" = "--reload" ]; then
            UVICORN_ARGS+=(--reload)
        fi

        ensure_port_available || exit 1

        sync_broker_sidecar
        run_db_migrations

        echo "🚀 momo-trading 시작 (포그라운드)"
        echo "   Host: $HOST:$PORT"
        echo "   Admin: http://localhost:$PORT/admin"
        echo "   Admin: http://127.0.0.1:$PORT/admin"
        if [ "${1:-}" = "-r" ] || [ "${1:-}" = "--reload" ]; then
            echo "   Mode: reload"
        else
            echo "   Mode: stable"
        fi
        echo "   종료: Ctrl+C"
        echo ""

        "$PYTHON_BIN" "${UVICORN_ARGS[@]}"
        ;;

    *)
        echo "사용법: $0 [--reload|-d|stop|status|logs]"
        exit 1
        ;;
esac
