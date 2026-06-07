"""Experiment JSONL schema checks and standard field accessors."""

from __future__ import annotations

from collections import Counter

from budgetflow.observability import build_harness_trust, parse_harness_evidence

REQUIRED_FIELDS = frozenset({
    "instance_id", "strategy", "routing", "harness_resolved",
    "exit_status", "exit_reason", "total_cost", "llm_turns",
    "elapsed_s", "detail", "turn_trace_count",
    "run_series", "policy_lane", "task_order_index",
    "row_started_at", "row_finished_at",
    "harness_evidence", "observability_status",
})

OPTIONAL_BUT_DESIRED = frozenset({
    "failure_class", "forensic_summary", "backend_picks",
    "submitted_patch", "attempt_id",
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
            inst = rec.get("instance_id", "?")
            strat = rec.get("strategy", "?")
            issues.append(f"NO_TRACE row {i}: {inst} {strat} — turn_trace_count={trace_count}")
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
    """Warn when record schema can silently confuse downstream evaluation.

    These are warnings for old artifacts, but new experiment rows should be
    clean. Do not mutate historical JSONL; replay should reveal its limits.
    """
    issues: list[str] = []
    for i, rec in enumerate(records):
        inst = rec.get("instance_id", "?")
        strat = rec.get("strategy", "?")
        llm_turns = rec.get("llm_turns")
        turns = rec.get("turns")
        if llm_turns not in (None, "") and turns != llm_turns:
            issues.append(
                f"TURN_ALIAS_MISMATCH row {i}: {inst} {strat} — "
                f"turns={turns!r} llm_turns={llm_turns!r}"
            )
        harness_resolved = rec.get("harness_resolved")
        resolved = rec.get("resolved")
        if harness_resolved is not None and resolved != harness_resolved:
            issues.append(
                f"RESOLVED_ALIAS_MISMATCH row {i}: {inst} {strat} — "
                f"resolved={resolved!r} harness_resolved={harness_resolved!r}"
            )
        has_budget_cap = rec.get("batch_budget_cap") not in (None, "", 0, 0.0)
        if has_budget_cap and not rec.get("budget_mode"):
            issues.append(
                f"BUDGET_MODE_MISSING row {i}: {inst} {strat} — "
                "cannot distinguish shared-cap from per-task-cap semantics"
            )
    return issues


def _routing_memory_source(record: dict) -> str:
    """Return the standard routing-memory source, with legacy fallback."""
    source = record.get("routing_policy_memory_source")
    if source:
        return str(source)
    prior = record.get("routing_prior_summary") or {}
    if isinstance(prior, dict):
        return str(prior.get("policy_memory_source") or "")
    return ""


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
    """Use the standardized row schema first, then legacy run fields."""
    if record.get("routing_policy_memory_source"):
        return True
    if record.get("routing_learned_action") not in (None, "", "none", "default"):
        return True
    return bool(record.get("policy_memory_enabled"))


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
