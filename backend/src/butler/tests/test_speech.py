"""Tests for speech-to-text service."""

import tempfile
from pathlib import Path

import pytest

from butler.services.speech import transcribe_audio, _mime_type


class TestMimeType:
    def test_amr(self):
        assert _mime_type("voice.amr") == "audio/amr"

    def test_mp3(self):
        assert _mime_type("voice.mp3") == "audio/mpeg"

    def test_wav(self):
        assert _mime_type("audio.wav") == "audio/wav"


@pytest.mark.asyncio
async def test_transcribe_with_empty_file():
    """Empty file should return empty string (no API call made)."""
    with tempfile.NamedTemporaryFile(suffix=".amr", delete=False) as f:
        f.write(b"")  # Empty file — too small to be valid audio
        path = f.name

    try:
        result = await transcribe_audio(path, "test.amr")
        assert result == ""  # Empty file can't be transcribed
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_transcribe_nonexistent_file():
    """Nonexistent file returns empty string."""
    result = await transcribe_audio("/tmp/nonexistent_voice_xyz.amr", "test.amr")
    assert result == ""
