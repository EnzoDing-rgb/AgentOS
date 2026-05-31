from __future__ import annotations

from .types import Stage

# concept.md §3.3 / §3.4 cold-start defaults — sole source for Tier 1 reproduction.
W_I: dict[Stage, float] = {
    Stage.LOCALIZATION: 1.0,
    Stage.REPAIR: 3.0,
    Stage.VALIDATION: 2.5,
}

# Tier pool requested by experiment owner:
# T1 = GPT-5.3 Codex Spark, T2 = DeepSeek V4 Flash, T3 = DeepSeek V4 Pro.
TIER1_BACKEND = "tier1_spark"
TIER2_BACKEND = "tier2_flash"
TIER3_BACKEND = "tier3_pro"

PROGRESS_TABLE: dict[Stage, dict[str, float]] = {
    Stage.LOCALIZATION: {
        TIER1_BACKEND: 0.45,
        TIER2_BACKEND: 0.55,
        TIER3_BACKEND: 0.50,
    },
    Stage.REPAIR: {
        TIER1_BACKEND: 0.25,
        TIER2_BACKEND: 0.40,
        TIER3_BACKEND: 0.45,
    },
    Stage.VALIDATION: {
        TIER1_BACKEND: 0.35,
        TIER2_BACKEND: 0.42,
        TIER3_BACKEND: 0.40,
    },
}

# Progress-based escalation (budgetflow_full only): consecutive read-only steps.
ESCALATION_THRESHOLD = 5

# Anti-stall: all strategies share same no-progress streak.
STAGNATION_REPEAT_CMD_LIMIT = 6
STAGNATION_NO_PROGRESS_STEPS = 30

BUDGET_PRESSURE_INIT = 0.01
PRESSURE_MAX = 1.5
UNCAPPED_BUDGET_THRESHOLD = 1_000_000.0

DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEEPSEEK_V4_FLASH_MODEL = "deepseek/deepseek-chat"
DEEPSEEK_V4_PRO_MODEL = "deepseek/deepseek-reasoner"

# litellm needs provider prefix; api_base/api_key pin calls to AICode007 (not OpenAI official).
TIER1_MODEL_ID = "gpt-5.3-codex-spark"
TIER1_MODEL = f"openai/{TIER1_MODEL_ID}"
TIER2_MODEL = DEEPSEEK_V4_FLASH_MODEL
TIER3_MODEL = DEEPSEEK_V4_PRO_MODEL

# Terminal model= labels (hyphenated; lowercase product tokens).
TIER1_DISPLAY = TIER1_MODEL_ID
TIER2_DISPLAY = "deepseek-v4-flash"
TIER3_DISPLAY = "deepseek-v4-pro"

TIER_DISPLAY_BY_BACKEND: dict[str, str] = {
    TIER1_BACKEND: TIER1_DISPLAY,
    TIER2_BACKEND: TIER2_DISPLAY,
    TIER3_BACKEND: TIER3_DISPLAY,
}

TIER_MODEL_BY_BACKEND: dict[str, str] = {
    TIER1_BACKEND: TIER1_MODEL,
    TIER2_BACKEND: TIER2_MODEL,
    TIER3_BACKEND: TIER3_MODEL,
}


def tier_display_name(backend_name: str) -> str:
    """Map tier backend id (e.g. tier3_pro) to full product name."""
    if not backend_name or backend_name == "-":
        return "-"
    return TIER_DISPLAY_BY_BACKEND.get(backend_name, backend_name)


def tier_model_id(backend_name: str) -> str:
    return TIER_MODEL_BY_BACKEND.get(backend_name, backend_name)


# Back-compat for probe/baseline scripts.
DEEPSEEK_FLASH_MODEL = DEEPSEEK_V4_FLASH_MODEL
DEEPSEEK_PRO_MODEL = DEEPSEEK_V4_PRO_MODEL

# Legacy alias (pilot docs); compare uses DeepSeek only.
AICODE007_API_BASE = "https://api.aicode007.com/v1"
