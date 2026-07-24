"""Tests for gap-analysis 'Medium' additions: org settings, amount-tiered
dual approval, self-serve bank template admin UI (backend), register
export, and the analytics dashboard summary."""
import base64
import csv
import datetime as dt
import io
import subprocess

import pytest
from fastapi.testclient import TestClient

from tests.test_app import SAMPLE_FIELDS, SCHEMA, _auth, _setup_org_basics, _signup


@pytest.fixture(scope="module")
def client():
    subprocess.run(
        ["psql", "-d", "chequeapp", "-q", "-c",
         "DROP SCHEMA public CASCADE; CREATE SCHEMA public; "
         "GRANT USAGE, CREATE ON SCHEMA public TO app_user;", "-f", SCHEMA],
        check=True, capture_output=True,
    )
    from app.main import app
    return TestClient(app)


def _add_user(client, admin_tok, email, role):
    r = client.post("/users", json={"email": email, "password": "pw12345", "role": role},
                    headers=_auth(admin_tok))
    assert r.status_code == 201, r.text
    tok = client.post("/auth/login", json={"email": email, "password": "pw12345"}).json()["token"]
    return tok


def _create_cheque(client, tok, payee, tpl, amount):
    r = client.post("/cheques", json={
        "bank_template_id": tpl, "payee_id": payee,
        "amount_paise": amount, "cheque_date": str(dt.date.today())}, headers=_auth(tok))
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------- org settings ----------------

def test_org_settings_get_update_admin_only(client):
    tok, _ = _signup(client, "Org Settings", "settings@settings.test")

    r = client.get("/org/settings", headers=_auth(tok))
    assert r.status_code == 200
    assert r.json() == {"maker_checker_enabled": False, "dual_approval_threshold_paise": None}

    maker_tok = _add_user(client, tok, "maker@settings.test", "maker")
    r = client.patch("/org/settings", json={"maker_checker_enabled": True}, headers=_auth(maker_tok))
    assert r.status_code == 403

    r = client.patch("/org/settings",
                     json={"maker_checker_enabled": True, "dual_approval_threshold_paise": 10000000},
                     headers=_auth(tok))
    assert r.status_code == 200
    assert r.json() == {"maker_checker_enabled": True, "dual_approval_threshold_paise": 10000000}

    r = client.patch("/org/settings", json={"dual_approval_threshold_paise": 0}, headers=_auth(tok))
    assert r.status_code == 400 and r.json()["error"]["field"] == "dual_approval_threshold_paise"

    r = client.patch("/org/settings", json={"clear_dual_approval_threshold": True}, headers=_auth(tok))
    assert r.status_code == 200 and r.json()["dual_approval_threshold_paise"] is None


# ---------------- amount-tiered dual approval ----------------

def test_dual_approval_required_above_threshold(client):
    admin_tok, _ = _signup(client, "Org Dual", "admin@dual.test")
    payee, tpl = _setup_org_basics(client, admin_tok)
    client.patch("/org/settings",
                 json={"maker_checker_enabled": True, "dual_approval_threshold_paise": 10000000},
                 headers=_auth(admin_tok))  # >= Rs 1,00,000 needs 2 checkers
    checker1 = _add_user(client, admin_tok, "checker1@dual.test", "checker")
    checker2 = _add_user(client, admin_tok, "checker2@dual.test", "checker")

    big_id = _create_cheque(client, admin_tok, payee, tpl, 15000000)  # Rs 1,50,000 -> dual required
    small_id = _create_cheque(client, admin_tok, payee, tpl, 500000)  # Rs 5,000 -> single approval

    client.post(f"/cheques/{small_id}/submit", headers=_auth(admin_tok))
    client.post(f"/cheques/{big_id}/submit", headers=_auth(admin_tok))

    # small cheque: one checker approval is final
    r = client.post(f"/cheques/{small_id}/approve", headers=_auth(checker1))
    assert r.status_code == 200 and r.json()["status"] == "approved"

    # big cheque: first approval only moves to pending_second_approval
    r = client.post(f"/cheques/{big_id}/approve", headers=_auth(checker1))
    assert r.status_code == 200
    assert r.json()["status"] == "pending_second_approval"
    assert r.json()["first_approved_by"] is not None

    # the same checker cannot give the second approval
    r = client.post(f"/cheques/{big_id}/approve", headers=_auth(checker1))
    assert r.status_code == 403

    # the creator still can never approve, even at the second stage
    r = client.post(f"/cheques/{big_id}/approve", headers=_auth(admin_tok))
    assert r.status_code == 403

    # a different checker gives the final approval
    r = client.post(f"/cheques/{big_id}/approve", headers=_auth(checker2))
    assert r.status_code == 200 and r.json()["status"] == "approved"

    # only now can it be printed
    r = client.post(f"/cheques/{big_id}/print", headers=_auth(admin_tok))
    assert r.status_code == 200


