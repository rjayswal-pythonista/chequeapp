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
(live amount-to-words), bulk CSV upload, checker approvals queue, register with
per-printer-type print modal (inkjet/laser PDF, dot matrix ESC/P .prn, digital
PDF, optional crossing stamp + cancelled watermark), print calibration
(per-template mm offsets), billing status page.

    cd frontend && npm install && npm run dev   # proxies /api -> localhost:8000

## Printer paths
- Inkjet/laser: positioned PDF via ReportLab (open + OS print dialog)
- Dot matrix: raw ESC/P stream at 10 CPI / 6 LPI (download .prn, send raw:
  `lp -o raw file.prn` or `copy /b file.prn LPT1`); physical calibration
  against the client's printer model still required
- Digital: same PDF, downloaded for records/email

## Print styling & crossing (Gap Analysis — High priority)
- Per-field font family (Helvetica/Times-Roman/Courier), bold, underline via
  optional keys on each bank_templates.fields entry
- Crossing stamps (A/C Payee Only, Not Negotiable, custom text) and a
  Cancelled watermark, selectable per print/reprint via query params
  (`crossing`, `crossing_text`, `watermark_cancelled`); rendered as diagonal
  lines/rotated text in the PDF path and a plain banner line in the ESC/P path

## Bulk cheque entry (Gap Analysis — High priority)
`POST /cheques/bulk` (multipart form: `bank_template_id` + CSV `file`).
Columns: `payee_name`, `amount` (rupees), `cheque_date` (YYYY-MM-DD), optional
`memo`. Each row is validated and inserted independently (per-row DB savepoint)
— one bad row never blocks the rest of the batch. Missing payees are created
automatically. Frontend page: Bulk upload.

## Billing (Task 5.8)
Webhook-driven subscription state machine (active -> grace -> lapsed ->
active) with idempotent event handling and lazy grace expiry. Lapsed orgs
are read-only: register/search keep working, create/print return 402
SUBSCRIPTION_LAPSED. Razorpay HMAC signature verification is stubbed
(no live credentials in this scaffold) — see app/billing.py.

## Free trial + per-tier resource caps
New orgs get a 14-day free trial (`organizations.trial_ends_at`, set at
signup). If it passes with no successful payment ever recorded
(`subscription_started_at` stays NULL), the org lazily lapses into the
same read-only fallback as a failed-payment grace expiry — checked on
write, same pattern as `check_writable()`'s existing grace logic. One real
successful webhook payment sets `subscription_started_at` once, permanently
ending trial-expiry checks for that org.

Per-tier caps (`billing.TIER_LIMITS`) are enforced at creation time:
Starter = 1 bank template / 1 user, Growth = 5 / 5, Business = unlimited.
Exceeding a cap returns `402 PLAN_LIMIT_REACHED`. `PATCH /org/settings`
lets an admin change `plan_tier` directly — a manual stand-in for a real
Razorpay checkout/upgrade flow, and deliberately allowed even while an
org is lapsed (otherwise there'd be no way out of read-only mode without
live payment credentials).

## Amount-tiered dual approval (Gap Analysis — Medium priority)
Admin-configurable `dual_approval_threshold_paise` (Settings page /
`PATCH /org/settings`, admin-only). Cheques at or above the threshold move
`pending_approval` -> `pending_second_approval` -> `approved`, requiring two
distinct checkers (the same checker can't give both approvals; the creator
can never approve at either stage). Below the threshold, a single approval
is final, same as before.

## Self-serve bank template admin UI (Gap Analysis)
`GET/PATCH /bank-templates/{id}` (admin-only for create/edit) plus a
frontend Bank templates page — build/edit templates (dimensions, per-field
x/y/font/bold/underline) without hand-writing JSON via the API.

Field placement is visual, not just numeric: click a field to arm it, then
click on a to-scale canvas (or drag an existing marker) to set its x/y —
the exact mm values update live and a confirmation shows what was set.
Arrow keys nudge the selected field by 0.5mm (Shift = 2mm). Optionally
upload a photo/scan of the real blank cheque leaf as a canvas background
(client-side only, stored in browser localStorage) so you click directly on
the payee/amount/date boxes instead of guessing coordinates. The numeric
inputs are still available below the canvas for typing exact values.

`GET /bank-templates/{id}/alignment-grid` returns a plain 10mm-ruled PDF
(no offset applied) to print on blank paper and hold against the real leaf —
read off the physical printer drift and enter it on the Calibration page.
This is a separate concern from field placement: it calibrates the
printer/tray, not where each field sits on the template.

## Exportable register (Gap Analysis — Medium priority)
`GET /cheques/export?format=csv|pdf` (same filters as `/cheques`). Register
page has Export CSV / Export PDF buttons.

## Cheque analytics dashboard (Gap Analysis — Medium priority)
`GET /analytics/summary`: counts by status, spend by month, top payees by
spend, average approval turnaround time. Frontend Analytics page.

## CI
`.github/workflows/ci.yml` runs the full pytest suite against a Postgres
service container, plus a frontend production build, on every push/PR to
`main`.

## Not yet built
Object storage for PDFs (currently base64 in responses), live Razorpay
credentials + signature verification, email/SMS/WhatsApp notifications,
stop-payment register, accounting-software export, multi-branch/account
management, white-label branding.
