"""
Authentication API. JWT-based login with dev PIN for MVP.

POST /api/auth/login  — login with PIN (MVP) or passkey challenge
GET  /api/auth/me     — get current user info
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address, IPv6Address, ip_address

import jwt
from fastapi import APIRouter, Header, HTTPException, Request

from butler.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# JWT secret — MUST be set via BUTLER_JWT_SECRET env var.
_DEFAULT_JWT_SECRET = "butler-dev-secret-change-in-production"
JWT_SECRET = os.environ.get("BUTLER_JWT_SECRET", _DEFAULT_JWT_SECRET)
JWT_ALGORITHM = "HS256"
# Short-lived tokens for security
ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_HOURS = 24

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


def _get_client_ip(request: Request | None) -> str:
    """Extract real client IP, checking X-Forwarded-For first."""
    if request is None:
        return "0.0.0.0"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "127.0.0.1"


def _make_fingerprint(ip: str, user_agent: str) -> str:
    """Create a client fingerprint from IP prefix and UA hash."""
    # Use /24 for IPv4, /64 for IPv6
    try:
        addr = ip_address(ip)
        if isinstance(addr, IPv4Address):
            ip_prefix = ".".join(str(addr).split(".")[:3]) + ".0/24"
        else:
            ip_prefix = ":".join(str(addr).split(":")[:4]) + "::/64"
    except ValueError:
        ip_prefix = "unknown"

    ua_hash = hashlib.sha256(user_agent.encode()).hexdigest()[:16] if user_agent else "none"
    return f"{ip_prefix}|{ua_hash}"


def create_token(payload: dict, request: Request | None = None, user_agent: str = "") -> str:
    """Create a JWT access token with client fingerprint binding."""
    data = payload.copy()
    data["exp"] = datetime.now(tz=timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    data["iat"] = datetime.now(tz=timezone.utc)
    data["type"] = "access"
    if request:
        ip = _get_client_ip(request)
        data["fingerprint"] = _make_fingerprint(ip, user_agent)
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(payload: dict, request: Request | None = None, user_agent: str = "") -> str:
    """Create a long-lived refresh token."""
    data = payload.copy()
    data["exp"] = datetime.now(tz=timezone.utc) + timedelta(hours=REFRESH_TOKEN_HOURS)
    data["iat"] = datetime.now(tz=timezone.utc)
    data["type"] = "refresh"
    if request:
        ip = _get_client_ip(request)
        data["fingerprint"] = _make_fingerprint(ip, user_agent)
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str, expected_fingerprint: str = "") -> dict:
    """Verify and decode a JWT token. Optionally validate client fingerprint."""
    payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

    # Validate fingerprint if provided (skip if empty = dev mode)
    if expected_fingerprint:
        token_fp = payload.get("fingerprint", "")
        if token_fp and not _fingerprint_matches(token_fp, expected_fingerprint):
            raise jwt.InvalidTokenError("Client fingerprint mismatch")

    return payload


def _fingerprint_matches(token_fp: str, expected_fp: str) -> bool:
    """Compare fingerprints, allowing IP prefix changes within same /24."""
    t_ip, t_ua = token_fp.split("|", 1) if "|" in token_fp else (token_fp, "")
    e_ip, e_ua = expected_fp.split("|", 1) if "|" in expected_fp else (expected_fp, "")
    # UA hash must match exactly
    if t_ua != e_ua:
        return False
    # IP prefix match (allow subnet changes within /24 for IPv4)
    t_prefix = t_ip.rsplit(".", 1)[0] if "." in t_ip else t_ip.split(":")[0]
    e_prefix = e_ip.rsplit(".", 1)[0] if "." in e_ip else e_ip.split(":")[0]
    return t_prefix == e_prefix


@router.post("/login")
async def login(pin: str = "", request: Request = None):  # type: ignore[assignment]
    """Login with PIN (dev only) or passkey. Returns JWT access + refresh tokens."""
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

    ua = request.headers.get("User-Agent", "") if request else ""
    access_token = create_token(account, request, ua)
    refresh_token = create_refresh_token(account, request, ua)
    return {
        "token": access_token,
        "refresh_token": refresh_token,
        "tenant_id": account["tenant_id"],
        "display_name": account["display_name"],
        "plan_tier": account["plan_tier"],
        "role": account.get("role", "principal"),
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
    }


@router.post("/refresh")
async def refresh_token(request: Request):
    """Exchange a refresh token for a new access token."""
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")
    try:
        payload = jwt.decode(
            authorization[7:], JWT_SECRET, algorithms=[JWT_ALGORITHM]
        )
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Not a refresh token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Issue new access token with current fingerprint
    ua = request.headers.get("User-Agent", "")
    access_data = {k: v for k, v in payload.items()
                   if k not in ("exp", "iat", "type", "fingerprint")}
    new_token = create_token(access_data, request, ua)
    return {
        "token": new_token,
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
    }


@router.get("/me")
async def get_current_user(request: Request):
    """Get current user info from JWT token with fingerprint verification."""
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")

    token = authorization[7:]
    try:
        # Verify with fingerprint
        ip = _get_client_ip(request)
        ua = request.headers.get("User-Agent", "")
        expected_fp = _make_fingerprint(ip, ua) if not DEV_MODE else ""
        payload = verify_token(token, expected_fp)
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=str(e))
