"""
Backend tests for cdxi Admin OS.
Covers: auth, KPIs, clients CRUD, milestones toggle + business rule,
Stripe checkout session creation, unauth 401s.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://cdxi-admin-os.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@cdxi.com"
ADMIN_PASSWORD = "cdxi2026"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data and isinstance(data["access_token"], str)
    assert data["user"]["email"] == ADMIN_EMAIL
    return data["access_token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# --- Auth ---
class TestAuth:
    def test_login_success(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["user"]["email"] == ADMIN_EMAIL
        assert d["user"]["role"] == "admin"
        assert len(d["access_token"]) > 20

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=30)
        assert r.status_code == 401

    def test_me_with_token(self, auth_headers):
        r = requests.get(f"{API}/auth/me", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_me_without_token_401(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_kpis_unauth_401(self):
        r = requests.get(f"{API}/kpis", timeout=30)
        assert r.status_code == 401

    def test_clients_unauth_401(self):
        r = requests.get(f"{API}/clients", timeout=30)
        assert r.status_code == 401


# --- KPIs ---
class TestKPIs:
    def test_kpis_shape(self, auth_headers):
        r = requests.get(f"{API}/kpis", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("active_projects", "revenue_pipeline", "overdue_payments", "total_clients"):
            assert k in d
        assert isinstance(d["active_projects"], int)
        assert isinstance(d["total_clients"], int)
        assert d["total_clients"] >= 2  # seed data


# --- Clients / Seed ---
class TestClients:
    def test_list_clients_seed(self, auth_headers):
        r = requests.get(f"{API}/clients", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        clients = r.json()
        assert isinstance(clients, list)
        assert len(clients) >= 2
        names = {c["name"] for c in clients}
        assert "Christian Dix" in names
        assert "Bianca Scott" in names

        cd = next(c for c in clients if c["name"] == "Christian Dix")
        assert cd["project"] is not None
        assert cd["project"]["name"] == "m8s rates"
        assert cd["project"]["progress"] == 66
        # next unpaid milestone
        assert cd["project"]["next_payment"] == 1100.0
        assert cd["project"]["next_due"] == "2026-04-29"
        assert len(cd["project"]["milestones"]) == 3

        bs = next(c for c in clients if c["name"] == "Bianca Scott")
        assert bs["project"]["progress"] == 100
        assert bs["project"]["status"] == "Completed"
        assert bs["project"]["next_payment"] is None


# --- Client + Project + Milestone lifecycle ---
class TestLifecycle:
    created_client_id = None
    created_project_id = None
    created_milestone_id = None

    def test_01_create_client(self, auth_headers):
        payload = {"name": "TEST_Client_X", "email": "testx@example.com", "project_name": "TEST_Project_X", "total_amount": 500.0}
        r = requests.post(f"{API}/clients", headers=auth_headers, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "TEST_Client_X"
        assert data["project"]["name"] == "TEST_Project_X"
        assert data["project"]["progress"] == 0
        TestLifecycle.created_client_id = data["id"]
        TestLifecycle.created_project_id = data["project"]["id"]

    def test_02_get_client(self, auth_headers):
        r = requests.get(f"{API}/clients/{TestLifecycle.created_client_id}", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_Client_X"

    def test_03_add_milestone(self, auth_headers):
        payload = {"name": "TEST_Milestone_1", "amount": 250.0, "due_date": "2026-05-01"}
        r = requests.post(f"{API}/projects/{TestLifecycle.created_project_id}/milestones",
                          headers=auth_headers, json=payload, timeout=30)
        assert r.status_code == 200
        m = r.json()
        assert m["name"] == "TEST_Milestone_1"
        assert m["payment_status"] == "unpaid"
        assert m["completed"] is False
        TestLifecycle.created_milestone_id = m["id"]

    def test_04_complete_before_paid_returns_400(self, auth_headers):
        r = requests.patch(f"{API}/milestones/{TestLifecycle.created_milestone_id}",
                           headers=auth_headers, json={"completed": True}, timeout=30)
        assert r.status_code == 400
        assert "paid" in r.json().get("detail", "").lower()

    def test_05_toggle_paid(self, auth_headers):
        r = requests.patch(f"{API}/milestones/{TestLifecycle.created_milestone_id}",
                           headers=auth_headers, json={"payment_status": "paid"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["payment_status"] == "paid"

    def test_06_can_complete_after_paid(self, auth_headers):
        r = requests.patch(f"{API}/milestones/{TestLifecycle.created_milestone_id}",
                           headers=auth_headers, json={"completed": True}, timeout=30)
        assert r.status_code == 200
        assert r.json()["completed"] is True

    def test_07_toggle_unpaid_persists(self, auth_headers):
        r = requests.patch(f"{API}/milestones/{TestLifecycle.created_milestone_id}",
                           headers=auth_headers, json={"payment_status": "unpaid", "completed": False}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["payment_status"] == "unpaid"

        # verify via GET client
        r2 = requests.get(f"{API}/clients/{TestLifecycle.created_client_id}", headers=auth_headers, timeout=30)
        ms = r2.json()["project"]["milestones"]
        target = next(m for m in ms if m["id"] == TestLifecycle.created_milestone_id)
        assert target["payment_status"] == "unpaid"

    def test_08_stripe_checkout(self, auth_headers):
        # Set paid status first to unpaid (already is); then create checkout
        r = requests.post(f"{API}/milestones/{TestLifecycle.created_milestone_id}/checkout",
                          headers=auth_headers, json={"origin_url": BASE_URL}, timeout=60)
        # May be 200 with stripe url, or 400 if stripe key rejects test mode
        assert r.status_code == 200, f"checkout failed: {r.status_code} {r.text}"
        data = r.json()
        assert "url" in data and data["url"].startswith("http")
        assert "session_id" in data
        TestLifecycle.session_id = data["session_id"]

    def test_09_payment_status_poll(self, auth_headers):
        sid = getattr(TestLifecycle, "session_id", None)
        if not sid:
            pytest.skip("no session id")
        r = requests.get(f"{API}/payments/status/{sid}", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["session_id"] == sid
        assert "payment_status" in d
        assert "status" in d

    def test_10_delete_cascade(self, auth_headers):
        r = requests.delete(f"{API}/clients/{TestLifecycle.created_client_id}", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        # verify client gone
        r2 = requests.get(f"{API}/clients/{TestLifecycle.created_client_id}", headers=auth_headers, timeout=30)
        assert r2.status_code == 404
