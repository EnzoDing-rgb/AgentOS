from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.adapter.mini_swe_proxy import evidence_floor_tier
from budgetflow.types import Stage


def test_budgetflow_full_uses_strong_floor_for_repair_and_validation() -> None:
    assert evidence_floor_tier(strategy="budgetflow_full", stage=Stage.REPAIR, agent_phase=None) == 3
    assert evidence_floor_tier(strategy="budgetflow_full", stage=Stage.VALIDATION, agent_phase=None) == 3


def test_budgetflow_full_uses_strong_floor_for_agent_edit_phase() -> None:
    assert evidence_floor_tier(strategy="budgetflow_full", stage=Stage.LOCALIZATION, agent_phase="edit_gold") == 3
    assert evidence_floor_tier(strategy="budgetflow_full", stage=Stage.LOCALIZATION, agent_phase="test") == 3


def test_floor_does_not_change_stage_blind_or_localization() -> None:
    assert evidence_floor_tier(strategy="stage_blind", stage=Stage.REPAIR, agent_phase="edit_gold") == 1
    assert evidence_floor_tier(strategy="budgetflow_full", stage=Stage.LOCALIZATION, agent_phase="explore") == 1

