from __future__ import annotations

from .types import Stage

# concept.md §3.3 / §3.4 cold-start defaults — sole source for Tier 1 reproduction.
W_I: dict[Stage, float] = {
    Stage.LOCALIZATION: 1.0,
    Stage.REPAIR: 3.0,
    Stage.VALIDATION: 2.5,
}

# Tier pool: Qwen family via 阿里云百炼 (DashScope).
# T1 = Qwen3.6-Flash (lightweight, ¥1.2/M in, ¥7.2/M out)
# T2 = Qwen3.6-Plus (balanced, ¥2/M in, ¥12/M out)
# T3 = Qwen3.7-Max (flagship, ¥4/M in, ¥16/M out, 5折 until 2026-06-22)
TIER1_BACKEND = "tier1_qwen_flash"
TIER2_BACKEND = "tier2_qwen_plus"
TIER3_BACKEND = "tier3_qwen_max"

PROGRESS_TABLE: dict[Stage, dict[str, float]] = {
    Stage.LOCALIZATION: {
        TIER1_BACKEND: 0.30,
        TIER2_BACKEND: 0.50,
        TIER3_BACKEND: 0.62,
    },
    Stage.REPAIR: {
        TIER1_BACKEND: 0.15,
        TIER2_BACKEND: 0.35,
        TIER3_BACKEND: 0.45,
    },
    Stage.VALIDATION: {
        TIER1_BACKEND: 0.25,
        TIER2_BACKEND: 0.45,
        TIER3_BACKEND: 0.55,
    },
}

# Scale factor converting progress deltas (0-1 probabilities) to cost-comparable units.
# Lower = more conservative about upgrading to expensive models.
PROGRESS_SCALE: float = 18.0

# Per-tier escalation patience: cheaper tiers get less patience before upgrading.
# Core BudgetFlow mechanism: "try cheap, escalate on failure within this task."
# T1 is expected to fail often → upgrade quickly. T3 gets most patience.
# Resets when a step makes progress (bash_has_progress returns True).
TIER_ESCALATION_PATIENCE: dict[int, int] = {
    1: 3,   # spark/gpt-5.2 → upgrade to T2 after 3 non-progress steps
    2: 5,   # flash → upgrade to T3 after 5 non-progress steps
    3: 10,  # pro → if this fails for 10 steps, task is genuinely stuck (stagnation)
}

# Adaptive routing (budgetflow_full only): rolling task feedback + in-run recovery.
ADAPTIVE_WINDOW = 5
ADAPTIVE_MIN_SAMPLES = 2
ADAPTIVE_WEAK_RESOLVE_MAX = 0.25
ADAPTIVE_STAGNATION_FRAC = 0.5
ADAPTIVE_PRESSURE_BOOST = 0.18
ADAPTIVE_PRESSURE_BOOST_STRONG = 0.32
ADAPTIVE_TTL_STEPS = 15

# Anti-stall: all strategies share same no-progress streak.
STAGNATION_REPEAT_CMD_LIMIT = 6
STAGNATION_NO_PROGRESS_STEPS = 40

BUDGET_PRESSURE_INIT = 0.01
PRESSURE_MAX = 1.5
UNCAPPED_BUDGET_THRESHOLD = 1_000_000.0

# 阿里云百炼 (DashScope) OpenAI-compatible endpoint.
DASHSCOPE_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# Qwen model IDs (bare names, no provider prefix — litellm routes via api_base).
QWEN_T1_MODEL = "qwen3.6-flash"
QWEN_T2_MODEL = "qwen3.6-plus"
QWEN_T3_MODEL = "qwen3.7-max"

# litellm model strings: openai/ prefix + custom api_base → 百炼.
TIER1_MODEL = f"openai/{QWEN_T1_MODEL}"
TIER2_MODEL = f"openai/{QWEN_T2_MODEL}"
TIER3_MODEL = f"openai/{QWEN_T3_MODEL}"

# Terminal model= labels for console output.
TIER1_DISPLAY = "qwen3.6-flash"
TIER2_DISPLAY = "qwen3.6-plus"
TIER3_DISPLAY = "qwen3.7-max"

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

# Back-compat aliases for scripts that reference old model names.
DEEPSEEK_API_BASE = DASHSCOPE_API_BASE
DEEPSEEK_V4_FLASH_MODEL = TIER2_MODEL
DEEPSEEK_V4_PRO_MODEL = TIER3_MODEL


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
