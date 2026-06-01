from __future__ import annotations

import os

from .types import Stage

# concept.md §3.3 / §3.4 cold-start defaults — sole source for Tier 1 reproduction.
W_I: dict[Stage, float] = {
    Stage.LOCALIZATION: 1.0,
    Stage.REPAIR: 3.0,
    Stage.VALIDATION: 2.5,
}

# §8.4 weight-ordering sub-ablation: swap only the w_i profile, mechanism fixed.
# Select at run time via env var BF_W_PROFILE (empty/unknown -> repair_heavy default).
# Tests external hypothesis "judging a patch > writing it" (validation_heavy).
W_I_PROFILES: dict[str, dict[Stage, float]] = {
    "repair_heavy": dict(W_I),  # current default ordering
    "validation_heavy": {
        Stage.LOCALIZATION: 1.0,
        Stage.REPAIR: 2.0,
        Stage.VALIDATION: 3.5,
    },
    "flat": {
        Stage.LOCALIZATION: 1.0,
        Stage.REPAIR: 1.0,
        Stage.VALIDATION: 1.0,
    },
}


def active_w_i_profile_name() -> str:
    """Profile name for logging; unknown/empty env -> repair_heavy (W_I default)."""
    name = os.environ.get("BF_W_PROFILE", "").strip()
    return name if name in W_I_PROFILES else "repair_heavy"


def active_w_i() -> dict[Stage, float]:
    """Return the active w_i profile selected by BF_W_PROFILE (default repair_heavy)."""
    name = os.environ.get("BF_W_PROFILE", "").strip()
    return W_I_PROFILES.get(name, W_I)

# Tier pool: Qwen family via 阿里云百炼 — 4-tier with coder models.
# T1=qwen3.5-flash (¥0.3/¥0.6), T2=qwen3-coder-flash (¥0.5/¥2),
# T3=qwen3.6-plus (¥2/¥6), T4=qwen3-coder-plus (¥4/¥12, SWE-bench 78.8%)
TIER1_BACKEND = "tier1_qwen35_flash"
TIER2_BACKEND = "tier2_qwen3_coder_flash"
TIER3_BACKEND = "tier3_qwen36_plus"
TIER4_BACKEND = "tier4_qwen3_coder_plus"
TIER5_BACKEND = "tier5_gpt55"

PROGRESS_TABLE: dict[Stage, dict[str, float]] = {
    Stage.LOCALIZATION: {
        TIER1_BACKEND: 0.30,
        TIER2_BACKEND: 0.50,
        TIER3_BACKEND: 0.62,
        TIER4_BACKEND: 0.65,  # coder-plus bit better even for LOC
        TIER5_BACKEND: 0.75,  # GPT-5.5 ceiling
    },
    Stage.REPAIR: {
        TIER1_BACKEND: 0.15,
        TIER2_BACKEND: 0.38,  # coder-flash bit better at repair
        TIER3_BACKEND: 0.45,
        TIER4_BACKEND: 0.62,  # coder-plus significantly better at repair
        TIER5_BACKEND: 0.75,  # GPT-5.5 ceiling
    },
    Stage.VALIDATION: {
        TIER1_BACKEND: 0.25,
        TIER2_BACKEND: 0.45,
        TIER3_BACKEND: 0.55,
        TIER4_BACKEND: 0.60,  # coder-plus better at validation too
        TIER5_BACKEND: 0.72,  # GPT-5.5 ceiling
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
    1: 4,   # T1→T2 after 4 non-progress steps
    2: 5,   # T2→T3 after 5 non-progress steps
    3: 5,   # T3→T4 after 5 non-progress steps (give T3 a fair chance)
    4: 5,   # T4 stop-loss after 5 non-progress steps
}

# After T4 fails to make progress, downgrade to this tier instead of stagnation.
T4_DOWNGRADE_TIER = 2

# Per-tier max consecutive turns before forced upgrade.
TIER_MAX_TURNS: dict[int, int] = {
    1: 20,
    2: 35,
    3: 30,   # T3 max 30 turns → force T4 (coder-plus is cheap, use it)
    4: 999,
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

# Qwen model IDs — coder models for T2/T4 (code-specialized).
QWEN_T1_MODEL = "qwen3.5-flash"
QWEN_T2_MODEL = "qwen3-coder-flash"
QWEN_T3_MODEL = "qwen3.6-plus"
QWEN_T4_MODEL = "qwen3-coder-plus"

# litellm model strings: openai/ prefix + custom api_base → 百炼.
TIER1_MODEL = f"openai/{QWEN_T1_MODEL}"
TIER2_MODEL = f"openai/{QWEN_T2_MODEL}"
TIER3_MODEL = f"openai/{QWEN_T3_MODEL}"
TIER4_MODEL = f"openai/{QWEN_T4_MODEL}"
TIER5_MODEL = "openai/gpt-5.5"  # aicode007 GPT-5.5 ceiling test

# Terminal model= labels for console output.
TIER1_DISPLAY = "qwen3.5-flash"
TIER2_DISPLAY = "qwen3-coder-flash"
TIER3_DISPLAY = "qwen3.6-plus"
TIER4_DISPLAY = "qwen3-coder-plus"
TIER5_DISPLAY = "gpt-5.5"

TIER_DISPLAY_BY_BACKEND: dict[str, str] = {
    TIER1_BACKEND: TIER1_DISPLAY,
    TIER2_BACKEND: TIER2_DISPLAY,
    TIER3_BACKEND: TIER3_DISPLAY,
    TIER4_BACKEND: TIER4_DISPLAY,
    TIER5_BACKEND: TIER5_DISPLAY,
}

TIER_MODEL_BY_BACKEND: dict[str, str] = {
    TIER1_BACKEND: TIER1_MODEL,
    TIER2_BACKEND: TIER2_MODEL,
    TIER3_BACKEND: TIER3_MODEL,
    TIER4_BACKEND: TIER4_MODEL,
    TIER5_BACKEND: TIER5_MODEL,
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
