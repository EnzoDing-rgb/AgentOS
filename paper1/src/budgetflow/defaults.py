from __future__ import annotations

from .types import Stage

# concept.md §3.3 / §3.4 cold-start defaults — sole source for Tier 1 reproduction.
W_I: dict[Stage, float] = {
    Stage.LOCALIZATION: 1.0,
    Stage.REPAIR: 3.0,
    Stage.VALIDATION: 2.5,
}

TIER1_BACKEND = "tier1_gpt52"
TIER2_BACKEND = "tier2_deepseek_pro"
TIER3_BACKEND = "tier3_gpt54_mini"

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

# Tier 1 / 3 — aicode007 (OpenAI-compatible)
TIER1_MODEL = "gpt-5.2"
TIER3_MODEL = "gpt-5.4-mini"
AICODE007_API_BASE = "https://api.aicode007.com/v1"

# Tier 2 — DeepSeek official
TIER2_MODEL = "deepseek/deepseek-v4-pro"
DEEPSEEK_API_BASE = "https://api.deepseek.com"

# Legacy aliases (baseline runner / docs)
DEEPSEEK_FLASH_MODEL = TIER2_MODEL
DEEPSEEK_PRO_MODEL = TIER3_MODEL
