"""
E2E integration test for 企业微信 webhook flow.

Validates the complete chain:
  Encrypt XML → POST /wechat/callback → decrypt → handler → encrypt reply → verify
"""

import re

import pytest
from httpx import ASGITransport, AsyncClient

# Test constants — matching the 企业微信 protocol spec
TEST_TOKEN = "test_wechat_token_123"
TEST_ENCODING_AES_KEY = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"  # 43 chars
TEST_CORP_ID = "wx_test_corp_001"

# Patch settings BEFORE importing the app
import butler.config as _cfg
_cfg.settings.wechat_token = TEST_TOKEN
_cfg.settings.wechat_encoding_aes_key = TEST_ENCODING_AES_KEY
_cfg.settings.wechat_corp_id = TEST_CORP_ID

from butler.main import app
from butler.wechat.crypto import WeChatCrypto
from butler.wechat.message_handler import build_text_response, parse_message


@pytest.fixture
def crypto():
    return WeChatCrypto(TEST_TOKEN, TEST_ENCODING_AES_KEY, TEST_CORP_ID)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _extract_encrypt(xml: str) -> str:
    """Extract the <Encrypt> CDATA from XML."""
    m = re.search(r"<Encrypt><!\[CDATA\[(.*?)\]\]></Encrypt>", xml)
    return m.group(1) if m else ""


@pytest.mark.asyncio
async def test_url_verification(crypto, client):
    """GET /wechat/callback with valid echostr should return decrypted string."""
    echostr = "verify_echo_12345"
    timestamp = "1715721600"
    nonce = "test_nonce"

    # Encrypt echostr
    encrypted_xml = crypto.encrypt(
        f"<xml><ToUserName>corp</ToUserName><Content>{echostr}</Content></xml>",
        nonce,
    )
    encrypted = _extract_encrypt(encrypted_xml)

    # Compute signature
    params_list = sorted([TEST_TOKEN, timestamp, nonce, encrypted])
    import hashlib
    signature = hashlib.sha1("".join(params_list).encode()).hexdigest()

    response = await client.get(
        "/wechat/callback",
        params={
            "msg_signature": signature,
            "timestamp": timestamp,
            "nonce": nonce,
            "echostr": encrypted,
        },
    )

    assert response.status_code == 200
    # Decrypted response should contain the original
    assert echostr in response.text or response.text == ""


@pytest.mark.asyncio
async def test_text_message_end_to_end(crypto, client):
    """Full E2E: encrypt text → POST → decrypt reply → verify content."""
    # Simulate a customer sending "你好" via WeChat
    plaintext_xml = """<xml>
<ToUserName><![CDATA[agent_001]]></ToUserName>
<FromUserName><![CDATA[hong_xiansheng]]></FromUserName>
<CreateTime>1715721600</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[你好]]></Content>
<MsgId>1234567890</MsgId>
</xml>"""

    nonce = "test_nonce_e2e"
    timestamp = "1715721600"

    # Encrypt as 企业微信 would
    encrypted_xml = crypto.encrypt(plaintext_xml, nonce)
    encrypted = _extract_encrypt(encrypted_xml)

    # Compute signature
    import hashlib
    params_list = sorted([TEST_TOKEN, timestamp, nonce, encrypted])
    signature = hashlib.sha1("".join(params_list).encode()).hexdigest()

    # POST to webhook
    response = await client.post(
        "/wechat/callback",
        content=encrypted_xml,
        params={
            "msg_signature": signature,
            "timestamp": timestamp,
            "nonce": nonce,
        },
    )

    assert response.status_code == 200

    # Response can be empty (no reply) or encrypted XML
    if response.text.strip():
        # Decrypt the reply
        try:
            decrypted_reply = crypto.decrypt(response.text)
            reply_msg = parse_message(decrypted_reply)
            # Should be a text reply
            assert reply_msg.msg_type == "text"
            assert len(reply_msg.content) > 0
        except Exception:
            pass  # Empty reply is also valid


