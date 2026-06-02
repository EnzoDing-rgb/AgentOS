from __future__ import annotations

import os
from dataclasses import dataclass

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

@dataclass(frozen=True)
class TierConfig:
    tier: int
    backend: str
    model: str
    provider: str
    api_base: str
    api_key_env: str
    display: str
    text_mode: bool = False


# 阿里云百炼 (DashScope) OpenAI-compatible endpoint.
DASHSCOPE_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
AICODE007_API_BASE = "https://api.aicode007.com/v1"

# BudgetFlow uses stable tier identities; provider/model details live here.
TIER1_BACKEND = "tier1"
TIER2_BACKEND = "tier2"
TIER3_BACKEND = "tier3"

QWEN_CODER_FLASH_MODEL = "qwen3-coder-flash"
QWEN_CODER_PLUS_MODEL = "qwen3-coder-plus"
GPT54_MODEL = "openai/gpt-5.4"

TIER_CONFIGS: dict[str, TierConfig] = {
    TIER1_BACKEND: TierConfig(
        tier=1,
        backend=TIER1_BACKEND,
        model=f"openai/{QWEN_CODER_FLASH_MODEL}",
        provider="dashscope",
        api_base=DASHSCOPE_API_BASE,
        api_key_env="DASHSCOPE_API_KEY",
        display="qwen3-coder-flash",
    ),
    TIER2_BACKEND: TierConfig(
        tier=2,
        backend=TIER2_BACKEND,
        model=f"openai/{QWEN_CODER_PLUS_MODEL}",
        provider="dashscope",
        api_base=DASHSCOPE_API_BASE,
        api_key_env="DASHSCOPE_API_KEY",
        display="qwen3-coder-plus",
    ),
    TIER3_BACKEND: TierConfig(
        tier=3,
        backend=TIER3_BACKEND,
        model=GPT54_MODEL,
        provider="aicode007",
        api_base=AICODE007_API_BASE,
        api_key_env="AICODE007_API_KEY",
        display="GPT-5.4",
        text_mode=True,
    ),
}

PROGRESS_TABLE: dict[Stage, dict[str, float]] = {
    Stage.LOCALIZATION: {
        TIER1_BACKEND: 0.50,
        TIER2_BACKEND: 0.65,
        TIER3_BACKEND: 0.68,
    },
    Stage.REPAIR: {
        TIER1_BACKEND: 0.38,
        TIER2_BACKEND: 0.62,
        TIER3_BACKEND: 0.68,
    },
    Stage.VALIDATION: {
        TIER1_BACKEND: 0.45,
        TIER2_BACKEND: 0.60,
        TIER3_BACKEND: 0.66,
    },
}

# Scale factor converting progress deltas (0-1 probabilities) to cost-comparable units.
# Lower = more conservative about upgrading to expensive models.
PROGRESS_SCALE: float = 18.0

# Per-tier escalation patience: cheaper tiers get less patience before upgrading.
# Core BudgetFlow mechanism: "try cheap, escalate on failure within this task."
# Resets when a step makes progress (bash_has_progress returns True).
TIER_ESCALATION_PATIENCE: dict[int, int] = {
    1: 4,
    2: 5,
    3: 5,
}

# After the strongest tier fails to make progress, downgrade instead of stagnation.
STRONGEST_DOWNGRADE_TIER = 2

# Per-tier max consecutive turns before forced upgrade.
TIER_MAX_TURNS: dict[int, int] = {
    1: 20,
    2: 35,
    3: 999,
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

TIER1_MODEL = TIER_CONFIGS[TIER1_BACKEND].model
TIER2_MODEL = TIER_CONFIGS[TIER2_BACKEND].model
TIER3_MODEL = TIER_CONFIGS[TIER3_BACKEND].model

TIER1_DISPLAY = TIER_CONFIGS[TIER1_BACKEND].display
TIER2_DISPLAY = TIER_CONFIGS[TIER2_BACKEND].display
TIER3_DISPLAY = TIER_CONFIGS[TIER3_BACKEND].display

TIER_DISPLAY_BY_BACKEND: dict[str, str] = {
    backend: config.display for backend, config in TIER_CONFIGS.items()
}

TIER_MODEL_BY_BACKEND: dict[str, str] = {
    backend: config.model for backend, config in TIER_CONFIGS.items()
}

# Back-compat aliases for scripts that reference old provider names.
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
