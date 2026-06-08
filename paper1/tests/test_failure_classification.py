from __future__ import annotations

from budgetflow.failure_classification import (
    _is_conservation_lockout,
    build_forensic_summary,
    build_verdict,
    classify_failure,
)


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


def test_host_dependency_contamination_is_infra_not_model() -> None:
    record = {
        "harness_resolved": False,
        "patch_extracted": True,
        "agent_gold_edited": True,
        "exit_status": "Submitted",
        "detail": (
            "test_patch=ok; fail_before=fail; model_patch=ok; "
            "fail_after=fail; ValueError: numpy.dtype size changed"
        ),
        "turn_trace_count": 1,
    }

    assert classify_failure(record) == "infra_fail"
    verdict = build_verdict(record)
    assert verdict["verdict_axis"] == "infra_fail"
    assert verdict["failure_owner"] == "infra"
    assert verdict["failure_subtype"] == "provider_or_parser_error"


def test_forensic_summary_provider_unavailable_axis() -> None:
    summary = build_forensic_summary(
        {
            "harness_resolved": False,
            "patch_extracted": False,
            "exit_status": "ServiceUnavailableError",
            "exit_reason": "ServiceUnavailableError",
            "turn_traces": [{"error_type": "ServiceUnavailableError"}],
        }
    )

    assert classify_failure({"exit_status": "ServiceUnavailableError"}) == "infra_fail"
    assert summary["primary_axis"] == "infra/provider"
    assert "ServiceUnavailableError" in summary["failure_chain"]


def test_billing_guard_verdict_is_infra_not_protocol() -> None:
    record = {
        "harness_resolved": False,
        "patch_extracted": False,
        "agent_gold_edited": False,
        "exit_status": "UpstreamExit",
        "exit_reason": "billing_guard backend=tier2 sample=litellm.BadRequestError: access denied",
        "detail": "no model patch extracted",
        "turn_trace_count": 1,
        "turn_traces": [{"error_type": "BudgetFlowUpstreamError"}],
    }

    assert classify_failure(record) == "infra_fail"
    verdict = build_verdict(record)
    assert verdict["verdict_axis"] == "infra_fail"
    assert verdict["failure_owner"] == "infra"
    assert verdict["failure_subtype"] == "provider_or_parser_error"


def test_format_error_verdict_is_protocol_not_infra() -> None:
    record = {
        "harness_resolved": False,
        "patch_extracted": False,
        "agent_gold_edited": False,
        "exit_status": "FormatError",
        "exit_reason": "format_error_no_tool_calls",
        "detail": "no model patch extracted",
        "turn_trace_count": 1,
    }

    assert classify_failure(record) == "extract_fail"
    verdict = build_verdict(record)
    assert verdict["verdict_axis"] == "protocol_fail"
    assert verdict["failure_owner"] == "protocol"
    assert verdict["failure_subtype"] == "extraction_protocol_fail"


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
            "backend_picks": ["tier2", "tier3"],
            "budget_spent": 12.5,
            "budget_available": 0.0,
        }
    )

    assert summary["primary_axis"] == "budget"
    assert summary["budget"]["exhausted_after_patch"] is True
    assert summary["patch"]["source"] == "worktree"
    assert summary["harness"]["fail_after"] == "fail"
    assert "budget_exhausted" in summary["failure_chain"]


# ── Phase AA: Conservation lockout tests ──────────────────────────────────────

def _bfc_lockout_record(**overrides):
    return {
        "harness_resolved": False,
        "exit_reason": "stagnation_repeat_command",
        "exit_status": "StagnationExit",
        "routing": "budgetflow_conservative",
        "patch_extracted": False,
        "agent_gold_edited": False,
        "forensic_summary": {"budget": {"exhausted": False, "spent": 0.03, "available": 0.31}},
        "turn_traces": [
            {
                "backend_tier": 2,
                "final_backend": "tier2",
                "router_reason": "bf_cons_max_tier=2",
                "router_branch": "budgetflow_conservative",
            }
        ],
        **overrides,
    }


def test_conservation_lockout_detected() -> None:
    rec = _bfc_lockout_record()
    assert _is_conservation_lockout(rec) is True


def test_conservation_lockout_classify_as_budget_fail() -> None:
    rec = _bfc_lockout_record()
    assert classify_failure(rec) == "budget_fail"


def test_conservation_lockout_verdict_axis() -> None:
    rec = _bfc_lockout_record()
    v = build_verdict(rec)
    assert v["verdict_axis"] == "budget_fail"
    assert v["failure_owner"] == "budget"
    assert v["failure_subtype"] == "conservation_lockout"


