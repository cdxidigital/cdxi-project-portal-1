# cdxi Admin OS

Multi-client control panel for project, milestone and payment operations.

- **Frontend** — Create React App + TailwindCSS + shadcn/ui (`frontend/`)
- **Backend** — FastAPI + Motor (MongoDB) + Stripe Checkout (`backend/`)

## Quick start

1. Copy env templates and fill in values:

   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```

2. Run both servers:

   ```bash
   ./dev.sh           # macOS / Linux
   dev.bat            # Windows
   ```

   This installs dependencies on first run, creates a Python virtualenv at
   `backend/venv`, and starts:

   - Frontend: <http://localhost:3000>
   - Backend:  <http://localhost:8000>
   - Docs:     <http://localhost:8000/docs>
   - Health:   <http://localhost:8000/api/health>

## Backend env vars

See [`backend/.env.example`](./backend/.env.example). Required: `MONGO_URL`,
`DB_NAME`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `STRIPE_API_KEY`.

The first boot seeds an admin user from `ADMIN_EMAIL` / `ADMIN_PASSWORD` and a
small set of demo clients.

## Frontend env vars

`REACT_APP_BACKEND_URL` controls the API origin. Leave blank to call
same-origin (useful when the frontend is served from the same host as the API
in production).
