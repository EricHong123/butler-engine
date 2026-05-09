"""Central configuration via pydantic-settings. Includes presets for all major Chinese LLM providers."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Load .env into os.environ (for non-BUTLER_ prefixed keys like DEEPSEEK_API_KEY) ──
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


def _load_env_file(path: Path) -> None:
    """Manually load .env file into os.environ. Pydantic-settings only loads
    BUTLER_-prefixed keys, but provider API keys use different env var names."""
    if not path.exists():
        return
    for line in path.read_text().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and val and key not in os.environ:
            os.environ[key] = val


_load_env_file(_ENV_PATH)


# ── Provider Presets ──
# Each preset defines: model name, base URL, and which env var holds the API key.
# Set BUTLER_PROVIDER=<key> and the corresponding API_KEY env var.

PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    # Claude 系列
    "claude": {
        "model": "claude-sonnet-4-6-20250514",
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "provider_type": "anthropic",
        "description": "Anthropic Claude — 最强推理+工具调用，英文最优",
    },
    # 深度求索
    "deepseek": {
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "provider_type": "openai",
        "description": "DeepSeek V3/R1 — 中文流畅，性价比最高",
    },
    # 阿里通义千问
    "qwen": {
        "model": "qwen-plus",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "provider_type": "openai",
        "description": "阿里通义千问 Qwen — 中文理解强，阿里云生态集成",
    },
    # 月之暗面 Kimi
    "kimi": {
        "model": "moonshot-v1-32k",
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "provider_type": "openai",
        "description": "Moonshot Kimi — 超长上下文（128K），文档分析强",
    },
    # 智谱 GLM
    "zhipu": {
        "model": "glm-4-plus",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "ZHIPU_API_KEY",
        "provider_type": "openai",
        "description": "智谱 GLM-4 — 多模态，中文问答优秀",
    },
    # 字节豆包
    "doubao": {
        "model": "doubao-pro-256k",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key_env": "ARK_API_KEY",
        "provider_type": "openai",
        "description": "字节豆包 Doubao — 256K超长上下文，企业级并发",
    },
    # 百川智能
    "baichuan": {
        "model": "Baichuan4",
        "base_url": "https://api.baichuan-ai.com/v1",
        "api_key_env": "BAICHUAN_API_KEY",
        "provider_type": "openai",
        "description": "百川 Baichuan4 — 中文理解和生成均衡",
    },
    # MiniMax
    "minimax": {
        "model": "abab6.5s-chat",
        "base_url": "https://api.minimax.chat/v1",
        "api_key_env": "MINIMAX_API_KEY",
        "provider_type": "openai",
        "description": "MiniMax 海螺 — 语音合成强，适合语音回复场景",
    },
    # 商汤日日新
    "sensenova": {
        "model": "SenseChat-5",
        "base_url": "https://api.sensenova.cn/v1",
        "api_key_env": "SENSENOVA_API_KEY",
        "provider_type": "openai",
        "description": "商汤日日新 SenseChat — 多模态，视觉理解强",
    },
    # 腾讯混元
    "hunyuan": {
        "model": "hunyuan-pro",
        "base_url": "https://api.hunyuan.cloud.tencent.com/v1",
        "api_key_env": "HUNYUAN_API_KEY",
        "provider_type": "openai",
        "description": "腾讯混元 Hunyuan — 微信生态整合，企业微信天然对接",
    },
    # 阶跃星辰
    "stepfun": {
        "model": "step-2-16k",
        "base_url": "https://api.stepfun.com/v1",
        "api_key_env": "STEPFUN_API_KEY",
        "provider_type": "openai",
        "description": "阶跃星辰 Step — 数学推理强，多模态",
    },
    # OpenAI
    "openai": {
        "model": "gpt-4o",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "provider_type": "openai",
        "description": "OpenAI GPT-4o — 综合能力最强（需海外 API Key）",
    },
    # 自定义：手动设 MODEL / BASE_URL / API_KEY
    "custom": {
        "model": "",
        "base_url": "",
        "api_key_env": "OPENAI_API_KEY",
        "provider_type": "openai",
        "description": "自定义 OpenAI 兼容端点",
    },
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BUTLER_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # ── App ──
    app_name: str = "butler-engine"
    debug: bool = False
    data_root: Path = Path(__file__).resolve().parent.parent.parent / "data"

    # ── Database ──
    # Dev: SQLite (auto-resolved). Prod: postgresql+asyncpg://user:pass@host:5432/db
    database_url: str = ""  # Set below if empty

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"

    # ── Provider 选择 ──
    # 设为上面任意 preset key（deepseek/qwen/kimi/zhipu/doubao/minimax/...）
    # 留空则从下面的 model / base_url 手动配置
    provider: str = ""

    # ── 手动 LLM 配置（provider 为空时生效）──
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com/v1"
    default_model: str = "deepseek-chat"
    fallback_model: str = "deepseek-chat"
    chat_model: str = ""
    max_turns: int = 50
    max_budget_usd: float = 5.0
    compact_threshold_tokens: int = 80_000

    # ── WeChat ──
    wechat_corp_id: str = ""
    wechat_token: str = ""
    wechat_encoding_aes_key: str = ""
    wechat_agent_id: str = ""

    # ── Security ──
    encryption_master_key: str = ""
    audit_log_retention_days: int = 365

    # ── Review ──
    review_queue_sla_seconds: int = 300

    @property
    def resolved_model(self) -> str:
        """Effective model name: chat_model > preset model > default_model."""
        if self.chat_model:
            return self.chat_model
        if self.provider and self.provider in PROVIDER_PRESETS:
            preset = PROVIDER_PRESETS[self.provider]
            return preset["model"]
        return self.default_model

    @property
    def resolved_base_url(self) -> str:
        """Effective base URL for OpenAI-compatible API."""
        if self.provider and self.provider in PROVIDER_PRESETS:
            preset = PROVIDER_PRESETS[self.provider]
            return preset["base_url"]
        return self.openai_base_url

    @property
    def resolved_api_key(self) -> str:
        """Effective API key, resolved from the appropriate env var."""
        if self.provider and self.provider in PROVIDER_PRESETS:
            preset = PROVIDER_PRESETS[self.provider]
            env_var = preset["api_key_env"]
            return os.environ.get(env_var, "")
        return self.openai_api_key or self.anthropic_api_key

    @property
    def resolved_provider_type(self) -> str:
        """'anthropic' or 'openai' — determines which SDK to use."""
        if self.provider and self.provider in PROVIDER_PRESETS:
            return PROVIDER_PRESETS[self.provider]["provider_type"]
        if self.anthropic_api_key and not self.openai_api_key:
            return "anthropic"
        return "openai"

    def model_post_init(self, _):
        self.data_root.mkdir(parents=True, exist_ok=True)
        if not self.database_url:
            db_path = Path(__file__).resolve().parent.parent.parent / "butler.db"
            object.__setattr__(self, "database_url", f"sqlite+aiosqlite:///{db_path}")


settings = Settings()
