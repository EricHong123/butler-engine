"""
Authentication API. JWT-based login with dev PIN for MVP.

POST /api/auth/login  — login with PIN (MVP) or passkey challenge
GET  /api/auth/me     — get current user info
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Header, HTTPException, Request

from butler.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# JWT secret — MUST be set via BUTLER_JWT_SECRET env var.
# The default is only valid in dev mode (BUTLER_DEBUG=true).
_DEFAULT_JWT_SECRET = "butler-dev-secret-change-in-production"
JWT_SECRET = os.environ.get("BUTLER_JWT_SECRET", _DEFAULT_JWT_SECRET)
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# Production safety check
_IS_PRODUCTION = (
    os.environ.get("BUTLER_ENV", "development") == "production"
    or os.environ.get("ENV", "development") == "production"
)

if _IS_PRODUCTION and JWT_SECRET == _DEFAULT_JWT_SECRET:
    raise RuntimeError(
        "FATAL: BUTLER_JWT_SECRET must be set in production. "
        "The default value is only for local development."
    )

# Dev PINs — ONLY available when BUTLER_DEBUG=true or BUTLER_ENV=development
# In production, only WebAuthn/passkey authentication is accepted.
DEV_MODE = (
    os.environ.get("BUTLER_DEBUG", "").lower() == "true"
    or os.environ.get("BUTLER_ENV", "development") != "production"
)

DEV_ACCOUNTS: dict[str, dict] = {}
if DEV_MODE:
    DEV_ACCOUNTS = {
        # PIN: 888888
        hashlib.sha256("888888".encode()).hexdigest(): {
            "tenant_id": "demo-001",
            "customer_id": "cust-001",
            "display_name": "洪先生",
            "plan_tier": "family",
            "role": "principal",
        },
        # PIN: 666666 → spouse
        hashlib.sha256("666666".encode()).hexdigest(): {
            "tenant_id": "demo-001",
            "customer_id": "cust-002",
            "display_name": "洪太太",
            "plan_tier": "family",
            "role": "spouse",
        },
        # PIN: 111111 → child
        hashlib.sha256("111111".encode()).hexdigest(): {
            "tenant_id": "demo-001",
            "customer_id": "cust-003",
            "display_name": "洪明",
            "plan_tier": "family",
            "role": "child",
        },
        # PIN: 123456 → reviewer/admin
        hashlib.sha256("123456".encode()).hexdigest(): {
            "tenant_id": "demo-001",
            "customer_id": "admin-001",
            "display_name": "Reviewer",
            "plan_tier": "family",
            "role": "admin",
        },
    }


def create_token(payload: dict) -> str:
    """Create a JWT token with expiry."""
    data = payload.copy()
    data["exp"] = datetime.now(tz=timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS)
    data["iat"] = datetime.now(tz=timezone.utc)
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """Verify and decode a JWT token. Raises on invalid/expired."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


@router.post("/login")
async def login(pin: str = ""):
    """Login with PIN (dev only) or passkey. Returns JWT token."""
    if not pin or len(pin) < 4:
        raise HTTPException(status_code=400, detail="PIN required")

    if not DEV_MODE:
        raise HTTPException(
            status_code=400,
            detail="PIN login is disabled in production. Use WebAuthn/passkey.",
        )

    pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    account = DEV_ACCOUNTS.get(pin_hash)

    if not account:
        raise HTTPException(status_code=401, detail="Invalid PIN")

    token = create_token(account)
    return {
        "token": token,
        "tenant_id": account["tenant_id"],
        "display_name": account["display_name"],
        "plan_tier": account["plan_tier"],
        "role": account.get("role", "principal"),
    }


@router.get("/me")
async def get_current_user(request: Request):
    """Get current user info from JWT token."""
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")
    try:
        payload = verify_token(authorization[7:])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
