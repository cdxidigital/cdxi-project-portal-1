"""
cdxi Admin OS — FastAPI backend.

Responsibilities:
  * JWT-based admin auth (bcrypt + PyJWT)
  * Clients, projects, milestones CRUD
  * Stripe Checkout integration for milestone payments
  * KPIs aggregation

Production notes:
  * Uses FastAPI lifespan (on_event is deprecated).
  * Avoids N+1 queries on the clients/KPIs endpoints by batching milestone reads.
  * CORS is configured conservatively: credentials are only enabled when an
    explicit origin allowlist is supplied.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import bcrypt
import jwt as pyjwt
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field, field_validator
from starlette.middleware.cors import CORSMiddleware

from emergentintegrations.payments.stripe.checkout import (
    CheckoutSessionRequest,
    StripeCheckout,
)

# --- Env loading -------------------------------------------------------------
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Set it in backend/.env or the deployment environment."
        )
    return val


MONGO_URL = _require_env("MONGO_URL")
DB_NAME = _require_env("DB_NAME")
JWT_SECRET = _require_env("JWT_SECRET")
ADMIN_EMAIL = _require_env("ADMIN_EMAIL")
ADMIN_PASSWORD = _require_env("ADMIN_PASSWORD")
STRIPE_API_KEY = _require_env("STRIPE_API_KEY")

JWT_ALG = "HS256"
JWT_EXPIRY_DAYS = int(os.environ.get("JWT_EXPIRY_DAYS", "7"))

# CORS: comma-separated list. "*" means allow any origin but disables credentials
# (browsers reject credentials: include with wildcard origin).
_cors_raw = os.environ.get("CORS_ORIGINS", "*").strip()
CORS_ORIGINS: List[str] = [o.strip() for o in _cors_raw.split(",") if o.strip()]
CORS_ALLOW_CREDENTIALS = CORS_ORIGINS != ["*"]

# Optional override for the public URL used in the Stripe webhook registration.
# Useful behind proxies where request.base_url resolves to an internal host.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

# --- Logging -----------------------------------------------------------------
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("cdxi")

# --- Database ----------------------------------------------------------------
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# --- Security ----------------------------------------------------------------
security = HTTPBearer(auto_error=False)


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
        "type": "access",
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
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


# --- Models ------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    user: Dict[str, Any]


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    project_name: str = Field(min_length=1, max_length=200)
    total_amount: float = 0.0

    @field_validator("total_amount")
    @classmethod
    def non_negative_total(cls, v: float) -> float:
        if v < 0:
            raise ValueError("total_amount must be >= 0")
        return float(v)


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    email: Optional[EmailStr] = None


class MilestoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    amount: float
    due_date: Optional[str] = None  # ISO date string (YYYY-MM-DD)

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be > 0")
        return float(v)


class MilestoneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    amount: Optional[float] = None
    due_date: Optional[str] = None
    payment_status: Optional[Literal["paid", "unpaid"]] = None
    completed: Optional[bool] = None

    @field_validator("amount")
    @classmethod
    def positive_amount(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("amount must be > 0")
        return v


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[
        Literal["Not Started", "In Progress", "Completed", "Delayed"]
    ] = None


class CheckoutBody(BaseModel):
    origin_url: str

    @field_validator("origin_url")
    @classmethod
    def require_http(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("origin_url must be an http(s) URL")
        return v


# --- Business logic ----------------------------------------------------------
def _project_view_from_milestones(
    project: Dict[str, Any], milestones: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build a computed project view given its milestones (already ordered)."""
    total = len(milestones)
    completed = sum(1 for m in milestones if m.get("completed"))
    progress = int((completed / total) * 100) if total else 0

    next_payment: Optional[float] = None
    next_due: Optional[str] = None
    for m in milestones:
        if m.get("payment_status") != "paid":
            next_payment = m.get("amount")
            next_due = m.get("due_date")
            break

    status = project.get("status") or "Not Started"
    if total and completed == total:
        status = "Completed"
    elif completed > 0 and status == "Not Started":
        status = "In Progress"

    return {
        **project,
        "milestones": milestones,
        "progress": progress,
        "next_payment": next_payment,
        "next_due": next_due,
        "status": status,
    }


