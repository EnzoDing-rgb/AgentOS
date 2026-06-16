from __future__ import annotations

from budgetflow.failure_classification import (
    _is_conservation_lockout,
    build_forensic_summary,
    build_score_status,
    build_verdict,
    classify_failure,
    compute_exit_owner,
    EXIT_OWNER_BUDGETFLOW_STOPLOSS,
    EXIT_OWNER_AGENT_HARNESS,
    EXIT_OWNER_PARSER_PROTOCOL,
    EXIT_OWNER_BUDGET_EXHAUSTED,
    EXIT_OWNER_PROVIDER_ERROR,
    EXIT_OWNER_MODEL_CRASH,
    EXIT_OWNER_AGENT_EXIT,
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

def _conservative_lockout_record(**overrides):
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
    rec = _conservative_lockout_record()
    assert _is_conservation_lockout(rec) is True


def test_conservation_lockout_classify_as_budget_fail() -> None:
    rec = _conservative_lockout_record()
    assert classify_failure(rec) == "budget_fail"


def test_conservation_lockout_verdict_axis() -> None:
    rec = _conservative_lockout_record()
    v = build_verdict(rec)
    assert v["verdict_axis"] == "budget_fail"
    assert v["failure_owner"] == "budget"
    assert v["failure_subtype"] == "conservation_lockout"


def test_conservation_lockout_not_triggered_for_bo() -> None:
    rec = _conservative_lockout_record(routing="budget_only")
    assert _is_conservation_lockout(rec) is False
    assert classify_failure(rec) == "loc_fail"


def test_conservation_lockout_not_triggered_when_budget_exhausted() -> None:
    rec = _conservative_lockout_record(
        forensic_summary={"budget": {"exhausted": True, "spent": 1.0, "available": 0.0}},
    )
    assert _is_conservation_lockout(rec) is False


def test_conservation_lockout_not_triggered_when_patch_extracted() -> None:
    rec = _conservative_lockout_record(patch_extracted=True)
    assert _is_conservation_lockout(rec) is False


def test_conservation_lockout_not_triggered_for_pass() -> None:
    rec = _conservative_lockout_record(harness_resolved=True, patch_extracted=True, agent_gold_edited=True)
    assert _is_conservation_lockout(rec) is False
    assert classify_failure(rec) == "pass"


def test_conservation_lockout_detected_for_value_aware() -> None:
    rec = _conservative_lockout_record(routing="segment_value_aware")
    assert _is_conservation_lockout(rec) is True
    assert classify_failure(rec) == "budget_fail"


def test_conservation_lockout_not_triggered_non_stagnation() -> None:
    rec = _conservative_lockout_record(exit_reason="format_error_no_tool_calls")
    assert _is_conservation_lockout(rec) is False


def test_conservation_lockout_not_triggered_after_t3_access() -> None:
    rec = _conservative_lockout_record(
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

    rec = _conservative_lockout_record(
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
        "routing": "segment_value_aware",
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
        "routing": "segment_value_aware",
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


def test_score_status_pass_requires_trusted_evidence() -> None:
    rec = {
        "harness_resolved": True,
        "patch_extracted": True,
        "patch_source": "submission",
        "submitted_patch": "/tmp/patch.diff",
        "agent_gold_edited": True,
        "agent_gold_files": ["sympy/core/basic.py"],
        "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=pass; pass_to_pass=pass",
        "turn_trace_count": 1,
    }

    score = build_score_status(rec)

    assert score["score_status"] == "pass"
    assert score["scoreable"] is True


def test_score_status_true_fail_for_clean_validation_failure() -> None:
    rec = {
        "harness_resolved": False,
        "patch_extracted": True,
        "patch_source": "submission",
        "submitted_patch": "/tmp/patch.diff",
        "agent_gold_edited": True,
        "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail; pass_to_pass=pass",
        "turn_trace_count": 3,
        "turn_traces": [{"backend_tier": 2}],
    }

    score = build_score_status(rec)

    assert score["score_status"] == "true_fail"
    assert score["scoreable"] is True
    assert score["true_fail_reason"] == "model_fail"


def test_score_status_abort_for_provider_failure() -> None:
    rec = {
        "harness_resolved": False,
        "patch_extracted": False,
        "agent_gold_edited": False,
        "exit_status": "ServiceUnavailableError",
        "exit_reason": "ServiceUnavailableError",
        "detail": "",
        "turn_trace_count": 1,
        "turn_traces": [{"error_type": "ServiceUnavailableError"}],
    }

    score = build_score_status(rec)

    assert score["score_status"] == "abort"
    assert score["scoreable"] is False
    assert score["abort_owner"] == "infra"
    assert score["abort_reason"] == "provider_or_infra_error"


def test_score_status_abort_for_protocol_failure() -> None:
    rec = {
        "harness_resolved": False,
        "patch_extracted": False,
        "agent_gold_edited": False,
        "exit_status": "FormatError",
        "exit_reason": "format_error_no_actions",
        "detail": "no model patch extracted",
        "turn_trace_count": 1,
    }

    score = build_score_status(rec)

    assert score["score_status"] == "abort"
    assert score["abort_owner"] == "protocol"
    assert score["abort_stage"] == "extraction"


def test_score_status_budget_exhaustion_with_trace_is_true_fail() -> None:
    rec = {
        "harness_resolved": False,
        "patch_extracted": True,
        "patch_source": "submission",
        "submitted_patch": "/tmp/patch.diff",
        "agent_gold_edited": True,
        "exit_status": "BudgetFlowBudgetError",
        "exit_reason": "budget_exhausted",
        "detail": "test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail; pass_to_pass=pass",
        "turn_trace_count": 4,
        "turn_traces": [{"backend_tier": 3}],
    }

    score = build_score_status(rec)

    assert score["score_status"] == "true_fail"
    assert score["true_fail_reason"] == "budget_fail"


# ── Score status: model_fail/repair not aborted by harness trust ──────────

def _model_fail_repair_nameerror_record(**overrides):
    """NameError crash after extracting patch and editing gold file.

    test_patch=ok + fail_before=fail ensures build_verdict routes to
    model_fail (not harness_fail), matching real 5×14 NameError records.
    """
    return {
        "harness_resolved": False,
        "patch_extracted": True,
        "patch_source": "submission",
        "submitted_patch": "/tmp/patch.diff",
        "agent_gold_edited": True,
        "agent_gold_files": ["sympy/core/basic.py"],
        "exit_status": "NameError",
        "exit_reason": "NameError",
        "detail": "compat=sympy/printing/latex.py; test_patch=ok; fail_before=fail; "
                  "model_patch=Checking patch sympy/core/compatibility.py...; "
                  "error: patch failed: sympy/core/compatibility.py:117",
        "turn_trace_count": 5,
        "turn_traces": [{"error_type": "NameError"}],
        **overrides,
    }


def test_nameerror_model_fail_repair_is_true_fail_not_abort() -> None:
    """NameError with model_fail axis and repair stage must be true_fail.

    Regression: harness trust blocking/incomplete must not override a clear
    model_fail at repair stage. The agent extracted a patch and edited the
    gold file before crashing — the failure is the model's, not harness's.
    """
    rec = _model_fail_repair_nameerror_record()
    verdict = build_verdict(rec)
    assert verdict["verdict_axis"] == "model_fail"
    assert verdict["failure_stage"] == "repair"
    assert verdict["failure_owner"] == "model"

    score = build_score_status(rec)
    assert score["score_status"] == "true_fail", (
        f"NameError + model_fail/repair must be true_fail, got {score['score_status']} "
        f"abort_reason={score.get('abort_reason')}"
    )
    assert score["scoreable"] is True
    assert classify_failure(rec) == "repair_fail"


def test_nameerror_model_fail_repair_in_5x14_jsonl() -> None:
    """Verify the fix against the exact 5×14 NameError records.

    These 4 records are in data/runs/compare_14x5-0.jsonl. They all have:
    - exit=NameError, patch_extracted=True, gold_edited=True
    - verdict: axis=model_fail, stage=repair
    - trust: incomplete, severity=blocking
    They should be true_fail, not abort.
    """
    rec = _model_fail_repair_nameerror_record(
        exit_status="NameError",
        exit_reason="NameError",
        turn_traces=[{"error_type": "NameError", "backend_tier": 3}],
    )
    score = build_score_status(rec)
    assert score["score_status"] == "true_fail", (
        f"Expected true_fail for 5×14 NameError record, got {score['score_status']}"
    )
    assert classify_failure(rec) == "repair_fail"


def test_format_error_text_action_no_patch_is_abort() -> None:
    """format_error_text_action with no patch extracted is protocol abort."""
    rec = {
        "harness_resolved": False,
        "patch_extracted": False,
        "agent_gold_edited": False,
        "exit_status": "FormatError",
        "exit_reason": "format_error_text_action",
        "detail": "no model patch extracted",
        "turn_trace_count": 1,
    }
    verdict = build_verdict(rec)
    assert verdict["verdict_axis"] == "protocol_fail"
    assert verdict["failure_stage"] == "extraction"

    score = build_score_status(rec)
    assert score["score_status"] == "abort"
    assert score["abort_owner"] == "protocol"
    assert classify_failure(rec) == "extract_fail"


def test_harness_fail_blocking_incomplete_is_abort() -> None:
    """Genuine harness_fail with blocking severity stays abort."""
    rec = {
        "harness_resolved": False,
        "patch_extracted": True,
        "patch_source": "submission",
        "agent_gold_edited": True,
        "agent_gold_files": ["sympy/core/basic.py"],
        "exit_status": "StagnationExit",
        "exit_reason": "stagnation_repeat_command",
        "detail": "test_patch=fail; fail_before=unknown",
        "turn_trace_count": 1,
        "turn_traces": [{}],
    }
    verdict = build_verdict(rec)
    assert verdict["verdict_axis"] == "harness_fail", (
        f"Expected harness_fail axis, got {verdict['verdict_axis']}"
    )

    score = build_score_status(rec)
    assert score["score_status"] == "abort", (
        f"harness_fail + blocking must stay abort, got {score['score_status']}"
    )
    assert score["abort_reason"] == "untrusted_harness_evidence"


def test_model_patch_apply_failure_is_scoreable_model_true_fail() -> None:
    """Patch apply failure is model/patch quality, not harness infra abort."""
    rec = {
        "harness_resolved": False,
        "patch_extracted": True,
        "patch_source": "submission",
        "submitted_patch": "/tmp/submitted.patch",
        "agent_gold_edited": False,
        "agent_gold_files": [],
        "exit_status": "StagnationExit",
        "exit_reason": "stagnation_no_progress",
        "detail": (
            "test_patch=ok; fail_before=fail; "
            "model_patch=Checking patch sympy/core/basic.py... error: while searching for: x"
        ),
        "turn_trace_count": 1,
        "turn_traces": [{}],
    }

    assert classify_failure(rec) == "repair_fail"
    verdict = build_verdict(rec)
    assert verdict["verdict_axis"] == "model_fail"
    assert verdict["failure_owner"] == "model"
    assert verdict["failure_stage"] == "repair"
    assert verdict["failure_subtype"] == "patch_apply_model_fail"

    score = build_score_status(rec)
    assert score["score_status"] == "true_fail"
    assert score["scoreable"] is True
    assert score["abort_reason"] == ""


def test_budget_exhausted_kept_as_abort_when_severity_blocking() -> None:
    """budget_exhausted with blocking harness evidence stays abort.

    The model exhausted budget before resolving — current design keeps this
    as abort rather than true_fail. Ensure no regression from the model_fail
    repair fix.
    """
    rec = _model_fail_repair_nameerror_record(
        exit_status="BudgetFlowBudgetError",
        exit_reason="budget_exhausted",
        patch_extracted=True,
        agent_gold_edited=False,
        detail="test_patch=unknown; fail_before=unknown",
    )
    verdict = build_verdict(rec)
    assert verdict["verdict_axis"] == "budget_fail"

    score = build_score_status(rec)
    # budget_exhausted with blocking severity + no gold_edit stays abort
    assert score["score_status"] == "abort", (
        f"budget_exhausted with blocking trust must stay abort, got {score['score_status']}"
    )


def test_model_fail_localization_stagnation_is_true_fail() -> None:
    """model_fail at localization stage (no patch) is true_fail, not abort.

    severity=warn for record with no patch extracted — not blocking enough
    to abort. The model failed to localize, which is a real model failure.
    """
    rec = {
        "harness_resolved": False,
        "patch_extracted": False,
        "agent_gold_edited": False,
        "exit_status": "StagnationExit",
        "exit_reason": "stagnation_no_progress",
        "routing": "segment_value_aware",
        "turn_trace_count": 1,
        "detail": "",
        "turn_traces": [{}],
    }
    verdict = build_verdict(rec)
    assert verdict["verdict_axis"] == "model_fail"
    assert verdict["failure_stage"] == "localization"

    score = build_score_status(rec)
    assert score["score_status"] == "true_fail"
    assert score["scoreable"] is True


def test_legacy_aborts_reclassify_by_owner_not_stored_status() -> None:
    """Historical abort rows are forensic input; current taxonomy owns scoring."""
    import json
    from pathlib import Path

    jsonl = Path("paper1/data/runs/compare_14x5-0.jsonl")
    if not jsonl.exists():
        import pytest
        pytest.skip("5×14 JSONL not available")

    with jsonl.open() as f:
        records = [json.loads(l) for l in f if l.strip()]

    protocol_aborts = []
    true_fails_from_abort = []
    for r in records:
        score = build_score_status(r)
        stored = r.get("score_status")
        if score["score_status"] == "abort":
            protocol_aborts.append(r)
        elif stored == "abort" and score["score_status"] == "true_fail":
            true_fails_from_abort.append(r)

    assert true_fails_from_abort
    for r in true_fails_from_abort:
        score = build_score_status(r)
        assert score["score_status"] == "true_fail"
        assert score["abort_reason"] == ""
        assert build_verdict(r)["failure_owner"] in {"model", "budget"}

    assert protocol_aborts
    for r in protocol_aborts:
        score = build_score_status(r)
        assert score["abort_owner"] in {"protocol", "harness", "infra"}


# ── Exit owner classification tests ─────────────────────────────────────

def test_exit_owner_bare_stagnation_is_agent_harness() -> None:
    """bare_t2_baseline stagnation must be agent_harness, NOT budgetflow_stoploss."""
    rec = {
        "exit_reason": "stagnation_no_progress",
        "exit_status": "StagnationExit",
        "routing": "all_tier2",
    }
    assert compute_exit_owner(rec) == EXIT_OWNER_AGENT_HARNESS


def test_exit_owner_enterprise_stagnation_is_agent_harness() -> None:
    """enterprise_router stagnation must also be agent_harness."""
    rec = {
        "exit_reason": "stagnation_repeat_command",
        "exit_status": "StagnationExit",
        "routing": "enterprise_router",
    }
    assert compute_exit_owner(rec) == EXIT_OWNER_AGENT_HARNESS


def test_exit_owner_budgetflow_stagnation_is_stoploss() -> None:
    """budgetflow_segment stagnation must be budgetflow_stoploss."""
    rec = {
        "exit_reason": "stagnation_no_progress",
        "exit_status": "StagnationExit",
        "routing": "segment_value_aware",
    }
    assert compute_exit_owner(rec) == EXIT_OWNER_BUDGETFLOW_STOPLOSS


def test_exit_owner_post_patch_verified_stable_is_stoploss() -> None:
    """post_patch_verified_stable is exclusive to BudgetFlow."""
    rec = {
        "exit_reason": "post_patch_verified_stable",
        "exit_status": "StagnationExit",
        "routing": "segment_value_aware",
    }
    assert compute_exit_owner(rec) == EXIT_OWNER_BUDGETFLOW_STOPLOSS


def test_exit_owner_rescue_timeout_is_stoploss() -> None:
    """rescue_timeout_gold_edited is exclusive to BudgetFlow."""
    rec = {
        "exit_reason": "rescue_timeout_gold_edited",
        "exit_status": "StagnationExit",
        "routing": "budgetflow_segment",
    }
    assert compute_exit_owner(rec) == EXIT_OWNER_BUDGETFLOW_STOPLOSS


def test_exit_owner_format_error_is_parser_protocol() -> None:
    """format_error_text_action must be parser_protocol."""
    rec = {
        "exit_reason": "format_error_text_action",
        "exit_status": "FormatError",
        "routing": "all_tier2",
    }
    assert compute_exit_owner(rec) == EXIT_OWNER_PARSER_PROTOCOL


def test_exit_owner_budget_exhausted() -> None:
    rec = {
        "exit_reason": "budget_exhausted",
        "exit_status": "BudgetFlowBudgetError",
        "routing": "enterprise_router",
    }
    assert compute_exit_owner(rec) == EXIT_OWNER_BUDGET_EXHAUSTED


def test_exit_owner_provider_error() -> None:
    rec = {
        "exit_reason": "ServiceUnavailableError",
        "exit_status": "ServiceUnavailableError",
        "routing": "bare_t3",
        "turn_traces": [{"error_type": "ServiceUnavailableError"}],
    }
    assert compute_exit_owner(rec) == EXIT_OWNER_PROVIDER_ERROR


def test_exit_owner_nameerror_is_model_crash() -> None:
    """NameError (model generated broken code) must be model_crash."""
    rec = {
        "exit_reason": "NameError",
        "exit_status": "NameError",
        "routing": "all_tier2",
    }
    assert compute_exit_owner(rec) == EXIT_OWNER_MODEL_CRASH


def test_exit_owner_harness_failed_is_agent_exit() -> None:
    """HarnessFailed (agent finished, tests didn't pass) must be agent_exit."""
    rec = {
        "exit_reason": "harness_failed",
        "exit_status": "HarnessFailed",
        "routing": "segment_value_aware",
    }
    assert compute_exit_owner(rec) == EXIT_OWNER_AGENT_EXIT


def test_exit_owner_explicit_field_takes_precedence() -> None:
    """If record already has exit_owner, use it."""
    rec = {
        "exit_owner": "custom_owner",
        "exit_reason": "stagnation_no_progress",
        "exit_status": "StagnationExit",
        "routing": "all_tier2",
    }
    assert compute_exit_owner(rec) == "custom_owner"


def test_exit_owner_budgetflow_same_router_stagnation_is_stoploss() -> None:
    """budgetflow_same_enterprise_router uses budgetflow routing pattern."""
    rec = {
        "exit_reason": "stagnation_no_progress",
        "exit_status": "StagnationExit",
        "routing": "budgetflow_same_router",
    }
    assert compute_exit_owner(rec) == EXIT_OWNER_BUDGETFLOW_STOPLOSS
