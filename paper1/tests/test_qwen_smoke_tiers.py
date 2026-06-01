from __future__ import annotations

from budgetflow.run_deepseek_smoke import TIER_MODELS, _expand_tiers


def test_expand_compare_group_covers_budgetflow_qwen_pool() -> None:
    assert _expand_tiers("compare") == ["t2", "t3", "t4"]


def test_expand_t4_candidates_group_covers_qwen_candidate_pool() -> None:
    assert _expand_tiers("t4_candidates") == ["t4", "max"]


def test_expand_tiers_preserves_explicit_aliases() -> None:
    assert _expand_tiers("flash,pro,coder_plus,qwen_max") == [
        "flash",
        "pro",
        "coder_plus",
        "qwen_max",
    ]


def test_qwen_smoke_tier_aliases_exist() -> None:
    for key in ["t1", "t2", "t3", "t4", "max", "flash", "pro", "coder_plus", "qwen_max"]:
        assert key in TIER_MODELS
