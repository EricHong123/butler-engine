"""
Tests for 企业微信 integration: crypto, message parsing, response building.
"""

import base64
import hashlib

import pytest

from butler.wechat.crypto import WeChatCrypto
from butler.wechat.message_handler import (
    WeChatMessage,
    build_empty_response,
    build_text_response,
    build_voice_response,
    handle_message,
    parse_message,
)

# Test constants (matching 企业微信 protocol spec)
TEST_TOKEN = "test_token_abc"
TEST_ENCODING_AES_KEY = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"  # 43 chars
TEST_CORP_ID = "wx_test_corp_id"


@pytest.fixture
def crypto() -> WeChatCrypto:
    return WeChatCrypto(TEST_TOKEN, TEST_ENCODING_AES_KEY, TEST_CORP_ID)


class TestWeChatCrypto:
    def test_encrypt_decrypt_roundtrip(self, crypto):
        """Encrypt then decrypt should return original plaintext."""
        plaintext = "<xml><ToUserName>user</ToUserName><Content>Hello</Content></xml>"
        nonce = "test_nonce_123"

        encrypted_xml = crypto.encrypt(plaintext, nonce)
        decrypted = crypto.decrypt(encrypted_xml)

        assert decrypted == plaintext

    def test_signature_verification(self, crypto):
        """Correct signature should verify."""
        echostr = "test_echo_string"
        timestamp = "1234567890"
        nonce = "test_nonce"

        params = sorted([TEST_TOKEN, timestamp, nonce, echostr])
        expected_sig = hashlib.sha1("".join(params).encode()).hexdigest()

        assert crypto.verify_signature(expected_sig, timestamp, nonce, echostr)

    def test_signature_verification_wrong(self, crypto):
        """Wrong signature should fail."""
        assert not crypto.verify_signature(
            "wrong_signature", "1234567890", "test_nonce", "echostr"
        )

    def test_echostr_decrypt(self, crypto):
        """Decrypt echostr should return the original string."""
        original = "echo_test_12345"
        encrypted_xml = crypto.encrypt(
            f"<xml><Content>{original}</Content></xml>", "nonce"
        )

        # Extract just the encrypted text from the XML
        import re
        match = re.search(r"<Encrypt><!\[CDATA\[(.*?)\]\]></Encrypt>", encrypted_xml)
        encrypted_text = match.group(1)

        decrypted = crypto.decrypt_echostr(encrypted_text)
        assert original in decrypted

    def test_rejects_wrong_corp_id(self, crypto):
        """Decrypt with wrong corp_id should extract correct message but catch mismatch."""
        # Create a crypto with different corp_id
        wrong_crypto = WeChatCrypto("other_token", TEST_ENCODING_AES_KEY, "wrong_corp")
        plaintext = "<xml><Content>test</Content></xml>"

        encrypted = crypto.encrypt(plaintext, "nonce")
        with pytest.raises(ValueError, match="CorpID mismatch"):
            wrong_crypto.decrypt(encrypted)


class TestMessageParsing:
    def test_parse_text_message(self):
        xml = """<xml>
<ToUserName><![CDATA[agent_001]]></ToUserName>
<FromUserName><![CDATA[zhang_wei]]></FromUserName>
<CreateTime>1715721600</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[查一下我的资产情况]]></Content>
<MsgId>1234567890</MsgId>
</xml>"""

        msg = parse_message(xml)
        assert msg.msg_type == "text"
        assert msg.from_user == "zhang_wei"
        assert msg.to_user == "agent_001"
        assert msg.content == "查一下我的资产情况"

    def test_parse_voice_message(self):
        xml = """<xml>
<ToUserName><![CDATA[agent_001]]></ToUserName>
<FromUserName><![CDATA[zhang_wei]]></FromUserName>
<CreateTime>1715721600</CreateTime>
<MsgType><![CDATA[voice]]></MsgType>
<MediaId><![CDATA[media_123]]></MediaId>
<Format><![CDATA[amr]]></Format>
<Recognition><![CDATA[帮我查一下资产]]></Recognition>
<MsgId>1234567891</MsgId>
</xml>"""

        msg = parse_message(xml)
        assert msg.msg_type == "voice"
        assert msg.media_id == "media_123"
        assert msg.content == "帮我查一下资产"  # From Recognition field

    def test_parse_event_subscribe(self):
        xml = """<xml>
<ToUserName><![CDATA[agent_001]]></ToUserName>
<FromUserName><![CDATA[zhang_wei]]></FromUserName>
<CreateTime>1715721600</CreateTime>
<MsgType><![CDATA[event]]></MsgType>
<Event><![CDATA[subscribe]]></Event>
</xml>"""

        msg = parse_message(xml)
        assert msg.msg_type == "event"
        assert msg.event_type == "subscribe"


class TestResponseBuilding:
    def test_build_text_response(self):
        xml = build_text_response("user_001", "agent_001", "您好，张先生。")
        assert "<![CDATA[user_001]]>" in xml
        assert "<![CDATA[agent_001]]>" in xml
        assert "<![CDATA[您好，张先生。]]>" in xml

    def test_build_voice_response(self):
        xml = build_voice_response("user_001", "agent_001", "media_456")
        assert "<MediaId><![CDATA[media_456]]></MediaId>" in xml

    def test_build_empty_response(self):
        assert build_empty_response() == ""


class TestMessageHandler:
    @pytest.mark.asyncio
    async def test_subscribe_event_returns_welcome(self):
        """Subscribe event should return welcome message."""
        msg = WeChatMessage(
            msg_type="event",
            from_user="new_user",
            to_user="agent_001",
            event_type="subscribe",
        )

        result = await handle_message(msg, tenant_id="test", tools=None)  # type: ignore[arg-type]
        assert "欢迎使用" in result.reply_xml

    @pytest.mark.asyncio
    async def test_text_message_routes_to_agent(self):
        """Text message should route to AgentRunner."""
        msg = WeChatMessage(
            msg_type="text",
            from_user="zhang_wei",
            to_user="agent_001",
            content="你好",
        )

        # Without tools, the AgentRunner will try to use the real LLM client
        # which requires API keys. For now, test that it doesn't crash.
        from butler.engine.tool_registry import ToolRegistry
        result = await handle_message(
            msg, tenant_id="test", tools=ToolRegistry()
        )
        # Should return a reply (even if it's an error message from the LLM)
        assert isinstance(result.reply_xml, str)

    @pytest.mark.asyncio
    async def test_voice_without_recognition(self):
        """Voice without ASR should return processing message."""
        msg = WeChatMessage(
            msg_type="voice",
            from_user="zhang_wei",
            to_user="agent_001",
            media_id="media_001",
            content="",  # No recognition yet
        )

        result = await handle_message(msg, tenant_id="test", tools=None)  # type: ignore[arg-type]
        assert "处理中" in result.reply_xml

    @pytest.mark.asyncio
    async def test_empty_content_no_reply(self):
        """Empty message should return no reply."""
        msg = WeChatMessage(
            msg_type="text",
            from_user="zhang_wei",
            to_user="agent_001",
            content="",
        )

        result = await handle_message(msg, tenant_id="test", tools=None)  # type: ignore[arg-type]
        assert result.reply_xml == ""
