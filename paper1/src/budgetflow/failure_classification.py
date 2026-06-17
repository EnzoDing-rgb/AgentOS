from __future__ import annotations

from collections import Counter
from typing import Any

from .harness_contamination import has_host_dependency_contamination
from .exit_reasons import (
    BUDGET_EXIT_REASONS,
    BUDGET_EXIT_STATUSES,
    is_budget_exit,
    is_fixed_tier_turn_cap_reason,
    record_is_budget_exhausted,
)
from .model_tiers import MODEL_CATALOG, parse_tier_label
from .observability import build_harness_trust, parse_harness_evidence

SCORE_PASS = "pass"
SCORE_TRUE_FAIL = "true_fail"
SCORE_ABORT = "abort"
SCOREABLE_STATUSES = frozenset({SCORE_PASS, SCORE_TRUE_FAIL})

# ── Exit owner taxonomy ────────────────────────────────────────────────────

EXIT_OWNER_BUDGETFLOW_STOPLOSS = "budgetflow_stoploss"
EXIT_OWNER_AGENT_HARNESS = "agent_harness"
EXIT_OWNER_PARSER_PROTOCOL = "parser_protocol"
EXIT_OWNER_BUDGET_EXHAUSTED = "budget_exhausted"
EXIT_OWNER_PROVIDER_ERROR = "provider_error"
EXIT_OWNER_MODEL_CRASH = "model_crash"
EXIT_OWNER_AGENT_EXIT = "agent_exit"
EXIT_OWNER_UNKNOWN = "unknown"

# Exit reasons that are exclusive to BudgetFlow mechanisms.
_BUDGETFLOW_ONLY_STAGNATION = frozenset({
    "post_patch_verified_stable",
    "post_patch_stable_no_submit",
    "rescue_timeout_gold_edited",
    "submit_timeout_after_gold_edit",
    "gold_edit_mid_tier_repair_limit",
})

_POST_PATCH_STOPLOSS_REASONS = frozenset({
    "post_patch_verified_stable",
    "post_patch_stable_no_submit",
})

# Strategies whose stagnation is attributed to agent_harness (NOT budgetflow).
_BARE_OR_ENTERPRISE_ROUTINGS = frozenset({
    "all_tier2", "bare_t3", "enterprise_router",
})

_BUDGETFLOW_FAMILY_ROUTINGS = frozenset({
    "budgetflow_conservative", "budgetflow_equal_weight",
    "budgetflow_same_router", "budgetflow_segment",
    "segment_value_aware", "stage_blind", "value_aware_task_level",
})


_INFRA_STATUSES = {
    "BadRequestError",
    "APIError",
    "RateLimitError",
    "AuthenticationError",
    "PermissionDeniedError",
    "ServiceUnavailableError",
    "UpstreamExit",
    "infra_error",
}

_PROTOCOL_STATUSES = {
    "FormatError",
}

_PROVIDER_UNAVAILABLE = {
    "ServiceUnavailableError",
    "provider_unavailable",
    "model_unavailable",
    "upstream_guard",
}

_BUDGET_REASONS = BUDGET_EXIT_REASONS
_BUDGET_STATUSES = BUDGET_EXIT_STATUSES

_HARNESS_STAGES = ("test_patch", "fail_before", "model_patch", "fail_after", "pass_to_pass")


def _is_budget_exit(status: str, reason: str) -> bool:
    return is_budget_exit(status, reason)


def _record_is_budget_exit(record: dict[str, Any]) -> bool:
    """Return True when either the row or underlying agent exhausted budget."""
    return record_is_budget_exhausted(record)


def _is_infra_exit(status: str) -> bool:
    status_l = status.lower()
    if status in _PROTOCOL_STATUSES or "format" in status_l:
        return False
    return status in _INFRA_STATUSES or "apierror" in status_l or "provider" in status_l


def _is_provider_unavailable(status: str, reason: str, errors: set[str]) -> bool:
    values = {status, reason, *errors}
    lowered = " ".join(values).lower()
    return bool(values & _PROVIDER_UNAVAILABLE) or any(
        marker in lowered
        for marker in (
            "serviceunavailableerror",
            "service unavailable",
            "provider_unavailable",
            "model unavailable",
            "model_not_found",
            "model is not supported",
            "503",
        )
    )


def _is_protocol_error(status: str, reason: str) -> bool:
    values = {status, reason}
    lowered = " ".join(values).lower()
    return status in _PROTOCOL_STATUSES or "format" in lowered


