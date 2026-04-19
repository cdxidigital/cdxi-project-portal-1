#!/bin/bash

# Development script for CDXI Project Portal
# Runs both frontend and backend servers concurrently

set -e

echo "🚀 Starting CDXI Project Portal development servers..."

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if frontend dependencies are installed
if [ ! -d "frontend/node_modules" ]; then
  echo -e "${BLUE}📦 Installing frontend dependencies...${NC}"
  cd frontend
  yarn install
  cd ..
fi

# Check if backend virtual environment exists
if [ ! -d "backend/venv" ]; then
  echo -e "${BLUE}📦 Creating Python virtual environment...${NC}"
  cd backend
  python -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  cd ..
else
  echo -e "${GREEN}✓ Virtual environment found${NC}"
fi

# Start both servers
echo -e "${GREEN}✓ Starting servers...${NC}"
echo -e "${BLUE}Frontend: http://localhost:3000${NC}"
echo -e "${BLUE}Backend: http://localhost:8000${NC}"
echo -e "${BLUE}API Docs: http://localhost:8000/docs${NC}"

# Create a function to handle cleanup
cleanup() {
  echo -e "\n${BLUE}🛑 Shutting down servers...${NC}"
  kill $FRONTEND_PID $BACKEND_PID 2>/dev/null || true
  exit 0
}

trap cleanup SIGINT SIGTERM

# Start frontend
cd frontend
yarn start &
FRONTEND_PID=$!
cd ..

# Start backend
cd backend
source venv/bin/activate
python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Wait for both processes
wait
