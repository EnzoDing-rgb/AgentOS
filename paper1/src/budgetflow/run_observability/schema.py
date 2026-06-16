"""Experiment JSONL schema checks and standard field accessors."""

from __future__ import annotations

from collections import Counter

from budgetflow.failure_classification import build_verdict
from budgetflow.observability import build_harness_trust, parse_harness_evidence

REQUIRED_FIELDS = frozenset({
    "instance_id", "strategy", "routing", "harness_resolved",
    "exit_status", "exit_reason", "total_cost", "llm_turns",
    "elapsed_s", "detail", "turn_trace_count",
    "prompt_tokens_total", "completion_tokens_total",
    "usage_source", "cost_mode",
    "protocol", "parser",
    "run_series", "policy_lane", "task_order_index",
    "row_started_at", "row_finished_at",
    "harness_evidence", "observability_status",
    "score_status", "scoreable",
    "harness_trust", "harness_issues", "harness_owner", "harness_severity",
})

OPTIONAL_BUT_DESIRED = frozenset({
    "failure_class", "forensic_summary", "backend_picks",
    "submitted_patch", "attempt_id",
    "frozen_plan_name", "frozen_plan_preferred_model",
    "frozen_plan_base_cap", "frozen_plan_priority",
    "abort_reason", "abort_owner", "abort_stage", "true_fail_reason",
})


def _check_duplicates(records: list[dict]) -> list[str]:
    issues: list[str] = []
    seen: set[tuple[str, str]] = set()
    for i, rec in enumerate(records):
        key = (str(rec.get("strategy", "")), str(rec.get("instance_id", "")))
        if not key[0] or not key[1]:
            continue
        if key in seen:
            issues.append(f"DUPLICATE row {i}: strategy={key[0]} instance={key[1]}")
        seen.add(key)
    return issues


def _check_pass_evidence(records: list[dict]) -> list[str]:
    issues: list[str] = []
    for i, rec in enumerate(records):
        if not rec.get("harness_resolved"):
            continue
        evidence = rec.get("harness_evidence") or {}
        if isinstance(evidence, dict):
            complete = evidence.get("evidence_complete", False)
        else:
            ev = parse_harness_evidence(str(rec.get("detail") or ""))
            complete = ev.evidence_complete
        if not complete:
            inst = rec.get("instance_id", "?")
            strat = rec.get("strategy", "?")
            detail = str(rec.get("detail", ""))[:120]
            issues.append(
                f"SUSPICIOUS_PASS row {i}: {inst} {strat} — resolved but evidence incomplete. "
                f"detail={detail}"
            )
    return issues


def _check_trace_coverage(records: list[dict]) -> list[str]:
    issues: list[str] = []
    for i, rec in enumerate(records):
        trace_count = int(rec.get("turn_trace_count") or 0)
        if trace_count <= 0:
            verdict = build_verdict(rec)
            if verdict.get("verdict_axis") == "budget_fail":
                continue
            inst = rec.get("instance_id", "?")
            strat = rec.get("strategy", "?")
            issues.append(f"NO_TRACE row {i}: {inst} {strat} — turn_trace_count={trace_count}")
            continue
        traces = rec.get("turn_traces") or []
        if not isinstance(traces, list):
            issues.append(f"BAD_TRACE row {i}: {rec.get('instance_id', '?')} {rec.get('strategy', '?')} — turn_traces is not a list")
            continue
        for j, trace in enumerate(traces):
            if not isinstance(trace, dict):
                continue
            if trace.get("response_ok") is not True:
                if trace.get("error_type") and not trace.get("provider_error_kind"):
                    issues.append(
                        f"PROVIDER_ERROR_OPAQUE row {i} trace {j}: {rec.get('instance_id', '?')} "
                        f"{rec.get('strategy', '?')} — provider error lacks provider_error_kind"
                    )
                continue
            if not trace.get("usage_source") or not trace.get("cost_mode"):
                issues.append(
                    f"COST_MODE_MISSING row {i} trace {j}: {rec.get('instance_id', '?')} "
                    f"{rec.get('strategy', '?')} — successful trace lacks usage_source/cost_mode"
                )
            if trace.get("parser_error_type"):
                if not trace.get("parser_error_message") and trace.get("parser_error_action_count") is None:
                    issues.append(
                        f"PARSER_ERROR_OPAQUE row {i} trace {j}: {rec.get('instance_id', '?')} "
                        f"{rec.get('strategy', '?')} — parser error lacks message/action count"
                    )
                continue
    return issues


def _check_missing_fields(records: list[dict]) -> list[str]:
    issues: list[str] = []
    for i, rec in enumerate(records):
        missing = [f for f in REQUIRED_FIELDS if f not in rec]
        if missing:
            inst = rec.get("instance_id", "?")
            strat = rec.get("strategy", "?")
            issues.append(f"MISSING_FIELDS row {i}: {inst} {strat} — missing={missing}")
    return issues


