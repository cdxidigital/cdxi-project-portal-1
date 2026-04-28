from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import secrets
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Config from env
CLIENT_PIN = os.environ['CLIENT_PIN']
CONSULTANT_PIN = os.environ['CONSULTANT_PIN']
STRATEGIC_RESERVE = float(os.environ.get('STRATEGIC_RESERVE', '150'))

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Session tokens are persisted in MongoDB collection `sessions`
# Document shape: {"_id": <token>, "role": "client"|"consultant", "created_at": iso}

# Static reference data
PROJECT_NODES = [
    {"id": "m8s", "name": "m8s rates", "status": "Active", "type": "P2P Marketplace"},
    {"id": "brand", "name": "Executive Branding", "status": "Active", "type": "Strategic Identity"},
    {"id": "ops", "name": "Ops Refinement", "status": "Scoped", "type": "Corporate Consulting"},
]

EAA_MODELS = [
    {"id": "navigator", "name": "Navigator EAA", "price": 1050, "hours": 8,
     "desc": "Strategic advisory access + 8 hrs delivery",
     "features": ["Executive access", "Standard response", "Multi-domain support", "Preferential project rates"]},
    {"id": "partner", "name": "Partner EAA", "price": 1950, "hours": 20,
     "desc": "Executive access + 20 hrs delivery",
     "features": ["Priority executive access", "Fast-track response", "Quarterly strategy audit", "Implementation oversight"],
     "recommended": True},
    {"id": "council", "name": "Advisory Council EAA", "price": 3450, "hours": 45,
     "desc": "Priority executive advisory + 45 hrs delivery",
     "features": ["Unlimited strategic counsel", "Immediate response window", "Bespoke reporting", "Direct principal access"]},
]

# Create the main app
app = FastAPI(title="cdxi Partner Portal API")
api_router = APIRouter(prefix="/api")


# ---------- Models ----------
class PinVerifyRequest(BaseModel):
    pin: str


class PinVerifyResponse(BaseModel):
    role: Literal["client", "consultant"]
    token: str


class StateResponse(BaseModel):
    role: str
    nda_accepted: bool
    eaa_selection: Optional[str] = None
    strategic_reserve: float
    active_balance: float
    total_expenses: float


class ExpenseCreate(BaseModel):
    desc: str
    amount: float