def test_conservation_lockout_not_triggered_for_bo() -> None:
    rec = _bfc_lockout_record(routing="budget_only")
    assert _is_conservation_lockout(rec) is False
    assert classify_failure(rec) == "loc_fail"


def test_conservation_lockout_not_triggered_when_budget_exhausted() -> None:
    rec = _bfc_lockout_record(
        forensic_summary={"budget": {"exhausted": True, "spent": 1.0, "available": 0.0}},
    )
    assert _is_conservation_lockout(rec) is False


def test_conservation_lockout_not_triggered_when_patch_extracted() -> None:
    rec = _bfc_lockout_record(patch_extracted=True)
    assert _is_conservation_lockout(rec) is False


def test_conservation_lockout_not_triggered_for_pass() -> None:
    rec = _bfc_lockout_record(harness_resolved=True, patch_extracted=True, agent_gold_edited=True)
    assert _is_conservation_lockout(rec) is False
    assert classify_failure(rec) == "pass"


def test_conservation_lockout_detected_for_bfv() -> None:
    rec = _bfc_lockout_record(routing="budgetflow_value_aware")
    assert _is_conservation_lockout(rec) is True
    assert classify_failure(rec) == "budget_fail"


def test_conservation_lockout_not_triggered_non_stagnation() -> None:
    rec = _bfc_lockout_record(exit_reason="format_error_no_tool_calls")
    assert _is_conservation_lockout(rec) is False


def test_conservation_lockout_not_triggered_after_t3_access() -> None:
    rec = _bfc_lockout_record(
        turn_traces=[
            {"backend_tier": 2, "final_backend": "tier2", "router_reason": "bf_cons_max_tier=2"},
            {"backend_tier": 3, "final_backend": "tier3", "router_reason": "bf_cons_escalated_t3"},
        ]
    )

    assert _is_conservation_lockout(rec) is False
    assert classify_failure(rec) == "loc_fail"
    verdict = build_verdict(rec)
    assert verdict["verdict_axis"] == "model_fail"
    assert verdict["failure_stage"] == "localization"
    assert verdict["failure_subtype"] == "loc_model_fail"


def test_conservation_lockout_uses_catalog_strongest_tier(monkeypatch) -> None:
    import budgetflow.failure_classification as fc

    class _Cfg:
        def __init__(self, tier: int) -> None:
            self.tier = tier

    class _Catalog:
        configs = (_Cfg(1), _Cfg(3), _Cfg(5))

    monkeypatch.setattr(fc, "MODEL_CATALOG", _Catalog())

    rec = _bfc_lockout_record(
        turn_traces=[
            {"backend_tier": 3, "final_backend": "tier3", "router_reason": "bf_cons_max_tier=3"},
        ]
    )

    assert _is_conservation_lockout(rec) is True

    rec["turn_traces"].append(
        {"backend_tier": 5, "final_backend": "tier5", "router_reason": "bf_cons_escalated_strongest"}
    )

    assert _is_conservation_lockout(rec) is False


def test_stagnation_without_patch_is_localization_fail_not_extract_fail() -> None:
    rec = {
        "harness_resolved": False,
        "exit_reason": "stagnation_no_progress",
        "exit_status": "StagnationExit",
        "routing": "budgetflow_value_aware",
        "patch_extracted": False,
        "agent_gold_edited": False,
        "turn_traces": [{"backend_tier": 3, "final_backend": "tier3"}],
    }

    assert classify_failure(rec) == "loc_fail"


def test_post_patch_verified_stable_is_model_validation_not_budget_or_infra() -> None:
    rec = {
        "harness_resolved": False,
        "exit_status": "StagnationExit",
        "exit_reason": "post_patch_verified_stable",
        "routing": "budgetflow_value_aware",
        "patch_extracted": True,
        "agent_gold_edited": True,
        "agent_attempted_submit": False,
        "agent_submitted": False,
        "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail; pass_to_pass=pass",
        "turn_trace_count": 5,
        "turn_traces": [{"patch_stable_steps": 4, "agent_pytest": "pass"}],
    }

    assert classify_failure(rec) == "repair_fail"
    verdict = build_verdict(rec)
    assert verdict["verdict_axis"] == "model_fail"
    assert verdict["failure_owner"] == "model"
    assert verdict["failure_stage"] == "validation"
    assert verdict["failure_subtype"] == "validation_model_fail"