async def compute_project_view(project: Dict[str, Any]) -> Dict[str, Any]:
    """Attach milestones, progress %, and next_payment to a single project."""
    milestones = (
        await db.milestones.find({"project_id": project["id"]}, {"_id": 0})
        .sort("order", 1)
        .to_list(1000)
    )
    return _project_view_from_milestones(project, milestones)


# --- App / routes ------------------------------------------------------------
@asynccontextmanager
async def lifespan(_: FastAPI):
    # Startup
    await db.users.create_index("email", unique=True)
    await db.clients.create_index("id", unique=True)
    await db.clients.create_index("created_at")
    await db.projects.create_index("id", unique=True)
    await db.projects.create_index("client_id")
    await db.milestones.create_index("id", unique=True)
    await db.milestones.create_index([("project_id", 1), ("order", 1)])
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.payment_transactions.create_index("milestone_id")
    await _seed_admin()
    await _seed_example_data()
    logger.info("cdxi api ready")
    yield
    # Shutdown
    client.close()
    logger.info("cdxi api stopped")


app = FastAPI(title="cdxi Admin OS", version="1.0.0", lifespan=lifespan)
api = APIRouter(prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Auth endpoints ----------------------------------------------------------
@api.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
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
async def me(user: Dict[str, Any] = Depends(get_current_user)):
    return user


@api.post("/auth/logout")
async def logout(_: Dict[str, Any] = Depends(get_current_user)):
    # JWTs are stateless; the client drops the token. Endpoint exists so the
    # frontend can hit a single logout URL and also validate the token is live.
    return {"ok": True}


# --- KPIs --------------------------------------------------------------------
@api.get("/kpis")
async def kpis(_: Dict[str, Any] = Depends(get_current_user)):
    # Batch-fetch everything, avoid N+1.
    projects = await db.projects.find({}, {"_id": 0}).to_list(10000)
    all_milestones = await db.milestones.find({}, {"_id": 0}).to_list(100000)

    by_project: Dict[str, List[Dict[str, Any]]] = {}
    for m in all_milestones:
        by_project.setdefault(m["project_id"], []).append(m)

    today = datetime.now(timezone.utc).date().isoformat()
    active = 0
    revenue_pipeline = 0.0
    overdue = 0.0

    for p in projects:
        ms = by_project.get(p["id"], [])
        total = len(ms)
        done = sum(1 for m in ms if m.get("completed"))
        if total == 0 or done < total:
            active += 1
        for m in ms:
            if m.get("payment_status") == "paid":
                continue
            amount = float(m.get("amount") or 0)
            revenue_pipeline += amount
            due = m.get("due_date")
            if due and isinstance(due, str) and due < today:
                overdue += amount

    total_clients = await db.clients.count_documents({})
    return {
        "active_projects": active,
        "revenue_pipeline": round(revenue_pipeline, 2),
        "overdue_payments": round(overdue, 2),
        "total_clients": total_clients,
    }


# --- Clients -----------------------------------------------------------------
@api.get("/clients")
async def list_clients(_: Dict[str, Any] = Depends(get_current_user)):
    clients = (
        await db.clients.find({}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(10000)
    )
    if not clients:
        return []

    client_ids = [c["id"] for c in clients]
    projects = await db.projects.find(
        {"client_id": {"$in": client_ids}}, {"_id": 0}
    ).to_list(20000)

    projects_by_client: Dict[str, Dict[str, Any]] = {
        p["client_id"]: p for p in projects
    }
    project_ids = [p["id"] for p in projects]

    milestones = (
        await db.milestones.find(
            {"project_id": {"$in": project_ids}}, {"_id": 0}
        )
        .sort("order", 1)
        .to_list(100000)
    )
    ms_by_project: Dict[str, List[Dict[str, Any]]] = {}
    for m in milestones:
        ms_by_project.setdefault(m["project_id"], []).append(m)

    result = []
    for c in clients:
        project = projects_by_client.get(c["id"])
        project_view = None
        if project:
            project_view = _project_view_from_milestones(
                project, ms_by_project.get(project["id"], [])
            )
        result.append({**c, "project": project_view})
    return result


@api.post("/clients")
async def create_client(
    body: ClientCreate, _: Dict[str, Any] = Depends(get_current_user)
):
    cid = str(uuid.uuid4())
    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.clients.insert_one(
        {"id": cid, "name": body.name, "email": body.email, "created_at": now}
    )
    await db.projects.insert_one(
        {
            "id": pid,
            "client_id": cid,
            "name": body.project_name,
            "status": "Not Started",
            "total_amount": float(body.total_amount),
            "created_at": now,
        }
    )
    client_doc = await db.clients.find_one({"id": cid}, {"_id": 0})
    project = await db.projects.find_one({"id": pid}, {"_id": 0})
    return {**client_doc, "project": _project_view_from_milestones(project, [])}


@api.get("/clients/{client_id}")
async def get_client(
    client_id: str, _: Dict[str, Any] = Depends(get_current_user)
):
    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    project = await db.projects.find_one({"client_id": client_id}, {"_id": 0})
    project_view = await compute_project_view(project) if project else None
    return {**c, "project": project_view}


@api.patch("/clients/{client_id}")
async def update_client(
    client_id: str,
    body: ClientUpdate,
    _: Dict[str, Any] = Depends(get_current_user),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        result = await db.clients.update_one({"id": client_id}, {"$set": updates})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Client not found")
    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    project = await db.projects.find_one({"client_id": client_id}, {"_id": 0})
    project_view = await compute_project_view(project) if project else None
    return {**c, "project": project_view}


@api.delete("/clients/{client_id}")
async def delete_client(
    client_id: str, _: Dict[str, Any] = Depends(get_current_user)
):
    c = await db.clients.find_one({"id": client_id})
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    project = await db.projects.find_one({"client_id": client_id})
    if project:
        await db.milestones.delete_many({"project_id": project["id"]})
        await db.projects.delete_one({"id": project["id"]})
    await db.clients.delete_one({"id": client_id})
    return {"ok": True}


# --- Projects ----------------------------------------------------------------
@api.patch("/projects/{project_id}")
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    _: Dict[str, Any] = Depends(get_current_user),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        result = await db.projects.update_one(
            {"id": project_id}, {"$set": updates}
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Project not found")
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return await compute_project_view(p)


# --- Milestones --------------------------------------------------------------
@api.post("/projects/{project_id}/milestones")
async def add_milestone(
    project_id: str,
    body: MilestoneCreate,
    _: Dict[str, Any] = Depends(get_current_user),
):
    project = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    existing_count = await db.milestones.count_documents({"project_id": project_id})
    mid = str(uuid.uuid4())
    doc = {
        "id": mid,
        "project_id": project_id,
        "name": body.name,
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
    _: Dict[str, Any] = Depends(get_current_user),
):
    m = await db.milestones.find_one({"id": milestone_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Milestone not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    merged = {**m, **updates}
    if merged.get("completed") and merged.get("payment_status") != "paid":
        raise HTTPException(
            status_code=400,
            detail="Milestone cannot be completed until payment is paid",
        )
    if updates:
        await db.milestones.update_one({"id": milestone_id}, {"$set": updates})
    return await db.milestones.find_one({"id": milestone_id}, {"_id": 0})


@api.delete("/milestones/{milestone_id}")
async def delete_milestone(
    milestone_id: str, _: Dict[str, Any] = Depends(get_current_user)
):
    result = await db.milestones.delete_one({"id": milestone_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Milestone not found")
    return {"ok": True}


# --- Stripe ------------------------------------------------------------------
def _webhook_url(request: Request) -> str:
    base = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return f"{base}/api/webhook/stripe"


@api.post("/milestones/{milestone_id}/checkout")
async def create_checkout(
    milestone_id: str,
    body: CheckoutBody,
    request: Request,
    _: Dict[str, Any] = Depends(get_current_user),
):
    milestone = await db.milestones.find_one({"id": milestone_id}, {"_id": 0})
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    if milestone.get("payment_status") == "paid":
        raise HTTPException(status_code=400, detail="Milestone already paid")
    amount = float(milestone["amount"])
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid milestone amount")

    stripe_checkout = StripeCheckout(
        api_key=STRIPE_API_KEY, webhook_url=_webhook_url(request)
    )

    origin = body.origin_url.rstrip("/")
    success_url = f"{origin}/payment-status?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/"

    req = CheckoutSessionRequest(
        amount=amount,
        currency="usd",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"milestone_id": milestone_id, "project_id": milestone["project_id"]},
    )
    try:
        session = await stripe_checkout.create_checkout_session(req)
    except Exception as e:
        logger.exception("Stripe session creation failed")
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")

    await db.payment_transactions.insert_one(
        {
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
        }
    )

    return {"url": session.url, "session_id": session.session_id}


@api.get("/payments/status/{session_id}")
async def payment_status(
    session_id: str,
    request: Request,
    _: Dict[str, Any] = Depends(get_current_user),
):
    tx = await db.payment_transactions.find_one(
        {"session_id": session_id}, {"_id": 0}
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    stripe_checkout = StripeCheckout(
        api_key=STRIPE_API_KEY, webhook_url=_webhook_url(request)
    )
    status = None
    try:
        status = await stripe_checkout.get_checkout_status(session_id)
    except Exception as e:
        logger.warning("Stripe status lookup failed for %s: %s", session_id, e)

    if status is None:
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
            {"$set": {"payment_status": status.payment_status, "status": status.status}},
        )
        if status.payment_status == "paid":
            await db.milestones.update_one(
                {"id": tx["milestone_id"]},
                {"$set": {"payment_status": "paid"}},
            )

    return {
        "session_id": session_id,
        "payment_status": status.payment_status,
        "status": status.status,
        "amount_total": status.amount_total,
        "currency": status.currency,
    }


@api.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    stripe_checkout = StripeCheckout(
        api_key=STRIPE_API_KEY, webhook_url=_webhook_url(request)
    )
    try:
        evt = await stripe_checkout.handle_webhook(body, sig)
    except Exception as e:
        logger.error("Stripe webhook error: %s", e)
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


# --- Health ------------------------------------------------------------------
@api.get("/")
async def root():
    return {"service": "cdxi-admin-os", "status": "ok"}


@api.get("/health")
async def health():
    """Lightweight health check: verifies Mongo is reachable."""
    try:
        await db.command("ping")
        return {"status": "ok", "db": "ok"}
    except Exception as e:
        logger.error("Health check failed: %s", e)
        raise HTTPException(status_code=503, detail="Database unavailable")


app.include_router(api)


# --- Seeding -----------------------------------------------------------------
async def _seed_admin() -> None:
    existing = await db.users.find_one({"email": ADMIN_EMAIL.lower()})
    if existing is None:
        await db.users.insert_one(
            {
                "id": str(uuid.uuid4()),
                "email": ADMIN_EMAIL.lower(),
                "password_hash": hash_password(ADMIN_PASSWORD),
                "name": "Admin",
                "role": "admin",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        logger.info("Seeded admin user %s", ADMIN_EMAIL.lower())
    elif not verify_password(ADMIN_PASSWORD, existing["password_hash"]):
        await db.users.update_one(
            {"email": ADMIN_EMAIL.lower()},
            {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}},
        )
        logger.info("Rotated admin password from env")


async def _seed_example_data() -> None:
    if await db.clients.count_documents({}) > 0:
        return
    now = datetime.now(timezone.utc).isoformat()

    c1, p1 = str(uuid.uuid4()), str(uuid.uuid4())
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

    c2, p2 = str(uuid.uuid4()), str(uuid.uuid4())
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
