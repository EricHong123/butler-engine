"""
企业微信 Server API HTTP client.

API docs: https://developer.work.weixin.qq.com/document/path/90664
"""

from __future__ import annotations

from typing import Any

import httpx

from butler.config import settings


class WeChatAPIClient:
    """
    HTTP client for 企业微信 server API.

    Used for:
    - Sending proactive messages (no webhook context)
    - Access token management
    - Media upload/download
    """

    BASE_URL = "https://qyapi.weixin.qq.com/cgi-bin"

    def __init__(self) -> None:
        self._access_token: str | None = None
        self._token_expiry: float = 0.0

    async def get_access_token(self) -> str:
        """Get or refresh the access token."""
        import time as _time

        if self._access_token and _time.time() < self._token_expiry - 300:
            return self._access_token

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/gettoken",
                params={
                    "corpid": settings.wechat_corp_id,
                    "corpsecret": settings.wechat_agent_id,
                },
            )
            data = resp.json()
            if data.get("errcode") != 0:
                raise RuntimeError(f"Failed to get access token: {data}")

            self._access_token = data["access_token"]
            self._token_expiry = _time.time() + data.get("expires_in", 7200)
            return self._access_token

    async def send_text_message(
        self, user_id: str, content: str, agent_id: str | None = None
    ) -> dict[str, Any]:
        """
        Send a text message to a specific user via the app.

        Args:
            user_id: The 企业微信 user ID to send to
            content: Message text (max 2048 bytes)
            agent_id: Application agent ID (defaults to config)
        """
        token = await self.get_access_token()
        agent = agent_id or settings.wechat_agent_id
        body = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": int(agent),
            "text": {"content": content[:2048]},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/message/send",
                params={"access_token": token},
                json=body,
            )
            return resp.json()

    async def send_voice_message(
        self, user_id: str, media_id: str, agent_id: str | None = None
    ) -> dict[str, Any]:
        """Send a voice message (pre-uploaded media)."""
        token = await self.get_access_token()
        agent = agent_id or settings.wechat_agent_id
        body = {
            "touser": user_id,
            "msgtype": "voice",
            "agentid": int(agent),
            "voice": {"media_id": media_id},
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/message/send",
                params={"access_token": token},
                json=body,
            )
            return resp.json()

    async def download_media(self, media_id: str) -> bytes | None:
        """Download temporary media (voice, image) by media_id."""
        token = await self.get_access_token()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.BASE_URL}/media/get",
                params={"access_token": token, "media_id": media_id},
            )
            if resp.status_code == 200:
                return resp.content
        return None

    async def upload_media(
        self, media_type: str, file_data: bytes, filename: str
    ) -> dict[str, Any]:
        """Upload temporary media (voice, image, file)."""
        token = await self.get_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/media/upload",
                params={"access_token": token, "type": media_type},
                files={"media": (filename, file_data)},
            )
            return resp.json()
