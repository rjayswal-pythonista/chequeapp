# Cheque Printing SaaS — Backend Core

Working implementation of Technical Addendum task cards 5.1–5.6:
tenant-isolated auth (JWT + Postgres RLS), Indian amount-to-words,
validated cheque entry, maker-checker workflow, coordinate-positioned
PDF generation, register search + duplicate-free reprint.

## Stack
Python 3.12, FastAPI, PostgreSQL 16 (row-level security), psycopg3,
PyJWT + bcrypt, ReportLab.

## Setup
    createuser app_user --pwprompt        # password: app_pass (or set DATABASE_URL)
    createdb chequeapp
    psql -d chequeapp -f db/schema.sql    # run as table owner (postgres)
    pip install fastapi "psycopg[binary]" pyjwt bcrypt reportlab uvicorn
    uvicorn app.main:app --reload

## Tests
    pip install pytest httpx
    python -m pytest tests/ -v            # 16 tests, all task-card Done-when criteria

## Layout
    app/amount_words.py   Task 5.2 — pure function, unit-tested against corrected cases
    app/core.py           DB + JWT/bcrypt helpers; RLS context binding
    app/pdfgen.py         Task 5.5 — mm-coordinate PDF rendering, auto font-shrink
    app/main.py           Tasks 5.1/5.3/5.4/5.6 — API with standard error shape
    db/schema.sql         Addendum 3.1 schema + RLS policies
    tests/test_app.py     One test (or more) per task-card Done-when criterion
    NOTES.md              Decisions + corrections found while building (read first)

## Frontend (frontend/)
Vite + React app: login/signup, cheque entry with live cheque-leaf preview
(live amount-to-words), checker approvals queue, register with per-printer-type
print modal (inkjet/laser PDF, dot matrix ESC/P .prn, digital PDF), print
calibration (per-template mm offsets), billing status page.

    cd frontend && npm install && npm run dev   # proxies /api -> localhost:8000

## Printer paths
- Inkjet/laser: positioned PDF via ReportLab (open + OS print dialog)
- Dot matrix: raw ESC/P stream at 10 CPI / 6 LPI (download .prn, send raw:
  `lp -o raw file.prn` or `copy /b file.prn LPT1`); physical calibration
  against the client's printer model still required
- Digital: same PDF, downloaded for records/email

## Billing (Task 5.8)
Webhook-driven subscription state machine (active -> grace -> lapsed ->
active) with idempotent event handling and lazy grace expiry. Lapsed orgs
are read-only: register/search keep working, create/print return 402
SUBSCRIPTION_LAPSED. Razorpay HMAC signature verification is stubbed
(no live credentials in this scaffold) — see app/billing.py.

## Not yet built
Object storage for PDFs (currently base64 in responses), live Razorpay
credentials + signature verification, deployment/CI, admin panel.
