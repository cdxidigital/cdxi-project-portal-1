# cdxi Partner Portal — PRD

## Original Problem Statement
User pasted a React component for a "cdxi Partner Portal" featuring a PIN security gate,
NDA gate, EAA (Executive Advisory Agreement) tier selection, a ledger for expenses, a
roadmap of milestones, and an urgent-signal modal. Code was truncated mid-component.

## User Choices
- Build full-stack: React + FastAPI + MongoDB
- Persist expenses & EAA selections in MongoDB
- Move PINs from frontend constants to backend env vars
- Complete the truncated EAA cards / Ledger tab / Roadmap tab in the same design language
- Keep the existing visual style (Righteous + Inter, blue/slate palette, glass nav)

## Architecture
- **Backend**: FastAPI, motor (async Mongo), all routes under `/api`. PINs and
  STRATEGIC_RESERVE in `/app/backend/.env`. In-memory session token store
  (`Authorization: Bearer <token>`).
- **Frontend**: React 19 SPA in `/app/frontend/src/App.js`. Token persisted in
  `localStorage` (`cdxi_token`). All API calls use `process.env.REACT_APP_BACKEND_URL`.
- **MongoDB collections**: `client_state` (singleton doc tracking nda_accepted +
  eaa_selection), `expenses`, `urgent_signals`.

## User Personas
- **Client (PIN 4613)**: external partner; sees NDA gate until accepted, then unlocks
  Ledger and Roadmap tabs; selects an EAA tier; can send urgent signals.
- **Consultant (PIN 1991)**: principal/admin; bypasses NDA, can list incoming urgent
  signals.

## Core Requirements
1. PIN-based access control with two roles (env-driven PINs).
2. Session token issued on PIN verify, required for every other call.
3. NDA acceptance gate (clients only) that gates Ledger + Roadmap tabs.
4. EAA tier selection (Navigator / Partner / Council) — persists.
5. Ledger: strategic reserve, active balance, total burn, expense CRUD.
6. Roadmap: milestone list with project filter, NDA milestone reflects acceptance.
7. Urgent-signal modal: client → backend; consultant can list signals.

## What's Implemented (Jan 2026)
- POST `/api/auth/verify-pin`, POST `/api/auth/logout`
- GET `/api/state`, POST `/api/nda/accept`
- GET/POST/DELETE `/api/expenses`
- GET `/api/eaa/models`, POST `/api/eaa/select`
- POST `/api/urgent-signal`, GET `/api/urgent-signals` (consultant only)
- GET `/api/projects`, GET `/api/milestones`
- Full React SPA: PIN keypad with shake-on-error, glass-nav portal header,
  Command/Retainer/Ledger/Roadmap tabs, urgent-signal modal, NDA gate, project nodes,
  3 EAA cards with selection state, expense form + list with delete, milestone timeline
  with status dots and project filter, role badge (Client/Principal Access), logout.
- 100% backend tests (25/25) and 100% frontend flows (12/12) passing.

## Backlog (P1 / P2)
- P2: Move session tokens to MongoDB (or signed JWT) so they survive backend restarts.
- P2: Gate `/api/eaa/models` with auth dependency for consistency.
- P2: Split `App.js` into per-tab components (CommandView, RetainerView, LedgerView,
  RoadmapView, UrgentModal, AuthScreen).
- P2: Stripe Checkout for EAA tier upgrade with the active-balance net applied.
- P2: Email/Slack notification when an urgent signal is received.

## Next Action Items
- Await user feedback / next feature request.