def test_dual_approval_reject_from_either_stage(client):
    admin_tok, _ = _signup(client, "Org Dual Reject", "admin@dualreject.test")
    payee, tpl = _setup_org_basics(client, admin_tok)
    client.patch("/org/settings",
                 json={"maker_checker_enabled": True, "dual_approval_threshold_paise": 10000000},
                 headers=_auth(admin_tok))
    checker1 = _add_user(client, admin_tok, "c1@dualreject.test", "checker")

    cheque_id = _create_cheque(client, admin_tok, payee, tpl, 20000000)
    client.post(f"/cheques/{cheque_id}/submit", headers=_auth(admin_tok))
    client.post(f"/cheques/{cheque_id}/approve", headers=_auth(checker1))  # -> pending_second_approval

    r = client.post(f"/cheques/{cheque_id}/reject", json={"reason": "wrong amount"}, headers=_auth(checker1))
    assert r.status_code == 200 and r.json()["status"] == "rejected"


# ---------------- self-serve bank template admin endpoints ----------------

def test_bank_template_get_and_patch_admin_only(client):
    admin_tok, _ = _signup(client, "Org Tpl", "admin@tpl.test")
    maker_tok = _add_user(client, admin_tok, "maker@tpl.test", "maker")
    tpl = client.post("/bank-templates", json={
        "bank_name": "SBI", "page_width_mm": 203, "page_height_mm": 92,
        "fields": SAMPLE_FIELDS}, headers=_auth(admin_tok)).json()

    # a maker cannot create or edit templates
    r = client.post("/bank-templates", json={
        "bank_name": "ICICI", "page_width_mm": 200, "page_height_mm": 90,
        "fields": SAMPLE_FIELDS}, headers=_auth(maker_tok))
    assert r.status_code == 403

    r = client.get(f"/bank-templates/{tpl['id']}", headers=_auth(admin_tok))
    assert r.status_code == 200 and r.json()["bank_name"] == "SBI"
    assert r.json()["fields"]["payee_name"]["x_mm"] == SAMPLE_FIELDS["payee_name"]["x_mm"]

    r = client.patch(f"/bank-templates/{tpl['id']}", json={
        "bank_name": "SBI Updated", "page_width_mm": 210, "page_height_mm": 95,
        "fields": SAMPLE_FIELDS}, headers=_auth(maker_tok))
    assert r.status_code == 403

    r = client.patch(f"/bank-templates/{tpl['id']}", json={
        "bank_name": "SBI Updated", "page_width_mm": 210, "page_height_mm": 95,
        "fields": SAMPLE_FIELDS}, headers=_auth(admin_tok))
    assert r.status_code == 200 and r.json()["bank_name"] == "SBI Updated"
    assert r.json()["page_width_mm"] == 210


# ---------------- exportable register ----------------

def test_export_register_csv_and_pdf(client):
    tok, _ = _signup(client, "Org Export", "export@export.test")
    payee, tpl = _setup_org_basics(client, tok)
    _create_cheque(client, tok, payee, tpl, 250000)

    r = client.get("/cheques/export?format=csv", headers=_auth(tok))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["Date", "Payee", "Amount (INR)", "Status", "Memo"]
    assert rows[1][1] == "Sharma Traders Pvt Ltd"
    assert rows[1][2] == "2500.00"

    r = client.get("/cheques/export?format=pdf", headers=_auth(tok))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")

    r = client.get("/cheques/export?format=xls", headers=_auth(tok))
    assert r.status_code == 400 and r.json()["error"]["field"] == "format"


# ---------------- analytics dashboard ----------------

def test_analytics_summary(client):
    tok, _ = _signup(client, "Org Analytics", "admin@analytics.test")
    payee, tpl = _setup_org_basics(client, tok)
    checker_tok = _add_user(client, tok, "checker@analytics.test", "checker")

    c1 = _create_cheque(client, tok, payee, tpl, 100000)
    c2 = _create_cheque(client, tok, payee, tpl, 200000)
    client.post(f"/cheques/{c1}/submit", headers=_auth(tok))
    client.post(f"/cheques/{c1}/approve", headers=_auth(checker_tok))

    r = client.get("/analytics/summary", headers=_auth(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["by_status"]["approved"] == 1
    assert body["by_status"]["draft"] == 1
    assert body["pending_approval_count"] == 0
    payee_totals = {p["payee_name"]: p["total_paise"] for p in body["spend_by_payee"]}
    assert payee_totals["Sharma Traders Pvt Ltd"] == 300000
    assert len(body["spend_by_month"]) == 1
    assert body["avg_approval_hours"] is not None
