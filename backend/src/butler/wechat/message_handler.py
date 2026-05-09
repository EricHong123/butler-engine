"""
企业微信 message parser and router.

Handles incoming messages after decryption:
  - text, voice, image, event (subscribe/unsubscribe)
  - Routes to AgentRunner for AI processing
  - Manages human review queue for sensitive responses
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree as ET

from butler.wechat.client import WeChatAPIClient


# ── Message Types ──

@dataclass
class WeChatMessage:
    """Parsed incoming message from 企业微信."""
    msg_type: str  # text, voice, image, event
    from_user: str  # sender's 企业微信 user ID
    to_user: str  # our agent's user ID
    content: str = ""  # text content or voice recognition
    media_id: str = ""  # for voice/image
    event_type: str = ""  # for event messages (subscribe, etc.)
    msg_id: str = ""
    create_time: int = 0
    raw: dict[str, str] = field(default_factory=dict)


def parse_message(decrypted_xml: str) -> WeChatMessage:
    """Parse decrypted XML into a WeChatMessage."""
    root = ET.fromstring(decrypted_xml)

    def _text(tag: str) -> str:
        el = root.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    msg_type = _text("MsgType")

    return WeChatMessage(
        msg_type=msg_type,
        from_user=_text("FromUserName"),
        to_user=_text("ToUserName"),
        content=_text("Content") if msg_type == "text" else _text("Recognition"),
        media_id=_text("MediaId"),
        event_type=_text("Event") if msg_type == "event" else "",
        msg_id=_text("MsgId"),
        create_time=int(_text("CreateTime") or 0),
        raw={
            child.tag: child.text or ""
            for child in root
            if child.text
        },
    )


def build_text_response(
    from_user: str, to_user: str, content: str
) -> str:
    """Build a text response XML."""
    timestamp = int(time.time())
    return (
        "<xml>\n"
        f"<ToUserName><![CDATA[{from_user}]]></ToUserName>\n"
        f"<FromUserName><![CDATA[{to_user}]]></FromUserName>\n"
        f"<CreateTime>{timestamp}</CreateTime>\n"
        f"<MsgType><![CDATA[text]]></MsgType>\n"
        f"<Content><![CDATA[{content}]]></Content>\n"
        "</xml>"
    )


def build_voice_response(
    from_user: str, to_user: str, media_id: str
) -> str:
    """Build a voice response XML."""
    timestamp = int(time.time())
    return (
        "<xml>\n"
        f"<ToUserName><![CDATA[{from_user}]]></ToUserName>\n"
        f"<FromUserName><![CDATA[{to_user}]]></FromUserName>\n"
        f"<CreateTime>{timestamp}</CreateTime>\n"
        f"<MsgType><![CDATA[voice]]></MsgType>\n"
        f"<Voice><MediaId><![CDATA[{media_id}]]></MediaId></Voice>\n"
        "</xml>"
    )


def build_empty_response() -> str:
    """Return empty string for no-reply (enterprise WeChat accepts this)."""
    return ""


# ── Agent Runner Registry ──
# In production, this would be backed by Redis/Database.
# For MVP, we use an in-memory dict (one AgentRunner per user).

from butler.engine.agent_runner import AgentRunner, AgentRunnerConfig
from butler.engine.tool_registry import ToolRegistry

_runner_registry: dict[str, AgentRunner] = {}


def get_or_create_runner(
    user_id: str,
    tenant_id: str,
    tools: ToolRegistry,
    profile_markdown: str | None = None,
    memory_index: str | None = None,
) -> AgentRunner:
    """Get existing runner for this user or create a new one."""
    if user_id not in _runner_registry:
        config = AgentRunnerConfig(
            tenant_id=tenant_id,
            tools=tools,
            profile_markdown=profile_markdown,
            memory_index=memory_index,
        )
        _runner_registry[user_id] = AgentRunner(config)

    return _runner_registry[user_id]


# ── Message Router ──

@dataclass
class HandlerResult:
    """Result from processing a message."""
    reply_xml: str = ""  # Empty = no reply
    needs_review: bool = False
    review_context: dict | None = None


async def handle_message(
    msg: WeChatMessage,
    *,
    tenant_id: str,
    tools: ToolRegistry,
    profile_md: str | None = None,
    memory_idx: str | None = None,
    wechat_client: WeChatAPIClient | None = None,
) -> HandlerResult:
    """
    Route an incoming message to the appropriate handler.

    Returns a HandlerResult with the reply XML (encrypted by the caller).
    """
    # ── Event messages ──
    if msg.msg_type == "event":
        if msg.event_type == "subscribe":
            return HandlerResult(
                reply_xml=build_text_response(
                    msg.from_user, msg.to_user,
                    "欢迎使用家族AI管家。我是您的专属私人助理，随时为您服务。"
                )
            )
        return HandlerResult()  # Other events: no reply

    # ── Voice messages ──
    if msg.msg_type == "voice":
        # If ASR already transcribed by WeChat
        if msg.content:
            msg.msg_type = "text"  # Treat as text for processing
        elif wechat_client and msg.media_id:
            # Download voice media and transcribe
            voice_data = await wechat_client.download_media(msg.media_id)
            if voice_data:
                import tempfile
                from butler.services.speech import transcribe_audio

                with tempfile.NamedTemporaryFile(suffix=".amr", delete=False) as tmp:
                    tmp.write(voice_data)
                    tmp_path = tmp.name

                try:
                    transcription = await transcribe_audio(tmp_path, f"{msg.media_id}.amr")
                    if transcription.strip():
                        msg.content = transcription
                        msg.msg_type = "text"
                    else:
                        import os
                        os.unlink(tmp_path)
                        return HandlerResult(
                            reply_xml=build_text_response(
                                msg.from_user, msg.to_user,
                                "收到您的语音，正在转文字处理中，请稍候...",
                            )
                        )
                finally:
                    try:
                        import os
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            else:
                return HandlerResult(
                    reply_xml=build_text_response(
                        msg.from_user, msg.to_user,
                        "收到您的语音，正在处理中，请稍候...",
                    )
                )
        else:
            return HandlerResult(
                reply_xml=build_text_response(
                    msg.from_user, msg.to_user,
                    "收到您的语音，正在处理中，请稍候...",
                )
            )

    # ── Text messages ──
    if msg.msg_type == "text" and msg.content:
        # Guard: scan for prompt injection
        from butler.services.guard import scan_content, GuardResult
        guard = scan_content(msg.content, threshold=30)
        if guard.is_blocked:
            return HandlerResult(
                reply_xml=build_text_response(
                    msg.from_user, msg.to_user,
                    "您的消息包含异常指令，已被安全系统拦截。如需帮助请联系人工客服。",
                ),
                needs_review=False,
                ticket=None,
            )
        elif guard.is_suspicious:
            # Flag for review but still process
            from butler.engine.audit import audit_security_event
            import asyncio as _asyncio
            _asyncio.ensure_future(audit_security_event(
                tenant_id=tenant_id,
                event_type="injection_suspicious",
                details=f"score={guard.score} patterns={[m['pattern'] for m in guard.matches]}",
            ))

        # Get or create AgentRunner for this user
        runner = get_or_create_runner(
            msg.from_user, tenant_id, tools, profile_md, memory_idx
        )

        # Stream AI response
        response_parts: list[str] = []
        needs_review = False

        try:
            async for event in runner.submit_message(msg.content):
                if event.type == "text_delta":
                    response_parts.append(str(event.data))
                elif event.type == "tool_call":
                    # Check if this tool requires human review
                    if event.data.get("name") == "escalate_to_human":
                        needs_review = True
        except Exception as exc:
            response_parts.append(f"抱歉，处理您的请求时出现了问题。请稍后重试。")

        full_response = "".join(response_parts)

        # If needs review, queue it instead of replying directly
        if needs_review:
            from butler.review.queue import TicketPriority, get_review_queue

            review_queue, _ = await get_review_queue()
            ticket = await review_queue.submit(
                tenant_id=tenant_id,
                from_user=msg.from_user,
                to_user=msg.to_user,
                customer_query=msg.content,
                draft_response=full_response,
                reason="ai_flagged",
                priority=TicketPriority.STANDARD,
            )

            return HandlerResult(
                reply_xml=build_text_response(
                    msg.from_user, msg.to_user,
                    f"您的要求已收到（工单 {ticket.ticket_id}），我的团队正在处理，稍后给您回复。",
                ),
                needs_review=True,
                review_context={
                    "ticket_id": ticket.ticket_id,
                    "from_user": msg.from_user,
                    "to_user": msg.to_user,
                    "query": msg.content,
                    "draft_response": full_response,
                    "tenant_id": tenant_id,
                },
            )

        # Return AI response directly
        if full_response.strip():
            return HandlerResult(
                reply_xml=build_text_response(
                    msg.from_user, msg.to_user, full_response[:2048]
                )
            )

    # ── Default: no reply ──
    return HandlerResult()
