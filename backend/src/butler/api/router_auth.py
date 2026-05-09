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

# JWT secret — dev default, set BUTLER_JWT_SECRET in production
JWT_SECRET = os.environ.get("BUTLER_JWT_SECRET", "butler-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24

# Dev PINs (hash → tenant/customer mapping)
DEV_ACCOUNTS: dict[str, dict] = {
    # PIN: 888888
    hashlib.sha256("888888".encode()).hexdigest(): {
        "tenant_id": "demo-001",
        "customer_id": "cust-001",
        "display_name": "洪先生",
        "plan_tier": "family",
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
    """Login with PIN (MVP). Returns JWT token."""
    if not pin or len(pin) < 4:
        raise HTTPException(status_code=400, detail="PIN required")

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
