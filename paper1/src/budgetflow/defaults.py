from __future__ import annotations

from .types import Stage

# concept.md §3.3 / §3.4 cold-start defaults — sole source for Tier 1 reproduction.
W_I: dict[Stage, float] = {
    Stage.LOCALIZATION: 1.0,
    Stage.REPAIR: 3.0,
    Stage.VALIDATION: 2.5,
}

PROGRESS_TABLE: dict[Stage, dict[str, float]] = {
    Stage.LOCALIZATION: {"deepseek_flash": 0.30, "deepseek_pro": 0.35},
    Stage.REPAIR: {"deepseek_flash": 0.20, "deepseek_pro": 0.30},
    Stage.VALIDATION: {"deepseek_flash": 0.25, "deepseek_pro": 0.30},
}

BUDGET_PRESSURE_INIT = 0.35
PRESSURE_MAX = 1.5
UNCAPPED_BUDGET_THRESHOLD = 1_000_000.0

DEEPSEEK_FLASH_MODEL = "openai/deepseek-v4-flash"
DEEPSEEK_PRO_MODEL = "openai/deepseek-v4-pro"
DEEPSEEK_API_BASE = "https://api.deepseek.com"