def _parse_harness_detail(detail: str) -> dict[str, str]:
    stages = {name: "unknown" for name in _HARNESS_STAGES}
    for chunk in detail.split(";"):
        if "=" not in chunk:
            continue
        key, value = chunk.strip().split("=", 1)
        if key in stages:
            stages[key] = value.strip() or "unknown"
    return stages


def _turn_error_types(record: dict[str, Any]) -> set[str]:
    errors: set[str] = set()
    traces = record.get("turn_traces") or []
    if not isinstance(traces, list):
        return errors
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        error = trace.get("error_type")
        if error:
            errors.add(str(error))
    return errors


def _agent_environment_issues(record: dict[str, Any]) -> tuple[str, ...]:
    issues = record.get("agent_environment_issues") or []
    if not isinstance(issues, list):
        return ()
    return tuple(str(issue) for issue in issues if issue)


def score_status(record: dict[str, Any]) -> str:
    status = str(record.get("score_status") or "")
    if status in (SCORE_PASS, SCORE_TRUE_FAIL, SCORE_ABORT):
        return status
    if record.get("harness_resolved") in (True, "True", "true"):
        return SCORE_PASS
    return SCORE_TRUE_FAIL


def is_score_pass(record: dict[str, Any]) -> bool:
    return score_status(record) == SCORE_PASS


def is_score_true_fail(record: dict[str, Any]) -> bool:
    return score_status(record) == SCORE_TRUE_FAIL


def is_score_abort(record: dict[str, Any]) -> bool:
    return score_status(record) == SCORE_ABORT


def is_scoreable(record: dict[str, Any]) -> bool:
    return score_status(record) in SCOREABLE_STATUSES


def compute_exit_owner(record: dict[str, Any]) -> str:
    """Infer which component owns an exit reason.

    For existing JSONL rows that lack an explicit exit_owner field, this
    reconstructs the most likely owner from strategy + exit_reason +
    exit_status.  New runs should populate exit_owner at write time so this
    fallback is only a post-hoc diagnostic.

    Taxonomy:
      budgetflow_stoploss — BudgetFlow-specific stop-loss/stagnation
      agent_harness       — bare/enterprise strategies truncated by shared
                            stagnation guard (BudgetFlowLitellmModel.check_stagnation)
      parser_protocol     — format/parser errors (e.g. format_error_text_action)
      budget_exhausted    — hard or soft budget exhausted
      provider_error      — infra/provider failures
      unknown             — cannot determine from available fields
    """
    # Explicit field takes precedence.
    explicit = record.get("exit_owner")
    if isinstance(explicit, str) and explicit:
        return explicit

    status = str(record.get("exit_status") or "")
    reason = str(record.get("exit_reason") or "")
    routing = str(record.get("routing") or "")

    # Parser / protocol errors.
    if reason.startswith("format_error_") or "format" in status.lower():
        return EXIT_OWNER_PARSER_PROTOCOL

    # Budget exhaustion.
    if _record_is_budget_exit(record):
        return EXIT_OWNER_BUDGET_EXHAUSTED

    # Provider / infra errors.
    if _is_provider_unavailable(status, reason, _turn_error_types(record)):
        return EXIT_OWNER_PROVIDER_ERROR
    if _is_infra_exit(status):
        return EXIT_OWNER_PROVIDER_ERROR

    # Model-side crashes (NameError, etc.) — generated invalid code.
    if status == "NameError":
        return EXIT_OWNER_MODEL_CRASH

    # Clean agent exits — agent finished, harness ran, task not resolved.
    if status in ("HarnessFailed", "Submitted"):
        return EXIT_OWNER_AGENT_EXIT

    # Stagnation — the key distinction.
    if (
        reason.startswith("stagnation_")
        or is_fixed_tier_turn_cap_reason(reason)
        or reason in _BUDGETFLOW_ONLY_STAGNATION
    ):
        if reason in _BUDGETFLOW_ONLY_STAGNATION:
            return EXIT_OWNER_BUDGETFLOW_STOPLOSS
        # shared stagnation guard (check_stagnation) fires for ALL strategies.
        # For bare baselines and enterprise_router, attribute to agent_harness.
        if routing in _BARE_OR_ENTERPRISE_ROUTINGS:
            return EXIT_OWNER_AGENT_HARNESS
        # For budgetflow-family routing, attribute to budgetflow_stoploss.
        if routing in _BUDGETFLOW_FAMILY_ROUTINGS:
            return EXIT_OWNER_BUDGETFLOW_STOPLOSS
        return EXIT_OWNER_AGENT_HARNESS  # conservative default for unknown routing

    return EXIT_OWNER_UNKNOWN


