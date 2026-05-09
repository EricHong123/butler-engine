"""
企业微信 webhook endpoint. FastAPI router for receiving WeChat callbacks.

Flow:
  1. 企业微信 POST → /wechat/callback (encrypted XML)
  2. Verify signature → decrypt message
  3. Parse message → route to AgentRunner
  4. AI response → (optionally human review) → encrypt → return

GET /wechat/callback  → URL verification (echostr)
POST /wechat/callback → message callback
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from butler.config import settings
from butler.engine.tool_registry import ToolRegistry
from butler.wechat.crypto import WeChatCrypto
from butler.wechat.message_handler import (
    HandlerResult,
    WeChatMessage,
    build_empty_response,
    handle_message,
    parse_message,
)

router = APIRouter(prefix="/wechat", tags=["wechat"])

# Tenant/tool configuration — in production, looked up per-user
# For MVP, we use a single demo tenant
DEMO_TENANT_ID = "demo-001"
DEMO_TOOLS = ToolRegistry()  # Tools registered in later phases


def _get_crypto() -> WeChatCrypto:
    return WeChatCrypto(
        token=settings.wechat_token,
        encoding_aes_key=settings.wechat_encoding_aes_key,
        corp_id=settings.wechat_corp_id,
    )


@router.get("/callback")
async def verify_url(
    msg_signature: str = Query(..., alias="msg_signature"),
    timestamp: str = Query(..., alias="timestamp"),
    nonce: str = Query(..., alias="nonce"),
    echostr: str = Query(..., alias="echostr"),
):
    """
    URL verification callback. 企业微信 calls this when configuring the webhook.
    Must return the decrypted echostr within 5 seconds.
    """
    crypto = _get_crypto()
    if not crypto.verify_signature(msg_signature, timestamp, nonce, echostr):
        return Response(content="Invalid signature", status_code=403)

    try:
        decrypted = crypto.decrypt_echostr(echostr)
        return Response(content=decrypted, media_type="text/plain")
    except Exception as exc:
        return Response(content=f"Decrypt failed: {exc}", status_code=500)


@router.post("/callback")
async def message_callback(
    request: Request,
    msg_signature: str = Query(..., alias="msg_signature"),
    timestamp: str = Query(..., alias="timestamp"),
    nonce: str = Query(..., alias="nonce"),
):
    """
    Message callback. 企业微信 forwards user messages here.

    The request body is encrypted XML. We decrypt, process,
    encrypt the reply, and return it.
    """
    crypto = _get_crypto()

    # Read encrypted XML body
    encrypted_body = await request.body()
    encrypted_xml = encrypted_body.decode("utf-8")

    # Verify signature
    # Extract Encrypt field for signature verification
    import re
    encrypt_match = re.search(r"<Encrypt><!\[CDATA\[(.*?)\]\]></Encrypt>", encrypted_xml)
    encrypt_text = encrypt_match.group(1) if encrypt_match else ""

    if not crypto.verify_signature(msg_signature, timestamp, nonce, encrypt_text):
        return Response(content="Invalid signature", status_code=403)

    try:
        # Decrypt
        decrypted_xml = crypto.decrypt(encrypted_xml)

        # Parse
        msg = parse_message(decrypted_xml)

        # Handle
        result = await handle_message(
            msg,
            tenant_id=DEMO_TENANT_ID,
            tools=DEMO_TOOLS,
        )

        # Build reply
        if not result.reply_xml:
            return Response(content="", media_type="text/plain")

        # Encrypt reply
        encrypted_reply = crypto.encrypt(result.reply_xml, nonce)

        return Response(content=encrypted_reply, media_type="application/xml")

    except Exception as exc:
        # Log error, return empty to avoid retry storms
        return Response(content="", media_type="text/plain")
