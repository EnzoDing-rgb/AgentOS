from __future__ import annotations

from collections import Counter
from typing import Any

from .observability import parse_harness_evidence


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

_PROVIDER_UNAVAILABLE = {
    "ServiceUnavailableError",
    "provider_all_unavailable",
    "model_unavailable",
    "upstream_guard",
}

_BUDGET_REASONS = {
    "budget_exhausted",
    "cap_exhausted",
    "reserve_failed_budget",
}

_BUDGET_STATUSES = {
    "BudgetFlowBudgetError",
}

_HARNESS_STAGES = ("test_patch", "fail_before", "model_patch", "fail_after", "pass_to_pass")


def _is_budget_exit(status: str, reason: str) -> bool:
    status_l = status.lower()
    reason_l = reason.lower()
    return (
        status in _BUDGET_STATUSES
        or reason in _BUDGET_REASONS
        or "budget" in status_l
        or "budget" in reason_l
        or "cap" in status_l
        or "cap" in reason_l
    )


def _is_infra_exit(status: str) -> bool:
    status_l = status.lower()
    return status in _INFRA_STATUSES or "error" in status_l


def _is_provider_unavailable(status: str, reason: str, errors: set[str]) -> bool:
    values = {status, reason, *errors}
    lowered = " ".join(values).lower()
    return bool(values & _PROVIDER_UNAVAILABLE) or any(
        marker in lowered
        for marker in (
            "serviceunavailableerror",
            "service unavailable",
            "provider_all_unavailable",
            "model unavailable",
            "model_not_found",
            "model is not supported",
            "503",
        )
    )


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


def _failure_chain(record: dict[str, Any], harness: dict[str, str]) -> list[str]:
    chain: list[str] = []
    status = str(record.get("exit_status") or "")
    reason = str(record.get("exit_reason") or "")
    errors = _turn_error_types(record)

    if _is_budget_exit(status, reason):
        chain.append("budget_exhausted")
    if reason.startswith("stagnation_"):
        chain.append(reason)
    for error in sorted(errors):
        chain.append(error)
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
        if reason.startswith("stagnation_"):
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
    budget_exhausted = _is_budget_exit(status, reason)
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
            "spent": record.get("budget_spent") or record.get("task_cost") or record.get("total_cost"),
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
    if _is_budget_exit(status, reason):
        return "budget_fail"

    if _is_conservation_lockout(record):
        return "budget_fail"

    if _is_infra_exit(status):
        return "infra_fail"

    if not record.get("patch_extracted"):
        return "extract_fail"

    if not record.get("agent_gold_edited"):
        return "loc_fail"

    return "repair_fail"


def _is_conservation_lockout(record: dict[str, Any]) -> bool:
    """Detect when stagnation exit is caused by conservation factor blocking T3.

    Signals: stagnation exit + budget not exhausted + conservation strategy +
    no patch extracted. When the conservation factor (1.0 + max(0, pressure-0.3)*1.5)
    blocks T3 access, the agent stagnates at lower tiers — but the root cause
    is budget policy, not model behavior.
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
    return True


def build_verdict(record: dict[str, Any]) -> dict[str, Any]:
    """Produce per-row failure attribution fields for observability.

    Returns dict with: verdict_axis, failure_owner, failure_stage,
    evidence_complete, missing_evidence.
    """
    resolved = record.get("harness_resolved") in (True, "True", "true")
    evidence = parse_harness_evidence(str(record.get("detail") or ""))
    status = str(record.get("exit_status") or "")
    reason = str(record.get("exit_reason") or "")
    errors = _turn_error_types(record)
    patch_extracted = bool(record.get("patch_extracted"))
    gold_edited = bool(record.get("agent_gold_edited"))

    # Determine verdict axis
    if resolved:
        axis = "pass"
    elif _is_budget_exit(status, reason):
        axis = "budget_fail"
    elif _is_conservation_lockout(record):
        axis = "budget_fail"
    elif _is_provider_unavailable(status, reason, errors):
        axis = "routing_fail"
    elif not patch_extracted and (errors or "format" in status.lower() or "format" in reason.lower()):
        axis = "protocol_fail"
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
    harness = _parse_harness_detail(str(record.get("detail") or ""))
    if axis == "pass":
        stage = "none"
    elif axis == "budget_fail":
        stage = "runtime"
    elif axis == "protocol_fail":
        stage = "extraction"
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
