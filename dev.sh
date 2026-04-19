#!/usr/bin/env bash
# Development script for CDXI Project Portal.
# Runs frontend (CRA) and backend (FastAPI/uvicorn) concurrently.

# Note: we deliberately do NOT use `set -e` here because it interacts badly
# with `wait` on background jobs — a single child dying would skip cleanup.
set -u
set -o pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { printf "%b\n" "${BLUE}[dev]${NC} $*"; }
ok()   { printf "%b\n" "${GREEN}[dev]${NC} $*"; }
warn() { printf "%b\n" "${YELLOW}[dev]${NC} $*"; }
err()  { printf "%b\n" "${RED}[dev]${NC} $*" >&2; }

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Missing required command: $1"
    exit 1
  fi
}

require yarn
require python3

# --- Env file checks ---
if [ ! -f "backend/.env" ]; then
  warn "backend/.env not found — copy backend/.env.example and fill it in."
fi
if [ ! -f "frontend/.env" ]; then
  warn "frontend/.env not found — copy frontend/.env.example and fill it in."
fi

# --- Frontend deps ---
if [ ! -d "frontend/node_modules" ]; then
  log "Installing frontend dependencies…"
  (cd frontend && yarn install)
fi

# --- Backend venv + deps ---
if [ ! -d "backend/venv" ]; then
  log "Creating Python virtualenv…"
  python3 -m venv backend/venv
  # shellcheck disable=SC1091
  source backend/venv/bin/activate
  pip install --upgrade pip >/dev/null
  pip install -r backend/requirements.txt
  deactivate
else
  ok "Virtualenv found"
fi

FRONTEND_PID=""
BACKEND_PID=""

cleanup() {
  printf "\n"
  log "Shutting down servers…"
  if [ -n "${FRONTEND_PID}" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  if [ -n "${BACKEND_PID}" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
  exit 0
}

trap cleanup SIGINT SIGTERM EXIT

ok "Starting servers"
log "Frontend: http://localhost:3000"
log "Backend:  http://localhost:8000"
log "API docs: http://localhost:8000/docs"

(cd frontend && yarn start) &
FRONTEND_PID=$!

(
  cd backend
  # shellcheck disable=SC1091
  source venv/bin/activate
  exec python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

wait -n "$FRONTEND_PID" "$BACKEND_PID" 2>/dev/null || true
# One exited — tear the other down.
cleanup
