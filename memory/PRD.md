# cdxi Admin OS — PRD

## Original Problem Statement
Build the cdxi Multi-Client Admin Dashboard — a central operating system to manage clients, projects, milestones, progress and payments. Acts as a revenue enforcement engine: "Payment unlocks progress. Progress unlocks delivery. Delivery unlocks launch."

## Architecture
- **Backend**: FastAPI + Motor + MongoDB, JWT (HS256 / 7-day) with Bearer token, bcrypt password hashing, Stripe via `emergentintegrations` library (test key `sk_test_emergent`).
- **Frontend**: React + React Router + Tailwind + shadcn/ui + @phosphor-icons/react + sonner. Dark Swiss Brutalist aesthetic (Cabinet Grotesk / IBM Plex Sans / JetBrains Mono, 1px #27272A borders, sharp corners).
- **Auth**: Bearer token in `localStorage.cdxi_token`. Admin seeded on startup (email/password from `.env`).
- **Data**: Collections — `users`, `clients`, `projects`, `milestones`, `payment_transactions`. All IDs are UUIDs (not ObjectId). `_id` excluded from every read.

## User Personas
- **Agency Operator (Admin)** — single user managing multiple client projects, enforcing payment-gated delivery.

## Core Requirements (static)
- JWT admin login
- KPIs: Active Projects, Revenue Pipeline, Overdue Payments
- Clients table with status, progress bar, next payment, due date
- Client detail drawer: milestones, add/remove, mark paid toggle, Stripe checkout per unpaid milestone
- Business rule: milestone cannot be completed until its payment is paid
- Seed data on first boot: Christian Dix (m8s rates, 66%) + Bianca Scott (Cosmic Blueprint, 100%)

## What's Been Implemented (Feb 2026)
- ✅ Full CRUD for clients / projects / milestones
- ✅ JWT auth + /me / logout
- ✅ KPI aggregation endpoint
- ✅ Stripe Checkout session create + polling + webhook (with graceful fallback when test session not retrievable)
- ✅ Seed admin + example data (idempotent)
- ✅ Dark Swiss Brutalist UI: login, dashboard, client drawer, new-client dialog, payment-status page
- ✅ Payment-gated completion (unpaid milestones show blocked/striped state, completion disabled)
- ✅ Full data-testid coverage for testing
- ✅ Testing agent pass: 17/18 backend tests, all core frontend flows verified

## Admin Credentials
See `/app/memory/test_credentials.md` → `admin@cdxi.com` / `cdxi2026`

## Prioritised Backlog
**P0** — none (all core functionality shipped)

**P1**
- Real Stripe polling works end-to-end against real Stripe sessions (currently gracefully falls back when emergent proxy test sessions can't be re-read; manual Mark Paid works fine)
- Email notifications for overdue milestones (SendGrid / Resend)
- Edit client / project name / due dates inline

**P2**
- File deliverables upload per milestone (object storage)
- Multi-admin / team roles
- Client-side portal (read-only view per client with shareable link)
- Subscription / recurring billing mode
- CSV export of pipeline & aged receivables
- Dark/light theme toggle

## Deferred (beyond v1)
- Multi-tenant SaaS (Phase 4 in original doc)
- Automation layer (reminders, overdue alerts)
- Real-time updates via websockets