def build_score_status(record: dict[str, Any]) -> dict[str, Any]:
    """Classify whether a row is scoreable evidence.

    Raw harness FAIL means only "not resolved". This converts it into either a
    true strategy/model failure or an abort caused by infra/protocol/harness
    evidence gaps. Paper metrics and learning should consume score_status, not
    harness_resolved directly.
    """
    resolved = record.get("harness_resolved") in (True, "True", "true")
    verdict = build_verdict(record)
    axis = str(verdict.get("verdict_axis") or "")
    owner = str(verdict.get("failure_owner") or "")
    stage = str(verdict.get("failure_stage") or "")
    status = str(record.get("exit_status") or "")
    reason = str(record.get("exit_reason") or "")
    errors = _turn_error_types(record)
    detail = str(record.get("detail") or "")
    agent_env_issues = _agent_environment_issues(record)
    trust = build_harness_trust(record)
    trust_level = str(trust.get("harness_trust") or "")
    severity = str(trust.get("severity") or "")

    exit_owner = compute_exit_owner(record)

    if resolved:
        if (
            axis == "pass"
            and bool(verdict.get("evidence_complete"))
            and trust_level not in {"invalid", "suspicious"}
            and severity != "blocking"
        ):
            return {
                "score_status": SCORE_PASS,
                "scoreable": True,
                "abort_reason": "",
                "abort_owner": "",
                "abort_stage": "",
                "true_fail_reason": "",
                "exit_owner": exit_owner,
            }
        return {
            "score_status": SCORE_ABORT,
            "scoreable": False,
            "abort_reason": "untrusted_pass_evidence",
            "abort_owner": owner if owner != "none" else str(trust.get("harness_owner") or "harness"),
            "abort_stage": stage if stage != "none" else "harness",
            "true_fail_reason": "",
            "exit_owner": exit_owner,
        }

    abort_reason = ""
    abort_owner = owner
    abort_stage = stage
    if agent_env_issues:
        abort_reason = "agent_environment_issue"
        abort_owner = "infra"
        abort_stage = "runtime"
    elif has_host_dependency_contamination(detail):
        abort_reason = "host_dependency_contamination"
        abort_owner = "infra"
        abort_stage = "runtime"
    elif _is_provider_unavailable(status, reason, errors) or axis == "infra_fail":
        abort_reason = "provider_or_infra_error"
        abort_owner = "infra"
        abort_stage = "runtime"

    if not abort_reason:
        if exit_owner == EXIT_OWNER_BUDGETFLOW_STOPLOSS:
            return {
                "score_status": SCORE_TRUE_FAIL,
                "scoreable": True,
                "abort_reason": "",
                "abort_owner": "",
                "abort_stage": "",
                "true_fail_reason": "budgetflow_stoploss",
                "exit_owner": exit_owner,
            }
        if axis == "protocol_fail":
            abort_reason = "protocol_or_parser_error"
            abort_owner = "protocol"
            abort_stage = "extraction"
        elif axis == "harness_fail" or (
            severity == "blocking"
            and trust_level in {"invalid", "incomplete"}
            and axis != "budget_fail"
            and not (axis == "model_fail" and stage == "repair")
        ):
            abort_reason = "untrusted_harness_evidence"
            abort_owner = str(trust.get("harness_owner") or "harness")
            abort_stage = stage if stage else "harness"
        elif axis != "budget_fail" and int(record.get("turn_trace_count") or 0) <= 0:
            abort_reason = "missing_turn_trace"
            abort_owner = "infra"
            abort_stage = "runtime"

    if abort_reason:
        return {
            "score_status": SCORE_ABORT,
            "scoreable": False,
            "abort_reason": abort_reason,
            "abort_owner": abort_owner or "infra",
            "abort_stage": abort_stage or "runtime",
            "true_fail_reason": "",
            "exit_owner": exit_owner,
        }

    return {
        "score_status": SCORE_TRUE_FAIL,
        "scoreable": True,
        "abort_reason": "",
        "abort_owner": "",
        "abort_stage": "",
        "true_fail_reason": axis or classify_failure(record),
        "exit_owner": exit_owner,
    }


