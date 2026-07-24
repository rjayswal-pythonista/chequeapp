"""Cheque Printing SaaS backend — Tasks 5.1, 5.3, 5.4, 5.6.

Every authenticated request derives org_id from the JWT (never from the
request body) and binds it to the DB connection's RLS context, so a
query physically cannot see another tenant's rows.
"""
import base64
import csv
import datetime as dt
import io
import os

from fastapi import Depends, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import billing, core
from app.amount_words import amount_to_words
from app.escp import generate_cheque_escp
from app.pdfgen import generate_cheque_pdf

app = FastAPI(title="Cheque Printing SaaS")

# Comma-separated list of allowed frontend origins, e.g.
# "https://myapp.vercel.app,http://localhost:5173"
_origins = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATE_WINDOW_DAYS = 30  # cheque_date must be within +/- this many days


# ---------- standard error shape (addendum 4.1) ----------

class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, field: str | None = None):
        self.status, self.code, self.message, self.field = status, code, message, field


@app.exception_handler(ApiError)
async def api_error_handler(_req: Request, exc: ApiError):
    body = {"error": {"code": exc.code, "message": exc.message}}
    if exc.field:
        body["error"]["field"] = exc.field
    return JSONResponse(status_code=exc.status, content=body)


# ---------- auth dependency (Task 5.1) ----------

