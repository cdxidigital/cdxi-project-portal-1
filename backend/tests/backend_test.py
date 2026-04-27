"""Backend regression tests for cdxi Partner Portal.

Tests cover: PIN auth, NDA gate, expenses CRUD, EAA selection,
urgent signals, projects, milestones, logout invalidation.
"""
import os
import pytest
import requests
from dotenv import load_dotenv
from pathlib import Path

# Load backend .env for cleanup access if needed
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/') if os.environ.get('REACT_APP_BACKEND_URL') else None
if not BASE_URL:
    # fallback: read from frontend/.env
    fe = Path(__file__).resolve().parents[2] / "frontend" / ".env"
    for line in fe.read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip('/')

API = f"{BASE_URL}/api"
CLIENT_PIN = "4613"
CONSULTANT_PIN = "1991"


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def client_token(session):
    r = session.post(f"{API}/auth/verify-pin", json={"pin": CLIENT_PIN})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def consultant_token(session):
    r = session.post(f"{API}/auth/verify-pin", json={"pin": CONSULTANT_PIN})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def auth_headers(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- Auth ----------
class TestAuth:
    def test_root(self, session):
        r = session.get(f"{API}/")
        assert r.status_code == 200
        assert r.json().get("status") == "online"

    def test_client_pin_ok(self, session):
        r = session.post(f"{API}/auth/verify-pin", json={"pin": CLIENT_PIN})
        assert r.status_code == 200
        d = r.json()
        assert d["role"] == "client"
        assert isinstance(d["token"], str) and len(d["token"]) > 16

    def test_consultant_pin_ok(self, session):
        r = session.post(f"{API}/auth/verify-pin", json={"pin": CONSULTANT_PIN})
        assert r.status_code == 200
        assert r.json()["role"] == "consultant"

    def test_invalid_pin(self, session):
        r = session.post(f"{API}/auth/verify-pin", json={"pin": "0000"})
        assert r.status_code == 401

    def test_missing_token(self, session):
        r = session.get(f"{API}/state")
        assert r.status_code == 401

    def test_invalid_token(self, session):
        r = session.get(f"{API}/state", headers={"Authorization": "Bearer faketok"})
        assert r.status_code == 401


# ---------- State / NDA ----------
class TestStateAndNda:
    def test_state_shape_client(self, session, client_token):
        r = session.get(f"{API}/state", headers=auth_headers(client_token))
        assert r.status_code == 200
        d = r.json()
        for k in ["role", "nda_accepted", "strategic_reserve", "active_balance", "total_expenses"]:
            assert k in d
        assert d["role"] == "client"
        assert d["strategic_reserve"] == 150.0

    def test_state_consultant_nda_true(self, session, consultant_token):
        r = session.get(f"{API}/state", headers=auth_headers(consultant_token))
        assert r.status_code == 200
        assert r.json()["nda_accepted"] is True

    def test_nda_accept_persists(self, session, client_token):
        r = session.post(f"{API}/nda/accept", headers=auth_headers(client_token))
        assert r.status_code == 200
        assert r.json()["nda_accepted"] is True
        # verify
        r2 = session.get(f"{API}/state", headers=auth_headers(client_token))
        assert r2.json()["nda_accepted"] is True


# ---------- Expenses ----------
class TestExpenses:
    created_ids: list = []

    def test_add_expense_valid(self, session, client_token):
        before = session.get(f"{API}/state", headers=auth_headers(client_token)).json()
        bal_before = before["active_balance"]
        total_before = before["total_expenses"]

        payload = {"desc": "TEST_domain renewal", "amount": 12.50}
        r = session.post(f"{API}/expenses", headers=auth_headers(client_token), json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["desc"] == "TEST_domain renewal"
        assert d["amount"] == 12.50
        assert "id" in d
        TestExpenses.created_ids.append(d["id"])

        after = session.get(f"{API}/state", headers=auth_headers(client_token)).json()
        assert abs(after["total_expenses"] - (total_before + 12.50)) < 0.01
        assert abs(after["active_balance"] - (bal_before - 12.50)) < 0.01

    def test_add_expense_invalid_amount(self, session, client_token):
        r = session.post(f"{API}/expenses", headers=auth_headers(client_token),
                         json={"desc": "TEST_x", "amount": 0})
        assert r.status_code == 400

    def test_add_expense_empty_desc(self, session, client_token):
        r = session.post(f"{API}/expenses", headers=auth_headers(client_token),
                         json={"desc": "  ", "amount": 5})
        assert r.status_code == 400

    def test_list_expenses_contains_created(self, session, client_token):
        r = session.get(f"{API}/expenses", headers=auth_headers(client_token))
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()]
        for cid in TestExpenses.created_ids:
            assert cid in ids

    def test_delete_expense(self, session, client_token):
        # create a fresh one
        r = session.post(f"{API}/expenses", headers=auth_headers(client_token),
                         json={"desc": "TEST_temp", "amount": 1.00})
        eid = r.json()["id"]
        # delete
        r2 = session.delete(f"{API}/expenses/{eid}", headers=auth_headers(client_token))
        assert r2.status_code == 200
        # verify gone
        listing = session.get(f"{API}/expenses", headers=auth_headers(client_token)).json()
        assert eid not in [e["id"] for e in listing]

    def test_delete_nonexistent(self, session, client_token):
        r = session.delete(f"{API}/expenses/does-not-exist",
                           headers=auth_headers(client_token))
        assert r.status_code == 404

    def test_cleanup_test_expenses(self, session, client_token):
        listing = session.get(f"{API}/expenses", headers=auth_headers(client_token)).json()
        for e in listing:
            if e.get("desc", "").startswith("TEST_"):
                session.delete(f"{API}/expenses/{e['id']}", headers=auth_headers(client_token))


# ---------- EAA ----------
class TestEaa:
    def test_list_models(self, session):
        # public endpoint
        r = session.get(f"{API}/eaa/models")
        assert r.status_code == 200
        ids = {m["id"] for m in r.json()}
        assert ids == {"navigator", "partner", "council"}

    def test_select_valid(self, session, client_token):
        r = session.post(f"{API}/eaa/select", headers=auth_headers(client_token),
                         json={"tier_id": "partner"})
        assert r.status_code == 200
        assert r.json()["eaa_selection"] == "partner"
        s = session.get(f"{API}/state", headers=auth_headers(client_token)).json()
        assert s["eaa_selection"] == "partner"

    def test_select_invalid(self, session, client_token):
        r = session.post(f"{API}/eaa/select", headers=auth_headers(client_token),
                         json={"tier_id": "bogus"})
        assert r.status_code == 400


# ---------- Urgent signals ----------
class TestUrgentSignals:
    def test_create_signal_client(self, session, client_token):
        r = session.post(f"{API}/urgent-signal", headers=auth_headers(client_token),
                         json={"message": "TEST_urgent help"})
        assert r.status_code == 200
        d = r.json()
        assert d["message"] == "TEST_urgent help"
        assert d["role"] == "client"

    def test_list_signals_consultant(self, session, consultant_token):
        r = session.get(f"{API}/urgent-signals", headers=auth_headers(consultant_token))
        assert r.status_code == 200
        msgs = [s["message"] for s in r.json()]
        assert any(m.startswith("TEST_urgent") for m in msgs)

    def test_list_signals_client_forbidden(self, session, client_token):
        r = session.get(f"{API}/urgent-signals", headers=auth_headers(client_token))
        assert r.status_code == 403


# ---------- Projects/Milestones ----------
class TestProjectsMilestones:
    def test_projects(self, session, client_token):
        r = session.get(f"{API}/projects", headers=auth_headers(client_token))
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()}
        assert ids == {"m8s", "brand", "ops"}

    def test_milestones(self, session, client_token):
        r = session.get(f"{API}/milestones", headers=auth_headers(client_token))
        assert r.status_code == 200
        ms = r.json()
        assert len(ms) == 4
        nda_ms = next(m for m in ms if m["project"] == "Legal")
        # NDA was accepted in earlier test
        assert nda_ms["status"] == "completed"
        eaa_ms = next(m for m in ms if m["project"] == "Account")
        assert eaa_ms["status"] == "completed"  # we selected partner


# ---------- Logout ----------
class TestLogout:
    def test_logout_invalidates(self, session):
        # Get a fresh token
        r = session.post(f"{API}/auth/verify-pin", json={"pin": CLIENT_PIN})
        tok = r.json()["token"]
        # call something works
        r1 = session.get(f"{API}/state", headers=auth_headers(tok))
        assert r1.status_code == 200
        # logout
        r2 = session.post(f"{API}/auth/logout", headers=auth_headers(tok))
        assert r2.status_code == 200
        # token should now fail
        r3 = session.get(f"{API}/state", headers=auth_headers(tok))
        assert r3.status_code == 401