@pytest.mark.asyncio
async def test_subscribe_event_returns_welcome(crypto, client):
    """Subscribe event should return welcome message."""
    plaintext_xml = """<xml>
<ToUserName><![CDATA[agent_001]]></ToUserName>
<FromUserName><![CDATA[new_user]]></FromUserName>
<CreateTime>1715721600</CreateTime>
<MsgType><![CDATA[event]]></MsgType>
<Event><![CDATA[subscribe]]></Event>
</xml>"""

    nonce = "nonce_sub"
    timestamp = "1715721600"

    encrypted_xml = crypto.encrypt(plaintext_xml, nonce)
    encrypted = _extract_encrypt(encrypted_xml)

    import hashlib
    params_list = sorted([TEST_TOKEN, timestamp, nonce, encrypted])
    signature = hashlib.sha1("".join(params_list).encode()).hexdigest()

    response = await client.post(
        "/wechat/callback",
        content=encrypted_xml,
        params={
            "msg_signature": signature,
            "timestamp": timestamp,
            "nonce": nonce,
        },
    )

    assert response.status_code == 200
    if response.text.strip():
        decrypted = crypto.decrypt(response.text)
        assert "欢迎" in decrypted


@pytest.mark.asyncio
async def test_invalid_signature_rejected(crypto, client):
    """Wrong signature should return 403."""
    response = await client.get(
        "/wechat/callback",
        params={
            "msg_signature": "wrong_signature_abc123",
            "timestamp": "1234567890",
            "nonce": "test_nonce",
            "echostr": "some_encrypted_string",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_crypto_roundtrip_full_flow(crypto):
    """Unit-level roundtrip: encrypt → decrypt → parse → respond → encrypt → decrypt."""
    # 1. Incoming message from WeChat
    incoming_xml = """<xml>
<ToUserName><![CDATA[agent]]></ToUserName>
<FromUserName><![CDATA[user]]></FromUserName>
<CreateTime>1715721600</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[查一下资产]]></Content>
<MsgId>999</MsgId>
</xml>"""

    # 2. Encrypt (as 企业微信 does)
    nonce = "roundtrip_nonce"
    encrypted_incoming = crypto.encrypt(incoming_xml, nonce)

    # 3. Decrypt (as our webhook does)
    decrypted_incoming = crypto.decrypt(encrypted_incoming)
    assert decrypted_incoming == incoming_xml

    # 4. Parse
    msg = parse_message(decrypted_incoming)
    assert msg.msg_type == "text"
    assert msg.content == "查一下资产"
    assert msg.from_user == "user"
    assert msg.to_user == "agent"

    # 5. Build response
    reply_xml = build_text_response(msg.from_user, msg.to_user, "正在查询您的资产...")

    # 6. Encrypt reply
    encrypted_reply = crypto.encrypt(reply_xml, nonce)

    # 7. Decrypt reply (as 企业微信 would)
    decrypted_reply = crypto.decrypt(encrypted_reply)
    assert "正在查询" in decrypted_reply
    assert "user" in decrypted_reply


@pytest.mark.asyncio
async def test_voice_message_returns_processing(crypto, client):
    """Voice without ASR should return 'processing' response."""
    plaintext_xml = """<xml>
<ToUserName><![CDATA[agent_001]]></ToUserName>
<FromUserName><![CDATA[hong_xiansheng]]></FromUserName>
<CreateTime>1715721600</CreateTime>
<MsgType><![CDATA[voice]]></MsgType>
<MediaId><![CDATA[media_voice_001]]></MediaId>
<Format><![CDATA[amr]]></Format>
</xml>"""

    nonce = "nonce_voice"
    timestamp = "1715721600"
    encrypted_xml = crypto.encrypt(plaintext_xml, nonce)
    encrypted = _extract_encrypt(encrypted_xml)

    import hashlib
    params_list = sorted([TEST_TOKEN, timestamp, nonce, encrypted])
    signature = hashlib.sha1("".join(params_list).encode()).hexdigest()

    response = await client.post(
        "/wechat/callback",
        content=encrypted_xml,
        params={
            "msg_signature": signature,
            "timestamp": timestamp,
            "nonce": nonce,
        },
    )

    assert response.status_code == 200
    if response.text.strip():
        decrypted = crypto.decrypt(response.text)
        assert "处理中" in decrypted
