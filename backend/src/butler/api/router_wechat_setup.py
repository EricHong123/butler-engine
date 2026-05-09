"""
企业微信接入配置 API。帮助用户自助完成企业微信 Bot 的接入配置。

GET  /api/wechat-setup/status   — 当前配置状态
POST /api/wechat-setup/save     — 保存配置
POST /api/wechat-setup/test     — 测试连接
GET  /api/wechat-setup/callback-url — 生成回调 URL
"""

from __future__ import annotations

import hashlib
import os
import time as _time

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from butler.config import settings

router = APIRouter(prefix="/api/wechat-setup", tags=["wechat-setup"])


class WeChatConfigRequest(BaseModel):
    corp_id: str = Field(..., min_length=1, description="企业微信 Corp ID")
    token: str = Field(..., min_length=3, description="回调 Token")
    encoding_aes_key: str = Field(..., min_length=43, max_length=43, description="43 位 Encoding AES Key")
    agent_id: str = Field(..., description="应用 Agent ID")
    callback_url: str = Field("", description="回调 URL")


@router.get("/status")
async def get_status():
    """获取当前企业微信配置状态"""
    configured = bool(
        settings.wechat_corp_id
        and settings.wechat_token
        and settings.wechat_encoding_aes_key
    )
    return {
        "configured": configured,
        "corp_id": _mask(settings.wechat_corp_id),
        "token_configured": bool(settings.wechat_token),
        "encoding_aes_key_configured": bool(settings.wechat_encoding_aes_key),
        "agent_id": settings.wechat_agent_id or "未配置",
        "callback_url_hint": _guess_callback_url(),
    }


@router.post("/save")
async def save_config(config: WeChatConfigRequest):
    """保存企业微信配置到 .env 文件"""
    env_path = _get_env_path()

    # Read existing .env
    existing = {}
    if env_path.exists():
        for line in env_path.read_text().split("\n"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip().strip('"').strip("'")

    # Update WeChat fields
    existing["BUTLER_WECHAT_CORP_ID"] = config.corp_id
    existing["BUTLER_WECHAT_TOKEN"] = config.token
    existing["BUTLER_WECHAT_ENCODING_AES_KEY"] = config.encoding_aes_key
    existing["BUTLER_WECHAT_AGENT_ID"] = config.agent_id

    # Write back
    lines = []
    for k, v in existing.items():
        if v:
            lines.append(f"{k}={v}")
    env_path.write_text("\n".join(lines) + "\n")

    # Update runtime settings
    object.__setattr__(settings, "wechat_corp_id", config.corp_id)
    object.__setattr__(settings, "wechat_token", config.token)
    object.__setattr__(settings, "wechat_encoding_aes_key", config.encoding_aes_key)
    object.__setattr__(settings, "wechat_agent_id", config.agent_id)

    return {
        "status": "saved",
        "message": "配置已保存。请重启后端服务以使配置生效。",
        "need_restart": True,
    }


@router.post("/test")
async def test_connection(config: WeChatConfigRequest | None = None):
    """
    测试企业微信连接。验证：
    1. 加密/解密是否正确
    2. 回调 URL 签名验证
    3. 获取 Access Token
    """
    results = []

    # Use provided config or current settings
    corp_id = config.corp_id if config else settings.wechat_corp_id
    token = config.token if config else settings.wechat_token
    aes_key = config.encoding_aes_key if config else settings.wechat_encoding_aes_key
    agent_id = config.agent_id if config else settings.wechat_agent_id

    # Test 1: Validate Encoding AES Key
    if aes_key and len(aes_key) == 43:
        try:
            import base64
            decoded = base64.b64decode(aes_key + "=")
            if len(decoded) == 32:
                results.append({"test": "AES 密钥格式", "status": "pass", "detail": "43 位 Base64 编码，解码后 32 字节，格式正确"})
            else:
                results.append({"test": "AES 密钥格式", "status": "fail", "detail": f"解码后为 {len(decoded)} 字节，应为 32 字节"})
        except Exception as e:
            results.append({"test": "AES 密钥格式", "status": "fail", "detail": f"Base64 解码失败: {e}"})
    else:
        results.append({"test": "AES 密钥格式", "status": "fail", "detail": f"密钥长度 {len(aes_key or '')}，应为 43 位"})

    # Test 2: Signature verification
    if token and aes_key and corp_id:
        try:
            from butler.wechat.crypto import WeChatCrypto
            crypto = WeChatCrypto(token, aes_key, corp_id)
            test_echo = "test_echo_123"
            nonce = "test_nonce"
            timestamp = str(int(_time.time()))

            # Encrypt
            encrypted_xml = crypto.encrypt(
                f"<xml><Content>{test_echo}</Content></xml>", nonce
            )
            import re
            encrypted_text = re.search(
                r"<Encrypt><!\[CDATA\[(.*?)\]\]></Encrypt>", encrypted_xml
            )
            if encrypted_text:
                encrypted = encrypted_text.group(1)
                # Verify signature
                params = sorted([token, timestamp, nonce, encrypted])
                sig = hashlib.sha1("".join(params).encode()).hexdigest()
                verified = crypto.verify_signature(sig, timestamp, nonce, encrypted)

                # Decrypt back
                decrypted = crypto.decrypt(encrypted_xml)

                if verified and test_echo in decrypted:
                    results.append({"test": "加密/解密往返", "status": "pass", "detail": "签名验证 + 加解密往返正常"})
                else:
                    results.append({"test": "加密/解密往返", "status": "fail", "detail": "签名验证或解密失败"})
        except Exception as e:
            results.append({"test": "加密/解密往返", "status": "fail", "detail": str(e)})

    # Test 3: Get access token
    if corp_id and agent_id:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                    params={"corpid": corp_id, "corpsecret": agent_id},
                )
                data = resp.json()
                if data.get("errcode") == 0:
                    results.append({"test": "Access Token", "status": "pass", "detail": "成功获取 Access Token"})
                else:
                    results.append({
                        "test": "Access Token",
                        "status": "fail",
                        "detail": f"错误码 {data.get('errcode')}: {data.get('errmsg', '未知错误')}",
                        "hint": "Agent ID 可能不是 corpsecret。请在企业微信后台获取应用的 Secret。"
                    })
        except Exception as e:
            results.append({"test": "Access Token", "status": "fail", "detail": f"网络请求失败: {e}"})

    passed = sum(1 for r in results if r["status"] == "pass")
    return {
        "total": len(results),
        "passed": passed,
        "all_pass": passed == len(results),
        "results": results,
    }


@router.get("/callback-url")
async def get_callback_url():
    """获取建议的回调 URL"""
    return {
        "url": _guess_callback_url(),
        "note": "请将此 URL 配置到企业微信后台的「接收消息」→「回调 URL」中",
        "steps": [
            "1. 登录企业微信管理后台 (work.weixin.qq.com)",
            "2. 进入「应用管理」→ 选择你的应用",
            "3. 找到「接收消息」→「设置API接收」",
            "4. 填入上述 URL",
            "5. 填入 Token 和 EncodingAESKey",
            "6. 点击「保存」— 企业微信会发送验证请求",
        ],
    }


def _mask(s: str) -> str:
    if not s:
        return "未配置"
    if len(s) <= 8:
        return s[:2] + "****" + s[-2:]
    return s[:4] + "****" + s[-4:]


def _guess_callback_url() -> str:
    """根据环境推测回调 URL"""
    port = os.environ.get("PORT", "8000")
    host = os.environ.get("HOST", "your-domain.com")
    return f"https://{host}/wechat/callback"


def _get_env_path():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent.parent.parent / ".env"
