"""Tests for Tasks 5.7 (ESC/P) and 5.8 (billing) plus calibration."""
import base64
import datetime as dt
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


def _make_printed_cheque(client, tok, payee, tpl, amount=100000):
    cheque = client.post("/cheques", json={
        "bank_template_id": tpl, "payee_id": payee,
        "amount_paise": amount, "cheque_date": str(dt.date.today())},
        headers=_auth(tok)).json()
    r = client.post(f"/cheques/{cheque['id']}/print", headers=_auth(tok))
    assert r.status_code == 200
    return cheque["id"], r.json()


# ---------------- Task 5.7 — ESC/P dot matrix path ----------------

def test_escp_unit_grid_positioning():
    from app.escp import generate_cheque_escp
    tpl = {"printer_offset_x_mm": 0, "printer_offset_y_mm": 0, "fields": SAMPLE_FIELDS}
    out = generate_cheque_escp(tpl, {
        "payee_name": "Sharma Traders", "amount_figures": "45,000.00",
        "amount_words": "Forty Five Thousand Rupees Only",
        "date_day": "17", "date_month": "07", "date_year": "2026"})
    assert out.startswith(b"\x1b@")           # ESC @ init
    assert out.endswith(b"\x0c")              # form feed to next cheque
    assert b"Sharma Traders" in out
    # date row (y=8mm -> row 2) comes before payee row (y=18mm -> row 4)
    assert out.index(b"2026") < out.index(b"Sharma Traders")


def test_print_escp_format(client):
    tok, _ = _signup(client, "Org DM", "dm@dm.test")
    payee, tpl = _setup_org_basics(client, tok)
    cheque = client.post("/cheques", json={
        "bank_template_id": tpl, "payee_id": payee,
        "amount_paise": 4500000, "cheque_date": str(dt.date.today())},
        headers=_auth(tok)).json()
    r = client.post(f"/cheques/{cheque['id']}/print?format=escp", headers=_auth(tok))
    assert r.status_code == 200
    raw = base64.b64decode(r.json()["escp_base64"])
    assert raw.startswith(b"\x1b@") and b"Sharma Traders" in raw

    # reprint in the other format works off the same single row
    r = client.post(f"/cheques/{cheque['id']}/reprint?format=pdf", headers=_auth(tok))
    assert r.status_code == 200
    assert base64.b64decode(r.json()["pdf_base64"]).startswith(b"%PDF")

    r = client.post(f"/cheques/{cheque['id']}/reprint?format=fax", headers=_auth(tok))
    assert r.status_code == 400 and r.json()["error"]["field"] == "format"


# ---------------- calibration ----------------

def test_calibration_offsets_apply(client):
    tok, _ = _signup(client, "Org Cal", "cal@cal.test")
    payee, tpl = _setup_org_basics(client, tok)
    r = client.patch(f"/bank-templates/{tpl}/calibration",
                     json={"printer_offset_x_mm": 2.5, "printer_offset_y_mm": -1.0},
                     headers=_auth(tok))
    assert r.status_code == 200 and r.json()["printer_offset_x_mm"] == 2.5
    listed = client.get("/bank-templates", headers=_auth(tok)).json()
    assert listed[0]["printer_offset_x_mm"] == 2.5
    # printing still succeeds with offsets applied
    _make_printed_cheque(client, tok, payee, tpl)


# ---------------- Task 5.8 — billing lifecycle ----------------

def test_billing_grace_then_lapse_then_recover(client):
    tok, org_id = _signup(client, "Org Bill", "bill@bill.test")
    payee, tpl = _setup_org_basics(client, tok)

    # payment failure -> grace; writes still allowed during grace
    r = client.post("/billing/webhook", json={
        "event_id": "evt_1", "event": "payment.failed", "org_id": org_id})
    assert r.json()["status"] == "grace"
    _make_printed_cheque(client, tok, payee, tpl)  # succeeds in grace

    # duplicate delivery of the same event is a no-op
    r = client.post("/billing/webhook", json={
        "event_id": "evt_1", "event": "payment.failed", "org_id": org_id})
    assert r.json()["duplicate"] is True

    # time-travel: expire the grace window
    subprocess.run(["psql", "-d", "chequeapp", "-q", "-c",
        f"UPDATE organizations SET grace_until = now() - interval '1 day' WHERE id = '{org_id}'"],
        check=True, capture_output=True)

    # write blocked with SUBSCRIPTION_LAPSED...
    r = client.post("/cheques", json={
        "bank_template_id": tpl, "payee_id": payee,
        "amount_paise": 100, "cheque_date": str(dt.date.today())}, headers=_auth(tok))
    assert r.status_code == 402
    assert r.json()["error"]["code"] == "SUBSCRIPTION_LAPSED"

    # ...but reads keep working (read-only fallback, not lockout)
    r = client.get("/cheques", headers=_auth(tok))
    assert r.status_code == 200 and len(r.json()) == 1
    assert client.get("/billing/status", headers=_auth(tok)).json()["subscription_status"] == "lapsed"

    # successful payment recovers to active; writes work again
    r = client.post("/billing/webhook", json={
        "event_id": "evt_2", "event": "payment.captured", "org_id": org_id})
    assert r.json()["status"] == "active"
    r = client.post("/cheques", json={
        "bank_template_id": tpl, "payee_id": payee,
        "amount_paise": 100, "cheque_date": str(dt.date.today())}, headers=_auth(tok))
    assert r.status_code == 201
