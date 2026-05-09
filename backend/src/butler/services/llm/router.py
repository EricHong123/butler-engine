"""Model routing. Chinese-language content → DeepSeek; complex reasoning → Claude."""

from __future__ import annotations

import re

from butler.config import settings

# Chinese character Unicode range
_CJK_RE = re.compile(r"[一-鿿㐀-䶿]", re.UNICODE)


def route_model(messages: list[dict]) -> tuple[str, str]:
    """
    Resolve model and provider.
    Always uses the resolved config — preset or manual.

    Returns (model, provider) where provider is "anthropic" or "openai".
    """
    model = settings.resolved_model
    provider = settings.resolved_provider_type
    if provider == "anthropic":
        return model, "anthropic"
    return model, "openai"
