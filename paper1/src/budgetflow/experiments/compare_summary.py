"""Summary and console rendering for compare runs."""

from __future__ import annotations

import json
import time
from pathlib import Path

from budgetflow.console_log import backend_tier_label, format_run_verdict, status_fail, status_pass
from budgetflow.experiments.compare_config import fmt_usd as _fmt_usd
from budgetflow.failure_classification import classify_failure
from budgetflow.model_tiers import parse_tier_label

def _print_run_done(record: dict, *, done: int, total: int, strategy: str) -> None:
    gold_file = (record.get("agent_gold_files") or ["-"])[0]
    resolved = record["harness_resolved"]
    banner = status_pass(f"PASS [{done}/{total}]") if resolved else status_fail(f"FAIL [{done}/{total}]")
    picks = record.get("backend_picks") or []
    tier_line = ""
    if picks:
        last = backend_tier_label(picks[-1])
        tier_line = f" models: last={last} mix {_format_tier_mix(_tier_ratios(picks))}"
    print(
        f"{banner} {record['instance_id']} {strategy} "
        f"turns={record.get('llm_turns')} cost={_fmt_usd(record.get('task_cost', record.get('total_cost', 0)))} "
        f"batch_left={_fmt_usd(float(record.get('batch_available') or 0))} "
        f"exit={record.get('exit_status')} elapsed={record.get('elapsed_s')}s{tier_line}",
        flush=True,
    )
    verdict = format_run_verdict(
        harness_resolved=resolved,
        patch_extracted=record.get("patch_extracted", False),
        gold_edited=record.get("agent_gold_edited", False),
        gold_file=gold_file,
        detail=str(record.get("detail", "")),
    )
    print(f"  {verdict}", flush=True)


def _tier_ratios(picks: list[str]) -> dict[int, float]:
    counts: dict[int, int] = {}
    for pick in picks:
        tier = parse_tier_label(pick)
        if tier > 0:
            counts[tier] = counts.get(tier, 0) + 1
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {tier: count / total for tier, count in sorted(counts.items())}


def _average_tier_mix(mixes: list[dict[int, float]]) -> dict[int, float]:
    totals: dict[int, float] = {}
    count = 0
    for mix in mixes:
        if not mix:
            continue
        count += 1
        for tier, ratio in mix.items():
            totals[tier] = totals.get(tier, 0.0) + ratio
    if count <= 0:
        return {}
    return {tier: ratio / count for tier, ratio in sorted(totals.items())}


def _format_tier_mix(mix: dict[int, float]) -> str:
    if not mix:
        return "-"
    return " ".join(f"T{tier}={ratio * 100:.0f}%" for tier, ratio in sorted(mix.items()))


def _append_summary(lines: list[str], record: dict, *, index: int, total: int) -> None:
    status = "PASS" if record["harness_resolved"] else "FAIL"
    cap = record.get("batch_budget_cap")
    cap_s = _fmt_usd(cap)
    task_cost = float(record.get("task_cost") or record.get("total_cost") or 0.0)
    picks = record.get("backend_picks") or []
    tier_mix = _format_tier_mix(_tier_ratios(picks))
    lines.append(
        f"[{index}/{total}] DONE strategy={record['strategy']} task={record['instance_id']} {status} "
        f"exit={record.get('exit_status')} reason={record.get('exit_reason')} turns={record.get('llm_turns')} "
        f"class={record.get('failure_class', classify_failure(record))} "
        f"axis={(record.get('forensic_summary') or {}).get('primary_axis', '-')} "
        f"task_cost={_fmt_usd(task_cost)} batch_cap={cap_s} batch_avail={_fmt_usd(record.get('batch_available'))} "
        f"batch_spent={_fmt_usd(record.get('batch_spent'))} tiers={tier_mix} elapsed={record.get('elapsed_s')}s"
    )
    if record.get("backend_picks"):
        lines.append(f"  picks={record['backend_picks']}")
    if record.get("violations"):
        lines.append(f"  violations={record['violations']}")
    lines.append(f"  detail: {str(record.get('detail', ''))[:400]}")
    lines.append(json.dumps({k: v for k, v in record.items() if k != "detail"}, ensure_ascii=False))
    lines.append("")


