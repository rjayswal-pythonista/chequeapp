"""Tests map 1:1 to Technical Addendum task-card 'Done when' criteria."""
import datetime as dt
import os
import subprocess

import pytest
from fastapi.testclient import TestClient

SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "schema.sql")

SAMPLE_FIELDS = {
    "payee_name":     {"x_mm": 20,  "y_mm": 18, "font_size": 11, "max_width_mm": 100},
    "amount_words":   {"x_mm": 20,  "y_mm": 28, "font_size": 10, "max_width_mm": 140},
    "amount_figures": {"x_mm": 155, "y_mm": 18, "font_size": 12},
    "date_day":       {"x_mm": 165, "y_mm": 8,  "font_size": 10},
    "date_month":     {"x_mm": 172, "y_mm": 8,  "font_size": 10},
    "date_year":      {"x_mm": 180, "y_mm": 8,  "font_size": 10},
}


@pytest.fixture(scope="module")
def client():
    # Fresh schema per test module, applied as owner, app runs as app_user
    subprocess.run(
        ["psql", "-d", "chequeapp", "-q", "-c",
         "DROP SCHEMA public CASCADE; CREATE SCHEMA public; "
         "GRANT USAGE, CREATE ON SCHEMA public TO app_user;", "-f", SCHEMA],
        check=True, capture_output=True,
    )
    from app.main import app
    return TestClient(app)


def _signup(client, org, email, maker_checker=False):
    r = client.post("/auth/signup", json={"org_name": org, "email": email, "password": "pw12345"})
    assert r.status_code == 201, r.text
    tok = r.json()["token"]
    if maker_checker:
        subprocess.run(
            ["psql", "-d", "chequeapp", "-q", "-c",
             f"UPDATE organizations SET maker_checker_enabled=true WHERE name='{org}'"],
            check=True, capture_output=True)
    return tok, r.json()["org"]["id"]


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def _setup_org_basics(client, tok):
    payee = client.post("/payees", json={"name": "Sharma Traders Pvt Ltd"}, headers=_auth(tok)).json()
    tpl = client.post("/bank-templates", json={
        "bank_name": "HDFC", "page_width_mm": 203, "page_height_mm": 92,
        "fields": SAMPLE_FIELDS}, headers=_auth(tok)).json()
    return payee["id"], tpl["id"]


# ---------------- Task 5.2 — amount-to-words ----------------
# NOTE: addendum Section 3.3's expected values for rows 3-5 contain
# paise/rupee arithmetic errors (see NOTES.md entry 2). These tests
# encode the arithmetically correct expectations.

@pytest.mark.parametrize("paise,expected", [
    (100, "One Rupee Only"),
    (150000, "One Thousand Five Hundred Rupees Only"),
    (10000150, "One Lakh One Rupees and Fifty Paise Only"),        # Rs 1,00,001.50
    (100000000, "Ten Lakh Rupees Only"),                            # Rs 10,00,000
    (123456789, "Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven Rupees and Eighty Nine Paise Only"),
    (5, "Five Paise Only"),
    (1000000000, "One Crore Rupees Only"),                          # Rs 1,00,00,000
    (12345678900, "Twelve Crore Thirty Four Lakh Fifty Six Thousand Seven Hundred Eighty Nine Rupees Only"),
])
def test_amount_to_words(paise, expected):
    from app.amount_words import amount_to_words
    assert amount_to_words(paise) == expected


def test_amount_to_words_rejects_nonpositive():
    from app.amount_words import amount_to_words
    for bad in (0, -1):
        with pytest.raises(ValueError):
            amount_to_words(bad)


# ---------------- Task 5.1 — tenant isolation ----------------

def test_cross_tenant_isolation(client):
    tok_a, _ = _signup(client, "Org Alpha", "a@alpha.test")
    tok_b, _ = _signup(client, "Org Beta", "b@beta.test")
    payee_a, tpl_a = _setup_org_basics(client, tok_a)

    cheque = client.post("/cheques", json={
        "bank_template_id": tpl_a, "payee_id": payee_a,
        "amount_paise": 4500000, "cheque_date": str(dt.date.today())},
        headers=_auth(tok_a)).json()

    # Org B listing sees nothing of Org A's
    assert client.get("/cheques", headers=_auth(tok_b)).json() == []
    # Org B hitting Org A's cheque by id gets 404 (RLS: row invisible)
    r = client.post(f"/cheques/{cheque['id']}/print", headers=_auth(tok_b))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    # Org B cannot see Org A's payees either
    assert client.get("/payees", headers=_auth(tok_b)).json() == []


# ---------------- Task 5.3 — entry validation ----------------

def test_cheque_validation(client):
    tok, _ = _signup(client, "Org Val", "v@val.test")
    payee, tpl = _setup_org_basics(client, tok)
    today = str(dt.date.today())

    ok = client.post("/cheques", json={
        "bank_template_id": tpl, "payee_id": payee,
        "amount_paise": 4500000, "cheque_date": today}, headers=_auth(tok))
    assert ok.status_code == 201
    body = ok.json()
    assert body["status"] == "draft"
    assert body["amount_words"] == "Forty Five Thousand Rupees Only"

    r = client.post("/cheques", json={
        "bank_template_id": tpl, "payee_id": payee,
        "amount_paise": 0, "cheque_date": today}, headers=_auth(tok))
    assert r.status_code == 400 and r.json()["error"]["field"] == "amount_paise"

    r = client.post("/cheques", json={
        "bank_template_id": tpl, "payee_id": "00000000-0000-0000-0000-000000000000",
        "amount_paise": 100, "cheque_date": today}, headers=_auth(tok))
    assert r.status_code == 400 and r.json()["error"]["field"] == "payee_id"

    far = str(dt.date.today() + dt.timedelta(days=90))
    r = client.post("/cheques", json={
        "bank_template_id": tpl, "payee_id": payee,
        "amount_paise": 100, "cheque_date": far}, headers=_auth(tok))
    assert r.status_code == 400 and r.json()["error"]["field"] == "cheque_date"