class Expense(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    desc: str
    amount: float
    date: str
    created_at: str


class EaaSelectRequest(BaseModel):
    tier_id: str


class UrgentSignalRequest(BaseModel):
    message: str


class UrgentSignal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    message: str
    role: str
    created_at: str


# ---------- Auth helpers ----------
async def get_current_role(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1].strip()
    session = await db.sessions.find_one({"_id": token})
    if not session or "role" not in session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return session["role"]


async def get_client_state_doc() -> dict:
    """Get or create the singleton client_state document."""
    doc = await db.client_state.find_one({"_id": "singleton"})
    if not doc:
        doc = {"_id": "singleton", "nda_accepted": False, "eaa_selection": None}
        await db.client_state.insert_one(doc)
    return doc


# ---------- Routes ----------
@api_router.get("/")
async def root():
    return {"message": "cdxi Partner Portal API", "status": "online"}


@api_router.post("/auth/verify-pin", response_model=PinVerifyResponse)
async def verify_pin(payload: PinVerifyRequest):
    if payload.pin == CLIENT_PIN:
        role = "client"
    elif payload.pin == CONSULTANT_PIN:
        role = "consultant"
    else:
        raise HTTPException(status_code=401, detail="Invalid PIN")
    token = secrets.token_urlsafe(32)
    await db.sessions.insert_one({
        "_id": token,
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return PinVerifyResponse(role=role, token=token)


@api_router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
        await db.sessions.delete_one({"_id": token})
    return {"ok": True}


@api_router.get("/state", response_model=StateResponse)
async def get_state(role: str = Depends(get_current_role)):
    state = await get_client_state_doc()
    expenses = await db.expenses.find({}, {"_id": 0}).to_list(1000)
    total = sum(float(e.get("amount", 0)) for e in expenses)
    nda_accepted = bool(state.get("nda_accepted")) or role == "consultant"
    return StateResponse(
        role=role,
        nda_accepted=nda_accepted,
        eaa_selection=state.get("eaa_selection"),
        strategic_reserve=STRATEGIC_RESERVE,
        active_balance=max(0.0, STRATEGIC_RESERVE - total),
        total_expenses=total,
    )


@api_router.post("/nda/accept")
async def accept_nda(role: str = Depends(get_current_role)):
    await db.client_state.update_one(
        {"_id": "singleton"},
        {"$set": {"nda_accepted": True, "nda_accepted_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True, "nda_accepted": True}


@api_router.get("/expenses", response_model=List[Expense])
async def list_expenses(role: str = Depends(get_current_role)):
    items = await db.expenses.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return items


@api_router.post("/expenses", response_model=Expense)
async def add_expense(payload: ExpenseCreate, role: str = Depends(get_current_role)):
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    if not payload.desc.strip():
        raise HTTPException(status_code=400, detail="Description required")
    now = datetime.now(timezone.utc)
    item = {
        "id": str(uuid.uuid4()),
        "desc": payload.desc.strip(),
        "amount": float(payload.amount),
        "date": now.strftime("%d %b"),
        "created_at": now.isoformat(),
    }
    await db.expenses.insert_one(dict(item))
    return item


@api_router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, role: str = Depends(get_current_role)):
    res = await db.expenses.delete_one({"id": expense_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"ok": True}


@api_router.get("/eaa/models")
async def list_eaa_models(role: str = Depends(get_current_role)):
    return EAA_MODELS


@api_router.post("/eaa/select")
async def select_eaa(payload: EaaSelectRequest, role: str = Depends(get_current_role)):
    valid_ids = {m["id"] for m in EAA_MODELS}
    if payload.tier_id not in valid_ids:
        raise HTTPException(status_code=400, detail="Invalid tier id")
    await db.client_state.update_one(
        {"_id": "singleton"},
        {"$set": {"eaa_selection": payload.tier_id, "eaa_selected_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    return {"ok": True, "eaa_selection": payload.tier_id}


@api_router.post("/urgent-signal", response_model=UrgentSignal)
async def send_urgent_signal(payload: UrgentSignalRequest, role: str = Depends(get_current_role)):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message required")
    item = {
        "id": str(uuid.uuid4()),
        "message": payload.message.strip(),
        "role": role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.urgent_signals.insert_one(dict(item))
    return item


@api_router.get("/urgent-signals", response_model=List[UrgentSignal])
async def list_urgent_signals(role: str = Depends(get_current_role)):
    if role != "consultant":
        raise HTTPException(status_code=403, detail="Consultant access only")
    items = await db.urgent_signals.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return items


@api_router.get("/projects")
async def list_projects(role: str = Depends(get_current_role)):
    return PROJECT_NODES


@api_router.get("/milestones")
async def list_milestones(role: str = Depends(get_current_role)):
    state = await get_client_state_doc()
    nda_accepted = bool(state.get("nda_accepted")) or role == "consultant"
    return [
        {"id": 1, "title": "Master NDA Execution",
         "status": "completed" if nda_accepted else "pending",
         "date": "Ongoing", "project": "Legal",
         "desc": "Mutual NDA covering all cdxi/Partner ventures."},
        {"id": 2, "title": "MVP Functional Demo", "status": "completed",
         "date": "Apr 24", "project": "m8s rates",
         "desc": "Initial result delivery ($600 project fee paid)."},
        {"id": 3, "title": "EAA Tier Selection",
         "status": "completed" if state.get("eaa_selection") else "pending",
         "date": "TBD", "project": "Account",
         "desc": "Alignment on monthly advisory access level."},
        {"id": 4, "title": "Security Posture Review", "status": "upcoming",
         "date": "Week 1", "project": "ICT Infra",
         "desc": "Infrastructure vulnerability assessment."},
    ]


# Include router and middleware
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
