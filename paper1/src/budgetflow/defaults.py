from __future__ import annotations

from .types import Stage

# concept.md §3.3 / §3.4 cold-start defaults — sole source for Tier 1 reproduction.
W_I: dict[Stage, float] = {
    Stage.LOCALIZATION: 1.0,
    Stage.REPAIR: 3.0,
    Stage.VALIDATION: 2.5,
}

TIER1_BACKEND = "tier1_codex_spark"
TIER2_BACKEND = "tier2_gpt54_mini"
TIER3_BACKEND = "tier3_codex"

PROGRESS_TABLE: dict[Stage, dict[str, float]] = {
    Stage.LOCALIZATION: {
        TIER1_BACKEND: 0.30,
        TIER2_BACKEND: 0.35,
        TIER3_BACKEND: 0.33,
    },
    Stage.REPAIR: {
        TIER1_BACKEND: 0.10,
        TIER2_BACKEND: 0.22,
        TIER3_BACKEND: 0.32,
    },
    Stage.VALIDATION: {
        TIER1_BACKEND: 0.22,
        TIER2_BACKEND: 0.30,
        TIER3_BACKEND: 0.36,
    },
}

# Calibrated for 3-tier mock costs @ ~8k input tokens: repair T1→T2 score≈0.027, T2→T3≈0.009.
BUDGET_PRESSURE_INIT = 0.01
PRESSURE_MAX = 1.5
UNCAPPED_BUDGET_THRESHOLD = 1_000_000.0

# All tiers — AICode007 (OpenAI-compatible). openai/ prefix avoids litellm provider spam.
TIER1_MODEL = "openai/gpt-5.3-codex-spark"
TIER2_MODEL = "openai/gpt-5.4-mini"
TIER3_MODEL = "openai/gpt-5.3-codex"
AICODE007_API_BASE = "https://api.aicode007.com/v1"

# DeepSeek official API — litellm requires provider prefix (deepseek/...).
DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEEPSEEK_FLASH_MODEL = "deepseek/deepseek-chat"
DEEPSEEK_PRO_MODEL = "deepseek/deepseek-reasoner"
