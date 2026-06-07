from __future__ import annotations

import os

from .model_tiers import (
    MODEL_CATALOG,
    TIER1_BACKEND,
    TIER2_BACKEND,
    TIER3_BACKEND,
    TIER_CONFIGS,
    ModelCatalog,
    tier_display_name,
    tier_model_id,
)
from .types import Stage

# concept.md §3.3 / §3.4 cold-start defaults — sole source for Tier 1 reproduction.
W_I: dict[Stage, float] = {
    Stage.LOCALIZATION: 1.0,
    Stage.REPAIR: 3.0,
    Stage.VALIDATION: 2.5,
}

# §8.4 weight-ordering sub-ablation: swap only the w_i profile, mechanism fixed.
W_I_PROFILES: dict[str, dict[Stage, float]] = {
    "repair_heavy": dict(W_I),
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
    name = os.environ.get("BF_W_PROFILE", "").strip()
    return name if name in W_I_PROFILES else "repair_heavy"


def active_w_i() -> dict[Stage, float]:
    name = os.environ.get("BF_W_PROFILE", "").strip()
    return W_I_PROFILES.get(name, W_I)


PROGRESS_TABLE: dict[Stage, dict[str, float]] = {
    stage: {
        config.backend: config.progress_prior[stage.value]
        for config in MODEL_CATALOG.configs
        if stage.value in config.progress_prior
    }
    for stage in Stage
}

# Scale factor for upgrade thresholds:
# upgrade_threshold = delta_cost / (delta_progress * SCALE * w_i).
PROGRESS_SCALE: float = 0.3

# Per-tier routing controls. These are still policy parameters, but they are
# keyed by tier number so a provider/model swap does not touch routing code.
TIER_ESCALATION_PATIENCE: dict[int, int] = {
    config.tier: config.escalation_patience
    for config in MODEL_CATALOG.configs
    if config.escalation_patience is not None
}

TIER_MAX_TURNS: dict[int, int] = {
    config.tier: config.max_turns
    for config in MODEL_CATALOG.configs
    if config.max_turns is not None
}

# After the strongest tier stalls, fall back to this tier when available.
STRONGEST_DOWNGRADE_TIER = 2

# Once a worker has edited a gold/target file, long mid-tier repair loops are
# usually expensive noise. Give the second-cheapest tier a short runway, then
# force a stronger tier when one exists.
GOLD_EDIT_MID_TIER_REPAIR_TURN_LIMIT = 12

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
STAGNATION_NO_PROGRESS_STEPS = 12

# BFV-only Value-Triggered Escalation: high-value tasks that stall before any
# patch/gold edit get a short T3 / Strongest Model window before stop.
VALUE_TRIGGERED_ESCALATION_MIN_MULTIPLIER = 1.15
VALUE_TRIGGERED_ESCALATION_DEFAULT_WINDOW_TURNS = 3
VALUE_TRIGGERED_ESCALATION_MIN_HEADROOM_FRAC = 0.12

# PolicyMemory regret threshold: when full_vs_tight_regret exceeds this,
# budgetflow_full is auto-tightened.
POLICY_REGRET_THRESHOLD = 0.15

BUDGET_PRESSURE_INIT = 0.01
PRESSURE_MAX = 1.5
UNCAPPED_BUDGET_THRESHOLD = 1_000_000.0

# Convenience labels for banners and legacy diagnostic scripts. Core routing
# must use MODEL_CATALOG / ModelCatalog instead of assuming exactly three tiers.
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