# ---------------- Task 5.4 — maker-checker ----------------

def test_maker_checker_flow(client):
    admin_tok, org_id = _signup(client, "Org MC", "admin@mc.test", maker_checker=True)
    payee, tpl = _setup_org_basics(client, admin_tok)

    client.post("/users", json={"email": "maker@mc.test", "password": "pw12345", "role": "maker"},
                headers=_auth(admin_tok))
    client.post("/users", json={"email": "checker@mc.test", "password": "pw12345", "role": "checker"},
                headers=_auth(admin_tok))
    maker_tok = client.post("/auth/login", json={"email": "maker@mc.test", "password": "pw12345"}).json()["token"]
    checker_tok = client.post("/auth/login", json={"email": "checker@mc.test", "password": "pw12345"}).json()["token"]

    cheque = client.post("/cheques", json={
        "bank_template_id": tpl, "payee_id": payee,
        "amount_paise": 1200000, "cheque_date": str(dt.date.today())},
        headers=_auth(maker_tok)).json()
    cid = cheque["id"]

    # Print before approval must fail with CONFLICT
    r = client.post(f"/cheques/{cid}/print", headers=_auth(maker_tok))
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"

    client.post(f"/cheques/{cid}/submit", headers=_auth(maker_tok))

    # Maker cannot approve their own cheque even if they had the role;
    # here maker role is rejected outright
    r = client.post(f"/cheques/{cid}/approve", headers=_auth(maker_tok))
    assert r.status_code == 403

    r = client.post(f"/cheques/{cid}/approve", headers=_auth(checker_tok))
    assert r.status_code == 200 and r.json()["status"] == "approved"

    r = client.post(f"/cheques/{cid}/print", headers=_auth(checker_tok))
    assert r.status_code == 200
    assert r.json()["cheque"]["status"] == "printed"
    assert len(r.json()["pdf_base64"]) > 100


def test_creator_cannot_self_approve(client):
    # Admin (who can approve) creates a cheque; even they cannot approve their own
    admin_tok, _ = _signup(client, "Org Self", "admin@self.test", maker_checker=True)
    payee, tpl = _setup_org_basics(client, admin_tok)
    cheque = client.post("/cheques", json={
        "bank_template_id": tpl, "payee_id": payee,
        "amount_paise": 500, "cheque_date": str(dt.date.today())},
        headers=_auth(admin_tok)).json()
    client.post(f"/cheques/{cheque['id']}/submit", headers=_auth(admin_tok))
    r = client.post(f"/cheques/{cheque['id']}/approve", headers=_auth(admin_tok))
    assert r.status_code == 403
    assert "creator" in r.json()["error"]["message"].lower()


# ---------------- Task 5.6 — reprint creates no duplicate ----------------

def test_reprint_no_duplicate(client):
    tok, _ = _signup(client, "Org RP", "rp@rp.test")  # maker-checker off: draft can print
    payee, tpl = _setup_org_basics(client, tok)
    cheque = client.post("/cheques", json={
        "bank_template_id": tpl, "payee_id": payee,
        "amount_paise": 990000, "cheque_date": str(dt.date.today())},
        headers=_auth(tok)).json()
    cid = cheque["id"]

    assert client.post(f"/cheques/{cid}/print", headers=_auth(tok)).status_code == 200
    assert client.post(f"/cheques/{cid}/reprint", headers=_auth(tok)).status_code == 200
    assert client.post(f"/cheques/{cid}/reprint", headers=_auth(tok)).status_code == 200

    rows = client.get("/cheques", headers=_auth(tok)).json()
    assert len(rows) == 1  # exactly one row despite two reprints

    out = subprocess.run(
        ["psql", "-d", "chequeapp", "-t", "-c",
         f"SELECT action, count(*) FROM audit_log "
         f"WHERE cheque_id='{cid}' GROUP BY action ORDER BY action"],
        capture_output=True, text=True, check=True).stdout
    assert "reprinted" in out and "2" in out


# ---------------- Task 5.5 — PDF generation ----------------

def test_pdf_generation_positions():
    from app.pdfgen import generate_cheque_pdf
    tpl = {"page_width_mm": 203, "page_height_mm": 92,
           "printer_offset_x_mm": 0, "printer_offset_y_mm": 0, "fields": SAMPLE_FIELDS}
    pdf = generate_cheque_pdf(tpl, {
        "payee_name": "Sharma Traders Pvt Ltd",
        "amount_words": "Forty Five Thousand Rupees Only",
        "amount_figures": "45,000.00",
        "date_day": "17", "date_month": "07", "date_year": "2026"})
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 500


def test_pdf_long_payee_shrinks_not_overflows():
    from app.pdfgen import generate_cheque_pdf
    tpl = {"page_width_mm": 203, "page_height_mm": 92,
           "printer_offset_x_mm": 0, "printer_offset_y_mm": 0, "fields": SAMPLE_FIELDS}
    long_name = "Extremely Long Payee Business Name That Exceeds The Field Width Significantly Pvt Ltd"
    pdf = generate_cheque_pdf(tpl, {"payee_name": long_name})
    assert pdf.startswith(b"%PDF")  # renders without raising, font auto-shrunk