def current_user(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise ApiError(401, "UNAUTHORIZED", "Missing bearer token.")
    try:
        claims = core.decode_token(authorization.removeprefix("Bearer "))
    except Exception:
        raise ApiError(401, "UNAUTHORIZED", "Invalid or expired token.")
    return claims  # {sub, org_id, role}


def org_conn(claims: dict = Depends(current_user)):
    """Connection with RLS context bound to the caller's org."""
    with core.connect() as conn:
        core.set_org_context(conn, claims["org_id"])
        yield conn, claims


def org_conn_writable(claims: dict = Depends(current_user)):
    """Like org_conn, but blocks writes once the subscription has lapsed
    (Task 5.8 read-only fallback). Reads stay on org_conn and keep working."""
    with core.connect() as conn:
        core.set_org_context(conn, claims["org_id"])
        writable, status = billing.check_writable(conn, claims["org_id"])
        if not writable:
            raise ApiError(402, "SUBSCRIPTION_LAPSED",
                           "Subscription has lapsed. Viewing and search remain available; "
                           "renew to create or print cheques.")
        yield conn, claims


# ---------- schemas ----------

class SignupIn(BaseModel):
    org_name: str
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class PayeeIn(BaseModel):
    name: str


class TemplateIn(BaseModel):
    bank_name: str
    page_width_mm: float
    page_height_mm: float
    fields: dict


class ChequeIn(BaseModel):
    bank_template_id: str
    payee_id: str
    amount_paise: int
    cheque_date: dt.date
    memo: str | None = None


class RejectIn(BaseModel):
    reason: str


class UserIn(BaseModel):
    email: str
    password: str
    role: str  # 'maker' | 'checker' | 'admin'


# ---------- audit helper ----------

def audit(conn, org_id, cheque_id, actor, action, detail=None):
    import json
    conn.execute(
        "INSERT INTO audit_log (org_id, cheque_id, actor_user_id, action, detail) "
        "VALUES (%s, %s, %s, %s, %s)",
        (org_id, cheque_id, actor, action, json.dumps(detail) if detail else None),
    )


# ---------- auth endpoints ----------

@app.post("/auth/signup", status_code=201)
def signup(body: SignupIn):
    with core.connect() as conn:
        org = conn.execute(
            "INSERT INTO organizations (name) VALUES (%s) RETURNING id, name, plan_tier, maker_checker_enabled",
            (body.org_name,),
        ).fetchone()
        core.set_org_context(conn, org["id"])
        try:
            user = conn.execute(
                "INSERT INTO users (org_id, email, password_hash, role) "
                "VALUES (%s, %s, %s, 'admin') RETURNING id, email, role",
                (org["id"], body.email, core.hash_password(body.password)),
            ).fetchone()
        except Exception:
            raise ApiError(409, "CONFLICT", "An account with this email already exists.", "email")
        token = core.make_token(user["id"], org["id"], "admin")
        return {"user": {**user, "id": str(user["id"])},
                "org": {**org, "id": str(org["id"])},
                "token": token}


@app.post("/auth/login")
def login(body: LoginIn):
    with core.connect() as conn:
        row = conn.execute(
            "SELECT id, org_id, role, password_hash FROM users WHERE email = %s", (body.email,)
        ).fetchone()
    if not row or not core.check_password(body.password, row["password_hash"]):
        raise ApiError(401, "UNAUTHORIZED", "Invalid email or password.")
    return {"token": core.make_token(row["id"], row["org_id"], row["role"])}


@app.post("/users", status_code=201)
def add_user(body: UserIn, dep=Depends(org_conn)):
    conn, claims = dep
    if claims["role"] != "admin":
        raise ApiError(403, "FORBIDDEN", "Only admins can add users.")
    if body.role not in ("admin", "maker", "checker"):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid role.", "role")
    try:
        user = conn.execute(
            "INSERT INTO users (org_id, email, password_hash, role) VALUES (%s,%s,%s,%s) "
            "RETURNING id, email, role",
            (claims["org_id"], body.email, core.hash_password(body.password), body.role),
        ).fetchone()
    except Exception:
        raise ApiError(409, "CONFLICT", "An account with this email already exists.", "email")
    return {**user, "id": str(user["id"])}


# ---------- payees ----------

@app.get("/payees")
def list_payees(dep=Depends(org_conn)):
    conn, _ = dep
    rows = conn.execute("SELECT id, name FROM payees ORDER BY name").fetchall()
    return [{**r, "id": str(r["id"])} for r in rows]


@app.post("/payees", status_code=201)
def create_payee(body: PayeeIn, dep=Depends(org_conn_writable)):
    conn, claims = dep
    if not body.name.strip():
        raise ApiError(400, "VALIDATION_ERROR", "Payee name is required.", "name")
    row = conn.execute(
        "INSERT INTO payees (org_id, name) VALUES (%s, %s) RETURNING id, name",
        (claims["org_id"], body.name.strip()),
    ).fetchone()
    return {**row, "id": str(row["id"])}


# ---------- bank templates ----------

@app.post("/bank-templates", status_code=201)
def create_template(body: TemplateIn, dep=Depends(org_conn_writable)):
    import json
    conn, claims = dep
    row = conn.execute(
        "INSERT INTO bank_templates (org_id, bank_name, page_width_mm, page_height_mm, fields) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id, bank_name",
        (claims["org_id"], body.bank_name, body.page_width_mm, body.page_height_mm, json.dumps(body.fields)),
    ).fetchone()
    return {**row, "id": str(row["id"])}


# ---------- cheques (Tasks 5.3, 5.4, 5.6) ----------

def _get_cheque(conn, cheque_id):
    row = conn.execute("SELECT * FROM cheques WHERE id = %s", (cheque_id,)).fetchone()
    if not row:
        # RLS makes another org's cheque indistinguishable from a missing one
        raise ApiError(404, "NOT_FOUND", "Cheque not found.")
    return row


def _serialize(row):
    out = {k: v for k, v in row.items()}
    for k in ("id", "org_id", "bank_template_id", "payee_id", "created_by", "approved_by"):
        if out.get(k) is not None:
            out[k] = str(out[k])
    out["cheque_date"] = str(out["cheque_date"])
    for k in ("printed_at", "created_at"):
        if out.get(k) is not None:
            out[k] = out[k].isoformat()
    return out


@app.post("/cheques", status_code=201)
def create_cheque(body: ChequeIn, dep=Depends(org_conn_writable)):
    conn, claims = dep
    # Task 5.3 validation — reject before anything reaches the register
    if body.amount_paise <= 0:
        raise ApiError(400, "VALIDATION_ERROR", "Amount must be greater than zero.", "amount_paise")
    today = dt.date.today()
    if abs((body.cheque_date - today).days) > DATE_WINDOW_DAYS:
        raise ApiError(400, "VALIDATION_ERROR",
                       f"Cheque date must be within {DATE_WINDOW_DAYS} days of today.", "cheque_date")
    if not conn.execute("SELECT 1 FROM payees WHERE id = %s", (body.payee_id,)).fetchone():
        raise ApiError(400, "VALIDATION_ERROR", "Payee not found in your organization.", "payee_id")
    if not conn.execute("SELECT 1 FROM bank_templates WHERE id = %s", (body.bank_template_id,)).fetchone():
        raise ApiError(400, "VALIDATION_ERROR", "Bank template not found in your organization.", "bank_template_id")

    # amount_words is ALWAYS computed server-side — the two values can never disagree
    words = amount_to_words(body.amount_paise)
    row = conn.execute(
        "INSERT INTO cheques (org_id, bank_template_id, payee_id, amount_paise, amount_words, "
        "cheque_date, memo, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
        (claims["org_id"], body.bank_template_id, body.payee_id, body.amount_paise,
         words, body.cheque_date, body.memo, claims["sub"]),
    ).fetchone()
    audit(conn, claims["org_id"], row["id"], claims["sub"], "created")
    return _serialize(row)


@app.post("/cheques/{cheque_id}/submit")
def submit_cheque(cheque_id: str, dep=Depends(org_conn_writable)):
    conn, claims = dep
    row = _get_cheque(conn, cheque_id)
    if row["status"] != "draft":
        raise ApiError(409, "CONFLICT", f"Cannot submit a cheque in status '{row['status']}'.")
    row = conn.execute(
        "UPDATE cheques SET status = 'pending_approval' WHERE id = %s RETURNING *", (cheque_id,)
    ).fetchone()
    audit(conn, claims["org_id"], cheque_id, claims["sub"], "submitted")
    return _serialize(row)


@app.post("/cheques/{cheque_id}/approve")
def approve_cheque(cheque_id: str, dep=Depends(org_conn_writable)):
    conn, claims = dep
    if claims["role"] not in ("checker", "admin"):
        raise ApiError(403, "FORBIDDEN", "Only a checker or admin can approve cheques.")
    row = _get_cheque(conn, cheque_id)
    if row["status"] != "pending_approval":
        raise ApiError(409, "CONFLICT", f"Cannot approve a cheque in status '{row['status']}'.")
    # Maker-checker separation: the creator can never approve their own cheque
    if str(row["created_by"]) == claims["sub"]:
        raise ApiError(403, "FORBIDDEN", "The creator of a cheque cannot approve it.")
    row = conn.execute(
        "UPDATE cheques SET status = 'approved', approved_by = %s WHERE id = %s RETURNING *",
        (claims["sub"], cheque_id),
    ).fetchone()
    audit(conn, claims["org_id"], cheque_id, claims["sub"], "approved")
    return _serialize(row)


@app.post("/cheques/{cheque_id}/reject")
def reject_cheque(cheque_id: str, body: RejectIn, dep=Depends(org_conn_writable)):
    conn, claims = dep
    if claims["role"] not in ("checker", "admin"):
        raise ApiError(403, "FORBIDDEN", "Only a checker or admin can reject cheques.")
    row = _get_cheque(conn, cheque_id)
    if row["status"] != "pending_approval":
        raise ApiError(409, "CONFLICT", f"Cannot reject a cheque in status '{row['status']}'.")
    row = conn.execute(
        "UPDATE cheques SET status = 'rejected', rejected_reason = %s WHERE id = %s RETURNING *",
        (body.reason, cheque_id),
    ).fetchone()
    audit(conn, claims["org_id"], cheque_id, claims["sub"], "rejected", {"reason": body.reason})
    return _serialize(row)


CROSSING_VALUES = (None, "none", "ac_payee", "not_negotiable", "custom")


def _render_output(conn, row, fmt: str = "pdf", *, crossing: str | None = None,
                    crossing_text: str | None = None, watermark_cancelled: bool = False) -> str:
    tpl = conn.execute("SELECT * FROM bank_templates WHERE id = %s", (row["bank_template_id"],)).fetchone()
    payee = conn.execute("SELECT name FROM payees WHERE id = %s", (row["payee_id"],)).fetchone()
    d = row["cheque_date"]
    rupees, paise = divmod(row["amount_paise"], 100)
    figures = f"{rupees:,}.{paise:02d}"
    data = {
        "payee_name": payee["name"],
        "amount_words": row["amount_words"],
        "amount_figures": figures,
        "date_day": f"{d.day:02d}", "date_month": f"{d.month:02d}", "date_year": str(d.year),
    }
    if fmt == "escp":
        raw = generate_cheque_escp(tpl, data, crossing=crossing, crossing_text=crossing_text,
                                    watermark_cancelled=watermark_cancelled)
    else:
        raw = generate_cheque_pdf(tpl, data, crossing=crossing, crossing_text=crossing_text,
                                   watermark_cancelled=watermark_cancelled)
    return base64.b64encode(raw).decode()


@app.post("/cheques/{cheque_id}/print")
def print_cheque(cheque_id: str, format: str = "pdf", crossing: str | None = None,
                  crossing_text: str | None = None, watermark_cancelled: bool = False,
                  dep=Depends(org_conn_writable)):
    conn, claims = dep
    if format not in ("pdf", "escp"):
        raise ApiError(400, "VALIDATION_ERROR", "format must be 'pdf' or 'escp'.", "format")
    if crossing not in CROSSING_VALUES:
        raise ApiError(400, "VALIDATION_ERROR",
                       "crossing must be one of: none, ac_payee, not_negotiable, custom.", "crossing")
    row = _get_cheque(conn, cheque_id)
    mc = conn.execute(
        "SELECT maker_checker_enabled FROM organizations WHERE id = %s", (claims["org_id"],)
    ).fetchone()["maker_checker_enabled"]
    allowed = ("approved",) if mc else ("draft", "approved")
    if row["status"] not in allowed:
        raise ApiError(409, "CONFLICT",
                       "Cheque must be approved before printing." if mc
                       else f"Cannot print a cheque in status '{row['status']}'.")
    out_b64 = _render_output(conn, row, format, crossing=crossing, crossing_text=crossing_text,
                              watermark_cancelled=watermark_cancelled)
    row = conn.execute(
        "UPDATE cheques SET status = 'printed', printed_at = now() WHERE id = %s RETURNING *",
        (cheque_id,),
    ).fetchone()
    audit(conn, claims["org_id"], cheque_id, claims["sub"], "printed", {"format": format})
    key = "pdf_base64" if format == "pdf" else "escp_base64"
    return {"cheque": _serialize(row), key: out_b64}


@app.post("/cheques/{cheque_id}/reprint")
def reprint_cheque(cheque_id: str, format: str = "pdf", crossing: str | None = None,
                    crossing_text: str | None = None, watermark_cancelled: bool = False,
                    dep=Depends(org_conn_writable)):
    conn, claims = dep
    if format not in ("pdf", "escp"):
        raise ApiError(400, "VALIDATION_ERROR", "format must be 'pdf' or 'escp'.", "format")
    if crossing not in CROSSING_VALUES:
        raise ApiError(400, "VALIDATION_ERROR",
                       "crossing must be one of: none, ac_payee, not_negotiable, custom.", "crossing")
    row = _get_cheque(conn, cheque_id)
    if row["status"] != "printed":
        raise ApiError(409, "CONFLICT", "Only a printed cheque can be reprinted.")
    out_b64 = _render_output(conn, row, format, crossing=crossing, crossing_text=crossing_text,
                              watermark_cancelled=watermark_cancelled)  # regenerate — no new row, no status change
    audit(conn, claims["org_id"], cheque_id, claims["sub"], "reprinted", {"format": format})
    key = "pdf_base64" if format == "pdf" else "escp_base64"
    return {"cheque": _serialize(row), key: out_b64}


# ---------- bulk cheque entry (CSV) ----------

@app.post("/cheques/bulk", status_code=201)
def bulk_create_cheques(bank_template_id: str = Form(...), file: UploadFile = File(...),
                         dep=Depends(org_conn_writable)):
    conn, claims = dep
    if not conn.execute("SELECT 1 FROM bank_templates WHERE id = %s", (bank_template_id,)).fetchone():
        raise ApiError(400, "VALIDATION_ERROR", "Bank template not found in your organization.", "bank_template_id")

    raw = file.file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ApiError(400, "VALIDATION_ERROR", "File must be a UTF-8 encoded CSV.", "file")
    reader = csv.DictReader(io.StringIO(text))
    headers = {(h or "").strip() for h in (reader.fieldnames or [])}
    if not {"payee_name", "amount", "cheque_date"}.issubset(headers):
        raise ApiError(400, "VALIDATION_ERROR",
                       "CSV must have columns: payee_name, amount, cheque_date (memo optional).", "file")

    today = dt.date.today()
    results = []
    for i, raw_row in enumerate(reader, start=1):
        row = {(k or "").strip(): (v or "").strip() for k, v in raw_row.items()}
        payee_name = row.get("payee_name", "")
        try:
            with conn.transaction():
                if not payee_name:
                    raise ValueError("payee_name is required.")
                try:
                    amount_paise = round(float(row.get("amount", "")) * 100)
                except ValueError:
                    raise ValueError("amount must be a number.")
                if amount_paise <= 0:
                    raise ValueError("amount must be greater than zero.")
                try:
                    cheque_date = dt.date.fromisoformat(row.get("cheque_date", ""))
                except ValueError:
                    raise ValueError("cheque_date must be in YYYY-MM-DD format.")
                if abs((cheque_date - today).days) > DATE_WINDOW_DAYS:
                    raise ValueError(f"cheque_date must be within {DATE_WINDOW_DAYS} days of today.")
                memo = row.get("memo") or None

                payee = conn.execute(
                    "SELECT id FROM payees WHERE org_id = %s AND name = %s",
                    (claims["org_id"], payee_name),
                ).fetchone()
                if not payee:
                    payee = conn.execute(
                        "INSERT INTO payees (org_id, name) VALUES (%s, %s) RETURNING id",
                        (claims["org_id"], payee_name),
                    ).fetchone()

                words = amount_to_words(amount_paise)
                cheque = conn.execute(
                    "INSERT INTO cheques (org_id, bank_template_id, payee_id, amount_paise, amount_words, "
                    "cheque_date, memo, created_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (claims["org_id"], bank_template_id, payee["id"], amount_paise, words,
                     cheque_date, memo, claims["sub"]),
                ).fetchone()
                audit(conn, claims["org_id"], cheque["id"], claims["sub"], "created", {"bulk": True})
            results.append({"row": i, "status": "created", "cheque_id": str(cheque["id"]), "payee_name": payee_name})
        except ValueError as e:
            results.append({"row": i, "status": "error", "error": str(e), "payee_name": payee_name})

    created = sum(1 for r in results if r["status"] == "created")
    return {"created": created, "failed": len(results) - created, "rows": results}