def _format_strategy_totals(
    *,
    strategy_names: list[str],
    resolved_by_strategy: dict[str, list[bool]],
    task_cost_by_strategy: dict[str, list[float]],
    batch_spent_by_strategy: dict[str, float],
    turns_by_strategy: dict[str, list[int]],
    tier_mix_by_strategy: dict[str, list[dict[int, float]]],
    failure_by_strategy: dict[str, dict[str, int]],
    batch_caps: dict[str, float | None],
    budget_modes: dict[str, str] | None = None,
) -> list[str]:
    has_per_task = any(mode in {"per_task_cap", "dynamic_task_caps"} for mode in (budget_modes or {}).values())
    cap_label = "planned_cap" if has_per_task else "batch_cap"
    mode_label = "per-task cap" if has_per_task else "shared pool"
    lines = [f"=== BATCH RESOLVED + COST BY STRATEGY (governor units, {mode_label}) ==="]
    header = (
        f"{'strategy':<28} {'resolved':>8} {'batch_spent':>11} {cap_label:>10} "
        f"{'avg_task':>9} {'avg_turns':>10} {'tiers':>24}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for key in strategy_names:
        flags = resolved_by_strategy.get(key, [])
        costs = task_cost_by_strategy.get(key, [])
        turns = turns_by_strategy.get(key, [])
        failures = failure_by_strategy.get(key, {})
        resolved_n = sum(1 for f in flags if f)
        batch_spent = batch_spent_by_strategy.get(key, 0.0)
        cap = batch_caps.get(key)
        if (budget_modes or {}).get(key) == "per_task_cap" and cap is not None:
            cap = cap * max(len(flags), 1)
        cap_s = _fmt_usd(cap)
        cap_flag = ""
        if cap is not None and batch_spent > cap + 0.01:
            cap_flag = " OVER_CAP"
        avg_cost = sum(costs) / len(costs) if costs else 0.0
        avg_turns = sum(turns) / len(turns) if turns else 0.0
        tier_mix = _average_tier_mix(tier_mix_by_strategy.get(key, []))
        tier_s = _format_tier_mix({tier: ratio for tier, ratio in tier_mix.items() if ratio > 0})
        lines.append(
            f"{key:<28} {resolved_n}/{len(flags):<7} {_fmt_usd(batch_spent):>11} {cap_s:>10}{cap_flag} "
            f"{_fmt_usd(avg_cost):>9} {avg_turns:10.1f} {tier_s:>24}"
        )
        if failures:
            fail_s = ", ".join(f"{name}={count}" for name, count in sorted(failures.items()))
            lines.append(f"{'':<28} failure_class: {fail_s}")
    return lines


def _format_live_snapshot(
    *,
    strategy_names: list[str],
    resolved_by_strategy: dict[str, list[bool]],
    task_cost_by_strategy: dict[str, list[float]],
    turns_by_strategy: dict[str, list[int]],
    tier_mix_by_strategy: dict[str, list[dict[int, float]]],
    batch_spent_by_strategy: dict[str, float],
    batch_caps: dict[str, float | None],
    budget_modes: dict[str, str] | None = None,
    runs_done: int,
    total_runs: int,
    tasks_per_strategy: int,
    started: float,
    out_path: Path,
    global_line: str | None = None,
    failure_by_strategy: dict[str, dict[str, int]] | None = None,
    resolved_value_by_strategy: dict[str, list[float]] | None = None,
    task_value_by_strategy: dict[str, list[float]] | None = None,
    value_profile: str = "equal",
) -> list[str]:
    """Top-of-file dashboard: pass/fail + cost summary in one table."""
    total_pass = sum(sum(1 for flag in flags if flag) for flags in resolved_by_strategy.values())
    total_fail = runs_done - total_pass
    running = max(0, total_runs - runs_done)
    elapsed = time.time() - started
    lines = [
        f"=== RUN STATUS done={runs_done}/{total_runs} running={running} pass={total_pass} fail={total_fail} elapsed={elapsed:.0f}s ===",
    ]
    if global_line:
        lines.append(global_line)
    lines.append(
        f"{'strategy':<28} {'done':>4} {'plan':>4} {'PASS':>5} {'FAIL':>5} {'rate':>6} "
        f"{'avg_cost':>8} {'avg_turn':>7} {'tiers':>24} "
        f"{'batch_spent':>11} "
        f"{'planned_cap' if any(mode in {'per_task_cap', 'dynamic_task_caps'} for mode in (budget_modes or {}).values()) else 'batch_cap':>10}"
    )
    lines.append("-" * 110)
    for name in strategy_names:
        flags = resolved_by_strategy.get(name, [])
        costs = task_cost_by_strategy.get(name, [])
        turns = turns_by_strategy.get(name, [])
        failures = (failure_by_strategy or {}).get(name, {})
        done_n = len(flags)
        pass_n = sum(1 for flag in flags if flag)
        fail_n = done_n - pass_n
        rate = f"{100*pass_n/done_n:.0f}%" if done_n else "-"
        avg_cost = sum(costs) / len(costs) if costs else 0.0
        avg_turns = sum(turns) / len(turns) if turns else 0.0
        tier_mix = _average_tier_mix(tier_mix_by_strategy.get(name, []))
        tier_s = _format_tier_mix({tier: ratio for tier, ratio in tier_mix.items() if ratio > 0})
        batch_spent = batch_spent_by_strategy.get(name, 0.0)
        cap = batch_caps.get(name)
        if (budget_modes or {}).get(name) == "per_task_cap" and cap is not None:
            cap = cap * max(done_n, 1)
        cap_s = _fmt_usd(cap)
        lines.append(
            f"{name:<28} {done_n:>4} {tasks_per_strategy:>4} {pass_n:>5} {fail_n:>5} {rate:>6} "
            f"{_fmt_usd(avg_cost):>8} {avg_turns:>7.1f} {tier_s:>24} "
            f"{_fmt_usd(batch_spent):>11} {cap_s:>10}"
        )
        if failures:
            fail_s = ", ".join(f"{k}={v}" for k, v in sorted(failures.items()))
            lines.append(f"{'':<28} outcomes: {fail_s}")
    lines.append(f"jsonl={out_path}")
    # ── Value observability summary ────────────────────────────────────
    if resolved_value_by_strategy and task_value_by_strategy:
        lines.append("")
        lines.append("=== VALUE SUMMARY ===")
        lines.append(
            f"{'strategy':<28} {'resolved':>8} {'cost':>8} {'res_value':>9} "
            f"{'Yield':>7} {'Yield/$':>9} {'v_profile':>12}"
        )
        lines.append("-" * 92)
        for name in strategy_names:
            rv_list = resolved_value_by_strategy.get(name, [])
            tv_list = task_value_by_strategy.get(name, [])
            resolved_val = sum(rv_list)
            total_val = sum(tv_list)
            total_cost = sum(task_cost_by_strategy.get(name, []))
            yield_score = resolved_val / total_val if total_val > 0 else 0.0
            yield_per_dollar = resolved_val / total_cost if total_cost > 0 else 0.0
            lines.append(
                f"{name:<28} {sum(1 for r in resolved_by_strategy.get(name, []) if r):>8} "
                f"{_fmt_usd(total_cost):>8} {resolved_val:>9.2f} "
                f"{yield_score:>7.2f} {yield_per_dollar:>9.2f} {value_profile:>12}"
            )
        lines.append("")
    lines.append("")
    lines.append("=== EVENT LOG (newest at bottom) ===")
    lines.append("")
    return lines


def _write_summary_file(
    path: Path,
    *,
    summary_lines: list[str],
    strategy_names: list[str],
    resolved_by_strategy: dict[str, list[bool]],
    task_cost_by_strategy: dict[str, list[float]],
    batch_spent_by_strategy: dict[str, float],
    turns_by_strategy: dict[str, list[int]],
    tier_mix_by_strategy: dict[str, list[dict[int, float]]],
    failure_by_strategy: dict[str, dict[str, int]],
    batch_caps: dict[str, float | None],
    budget_modes: dict[str, str] | None,
    started: float,
    out_path: Path,
    runs_done: int,
    total_runs: int,
    tasks_per_strategy: int,
    global_line: str | None = None,
    resolved_value_by_strategy: dict[str, list[float]] | None = None,
    task_value_by_strategy: dict[str, list[float]] | None = None,
    value_profile: str = "equal",
) -> None:
    live = _format_live_snapshot(
        strategy_names=strategy_names,
        resolved_by_strategy=resolved_by_strategy,
        task_cost_by_strategy=task_cost_by_strategy,
        turns_by_strategy=turns_by_strategy,
        tier_mix_by_strategy=tier_mix_by_strategy,
        failure_by_strategy=failure_by_strategy,
        batch_spent_by_strategy=batch_spent_by_strategy,
        batch_caps=batch_caps,
        budget_modes=budget_modes,
        runs_done=runs_done,
        total_runs=total_runs,
        tasks_per_strategy=tasks_per_strategy,
        started=started,
        out_path=out_path,
        global_line=global_line,
        resolved_value_by_strategy=resolved_value_by_strategy,
        task_value_by_strategy=task_value_by_strategy,
        value_profile=value_profile,
    )
    lines = live + list(summary_lines)
    path.write_text("\n".join(lines) + "\n")
