from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import logging
import bcrypt
import jwt as pyjwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr

from emergentintegrations.payments.stripe.checkout import (
    StripeCheckout,
    CheckoutSessionRequest,
)

# --- Setup ---
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"
ADMIN_EMAIL = os.environ['ADMIN_EMAIL']
ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
STRIPE_API_KEY = os.environ['STRIPE_API_KEY']

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="cdxi Admin OS")
api = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helpers ---
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())

def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "access",
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)

async def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    token = None
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
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# --- Models ---
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str
    user: dict

class ClientCreate(BaseModel):
    name: str
    email: Optional[str] = None
    project_name: str
    total_amount: float = 0.0

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None

class MilestoneCreate(BaseModel):
    name: str
    amount: float
    due_date: Optional[str] = None  # ISO date string

class MilestoneUpdate(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[str] = None
    payment_status: Optional[Literal["paid", "unpaid"]] = None
    completed: Optional[bool] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[Literal["Not Started", "In Progress", "Completed", "Delayed"]] = None

# --- Business logic helpers ---
async def compute_project_view(project: dict) -> dict:
    """Attach milestones, progress %, next_payment to project."""
    milestones = await db.milestones.find(
        {"project_id": project["id"]}, {"_id": 0}
    ).sort("order", 1).to_list(1000)

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

    # auto-derive status
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

async def get_client_with_project(client_doc: dict) -> dict:
    project = await db.projects.find_one({"client_id": client_doc["id"]}, {"_id": 0})
    if project:
        project = await compute_project_view(project)
    return {**client_doc, "project": project}

# --- Auth endpoints ---
@api.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"])
    return LoginResponse(
        access_token=token,
        user={"id": user["id"], "email": user["email"], "name": user.get("name"), "role": user.get("role")},
    )

@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

@api.post("/auth/logout")
async def logout(user: dict = Depends(get_current_user)):
    return {"ok": True}

# --- KPIs ---
@api.get("/kpis")
async def kpis(user: dict = Depends(get_current_user)):
    projects = await db.projects.find({}, {"_id": 0}).to_list(1000)
    active = 0
    revenue_pipeline = 0.0
    overdue = 0.0
    now = datetime.now(timezone.utc).date().isoformat()
    for p in projects:
        milestones = await db.milestones.find({"project_id": p["id"]}, {"_id": 0}).to_list(1000)
        total = len(milestones)
        completed = sum(1 for m in milestones if m.get("completed"))
        if total == 0 or completed < total:
            active += 1
        for m in milestones:
            if m.get("payment_status") != "paid":
                revenue_pipeline += float(m.get("amount") or 0)
                if m.get("due_date") and m["due_date"] < now:
                    overdue += float(m.get("amount") or 0)
    return {
        "active_projects": active,
        "revenue_pipeline": round(revenue_pipeline, 2),
        "overdue_payments": round(overdue, 2),
        "total_clients": await db.clients.count_documents({}),
    }

# --- Clients ---
@api.get("/clients")
async def list_clients(user: dict = Depends(get_current_user)):
    clients = await db.clients.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [await get_client_with_project(c) for c in clients]

@api.post("/clients")
async def create_client(body: ClientCreate, user: dict = Depends(get_current_user)):
    cid = str(uuid.uuid4())
    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.clients.insert_one({
        "id": cid,
        "name": body.name,
        "email": body.email,
        "created_at": now,
    })
    await db.projects.insert_one({
        "id": pid,
        "client_id": cid,
        "name": body.project_name,
        "status": "Not Started",
        "total_amount": body.total_amount,
        "created_at": now,
    })
    client_doc = await db.clients.find_one({"id": cid}, {"_id": 0})
    return await get_client_with_project(client_doc)

@api.get("/clients/{client_id}")
async def get_client(client_id: str, user: dict = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return await get_client_with_project(c)

@api.patch("/clients/{client_id}")
async def update_client(client_id: str, body: ClientUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.clients.update_one({"id": client_id}, {"$set": updates})
    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return await get_client_with_project(c)

@api.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(get_current_user)):
    project = await db.projects.find_one({"client_id": client_id})
    if project:
        await db.milestones.delete_many({"project_id": project["id"]})
        await db.projects.delete_one({"id": project["id"]})
    await db.clients.delete_one({"id": client_id})
    return {"ok": True}

# --- Projects ---
@api.patch("/projects/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.projects.update_one({"id": project_id}, {"$set": updates})
    p = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return await compute_project_view(p)

# --- Milestones ---
@api.post("/projects/{project_id}/milestones")
async def add_milestone(project_id: str, body: MilestoneCreate, user: dict = Depends(get_current_user)):
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
async def update_milestone(milestone_id: str, body: MilestoneUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    # enforce: completion only when paid
    m = await db.milestones.find_one({"id": milestone_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Milestone not found")
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
async def delete_milestone(milestone_id: str, user: dict = Depends(get_current_user)):
    await db.milestones.delete_one({"id": milestone_id})
    return {"ok": True}

# --- Stripe ---
class CheckoutBody(BaseModel):
    origin_url: str

@api.post("/milestones/{milestone_id}/checkout")
async def create_checkout(
    milestone_id: str, body: CheckoutBody, request: Request, user: dict = Depends(get_current_user)
):
    milestone = await db.milestones.find_one({"id": milestone_id}, {"_id": 0})
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")
    if milestone.get("payment_status") == "paid":
        raise HTTPException(status_code=400, detail="Milestone already paid")
    amount = float(milestone["amount"])
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid milestone amount")

    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)

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
        "metadata": {"milestone_id": milestone_id, "project_id": milestone["project_id"]},
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {"url": session.url, "session_id": session.session_id}

@api.get("/payments/status/{session_id}")
async def payment_status(session_id: str, request: Request, user: dict = Depends(get_current_user)):
    tx = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    status = None
    try:
        status = await stripe_checkout.get_checkout_status(session_id)
    except Exception as e:
        logger.warning(f"Stripe status lookup failed for {session_id}: {e}")

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
    host_url = str(request.base_url).rstrip("/")
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    try:
        evt = await stripe_checkout.handle_webhook(body, sig)
    except Exception as e:
        logger.error(f"webhook error: {e}")
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

# --- Health ---
@api.get("/")
async def root():
    return {"service": "cdxi-admin-os", "status": "ok"}

app.include_router(api)

# --- Seeding ---
async def seed_admin():
    existing = await db.users.find_one({"email": ADMIN_EMAIL.lower()})
    if existing is None:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": ADMIN_EMAIL.lower(),
            "password_hash": hash_password(ADMIN_PASSWORD),
            "name": "Admin",
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Seeded admin user")
    elif not verify_password(ADMIN_PASSWORD, existing["password_hash"]):
        await db.users.update_one(
            {"email": ADMIN_EMAIL.lower()},
            {"$set": {"password_hash": hash_password(ADMIN_PASSWORD)}},
        )
        logger.info("Updated admin password")

async def seed_example_data():
    if await db.clients.count_documents({}) > 0:
        return
    now = datetime.now(timezone.utc).isoformat()
    # Christian Dix - m8s rates - 66% with unpaid next
    c1 = str(uuid.uuid4())
    p1 = str(uuid.uuid4())
    await db.clients.insert_one({"id": c1, "name": "Christian Dix", "email": "christian@m8srates.com", "created_at": now})
    await db.projects.insert_one({"id": p1, "client_id": c1, "name": "m8s rates", "status": "In Progress", "total_amount": 3300.0, "created_at": now})
    m1s = [
        {"name": "Discovery & Strategy", "amount": 1100.0, "due_date": "2026-01-15", "order": 0, "payment_status": "paid", "completed": True},
        {"name": "Design System", "amount": 1100.0, "due_date": "2026-03-01", "order": 1, "payment_status": "paid", "completed": True},
        {"name": "Development Build", "amount": 1100.0, "due_date": "2026-04-29", "order": 2, "payment_status": "unpaid", "completed": False},
    ]
    for m in m1s:
        await db.milestones.insert_one({"id": str(uuid.uuid4()), "project_id": p1, "created_at": now, **m})

    # Bianca Scott - Cosmic Blueprint - completed
    c2 = str(uuid.uuid4())
    p2 = str(uuid.uuid4())
    await db.clients.insert_one({"id": c2, "name": "Bianca Scott", "email": "bianca@cosmicblueprint.co", "created_at": now})
    await db.projects.insert_one({"id": p2, "client_id": c2, "name": "Cosmic Blueprint", "status": "Completed", "total_amount": 2400.0, "created_at": now})
    m2s = [
        {"name": "Blueprint Intake", "amount": 800.0, "due_date": "2025-11-10", "order": 0, "payment_status": "paid", "completed": True},
        {"name": "Chart Synthesis", "amount": 800.0, "due_date": "2025-12-05", "order": 1, "payment_status": "paid", "completed": True},
        {"name": "Final Delivery", "amount": 800.0, "due_date": "2026-01-20", "order": 2, "payment_status": "paid", "completed": True},
    ]
    for m in m2s:
        await db.milestones.insert_one({"id": str(uuid.uuid4()), "project_id": p2, "created_at": now, **m})
    logger.info("Seeded example clients")

@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.clients.create_index("id", unique=True)
    await db.projects.create_index("id", unique=True)
    await db.projects.create_index("client_id")
    await db.milestones.create_index("id", unique=True)
    await db.milestones.create_index("project_id")
    await db.payment_transactions.create_index("session_id", unique=True)
    await seed_admin()
    await seed_example_data()

@app.on_event("shutdown")
async def on_shutdown():
    client.close()
