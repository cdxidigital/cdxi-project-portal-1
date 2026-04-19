#!/usr/bin/env bash

# Development bootstrap for the cdxi Admin OS monorepo.
# Starts the FastAPI backend and the CRA frontend together, with proper
# dependency installation, signal handling and child cleanup.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${ROOT_DIR}/frontend"
BACKEND_DIR="${ROOT_DIR}/backend"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { printf "${BLUE}[dev]${NC} %s\n" "$*"; }
ok()  { printf "${GREEN}[dev]${NC} %s\n" "$*"; }
warn(){ printf "${YELLOW}[dev]${NC} %s\n" "$*"; }
err() { printf "${RED}[dev]${NC} %s\n" "$*" >&2; }

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    err "${PYTHON_BIN} not found on PATH. Install Python 3 or set PYTHON_BIN."
    exit 1
fi

if ! command -v yarn >/dev/null 2>&1; then
    err "yarn not found on PATH. Install yarn (https://yarnpkg.com)."
    exit 1
fi

# Frontend env check
if [ ! -f "${FRONTEND_DIR}/.env" ] && [ -f "${FRONTEND_DIR}/.env.example" ]; then
    warn "frontend/.env missing. Copying from .env.example."
    cp "${FRONTEND_DIR}/.env.example" "${FRONTEND_DIR}/.env"
fi

# Backend env check
if [ ! -f "${BACKEND_DIR}/.env" ] && [ -f "${BACKEND_DIR}/.env.example" ]; then
    warn "backend/.env missing. Copying from .env.example. Edit it before continuing!"
    cp "${BACKEND_DIR}/.env.example" "${BACKEND_DIR}/.env"
fi

# Frontend deps
if [ ! -d "${FRONTEND_DIR}/node_modules" ]; then
    log "Installing frontend dependencies (yarn install)…"
    (cd "${FRONTEND_DIR}" && yarn install --frozen-lockfile 2>/dev/null || yarn install)
fi

# Backend venv + deps
VENV_DIR="${BACKEND_DIR}/venv"
if [ ! -d "${VENV_DIR}" ]; then
    log "Creating Python virtualenv…"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"
    pip install --upgrade pip >/dev/null
    pip install -r "${BACKEND_DIR}/requirements.txt"
    deactivate
else
    ok "Backend virtualenv ready"
fi

ok "Starting servers…"
log "Frontend  http://localhost:3000"
log "Backend   http://localhost:8000"
log "API docs  http://localhost:8000/docs"

FRONTEND_PID=""
BACKEND_PID=""

cleanup() {
    printf "\n"
    log "Shutting down…"
    [ -n "${FRONTEND_PID}" ] && kill "${FRONTEND_PID}" 2>/dev/null || true
    [ -n "${BACKEND_PID}" ]  && kill "${BACKEND_PID}"  2>/dev/null || true
    wait 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

# Frontend
(
    cd "${FRONTEND_DIR}"
    yarn start
) &
FRONTEND_PID=$!

# Backend
(
    cd "${BACKEND_DIR}"
    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"
    exec python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

# If either dies, shut everything down.
wait -n "${FRONTEND_PID}" "${BACKEND_PID}" || true
err "A dev process exited. Cleaning up…"
cleanup