@app.get("/cheques")
def search_cheques(payee_id: str | None = None, status: str | None = None,
                   date_from: dt.date | None = None, date_to: dt.date | None = None,
                   dep=Depends(org_conn)):
    conn, _ = dep
    q = "SELECT * FROM cheques WHERE true"
    params: list = []
    if payee_id:
        q += " AND payee_id = %s"; params.append(payee_id)
    if status:
        q += " AND status = %s"; params.append(status)
    if date_from:
        q += " AND cheque_date >= %s"; params.append(date_from)
    if date_to:
        q += " AND cheque_date <= %s"; params.append(date_to)
    q += " ORDER BY created_at DESC"
    return [_serialize(r) for r in conn.execute(q, params).fetchall()]


# ---------- calibration (main spec 3.4: per-printer offsets) ----------

class CalibrationIn(BaseModel):
    printer_offset_x_mm: float
    printer_offset_y_mm: float


@app.patch("/bank-templates/{template_id}/calibration")
def set_calibration(template_id: str, body: CalibrationIn, dep=Depends(org_conn_writable)):
    conn, _ = dep
    row = conn.execute(
        "UPDATE bank_templates SET printer_offset_x_mm = %s, printer_offset_y_mm = %s "
        "WHERE id = %s RETURNING id, bank_name, printer_offset_x_mm, printer_offset_y_mm",
        (body.printer_offset_x_mm, body.printer_offset_y_mm, template_id),
    ).fetchone()
    if not row:
        raise ApiError(404, "NOT_FOUND", "Bank template not found.")
    return {**row, "id": str(row["id"]),
            "printer_offset_x_mm": float(row["printer_offset_x_mm"]),
            "printer_offset_y_mm": float(row["printer_offset_y_mm"])}


