"""
Speech-to-text (ASR) service. Transcribes voice messages to text.

Providers (auto-detected from config):
  - MiniMax (国内最优，中文识别率高)
  - OpenAI Whisper API (通用)
  - Local fallback: returns empty (triggers prompt for text input)
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

from butler.config import settings


async def transcribe_audio(
    file_path: Path | str,
    filename: str = "voice.amr",
) -> str:
    """
    Transcribe an audio file to text.
    Auto-selects provider based on configured API keys.
    Returns empty string if transcription fails.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        return ""

    # Try MiniMax first (best for Chinese)
    if settings.openai_api_key and "minimax" in settings.openai_base_url:
        result = await _transcribe_openai_compatible(file_path, filename)
        if result:
            return result

    # Try any OpenAI-compatible endpoint (DeepSeek doesn't do ASR, but we try anyway)
    if settings.openai_api_key:
        result = await _transcribe_openai_compatible(file_path, filename)
        if result:
            return result

    # Try MiniMax API key
    minimax_key = os.environ.get("MINIMAX_API_KEY", "")
    if minimax_key:
        result = await _transcribe_minimax(file_path, minimax_key)
        if result:
            return result

    return ""


async def _transcribe_openai_compatible(
    file_path: Path,
    filename: str,
) -> str:
    """Use OpenAI-compatible /v1/audio/transcriptions endpoint."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            with open(file_path, "rb") as f:
                response = await client.post(
                    f"{settings.openai_base_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    files={"file": (filename, f, _mime_type(filename))},
                    data={"model": "whisper-1", "language": "zh"},
                )
            if response.status_code == 200:
                data = response.json()
                return data.get("text", "")
    except Exception:
        pass
    return ""


async def _transcribe_minimax(file_path: Path, api_key: str) -> str:
    """Use MiniMax native ASR API."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            with open(file_path, "rb") as f:
                # MiniMax uses multipart form upload similar to OpenAI
                response = await client.post(
                    "https://api.minimax.chat/v1/audio/transcription",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": ("voice.amr", f, "audio/amr")},
                    data={"model": "speech-01", "language": "zh"},
                )
            if response.status_code == 200:
                data = response.json()
                return data.get("text", "")
    except Exception:
        pass
    return ""


def _mime_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".amr": "audio/amr",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
    }.get(ext, "audio/amr")
