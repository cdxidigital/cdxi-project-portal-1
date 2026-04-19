"""cdxi Admin OS - FastAPI backend.

Production-ready REST API for managing clients, projects, milestones, and
Stripe-powered milestone payments.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

import bcrypt
import jwt as pyjwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, field_validator
from starlette.middleware.cors import CORSMiddleware

from emergentintegrations.payments.stripe.checkout import (
    CheckoutSessionRequest,
    StripeCheckout,
)

# ---------------------------------------------------------------------------
# Environment & configuration
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.stderr.write(
            f"[cdxi] Missing required environment variable: {name}\n"
            f"       See backend/.env.example for the full list.\n"
        )
        raise SystemExit(1)
    return value


LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("cdxi")

MONGO_URL = _require_env("MONGO_URL")
DB_NAME = _require_env("DB_NAME")
JWT_SECRET = _require_env("JWT_SECRET")
ADMIN_EMAIL = _require_env("ADMIN_EMAIL").lower()
ADMIN_PASSWORD = _require_env("ADMIN_PASSWORD")
STRIPE_API_KEY = _require_env("STRIPE_API_KEY")

JWT_ALG = "HS256"
JWT_EXPIRY_DAYS = int(os.environ.get("JWT_EXPIRY_DAYS", "7"))
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
# If CORS is "*" we must not allow credentials (browser will reject).
ALLOW_CREDENTIALS = CORS_ORIGINS != ["*"]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# ---------------------------------------------------------------------------
# DB client
# ---------------------------------------------------------------------------

client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await db.users.create_index("email", unique=True)
    await db.clients.create_index("id", unique=True)
    await db.clients.create_index("created_at")
    await db.projects.create_index("id", unique=True)
    await db.projects.create_index("client_id")
    await db.milestones.create_index("id", unique=True)
    await db.milestones.create_index([("project_id", 1), ("order", 1)])
    await db.payment_transactions.create_index("session_id", unique=True)

    await _seed_admin()
    await _seed_example_data()
    logger.info("cdxi-admin-os started (db=%s)", DB_NAME)
    try:
        yield
    finally:
        client.close()
        logger.info("cdxi-admin-os stopped")


app = FastAPI(title="cdxi Admin OS", version="1.0.0", lifespan=lifespan)
api = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    token: Optional[str] = None
    if creds and creds.scheme.lower() == "bearer":
        token = creds.credentials
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = await db.users.find_one(
        {"id": payload["sub"]}, {"_id": 0, "password_hash": 0}
    )
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


def _validate_iso_date(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    if not _DATE_RE.match(value):
        raise ValueError("due_date must be ISO format YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("due_date is not a valid calendar date") from exc
    return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    user: dict


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    project_name: str = Field(min_length=1, max_length=200)
    total_amount: float = Field(default=0.0, ge=0)


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    email: Optional[EmailStr] = None


class MilestoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    amount: float = Field(ge=0)
    due_date: Optional[str] = None

    @field_validator("due_date")
    @classmethod
    def _check_due(cls, v: Optional[str]) -> Optional[str]:
        return _validate_iso_date(v)


class MilestoneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    amount: Optional[float] = Field(default=None, ge=0)
    due_date: Optional[str] = None
    payment_status: Optional[Literal["paid", "unpaid"]] = None
    completed: Optional[bool] = None

    @field_validator("due_date")
    @classmethod
    def _check_due(cls, v: Optional[str]) -> Optional[str]:
        return _validate_iso_date(v)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[Literal["Not Started", "In Progress", "Completed", "Delayed"]] = None


# ---------------------------------------------------------------------------
# Business logic helpers
# ---------------------------------------------------------------------------


def _derive_status(stored_status: Optional[str], total: int, completed: int) -> str:
    """Compute the effective project status without clobbering manual overrides.

    - If all milestones are paid+completed => "Completed".
    - If any milestone is completed and no explicit status has been set => "In Progress".
    - Otherwise return stored status (or default).
    """
    stored = stored_status or "Not Started"
    if total and completed == total:
        return "Completed"
    if completed > 0 and stored == "Not Started":
        return "In Progress"
    return stored


async def _attach_milestones(project: dict) -> dict:
    milestones = await db.milestones.find(
        {"project_id": project["id"]}, {"_id": 0}
    ).sort("order", 1).to_list(None)

    total = len(milestones)
    completed = sum(1 for m in milestones if m.get("completed"))
    progress = int((completed / total) * 100) if total else 0

    next_payment = None
    next_due = None
    for m in milestones:
        if m.get("payment_status") != "paid":
            next_payment = m.get("amount")
            next_due = m.get("due_date")
            break

    status_value = _derive_status(project.get("status"), total, completed)

    return {
        **project,
        "milestones": milestones,
        "progress": progress,
        "next_payment": next_payment,
        "next_due": next_due,
        "status": status_value,
    }


async def _batch_attach_projects(clients: list[dict]) -> list[dict]:
    """Attach the single project + computed view to each client in 2 queries."""
    if not clients:
        return []
    client_ids = [c["id"] for c in clients]
    projects = await db.projects.find(
        {"client_id": {"$in": client_ids}}, {"_id": 0}
    ).to_list(None)
    if not projects:
        return [{**c, "project": None} for c in clients]

    project_ids = [p["id"] for p in projects]
    milestones = await db.milestones.find(
        {"project_id": {"$in": project_ids}}, {"_id": 0}
    ).sort("order", 1).to_list(None)

    milestones_by_project: dict[str, list[dict]] = {}
    for m in milestones:
        milestones_by_project.setdefault(m["project_id"], []).append(m)

    project_by_client: dict[str, dict] = {}
    for p in projects:
        ms = milestones_by_project.get(p["id"], [])
        total = len(ms)
        completed = sum(1 for m in ms if m.get("completed"))
        progress = int((completed / total) * 100) if total else 0
        next_payment = None
        next_due = None
        for m in ms:
            if m.get("payment_status") != "paid":
                next_payment = m.get("amount")
                next_due = m.get("due_date")
                break
        project_by_client[p["client_id"]] = {
            **p,
            "milestones": ms,
            "progress": progress,
            "next_payment": next_payment,
            "next_due": next_due,
            "status": _derive_status(p.get("status"), total, completed),
        }

    return [{**c, "project": project_by_client.get(c["id"])} for c in clients]


async def _get_client_with_project(client_doc: dict) -> dict:
    project = await db.projects.find_one({"client_id": client_doc["id"]}, {"_id": 0})
    if project:
        project = await _attach_milestones(project)
    return {**client_doc, "project": project}


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@api.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        # Keep response generic to avoid user enumeration
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"])
    return LoginResponse(
        access_token=token,
        user={
            "id": user["id"],
            "email": user["email"],
            "name": user.get("name"),
            "role": user.get("role"),
        },
    )


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)) -> dict:
    return user


@api.post("/auth/logout")
async def logout(user: dict = Depends(get_current_user)) -> dict:
    # JWT is stateless; clients must discard the token.
    return {"ok": True}


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------


@api.get("/kpis")
async def kpis(user: dict = Depends(get_current_user)) -> dict:
    projects = await db.projects.find({}, {"_id": 0, "id": 1}).to_list(None)
    project_ids = [p["id"] for p in projects]

    if not project_ids:
        return {
            "active_projects": 0,
            "revenue_pipeline": 0.0,
            "overdue_payments": 0.0,
            "total_clients": await db.clients.count_documents({}),
        }

    milestones = await db.milestones.find(
        {"project_id": {"$in": project_ids}},
        {"_id": 0, "project_id": 1, "payment_status": 1, "completed": 1, "amount": 1, "due_date": 1},
    ).to_list(None)

    today_iso = date.today().isoformat()
    by_project: dict[str, list[dict]] = {}
    for m in milestones:
        by_project.setdefault(m["project_id"], []).append(m)

    active = 0
    revenue_pipeline = 0.0
    overdue = 0.0
    for pid in project_ids:
        ms = by_project.get(pid, [])
        total = len(ms)
        completed = sum(1 for m in ms if m.get("completed"))
        if total == 0 or completed < total:
            active += 1
        for m in ms:
            if m.get("payment_status") != "paid":
                amt = float(m.get("amount") or 0)
                revenue_pipeline += amt
                due = m.get("due_date")
                if due and _DATE_RE.match(str(due)) and str(due) < today_iso:
                    overdue += amt

    return {
        "active_projects": active,
        "revenue_pipeline": round(revenue_pipeline, 2),
        "overdue_payments": round(overdue, 2),
        "total_clients": await db.clients.count_documents({}),
    }


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


@api.get("/clients")
async def list_clients(user: dict = Depends(get_current_user)) -> list[dict]:
    clients = await db.clients.find({}, {"_id": 0}).sort("created_at", -1).to_list(None)
    return await _batch_attach_projects(clients)


@api.post("/clients", status_code=status.HTTP_201_CREATED)
async def create_client(body: ClientCreate, user: dict = Depends(get_current_user)) -> dict:
    cid = str(uuid.uuid4())
    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.clients.insert_one({
        "id": cid,
        "name": body.name.strip(),
        "email": body.email.lower() if body.email else None,
        "created_at": now,
    })
    await db.projects.insert_one({
        "id": pid,
        "client_id": cid,
        "name": body.project_name.strip(),
        "status": "Not Started",
        "total_amount": float(body.total_amount),
        "created_at": now,
    })
    client_doc = await db.clients.find_one({"id": cid}, {"_id": 0})
    return await _get_client_with_project(client_doc)


@api.get("/clients/{client_id}")
async def get_client(client_id: str, user: dict = Depends(get_current_user)) -> dict:
    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return await _get_client_with_project(c)


@api.patch("/clients/{client_id}")
async def update_client(
    client_id: str, body: ClientUpdate, user: dict = Depends(get_current_user)
) -> dict:
    existing = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Client not found")
    updates: dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.email is not None:
        updates["email"] = body.email.lower() if body.email else None
    if updates:
        await db.clients.update_one({"id": client_id}, {"$set": updates})
    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
    return await _get_client_with_project(c)


@api.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(get_current_user)) -> dict:
    existing = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Client not found")
    project = await db.projects.find_one({"client_id": client_id})
    if project:
        await db.milestones.delete_many({"project_id": project["id"]})
        await db.projects.delete_one({"id": project["id"]})
    await db.clients.delete_one({"id": client_id})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@api.patch("/projects/{project_id}")
async def update_project(
    project_id: str, body: ProjectUpdate, user: dict = Depends(get_current_user)
) -> dict:
    updates = body.model_dump(exclude_none=True)
    if updates:
        await db.projects.update_one({"id": project_id}, {"$set": updates})
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return await _attach_milestones(p)


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------


@api.post("/projects/{project_id}/milestones", status_code=status.HTTP_201_CREATED)
async def add_milestone(
    project_id: str,
    body: MilestoneCreate,
    user: dict = Depends(get_current_user),
) -> dict:
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    existing_count = await db.milestones.count_documents({"project_id": project_id})
    mid = str(uuid.uuid4())
    doc = {
        "id": mid,
        "project_id": project_id,
        "name": body.name.strip(),
        "amount": float(body.amount),
        "due_date": body.due_date,
        "order": existing_count,
        "payment_status": "unpaid",
        "completed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.milestones.insert_one(doc)
    return await db.milestones.find_one({"id": mid}, {"_id": 0})


@api.patch("/milestones/{milestone_id}")
async def update_milestone(
    milestone_id: str,
    body: MilestoneUpdate,
    user: dict = Depends(get_current_user),
) -> dict:
    m = await db.milestones.find_one({"id": milestone_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Milestone not found")

    updates = body.model_dump(exclude_none=True)
    merged = {**m, **updates}

    # Business rule: a milestone cannot be completed until it's paid.
    if merged.get("completed") and merged.get("payment_status") != "paid":
        raise HTTPException(
            status_code=400,
            detail="Milestone cannot be completed until payment is paid",
        )

    # If marking unpaid, force completed=False for consistency.
    if updates.get("payment_status") == "unpaid" and m.get("completed"):
        updates["completed"] = False

    if updates:
        if "name" in updates and isinstance(updates["name"], str):
            updates["name"] = updates["name"].strip()
        await db.milestones.update_one({"id": milestone_id}, {"$set": updates})
    return await db.milestones.find_one({"id": milestone_id}, {"_id": 0})


@api.delete("/milestones/{milestone_id}")
async def delete_milestone(
    milestone_id: str, user: dict = Depends(get_current_user)
) -> dict:
    result = await db.milestones.delete_one({"id": milestone_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------


class CheckoutBody(BaseModel):
    origin_url: str = Field(min_length=1, max_length=2048)


def _webhook_url(request: Request) -> str:
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return f"{base}/api/webhook/stripe"


@api.post("/milestones/{milestone_id}/checkout")
async def create_checkout(
    milestone_id: str,
    body: CheckoutBody,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    milestone = await db.milestones.find_one({"id": milestone_id}, {"_id": 0})
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    if milestone.get("payment_status") == "paid":
        raise HTTPException(status_code=400, detail="Milestone already paid")
    amount = float(milestone["amount"])
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid milestone amount")

    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=_webhook_url(request))

    origin = body.origin_url.rstrip("/")
    success_url = f"{origin}/payment-status?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/"

    req = CheckoutSessionRequest(
        amount=amount,
        currency="usd",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "milestone_id": milestone_id,
            "project_id": milestone["project_id"],
        },
    )
    session = await stripe_checkout.create_checkout_session(req)

    await db.payment_transactions.insert_one({
        "id": str(uuid.uuid4()),
        "session_id": session.session_id,
        "milestone_id": milestone_id,
        "project_id": milestone["project_id"],
        "amount": amount,
        "currency": "usd",
        "payment_status": "initiated",
        "status": "open",
        "metadata": {
            "milestone_id": milestone_id,
            "project_id": milestone["project_id"],
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {"url": session.url, "session_id": session.session_id}


@api.get("/payments/status/{session_id}")
async def payment_status(
    session_id: str, request: Request, user: dict = Depends(get_current_user)
) -> dict:
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=_webhook_url(request))
    try:
        live = await stripe_checkout.get_checkout_status(session_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Stripe status lookup failed for %s: %s", session_id, exc)
        live = None

    if live is None:
        return {
            "session_id": session_id,
            "payment_status": tx.get("payment_status", "pending"),
            "status": tx.get("status", "open"),
            "amount_total": int(float(tx.get("amount") or 0) * 100),
            "currency": tx.get("currency", "usd"),
        }

    if tx.get("payment_status") != "paid":
        await db.payment_transactions.update_one(
            {"session_id": session_id},
            {"$set": {"payment_status": live.payment_status, "status": live.status}},
        )
        if live.payment_status == "paid":
            await db.milestones.update_one(
                {"id": tx["milestone_id"]},
                {"$set": {"payment_status": "paid"}},
            )

    return {
        "session_id": session_id,
        "payment_status": live.payment_status,
        "status": live.status,
        "amount_total": live.amount_total,
        "currency": live.currency,
    }


@api.post("/webhook/stripe")
async def stripe_webhook(request: Request) -> dict:
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=_webhook_url(request))
    try:
        evt = await stripe_checkout.handle_webhook(body, sig)
    except Exception as exc:  # noqa: BLE001
        logger.error("webhook error: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid webhook")

    if evt.payment_status == "paid" and evt.session_id:
        tx = await db.payment_transactions.find_one({"session_id": evt.session_id})
        if tx and tx.get("payment_status") != "paid":
            await db.payment_transactions.update_one(
                {"session_id": evt.session_id},
                {"$set": {"payment_status": "paid", "status": "complete"}},
            )
            await db.milestones.update_one(
                {"id": tx["milestone_id"]},
                {"$set": {"payment_status": "paid"}},
            )
    return {"received": True}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@api.get("/")
async def root() -> dict:
    return {"service": "cdxi-admin-os", "status": "ok"}


@api.get("/health")
async def health() -> dict:
    try:
        await db.command("ping")
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("health: db ping failed: %s", exc)
        db_ok = False
    return {
        "service": "cdxi-admin-os",
        "status": "ok" if db_ok else "degraded",
        "db": "up" if db_ok else "down",
    }


app.include_router(api)


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


async def _seed_admin() -> None:
    """Ensure the admin user exists. Does NOT overwrite an existing password."""
    existing = await db.users.find_one({"email": ADMIN_EMAIL})
    if existing is None:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": ADMIN_EMAIL,
            "password_hash": hash_password(ADMIN_PASSWORD),
            "name": "Admin",
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Seeded admin user (%s)", ADMIN_EMAIL)
    else:
        logger.info("Admin user already exists (%s)", ADMIN_EMAIL)


async def _seed_example_data() -> None:
    if await db.clients.count_documents({}) > 0:
        return
    now = datetime.now(timezone.utc).isoformat()

    c1 = str(uuid.uuid4())
    p1 = str(uuid.uuid4())
    await db.clients.insert_one(
        {"id": c1, "name": "Christian Dix", "email": "christian@m8srates.com", "created_at": now}
    )
    await db.projects.insert_one(
        {
            "id": p1,
            "client_id": c1,
            "name": "m8s rates",
            "status": "In Progress",
            "total_amount": 3300.0,
            "created_at": now,
        }
    )
    for m in [
        {"name": "Discovery & Strategy", "amount": 1100.0, "due_date": "2026-01-15", "order": 0, "payment_status": "paid", "completed": True},
        {"name": "Design System", "amount": 1100.0, "due_date": "2026-03-01", "order": 1, "payment_status": "paid", "completed": True},
        {"name": "Development Build", "amount": 1100.0, "due_date": "2026-04-29", "order": 2, "payment_status": "unpaid", "completed": False},
    ]:
        await db.milestones.insert_one(
            {"id": str(uuid.uuid4()), "project_id": p1, "created_at": now, **m}
        )

    c2 = str(uuid.uuid4())
    p2 = str(uuid.uuid4())
    await db.clients.insert_one(
        {"id": c2, "name": "Bianca Scott", "email": "bianca@cosmicblueprint.co", "created_at": now}
    )
    await db.projects.insert_one(
        {
            "id": p2,
            "client_id": c2,
            "name": "Cosmic Blueprint",
            "status": "Completed",
            "total_amount": 2400.0,
            "created_at": now,
        }
    )
    for m in [
        {"name": "Blueprint Intake", "amount": 800.0, "due_date": "2025-11-10", "order": 0, "payment_status": "paid", "completed": True},
        {"name": "Chart Synthesis", "amount": 800.0, "due_date": "2025-12-05", "order": 1, "payment_status": "paid", "completed": True},
        {"name": "Final Delivery", "amount": 800.0, "due_date": "2026-01-20", "order": 2, "payment_status": "paid", "completed": True},
    ]:
        await db.milestones.insert_one(
            {"id": str(uuid.uuid4()), "project_id": p2, "created_at": now, **m}
        )

    logger.info("Seeded example clients")