def _failure_chain(record: dict[str, Any], harness: dict[str, str]) -> list[str]:
    chain: list[str] = []
    status = str(record.get("exit_status") or "")
    reason = str(record.get("exit_reason") or "")
    errors = _turn_error_types(record)

    if _record_is_budget_exit(record):
        chain.append("budget_exhausted")
    if reason.startswith("stagnation_") or is_fixed_tier_turn_cap_reason(reason) or reason in {
        "post_patch_verified_stable",
        "post_patch_stable_no_submit",
        "rescue_timeout_gold_edited",
        "submit_timeout_after_gold_edit",
    }:
        chain.append(reason)
    for error in sorted(errors):
        chain.append(error)
    for issue in _agent_environment_issues(record):
        chain.append(f"agent_environment_issue:{issue}")
    if record.get("patch_extracted"):
        chain.append("patch_extracted")
        source = str(record.get("patch_source") or "unknown")
        chain.append(f"patch_source_{source}")
    else:
        chain.append("no_patch_extracted")
    if record.get("agent_gold_edited"):
        chain.append("gold_file_edited")
    else:
        chain.append("gold_file_not_edited")
    if record.get("agent_submitted"):
        chain.append("agent_submitted")
    elif record.get("agent_attempted_submit"):
        chain.append("agent_attempted_submit_without_submission")
    for stage, value in harness.items():
        if value != "unknown":
            chain.append(f"harness_{stage}_{value}")
    return chain


def _primary_axis(record: dict[str, Any], harness: dict[str, str]) -> tuple[str, str]:
    if record.get("harness_resolved"):
        return "pass", "high"

    status = str(record.get("exit_status") or "")
    reason = str(record.get("exit_reason") or "")
    errors = _turn_error_types(record)

    if _is_budget_exit(status, reason):
        return "budget", "high"
    if _is_provider_unavailable(status, reason, errors):
        return "infra/provider", "high"
    if harness.get("test_patch") == "fail" or harness.get("fail_before") == "ok":
        return "harness", "high"
    if not record.get("patch_extracted"):
        if errors or "format" in status.lower() or "format" in reason.lower():
            return "protocol", "high"
        if reason.startswith("stagnation_") or is_fixed_tier_turn_cap_reason(reason):
            return "model_behavior", "medium"
        return "protocol", "medium"
    if not record.get("agent_gold_edited"):
        return "localization", "high"
    if harness.get("model_patch") == "fail":
        return "harness", "high"
    if harness.get("fail_after") == "fail":
        return "repair_quality", "high"
    if _is_infra_exit(status):
        return "infra", "medium"
    return "repair_quality", "medium"


def build_forensic_summary(record: dict[str, Any]) -> dict[str, Any]:
    harness = _parse_harness_detail(str(record.get("detail") or ""))
    status = str(record.get("exit_status") or "")
    reason = str(record.get("exit_reason") or "")
    budget_exhausted = _record_is_budget_exit(record)
    patch_extracted = bool(record.get("patch_extracted"))
    gold_edited = bool(record.get("agent_gold_edited"))
    primary_axis, confidence = _primary_axis(record, harness)
    picks = [str(pick) for pick in record.get("backend_picks") or []]
    mix = Counter(picks)
    chain = _failure_chain(record, harness)

    missing_evidence: list[str] = []
    if not record.get("detail"):
        missing_evidence.append("harness_detail")
    if not record.get("turn_trace_count") and not record.get("turn_traces"):
        missing_evidence.append("turn_traces")

    return {
        "primary_axis": primary_axis,
        "failure_chain": chain,
        "patch": {
            "extracted": patch_extracted,
            "source": str(record.get("patch_source") or ("none" if not patch_extracted else "unknown")),
            "gold_edited": gold_edited,
            "submitted": bool(record.get("agent_submitted")),
            "attempted_submit": bool(record.get("agent_attempted_submit")),
        },
        "harness": harness,
        "budget": {
            "exhausted": budget_exhausted,
            "exhausted_after_patch": budget_exhausted and (patch_extracted or gold_edited),
            "spent": record.get("budget_spent") or record.get("total_cost"),
            "available": record.get("budget_available") or record.get("batch_available"),
        },
        "policy": {
            "backend_mix": dict(sorted(mix.items())),
            "rescue_seen": any("rescue" in item for item in chain),
            "rescue_timeout_seen": any("rescue_timeout" in item for item in chain),
        },
        "confidence": confidence,
        "missing_evidence": missing_evidence,
    }


