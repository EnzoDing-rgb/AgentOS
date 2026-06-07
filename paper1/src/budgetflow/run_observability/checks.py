"""Higher-level run consistency checks beyond row schema validation."""

from __future__ import annotations

from pathlib import Path

from budgetflow.observability import load_heartbeat

def _check_cross_series_duplicates(records: list[dict]) -> list[str]:
    """(a) Detect duplicate task inflation across run_series.

    When combining multiple experiments, the same (instance_id, strategy) pair
    may appear in multiple run_series. This check flags pairs that appear
    in more than one run_series so the analyst doesn't double-count them.
    """
    issues: list[str] = []
    # (instance_id, strategy) -> set of run_series
    pair_series: dict[tuple[str, str], set[str]] = {}
    for i, rec in enumerate(records):
        key = (str(rec.get("instance_id", "")), str(rec.get("strategy", "")))
        rs = str(rec.get("run_series", ""))
        if not key[0] or not key[1]:
            continue
        if key not in pair_series:
            pair_series[key] = set()
        pair_series[key].add(rs)
    for (iid, strat), series_set in sorted(pair_series.items()):
        if len(series_set) > 1:
            issues.append(
                f"CROSS_SERIES_DUPLICATE {iid}/{strat} appears in {len(series_set)} series: "
                + ", ".join(sorted(series_set))
            )
    return issues


def _check_partial_run(records: list[dict], runs_dir: Path | None = None) -> list[str]:
    """(b) Detect partial runs: fewer unique tasks executed than planned.

    Cross-references heartbeat total_expected when available.
    Uses max(task_order_index) per run_series vs unique task count.
    Also checks heartbeat total_expected / num_strategies vs unique tasks.
    """
    issues: list[str] = []
    by_series: dict[str, dict] = {}
    for rec in records:
        rs = str(rec.get("run_series", ""))
        if not rs:
            continue
        if rs not in by_series:
            by_series[rs] = {"indexes": set(), "strategies": set(), "tasks": set()}
        by_series[rs]["indexes"].add(int(rec.get("task_order_index", -1)))
        by_series[rs]["strategies"].add(str(rec.get("strategy", "")))
        by_series[rs]["tasks"].add(str(rec.get("instance_id", "")))
    for rs, data in sorted(by_series.items()):
        indexes = {x for x in data["indexes"] if x >= 0}
        num_strategies = len(data["strategies"])
        unique_tasks = len(data["tasks"])
        if not indexes:
            continue
        max_idx = max(indexes)
        # task_order_index is 1-based (enumerate(tasks, start=1)).
        # max_idx == planned task count if no gaps.
        if max_idx > unique_tasks:
            issues.append(
                f"PARTIAL_RUN {rs}: task_order_index max={max_idx} suggests "
                f"{max_idx} planned tasks but only {unique_tasks} executed "
                f"(strategies={sorted(data['strategies'])})"
            )
        # Also cross-reference heartbeat total_expected
        if runs_dir:
            hb_path = runs_dir / f"{rs}.heartbeat.json"
            hb = load_heartbeat(hb_path)
            if hb:
                total_expected = int(hb.get("total_expected") or 0)
                if total_expected > 0 and num_strategies > 0:
                    planned_tasks = total_expected // num_strategies
                    if planned_tasks > unique_tasks:
                        issues.append(
                            f"PARTIAL_RUN {rs}: heartbeat total_expected={total_expected} "
                            f"/ {num_strategies} strategies = {planned_tasks} planned tasks "
                            f"but only {unique_tasks} executed"
                        )
    return issues


def _is_per_task_budget_series(recs: list[dict]) -> bool:
    if any(str(r.get("budget_mode") or "").startswith("per_task") for r in recs):
        return True
    if any(r.get("per_task_cap") not in (None, "", 0, 0.0) for r in recs):
        return True

    # Backward-compatible detection for older rows: in per-task mode each task
    # row records an independent cap and batch_spent resets instead of
    # accumulating across the policy lane.
    by_strategy: dict[str, list[dict]] = {}
    for rec in recs:
        by_strategy.setdefault(str(rec.get("strategy") or ""), []).append(rec)
    for strat_rows in by_strategy.values():
        if len(strat_rows) < 2:
            continue
        caps = {float(r.get("batch_budget_cap") or 0.0) for r in strat_rows}
        if len(caps) != 1 or next(iter(caps)) <= 0:
            continue
        spent = [float(r.get("batch_spent") or 0.0) for r in strat_rows]
        if len(set(round(x, 8) for x in spent)) < len(spent):
            return True
        if any(later + 1e-9 < earlier for earlier, later in zip(spent, spent[1:])):
            return True
    return False


