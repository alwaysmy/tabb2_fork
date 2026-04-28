#!/usr/bin/env bash
set -euo pipefail

USE_PROXY="${1:-}"
PROXY_PORT="${PROXY_PORT:-7890}"
APP_PORT="${APP_PORT:-8800}"

cd "$(dirname "$0")/.."

if [[ "$USE_PROXY" == "--proxy" ]]; then
  host_ip="$(awk '/nameserver/ {print $2; exit}' /etc/resolv.conf)"
  export http_proxy="http://${host_ip}:${PROXY_PORT}"
  export https_proxy="http://${host_ip}:${PROXY_PORT}"
  export HTTP_PROXY="$http_proxy"
  export HTTPS_PROXY="$https_proxy"
  echo "Proxy enabled: $http_proxy"
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.11+ first."
  exit 1
fi

if [[ ! -f ".venv/bin/activate" ]]; then
  rm -rf .venv
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo "Starting Tabbit2API on port ${APP_PORT} ..."
python -m uvicorn tabbit2api:app --host 0.0.0.0 --port "${APP_PORT}"