def classify_failure(record: dict[str, Any]) -> str:
    """Coarse failure class for experiment diagnosis.

    This is intentionally record-only: no oracle, no task-specific knowledge.
    """
    if record.get("harness_resolved"):
        return "pass"

    status = str(record.get("exit_status") or "")
    reason = str(record.get("exit_reason") or "")
    if has_host_dependency_contamination(str(record.get("detail") or "")):
        return "infra_fail"

    if _agent_environment_issues(record):
        return "infra_fail"

    if reason in _POST_PATCH_STOPLOSS_REASONS:
        return "repair_fail"

    if _record_is_budget_exit(record):
        return "budget_fail"

    if _is_conservation_lockout(record):
        return "budget_fail"

    if _is_protocol_error(status, reason) and not record.get("patch_extracted"):
        return "extract_fail"

    if _is_infra_exit(status):
        return "infra_fail"

    evidence = parse_harness_evidence(str(record.get("detail") or ""))
    if record.get("patch_extracted") and evidence.model_patch_status and not evidence.model_patch_ok:
        return "repair_fail"

    if (
        not record.get("patch_extracted")
        and (reason.startswith("stagnation_") or is_fixed_tier_turn_cap_reason(reason))
    ):
        return "loc_fail"

    if not record.get("patch_extracted"):
        return "extract_fail"

    if not record.get("agent_gold_edited"):
        return "loc_fail"

    return "repair_fail"


def _is_conservation_lockout(record: dict[str, Any]) -> bool:
    """Detect when stagnation exit is caused by conservation factor blocking the strongest tier.

    Signals: stagnation exit + budget not exhausted + conservation strategy +
    no patch extracted. When the conservation factor (1.0 + max(0, pressure-0.3)*1.5)
    blocks strongest-tier access, the agent stagnates at lower tiers — but the
    root cause is budget policy, not model behavior.
    """
    reason = str(record.get("exit_reason") or "")
    if not reason.startswith("stagnation_"):
        return False
    routing = str(record.get("routing") or "")
    if "conservative" not in routing and "value_aware" not in routing:
        return False
    forensic = record.get("forensic_summary") or {}
    budget = forensic.get("budget") or {}
    if budget.get("exhausted"):
        return False
    if record.get("patch_extracted") or record.get("agent_gold_edited"):
        return False
    traces = record.get("turn_traces") or []
    if not isinstance(traces, list) or not traces:
        return False
    strongest_tier = max((cfg.tier for cfg in MODEL_CATALOG.configs), default=0)
    saw_lockout_reason = False
    saw_strongest_access = False
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        backend_tier = int(trace.get("backend_tier") or 0)
        final_tier = parse_tier_label(trace.get("final_backend") or "")
        if max(backend_tier, final_tier) >= strongest_tier > 0:
            saw_strongest_access = True
        reason_text = " ".join(
            str(trace.get(key) or "")
            for key in ("router_reason", "router_branch")
        ).lower()
        if "max_tier=" in reason_text or "conservation" in reason_text or "lockout" in reason_text:
            saw_lockout_reason = True
    if saw_strongest_access:
        return False
    if not saw_lockout_reason:
        return False
    return True


