#!/bin/bash
set -Eeuo pipefail
cd "$(dirname "$0")"
NEED_INSTALL=0

if [ -f ".env.local" ]; then
  set -a
  source ".env.local"
  set +a
fi

if [ ! -d ".venv" ]; then
  echo "Создание виртуального окружения..."
  python3 -m venv .venv
  NEED_INSTALL=1
fi

if [ "$NEED_INSTALL" = "0" ]; then
  .venv/bin/python3 -c "from importlib.metadata import version; expected=[line.strip().split('==',1) for line in open('requirements.lock',encoding='utf-8') if '==' in line]; assert all(version(name)==value for name,value in expected)" 2>/dev/null || NEED_INSTALL=1
fi

if [ "$NEED_INSTALL" = "1" ]; then
  echo "Установка зависимостей..."
  .venv/bin/pip install -r requirements.lock -q
fi


cd backend
../.venv/bin/python3 -c "from app.database import create_tables, ensure_auth_schema_columns; create_tables(); ensure_auth_schema_columns()"

echo ""
echo "=========================================="
echo "Запуск серверов..."
echo "=========================================="
echo ""

# прод: фронт раздаёт FastAPI, один порт
# локалка: фронт на 3000, бэк на 8001
if [ "${PROD:-0}" = "1" ]; then
  ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1 --limit-concurrency 300 --ws-max-size 65536 --proxy-headers --forwarded-allow-ips=127.0.0.1
else
  ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload --ws-max-size 65536 &
  BACKEND_PID=$!

  cd ../frontend
  ../.venv/bin/python3 server.py 3000 &
  FRONTEND_PID=$!

  echo ""
  echo "=========================================="
  echo "Серверы запущены!"
  echo "=========================================="
  echo "Бэкенд:   http://127.0.0.1:8001"
  echo "Фронтенд: http://127.0.0.1:3000"
  echo ""
  echo "Для остановки Ctrl+C"
  echo "=========================================="

  trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
  wait
fi
