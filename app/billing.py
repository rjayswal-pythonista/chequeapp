"""Task 5.8 — subscription state machine + idempotent webhook processing.

States on organizations.subscription_status:
  active -> (payment failure) -> grace (grace_until = now + GRACE_DAYS)
  grace  -> (payment success) -> active
  grace  -> (grace_until passes, checked lazily on write) -> lapsed
  active -> (trial_ends_at passes with no payment ever, checked lazily) -> lapsed
  lapsed -> (payment success) -> active

New orgs start on a TRIAL_DAYS-long free trial (trial_ends_at set at
signup, subscription_started_at NULL). The trial silently expires into
'lapsed' the same way a grace period does — nothing further happens until
a real Razorpay payment succeeds, which sets subscription_started_at once
and permanently ends trial-expiry checks for that org.

Per-tier resource caps (TIER_LIMITS) are enforced separately at
create-time (bank templates, users) — see check_tier_limit().

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
TRIAL_DAYS = 14

# Per-tier resource caps enforced at signup/add-user/add-template time.
# None means unlimited. Business is the uncapped top tier.
TIER_LIMITS = {
    "starter": {"bank_templates": 1, "users": 1},
    "growth": {"bank_templates": 5, "users": 5},
    "business": {"bank_templates": None, "users": None},
}

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
        # First real payment ends the trial permanently — subscription_started_at
        # is only ever set once and is never cleared by later grace/lapse cycles.
        conn.execute(
            "UPDATE organizations SET subscription_status = 'active', grace_until = NULL, "
            "subscription_started_at = COALESCE(subscription_started_at, now()) "
            "WHERE id = %s",
            (org_id,),
        )

    row = conn.execute(
        "SELECT subscription_status FROM organizations WHERE id = %s", (org_id,)
    ).fetchone()
    return {"handled": event in FAILURE_EVENTS | SUCCESS_EVENTS, "duplicate": False,
            "status": row["subscription_status"] if row else None}


def check_writable(conn, org_id: str) -> tuple[bool, str, str | None]:
    """Lazily expire grace or an unpaid trial on write attempts.
    Returns (writable, status, reason) where reason is 'grace_expired',
    'trial_expired', or None (already lapsed some other way, or writable)."""
    row = conn.execute(
        "SELECT subscription_status, grace_until, trial_ends_at, subscription_started_at "
        "FROM organizations WHERE id = %s",
        (org_id,),
    ).fetchone()
    status = row["subscription_status"]
    now = dt.datetime.now(dt.timezone.utc)
    reason = None

    if status == "grace" and row["grace_until"] is not None and row["grace_until"] < now:
        conn.execute("UPDATE organizations SET subscription_status = 'lapsed' WHERE id = %s", (org_id,))
        # Commit now: the caller raises SUBSCRIPTION_LAPSED right after this,
        # and an uncommitted transition would be rolled back by that exception.
        conn.commit()
        status, reason = "lapsed", "grace_expired"
    elif status == "active" and row["subscription_started_at"] is None \
            and row["trial_ends_at"] is not None and row["trial_ends_at"] < now:
        conn.execute("UPDATE organizations SET subscription_status = 'lapsed' WHERE id = %s", (org_id,))
        conn.commit()
        status, reason = "lapsed", "trial_expired"

    return status != "lapsed", status, reason


def check_tier_limit(conn, org_id: str, plan_tier: str, resource: str) -> tuple[bool, int | None]:
    """Returns (allowed, limit). resource is 'bank_templates' or 'users'.
    limit is None when the tier has no cap on that resource."""
    limit = TIER_LIMITS.get(plan_tier, TIER_LIMITS["starter"]).get(resource)
    if limit is None:
        return True, None
    table = "bank_templates" if resource == "bank_templates" else "users"
    count = conn.execute(f"SELECT count(*) AS n FROM {table} WHERE org_id = %s", (org_id,)).fetchone()["n"]
    return count < limit, limit