@app.get("/bank-templates")
def list_templates(dep=Depends(org_conn)):
    conn, _ = dep
    rows = conn.execute(
        "SELECT id, bank_name, printer_offset_x_mm, printer_offset_y_mm FROM bank_templates ORDER BY bank_name"
    ).fetchall()
    return [{**r, "id": str(r["id"]),
             "printer_offset_x_mm": float(r["printer_offset_x_mm"]),
             "printer_offset_y_mm": float(r["printer_offset_y_mm"])} for r in rows]


# ---------- live amount-to-words for the entry form preview ----------

@app.get("/util/amount-words")
def util_amount_words(amount_paise: int, _claims=Depends(current_user)):
    if amount_paise <= 0:
        raise ApiError(400, "VALIDATION_ERROR", "Amount must be greater than zero.", "amount_paise")
    return {"words": amount_to_words(amount_paise)}


# ---------- billing (Task 5.8) ----------

@app.post("/billing/webhook")
def billing_webhook(payload: dict):
    # Production: verify X-Razorpay-Signature HMAC before processing (see billing.py note)
    with core.connect() as conn:
        try:
            result = billing.process_webhook(conn, payload)
        except ValueError as e:
            raise ApiError(400, "VALIDATION_ERROR", str(e))
    return result


@app.get("/billing/status")
def billing_status(dep=Depends(org_conn)):
    conn, claims = dep
    row = conn.execute(
        "SELECT plan_tier, subscription_status, grace_until FROM organizations WHERE id = %s",
        (claims["org_id"],),
    ).fetchone()
    return {"plan_tier": row["plan_tier"], "subscription_status": row["subscription_status"],
            "grace_until": row["grace_until"].isoformat() if row["grace_until"] else None}