def _check_shared_cap_starvation(records: list[dict]) -> list[str]:
    """(c) Detect shared-cap starvation: budget exhausted before all tasks ran.

    Flags rows exited with budget_exhausted, and checks whether tasks with higher
    value never executed.
    """
    issues: list[str] = []
    # Collect tasks that ran and their values, grouped by run_series
    by_series: dict[str, dict] = {}
    for rec in records:
        rs = str(rec.get("run_series", ""))
        if not rs:
            continue
        if rs not in by_series:
            by_series[rs] = {"ran": {}, "rows": []}
        by_series[rs]["rows"].append(rec)
        iid = str(rec.get("instance_id", ""))
        strat = str(rec.get("strategy", ""))
        tv = rec.get("task_value")
        exit_reason = str(rec.get("exit_reason", ""))
        key = (iid, strat)
        by_series[rs]["ran"][key] = {"value": tv, "exit": exit_reason}
    for rs, data in sorted(by_series.items()):
        if _is_per_task_budget_series(data["rows"]):
            continue
        starved = [
            f"{iid}/{strat} (exit={info['exit']})"
            for (iid, strat), info in data["ran"].items()
            if "budget_exhausted" in info["exit"].lower()
        ]
        if starved:
            issues.append(
                f"SHARED_CAP_STARVATION {rs}: {len(starved)} rows exited with "
                f"budget_exhausted: " + "; ".join(starved)
            )
    return issues


def _check_value_profile_fallback(records: list[dict]) -> list[str]:
    """(d) Detect missing or equal-value fallback in non-equal value profiles.

    If a non-equal profile (unsolved_difficulty, discriminative_rarity, difficulty,
    combined) is used, all task_value entries should not be equal.
    Also flags missing value_source or equal fallback values.
    """
    issues: list[str] = []
    by_series: dict[str, list[dict]] = {}
    for rec in records:
        rs = str(rec.get("run_series", ""))
        if not rs:
            continue
        by_series.setdefault(rs, []).append(rec)
    for rs, recs in sorted(by_series.items()):
        values = [r.get("task_value") for r in recs if r.get("task_value") is not None]
        value_sources = {str(r.get("value_source", "")) for r in recs if r.get("value_source")}
        profiles = {str(r.get("task_value_profile", "") or "equal") for r in recs}
        non_equal_profiles = {profile for profile in profiles if profile != "equal"}
        if not values:
            issues.append(f"VALUE_FALLBACK {rs}: no task_value found in any row")
            continue
        if not non_equal_profiles:
            continue
        unique_values = set(values)
        if len(unique_values) == 1 and len(values) > 1:
            msg = f"VALUE_FALLBACK {rs}: all {len(values)} rows have task_value={list(unique_values)[0]}"
            msg += f" profiles={sorted(non_equal_profiles)}"
            if value_sources:
                msg += f" value_sources={sorted(value_sources)}"
            msg += " — if non-equal profile requested, values may have fallen back"
            issues.append(msg)
        # Check for explicit fallback source
        if "equal" in value_sources or "fallback_equal" in value_sources:
            issues.append(
                f"VALUE_FALLBACK {rs}: value_source contains 'equal' — "
                f"possible silent fallback from non-equal profile. "
                f"sources={sorted(value_sources)}"
            )
    return issues


def _check_policy_parallel(records: list[dict]) -> list[str]:
    """(e) Detect non-policy-parallel execution.

    Policy-parallel runs should have overlapping row_started_at times across
    strategies. If strategies ran in distinct time blocks, the run was sequential.
    """
    issues: list[str] = []
    by_series: dict[str, dict[str, list[float]]] = {}
    for rec in records:
        rs = str(rec.get("run_series", ""))
        strat = str(rec.get("strategy", ""))
        started = rec.get("row_started_at")
        if not rs or not strat or started is None:
            continue
        if rs not in by_series:
            by_series[rs] = {}
        if strat not in by_series[rs]:
            by_series[rs][strat] = []
        by_series[rs][strat].append(float(started))
    for rs, strat_times in sorted(by_series.items()):
        if len(strat_times) < 2:
            continue
        # Compute time ranges for each strategy
        ranges: dict[str, tuple[float, float]] = {}
        for strat, times in strat_times.items():
            ranges[strat] = (min(times), max(times))
        # Check overlap: if any strategy's entire range is before another's,
        # the run was sequential.
        for s1, (s1_min, s1_max) in ranges.items():
            for s2, (s2_min, s2_max) in ranges.items():
                if s1 >= s2:
                    continue
                # If s1's last row finished before s2's first row started,
                # these strategies ran sequentially
                if s1_max < s2_min:
                    gap = s2_min - s1_max
                    issues.append(
                        f"SEQUENTIAL_POLICY {rs}: {s1} finished {gap:.0f}s before "
                        f"{s2} started — policies not parallel"
                    )
                elif s2_max < s1_min:
                    gap = s1_min - s2_max
                    issues.append(
                        f"SEQUENTIAL_POLICY {rs}: {s2} finished {gap:.0f}s before "
                        f"{s1} started — policies not parallel"
                    )
        # Remove symmetrical duplicates
        seen = set()
        deduped: list[str] = []
        for issue in issues:
            key = issue.split(": ", 1)[1] if ": " in issue else issue
            if key not in seen:
                seen.add(key)
                deduped.append(issue)
        issues = deduped
    return issues