def build_verdict(record: dict[str, Any]) -> dict[str, Any]:
    """Produce per-row failure attribution fields for observability.

    Returns dict with: verdict_axis, failure_owner, failure_stage,
    evidence_complete, missing_evidence.
    """
    resolved = record.get("harness_resolved") in (True, "True", "true")
    detail = str(record.get("detail") or "")
    evidence = parse_harness_evidence(detail)
    status = str(record.get("exit_status") or "")
    reason = str(record.get("exit_reason") or "")
    errors = _turn_error_types(record)
    patch_extracted = bool(record.get("patch_extracted"))
    gold_edited = bool(record.get("agent_gold_edited"))

    # Determine verdict axis
    if resolved:
        axis = "pass"
    elif _agent_environment_issues(record):
        axis = "infra_fail"
    elif has_host_dependency_contamination(detail):
        axis = "infra_fail"
    elif _record_is_budget_exit(record):
        axis = "budget_fail"
    elif _is_conservation_lockout(record):
        axis = "budget_fail"
    elif reason in _POST_PATCH_STOPLOSS_REASONS:
        axis = "model_fail"
    elif not patch_extracted and _is_protocol_error(status, reason):
        axis = "protocol_fail"
    elif _is_infra_exit(status) or _is_provider_unavailable(status, reason, errors):
        axis = "infra_fail"
    elif (
        not patch_extracted
        and (reason.startswith("stagnation_") or is_fixed_tier_turn_cap_reason(reason))
    ):
        axis = "model_fail"
    elif not evidence.evidence_complete and not resolved:
        # Harness couldn't verify the result properly
        if not evidence.test_patch_ok or not evidence.fail_before_failed:
            axis = "harness_fail"
        else:
            axis = "model_fail"
    elif not patch_extracted:
        axis = "protocol_fail"
    elif not gold_edited:
        axis = "model_fail"
    elif evidence.model_patch_ok is False or evidence.fail_after_passed is False:
        axis = "model_fail"
    elif _is_infra_exit(status):
        axis = "infra_fail"
    else:
        axis = "model_fail"

    # Determine failure owner
    if axis == "pass":
        owner = "none"
    elif axis in ("budget_fail",):
        owner = "budget"
    elif axis in ("harness_fail",):
        owner = "harness"
    elif axis in ("protocol_fail", "routing_fail"):
        owner = "protocol"
    elif axis in ("infra_fail",):
        owner = "infra"
    else:
        owner = "model"

    # Determine failure stage
    harness = _parse_harness_detail(detail)
    if axis == "pass":
        stage = "none"
    elif axis == "budget_fail":
        stage = "runtime"
    elif axis in ("infra_fail", "routing_fail"):
        stage = "runtime"
    elif axis == "protocol_fail":
        stage = "extraction"
    elif evidence.model_patch_status and not evidence.model_patch_ok:
        stage = "repair"
    elif reason == "post_patch_stable_no_submit":
        stage = "repair"
    elif reason == "post_patch_verified_stable":
        stage = "validation"
    elif not gold_edited:
        stage = "localization"
    elif harness.get("model_patch") == "fail":
        stage = "repair"
    elif harness.get("fail_after") == "fail":
        stage = "validation"
    elif axis == "harness_fail":
        if harness.get("test_patch") == "fail":
            stage = "test_patch"
        elif harness.get("fail_before") == "ok":
            stage = "fail_before"
        else:
            stage = "harness"
    else:
        stage = "repair"

    # Missing evidence
    missing: list[str] = []
    if not record.get("detail"):
        missing.append("harness_detail")
    if not record.get("turn_trace_count") and not record.get("turn_traces"):
        missing.append("turn_traces")
    if not patch_extracted and axis != "pass":
        missing.append("patch_text")
    if not record.get("agent_gold_edited") and axis == "model_fail":
        pass  # gold_edited=False is itself the signal, not missing evidence

    subtype = classify_failure_subtype(record, axis=axis, stage=stage)

    return {
        "verdict_axis": axis,
        "failure_owner": owner,
        "failure_stage": stage,
        "failure_subtype": subtype,
        "evidence_complete": evidence.evidence_complete and bool(record.get("turn_trace_count")),
        "missing_evidence": missing,
    }


def classify_failure_subtype(
    record: dict[str, Any],
    *,
    axis: str | None = None,
    stage: str | None = None,
) -> str:
    """Fine-grained failure subtype for observability.

    Returns one of:
      pass, budget_exhausted_after_progress, budget_exhausted_no_progress,
      conservation_lockout,
      loc_model_fail, repair_model_fail, validation_model_fail,
      extraction_protocol_fail, harness_incomplete,
      provider_or_parser_error, unknown
    """
    if axis is None or stage is None:
        v = build_verdict(record)
        axis = v["verdict_axis"]
        stage = v["failure_stage"]

    if axis == "pass":
        return "pass"

    if axis == "budget_fail":
        if _is_conservation_lockout(record):
            return "conservation_lockout"
        has_progress = bool(record.get("patch_extracted")) or bool(record.get("agent_gold_edited"))
        return "budget_exhausted_after_progress" if has_progress else "budget_exhausted_no_progress"

    if axis == "model_fail":
        evidence = parse_harness_evidence(str(record.get("detail") or ""))
        if evidence.model_patch_status and not evidence.model_patch_ok:
            return "patch_apply_model_fail"
        if stage == "localization":
            return "loc_model_fail"
        elif stage == "repair":
            return "repair_model_fail"
        elif stage == "validation":
            return "validation_model_fail"
        return "repair_model_fail"

    if axis in ("protocol_fail",):
        return "extraction_protocol_fail"

    if axis in ("harness_fail",):
        return "harness_incomplete"

    if axis in ("infra_fail", "routing_fail"):
        return "provider_or_parser_error"

    return "unknown"
