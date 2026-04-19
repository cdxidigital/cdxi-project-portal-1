@echo off
setlocal

cd /d "%~dp0"

where yarn >nul 2>&1
if errorlevel 1 (
  echo [dev] Missing required command: yarn
  exit /b 1
)
where python >nul 2>&1
if errorlevel 1 (
  echo [dev] Missing required command: python
  exit /b 1
)

if not exist "backend\.env" echo [dev] WARNING: backend\.env not found ^(copy backend\.env.example^)
if not exist "frontend\.env" echo [dev] WARNING: frontend\.env not found ^(copy frontend\.env.example^)

if not exist "frontend\node_modules" (
  echo [dev] Installing frontend dependencies...
  pushd frontend
  call yarn install
  popd
)

if not exist "backend\venv" (
  echo [dev] Creating Python virtualenv...
  python -m venv backend\venv
  call backend\venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r backend\requirements.txt
  call backend\venv\Scripts\deactivate.bat
)

echo [dev] Starting servers
echo [dev] Frontend: http://localhost:3000
echo [dev] Backend:  http://localhost:8000
echo [dev] API docs: http://localhost:8000/docs

start "cdxi-frontend" cmd /k "cd /d %~dp0frontend && yarn start"
start "cdxi-backend"  cmd /k "cd /d %~dp0backend && call venv\Scripts\activate.bat && python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000"

endlocal
