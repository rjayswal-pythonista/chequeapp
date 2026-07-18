"""Task 5.8 — subscription state machine + idempotent webhook processing.

States on organizations.subscription_status:
  active -> (payment failure) -> grace (grace_until = now + GRACE_DAYS)
  grace  -> (payment success) -> active
  grace  -> (grace_until passes, checked lazily on write) -> lapsed
  lapsed -> (payment success) -> active

Read endpoints keep working in every state; write endpoints return
SUBSCRIPTION_LAPSED (402) once lapsed — per the main spec's read-only
fallback, a lapsed customer can still view, search, and export their
register, they just cannot create or print new cheques.

The webhook handler is idempotent: event_id is recorded with a UNIQUE
constraint, and a duplicate delivery short-circuits before any state
change. In production, verify Razorpay's HMAC signature header before
processing (X-Razorpay-Signature); stubbed here as the scaffold has no
live gateway credentials.
"""
import datetime as dt
import json

GRACE_DAYS = 5

FAILURE_EVENTS = {"payment.failed", "subscription.halted"}
SUCCESS_EVENTS = {"payment.captured", "subscription.charged", "subscription.activated"}


def process_webhook(conn, payload: dict) -> dict:
    """Returns {"handled": bool, "duplicate": bool, "status": current_status}."""
    event_id = payload.get("event_id")
    event = payload.get("event")
    org_id = payload.get("org_id")
    if not event_id or not event or not org_id:
        raise ValueError("event_id, event, and org_id are required")

    # Idempotency gate: first delivery wins, duplicates are no-ops
    dup = conn.execute(
        "INSERT INTO webhook_events (event_id, payload) VALUES (%s, %s) "
        "ON CONFLICT (event_id) DO NOTHING RETURNING id",
        (event_id, json.dumps(payload)),
    ).fetchone()
    if dup is None:
        row = conn.execute(
            "SELECT subscription_status FROM organizations WHERE id = %s", (org_id,)
        ).fetchone()
        return {"handled": False, "duplicate": True,
                "status": row["subscription_status"] if row else None}

    if event in FAILURE_EVENTS:
        # Only start (not extend) a grace window on repeated failures
        conn.execute(
            "UPDATE organizations SET subscription_status = 'grace', "
            "grace_until = COALESCE(grace_until, now() + interval '%s days') "
            "WHERE id = %s AND subscription_status != 'lapsed'",
            (GRACE_DAYS, org_id),
        )
        conn.execute(
            "UPDATE organizations SET grace_until = COALESCE(grace_until, now() + interval '%s days') "
            "WHERE id = %s AND subscription_status = 'lapsed'",
            (GRACE_DAYS, org_id),
        )
    elif event in SUCCESS_EVENTS:
        conn.execute(
            "UPDATE organizations SET subscription_status = 'active', grace_until = NULL "
            "WHERE id = %s",
            (org_id,),
        )

    row = conn.execute(
        "SELECT subscription_status FROM organizations WHERE id = %s", (org_id,)
    ).fetchone()
    return {"handled": event in FAILURE_EVENTS | SUCCESS_EVENTS, "duplicate": False,
            "status": row["subscription_status"] if row else None}


def check_writable(conn, org_id: str) -> tuple[bool, str]:
    """Lazily expire grace on write attempts. Returns (writable, status)."""
    row = conn.execute(
        "SELECT subscription_status, grace_until FROM organizations WHERE id = %s",
        (org_id,),
    ).fetchone()
    status = row["subscription_status"]
    if status == "grace" and row["grace_until"] is not None \
            and row["grace_until"] < dt.datetime.now(dt.timezone.utc):
        conn.execute(
            "UPDATE organizations SET subscription_status = 'lapsed' WHERE id = %s",
            (org_id,),
        )
        # Commit now: the caller raises SUBSCRIPTION_LAPSED right after this,
        # and an uncommitted transition would be rolled back by that exception.
        conn.commit()
        status = "lapsed"
    return status != "lapsed", status
