@echo off
REM Development script for CDXI Project Portal
REM Runs both frontend and backend servers concurrently

setlocal enabledelayedexpansion

echo.
echo 🚀 Starting CDXI Project Portal development servers...
echo.

REM Check if frontend dependencies are installed
if not exist "frontend\node_modules" (
  echo 📦 Installing frontend dependencies...
  cd frontend
  call yarn install
  cd ..
)

REM Check if backend virtual environment exists
if not exist "backend\venv" (
  echo 📦 Creating Python virtual environment...
  cd backend
  python -m venv venv
  call venv\Scripts\activate.bat
  pip install -r requirements.txt
  cd ..
) else (
  echo ✓ Virtual environment found
)

echo.
echo ✓ Starting servers...
echo Frontend: http://localhost:3000
echo Backend: http://localhost:8000
echo API Docs: http://localhost:8000/docs
echo.

REM Start frontend in a new window
cd frontend
start "CDXI Frontend" cmd /k "yarn start"
cd ..

REM Start backend in a new window
cd backend
start "CDXI Backend" cmd /k "call venv\Scripts\activate.bat && python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000"
cd ..

echo ✓ Both servers are starting. Check the new windows for server output.
echo.
pause
