from __future__ import annotations

import os

from .model_tiers import (
    MODEL_CATALOG,
    TIER1_BACKEND,
    TIER2_BACKEND,
    TIER3_BACKEND,
    ModelCatalog,
    tier_display_name,
    tier_model_id,
)
from .types import Stage

# concept.md §3.3 / §3.4 bootstrap defaults — sole source for Tier 1 reproduction.
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


# Scale factor for upgrade thresholds:
# upgrade_threshold = delta_cost / (delta_progress * SCALE * w_i).
PROGRESS_SCALE: float = 0.3


def progress_table() -> dict[Stage, dict[str, float]]:
    """Progress priors from the currently loaded MODEL_CATALOG.

    Dynamic so that ``--model-catalog`` takes effect even when the catalog is
    loaded after import time.
    """
    return {
        stage: {
            config.backend: config.progress_prior[stage.value]
            for config in MODEL_CATALOG.configs
            if stage.value in config.progress_prior
        }
        for stage in Stage
    }


def tier_escalation_patience() -> dict[int, int]:
    """Per-tier escalation patience from the currently loaded catalog."""
    return {
        config.tier: config.escalation_patience
        for config in MODEL_CATALOG.configs
        if config.escalation_patience is not None
    }


def tier_max_turns() -> dict[int, int]:
    """Per-tier turn caps from the currently loaded catalog."""
    return {
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
GOLD_EDIT_SUBMIT_GRACE_TURNS = 2

# Adaptive routing (budgetflow_segment only): rolling task feedback + in-run recovery.
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

# Value-Triggered Escalation: high-value tasks that stall before any patch/gold
# edit get a short Strongest Model window before stop.
VALUE_TRIGGERED_ESCALATION_MIN_MULTIPLIER = 1.15
VALUE_TRIGGERED_ESCALATION_DEFAULT_WINDOW_TURNS = 3
VALUE_TRIGGERED_ESCALATION_MIN_HEADROOM_FRAC = 0.12

# Tier frontier fallback when a catalog tier omits max_turns. Normal runs use
# the reference tier's catalog max_turns, so this is a portability default, not
# a benchmark-specific tuning knob.
FRONTIER_DEFAULT_RUNWAY_TURNS = 35

# Paid mainline task cap. This is intentionally above the T2 catalog runway
# (currently 35 turns) so a routing policy can spend a short Strongest Model
# window, but far below the old exploratory 150-turn default.
PAID_MAINLINE_STEP_LIMIT = 60

# PolicyMemory regret threshold: when full_vs_baseline_regret exceeds this,
# budgetflow_segment receives stronger budget-pressure correction.
POLICY_REGRET_THRESHOLD = 0.15

BUDGET_PRESSURE_INIT = 0.01
PRESSURE_MAX = 1.5
UNCAPPED_BUDGET_THRESHOLD = 1_000_000.0

# Convenience labels for banners and legacy diagnostic scripts. Runtime routing
# must use MODEL_CATALOG / ModelCatalog instead of assuming exactly three tiers.
