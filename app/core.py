"""DB connection + auth helpers. App connects as app_user so RLS applies."""
import os
import datetime as dt

import bcrypt
import jwt
import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get("DATABASE_URL", "postgresql://app_user:app_pass@localhost/chequeapp")
ADMIN_DSN = os.environ.get("ADMIN_DATABASE_URL", "postgresql://postgres@localhost/chequeapp")
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-prod")
JWT_ALGO = "HS256"


def connect():
    return psycopg.connect(DSN, row_factory=dict_row)


def set_org_context(conn, org_id: str):
    """Bind this connection's RLS context to one tenant."""
    conn.execute("SELECT set_config('app.current_org_id', %s, false)", (str(org_id),))


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def check_password(pw: str, pw_hash: str) -> bool:
    return bcrypt.checkpw(pw.encode(), pw_hash.encode())


def make_token(user_id: str, org_id: str, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "org_id": str(org_id),
        "role": role,
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=12),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
