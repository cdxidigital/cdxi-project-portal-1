@echo off
REM Development bootstrap for the cdxi Admin OS monorepo (Windows).
REM Starts the FastAPI backend and the CRA frontend in two new console windows.

setlocal enabledelayedexpansion

echo.
echo Starting cdxi Admin OS development servers...
echo.

REM Seed env files from examples if missing
if not exist "frontend\.env" if exist "frontend\.env.example" (
  copy /Y "frontend\.env.example" "frontend\.env" >NUL
  echo Created frontend\.env from .env.example
)
if not exist "backend\.env" if exist "backend\.env.example" (
  copy /Y "backend\.env.example" "backend\.env" >NUL
  echo Created backend\.env from .env.example - edit it before continuing!
)

REM Frontend deps
if not exist "frontend\node_modules" (
  echo Installing frontend dependencies...
  pushd frontend
  call yarn install
  popd
)

REM Backend venv + deps
if not exist "backend\venv" (
  echo Creating Python virtual environment...
  pushd backend
  python -m venv venv
  call venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt
  call deactivate
  popd
) else (
  echo Backend virtualenv found.
)

echo.
echo Starting servers...
echo Frontend: http://localhost:3000
echo Backend:  http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo.

start "cdxi Frontend" cmd /k "cd /d %~dp0frontend && yarn start"
start "cdxi Backend"  cmd /k "cd /d %~dp0backend && call venv\Scripts\activate.bat && python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000"

echo Both servers are starting in new windows.
echo.
pause