def _check_desired_fields(records: list[dict]) -> list[str]:
    issues: list[str] = []
    for i, rec in enumerate(records):
        missing = [f for f in OPTIONAL_BUT_DESIRED if f not in rec]
        if missing:
            inst = rec.get("instance_id", "?")
            strat = rec.get("strategy", "?")
            issues.append(f"DESIRED_FIELDS row {i}: {inst} {strat} — missing={missing}")
    return issues


def _check_observability_schema(records: list[dict]) -> list[str]:
    """Warn when current records can silently confuse downstream evaluation."""
    issues: list[str] = []
    for i, rec in enumerate(records):
        inst = rec.get("instance_id", "?")
        strat = rec.get("strategy", "?")
        for legacy in ("turns", "resolved", "task_cost"):
            if legacy in rec:
                issues.append(
                    f"LEGACY_FIELD row {i}: {inst} {strat} — "
                    f"{legacy} is not part of the current evaluation schema"
                )
        has_budget_cap = rec.get("batch_budget_cap") not in (None, "", 0, 0.0)
        if has_budget_cap and not rec.get("budget_mode"):
            issues.append(
                f"BUDGET_MODE_MISSING row {i}: {inst} {strat} — "
                "cannot distinguish shared-cap from per-task-cap semantics"
            )
        score_status = str(rec.get("score_status") or "")
        if score_status not in {"pass", "true_fail", "abort"}:
            issues.append(
                f"SCORE_STATUS_INVALID row {i}: {inst} {strat} — score_status={score_status!r}"
            )
        if score_status == "abort" and not rec.get("abort_reason"):
            issues.append(
                f"ABORT_REASON_MISSING row {i}: {inst} {strat} — abort rows must explain owner/reason"
            )
        if score_status == "pass" and not rec.get("harness_resolved"):
            issues.append(
                f"SCORE_PASS_MISMATCH row {i}: {inst} {strat} — score_status=pass but harness_resolved=false"
            )
        if score_status == "true_fail" and rec.get("harness_resolved"):
            issues.append(
                f"SCORE_FAIL_MISMATCH row {i}: {inst} {strat} — score_status=true_fail but harness_resolved=true"
            )
        patch_source = str(rec.get("patch_source") or "none")
        if patch_source not in {"submission", "none"}:
            issues.append(
                f"PATCH_SOURCE_INVALID row {i}: {inst} {strat} — "
                f"patch_source={patch_source!r}; current runs only allow 'submission' or 'none'"
            )
    return issues


def _routing_memory_source(record: dict) -> str:
    """Return the standard routing-memory source."""
    return str(record.get("routing_policy_memory_source") or "")


def _routing_prior_task_seen(record: dict) -> float:
    prior = record.get("routing_prior_summary") or {}
    if not isinstance(prior, dict):
        return 0.0
    for key in (
        "policy_memory_effective_weight",
        "repo_evidence_weight",
        "task_evidence_weight",
        "task_seen",
    ):
        try:
            value = float(prior.get(key, 0) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return 0.0


def _routing_memory_used(record: dict) -> bool:
    """Return whether current routing-memory fields show active memory use."""
    if record.get("routing_policy_memory_source"):
        return True
    return False


def _check_harness_trust(records: list[dict]) -> tuple[list[str], dict[str, int], dict[str, int], dict[str, int]]:
    """Audit harness trust across all records.

    Returns (issues, trust_counts, owner_counts, severity_counts).
    """
    issues: list[str] = []
    trust_counts: dict[str, int] = Counter()
    owner_counts: dict[str, int] = Counter()
    severity_counts: dict[str, int] = Counter()
    for i, rec in enumerate(records):
        ht = build_harness_trust(rec)
        trust = ht["harness_trust"]
        owner = ht["harness_owner"]
        sev = ht.get("severity", "")
        trust_counts[trust] += 1
        if owner != "none":
            owner_counts[owner] += 1
        if sev and sev != "none":
            severity_counts[sev] += 1
        if trust in ("suspicious", "invalid"):
            inst = rec.get("instance_id", "?")
            strat = rec.get("strategy", "?")
            issues.append(
                f"HARNESS_{trust.upper()} row {i}: {inst} {strat} "
                f"owner={owner} severity={sev} issues={ht['harness_issues']}"
            )
    return issues, dict(trust_counts), dict(owner_counts), dict(severity_counts)


def _check_elapsed_sanity(records: list[dict]) -> list[str]:
    issues: list[str] = []
    for i, rec in enumerate(records):
        elapsed = rec.get("elapsed_s")
        if elapsed is None:
            continue
        try:
            elapsed = float(elapsed)
        except (TypeError, ValueError):
            issues.append(f"BAD_ELAPSED row {i}: elapsed_s={elapsed}")
            continue
        started = rec.get("row_started_at")
        finished = rec.get("row_finished_at")
        if started and finished:
            try:
                computed = float(finished) - float(started)
                if abs(computed - elapsed) > 10:
                    issues.append(
                        f"ELAPSED_MISMATCH row {i}: elapsed_s={elapsed:.1f} "
                        f"computed={computed:.1f}"
                    )
            except (TypeError, ValueError):
                pass
    return issues
