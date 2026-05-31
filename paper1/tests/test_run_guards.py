from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from budgetflow.run_guards import CompareRunGuards, GuardAction, _is_pipeline_failure, _looks_upstream  # noqa: E402


def _rec(*, resolved=False, patch=False, reason="", status=""):
    return {
        "strategy": "all_flash_tight",
        "harness_resolved": resolved,
        "patch_extracted": patch,
        "exit_reason": reason,
        "exit_status": status,
    }


def test_pipeline_failure_detection() -> None:
    assert _is_pipeline_failure(_rec(patch=False, reason="stagnation_no_progress", status="StagnationExit"))
    assert not _is_pipeline_failure(_rec(resolved=True, patch=True, reason="submitted"))


def test_global_guard_triggers() -> None:
    g = CompareRunGuards(global_min_samples=5, global_window=10, policy_consecutive_fail=99)
    action = GuardAction()
    strategies = ["s1", "s2", "s3", "s4", "s5"]
    for name in strategies:
        r = _rec(patch=False, reason="stagnation_no_progress", status="StagnationExit")
        r["strategy"] = name
        action = g.record_task(r)
    assert action.halt_all
    assert g.is_aborted()


def test_global_guard_not_blocked_by_patches_without_resolve() -> None:
    g = CompareRunGuards(global_min_samples=5, global_window=10, policy_consecutive_fail=99)
    action = GuardAction()
    for i in range(5):
        r = _rec(resolved=False, patch=True, reason="submitted", status="Submitted")
        r["strategy"] = f"s{i}"
        action = g.record_task(r)
    assert action.halt_all
    assert g.is_aborted()


def test_policy_guard_halts_strategy_only() -> None:
    g = CompareRunGuards(policy_consecutive_fail=3, policy_pipeline_fail_min=2)
    for _ in range(3):
        action = g.record_task(_rec(patch=False, reason="stagnation_no_progress", status="StagnationExit"))
    assert action.halt_strategy == "all_flash_tight"
    assert not action.halt_all
    assert g.is_strategy_halted("all_flash_tight")


def test_upstream_pattern() -> None:
    assert _looks_upstream("The gpt-5.3-codex-spark model is not supported when using Codex with a ChatGPT account")
    g = CompareRunGuards(upstream_consecutive=3)
    for _ in range(3):
        action = g.record_upstream_error("503 Service temporarily unavailable", backend="tier1_spark")
    assert action.halt_all
