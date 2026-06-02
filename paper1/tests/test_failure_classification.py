from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "budgetflow" / "failure_classification.py"


def _module():
    spec = importlib.util.spec_from_file_location("failure_classification_for_test", MODULE)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def classify_failure(record: dict) -> str:
    return _module().classify_failure(record)


def build_forensic_summary(record: dict) -> dict:
    return _module().build_forensic_summary(record)


def test_classify_pass() -> None:
    assert classify_failure({"harness_resolved": True, "patch_extracted": True}) == "pass"


def test_classify_extract_fail_before_localization() -> None:
    assert classify_failure({"harness_resolved": False, "patch_extracted": False}) == "extract_fail"


def test_classify_loc_fail_when_gold_not_edited() -> None:
    assert (
        classify_failure(
            {
                "harness_resolved": False,
                "patch_extracted": True,
                "agent_gold_edited": False,
                "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail",
            }
        )
        == "loc_fail"
    )


def test_classify_repair_fail_when_gold_edited_but_tests_fail() -> None:
    assert (
        classify_failure(
            {
                "harness_resolved": False,
                "patch_extracted": True,
                "agent_gold_edited": True,
                "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail",
            }
        )
        == "repair_fail"
    )


def test_classify_infra_fail_from_provider_error() -> None:
    assert (
        classify_failure(
            {
                "harness_resolved": False,
                "patch_extracted": True,
                "agent_gold_edited": True,
                "exit_status": "BadRequestError",
            }
        )
        == "infra_fail"
    )


def test_classify_budget_fail_from_budget_exit_with_progress() -> None:
    assert (
        classify_failure(
            {
                "harness_resolved": False,
                "patch_extracted": True,
                "agent_gold_edited": True,
                "exit_reason": "budget_exhausted",
            }
        )
        == "budget_fail"
    )


def test_classify_budget_error_status_before_generic_error() -> None:
    assert (
        classify_failure(
            {
                "harness_resolved": False,
                "patch_extracted": True,
                "agent_gold_edited": True,
                "exit_status": "BudgetFlowBudgetError",
                "exit_reason": "budget_exhausted",
            }
        )
        == "budget_fail"
    )


def test_forensic_summary_budget_after_patch() -> None:
    summary = build_forensic_summary(
        {
            "harness_resolved": False,
            "patch_extracted": True,
            "patch_source": "worktree",
            "agent_gold_edited": True,
            "agent_attempted_submit": False,
            "agent_submitted": False,
            "exit_status": "BudgetFlowBudgetError",
            "exit_reason": "budget_exhausted",
            "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail",
            "backend_picks": ["tier2_qwen3_coder_flash", "tier3_gpt53_codex"],
            "budget_spent": 12.5,
            "budget_available": 0.0,
        }
    )

    assert summary["primary_axis"] == "budget"
    assert summary["budget"]["exhausted_after_patch"] is True
    assert summary["patch"]["source"] == "worktree"
    assert summary["harness"]["fail_after"] == "fail"
    assert "budget_exhausted" in summary["failure_chain"]
