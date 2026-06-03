"""Compare N tasks × strategies: shared batch budget per policy.

Each policy runs its task list serially on one BudgetGovernor (shared pool).
Different policies may run in parallel (--jobs) using git worktrees for repo isolation.

Frozen caps: pass --read-frozen-caps to load data/frozen_caps.json (from run_pilot).
  Do not recompute loose/tight batch budgets during compare. See protocol_caps.py.

Usage (from paper1/):
  # fast smoke (default 3 tasks)
  PYTHONPATH=src:../external/mini-swe-agent/src python -u -m budgetflow.run_mini_swe_compare --preset 3x5 --jobs 5
  # full 5-task compare
  PYTHONPATH=src:../external/mini-swe-agent/src python -u -m budgetflow.run_mini_swe_compare --preset 5x5 --jobs 5

Outputs:
  data/runs/compare_3x5.jsonl  (or compare_5x5.jsonl)
  data/runs/compare_3x5.summary.log
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
MINI_SWE_SRC = REPO_ROOT.parent / "external" / "mini-swe-agent" / "src"
for path in (str(SRC), str(MINI_SWE_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from collections.abc import Callable  # noqa: E402

from budgetflow.adapter.runner import run_mini_swe_task  # noqa: E402
from budgetflow.compare_checkpoint import (  # noqa: E402
    CompareCheckpointStore,
    GlobalRunProgress,
    StrategyScoreboard,
    checkpoint_path_for,
)
from budgetflow.auto_budget import AutoBudgetEstimator, AutoBudgetMemory, BudgetEstimate  # noqa: E402
from budgetflow.console_log import backend_tier_label, dim, format_run_verdict, status_fail, status_pass, tag  # noqa: E402
from budgetflow.deepseek_backend import load_env_file  # noqa: E402
from budgetflow.failure_classification import build_forensic_summary, classify_failure  # noqa: E402
from budgetflow.governor import BudgetGovernor, GovernorConfig  # noqa: E402
from budgetflow.defaults import (  # noqa: E402
    BUDGET_PRESSURE_INIT,
    PRESSURE_MAX,
    TIER1_BACKEND,
    TIER2_BACKEND,
    TIER3_BACKEND,
    active_w_i_profile_name,
)
from budgetflow.heartbeat import run_with_heartbeat  # noqa: E402
from budgetflow.ledger import WorkflowLedgerStore  # noqa: E402
from budgetflow.lite_tasks import load_compare_easy_tasks, load_compare_medium_tasks, load_swebench_lite_tasks  # noqa: E402
from budgetflow.protocol_caps import read_protocol_caps  # noqa: E402
from budgetflow.provider_signature import check_required_signatures  # noqa: E402
from budgetflow.adaptive_routing import AdaptiveRoutingRegistry  # noqa: E402
from budgetflow.run_guards import CompareRunGuards, set_active_guard  # noqa: E402
from budgetflow.run_series import default_series_base, resolve_compare_stem  # noqa: E402
from budgetflow.run_trace import TraceConsoleLevel  # noqa: E402

RUNS_DIR = REPO_ROOT / "data" / "runs"
UNCAPPED_BUDGET = 1_000_000.0


def _fmt_usd(value: float | None) -> str:
    """Adaptive USD formatting for real-dollar costs (post price calibration).

    Values are now in the $0.01–$10 range, so fixed ``.1f`` destroys
    observability on sub-dollar task costs and caps.
    """
    if value is None:
        return "uncapped"
    if value == 0:
        return "0"
    if value < 0.01:
        return f"{value:.6f}"
    if value < 1.0:
        return f"{value:.4f}"
    return f"{value:.2f}"


@dataclass(frozen=True)
class CompareStrategy:
    name: str
    routing: str
    budget_tier: str | None  # None = uncapped (all_pro)


DEFAULT_STRATEGIES: tuple[CompareStrategy, ...] = (
    CompareStrategy("all_t1_tight", "all_flash", "tight"),
    CompareStrategy("all_t1_loose", "all_flash", "loose"),
    CompareStrategy("budget_only_tight", "budget_only", "tight"),
    CompareStrategy("stage_blind_tight", "stage_blind", "tight"),
    CompareStrategy("budgetflow_full_tight", "budgetflow_full", "tight"),
    CompareStrategy("budgetflow_equal_weight_tight", "budgetflow_equal_weight", "tight"),
    CompareStrategy("budget_only_loose", "budget_only", "loose"),
    CompareStrategy("stage_blind_loose", "stage_blind", "loose"),
    CompareStrategy("budgetflow_full_loose", "budgetflow_full", "loose"),
    CompareStrategy("budgetflow_equal_weight_loose", "budgetflow_equal_weight", "loose"),
    CompareStrategy("all_pro", "all_pro", None),
)

DIAGNOSTIC_STRATEGIES: tuple[CompareStrategy, ...] = (
    CompareStrategy("all_t3", "all_t3", None),
)

_STRATEGY_ALIASES = {
    # Backward-compatible — old spark names map to new T1 names.
    "all_spark_tight": "all_t1_tight",
    "all_spark_loose": "all_t1_loose",
    "all_flash_tight": "all_t1_tight",
    "all_flash_loose": "all_t1_loose",
    "all_gpt53": "all_t3",
    "all_gpt54": "all_t3",
    "budgetflow_auto_v2_tight": "budgetflow_equal_weight_tight",
    "budgetflow_auto_v2_loose": "budgetflow_equal_weight_loose",
}


def _normalize_strategy(name: str) -> str:
    """Resolve legacy strategy names to current canonical names."""
    return _STRATEGY_ALIASES.get(name, name)


def _strategy_catalog() -> tuple[CompareStrategy, ...]:
    return DEFAULT_STRATEGIES + DIAGNOSTIC_STRATEGIES


def _required_backends_for_strategies(strategies: tuple[CompareStrategy, ...]) -> list[str]:
    required: set[str] = set()
    for cfg in strategies:
        if cfg.routing == "all_flash":
            required.add(TIER1_BACKEND)
        elif cfg.routing in {"all_tier2"}:
            required.add(TIER2_BACKEND)
        elif cfg.routing in {"all_pro", "all_t3"}:
            required.add(TIER3_BACKEND)
        else:
            required.update({TIER1_BACKEND, TIER2_BACKEND, TIER3_BACKEND})
    return [b for b in (TIER1_BACKEND, TIER2_BACKEND, TIER3_BACKEND) if b in required]


def _w_i_profile_for_record(routing: str) -> str:
    """JSONL field: stage_blind forces w_i=1 at query time regardless of BF_W_PROFILE."""
    if routing == "stage_blind":
        return "flat_forced"
    if routing in {"budgetflow_equal_weight", "budgetflow_auto_v2"}:
        return "equal_weight"
    return active_w_i_profile_name()


def _batch_budget_cap(cfg: CompareStrategy, budget_caps: dict[str, float]) -> float:
    if cfg.budget_tier is None:
        return UNCAPPED_BUDGET
    return budget_caps[cfg.budget_tier]


def _task_difficulty_key(task) -> tuple[int, int, int, str]:
    """Lower = easier (heuristic)."""
    return (
        len(task.patch.splitlines()),
        len(task.fail_to_pass),
        len(task.pass_to_pass),
        str(task.instance_id),
    )


def _order_tasks_easy_first(tasks: list, *, task_set: str) -> list:
    if task_set != "medium":
        return list(tasks)
    return sorted(tasks, key=_task_difficulty_key)


def _task_descriptor(task) -> str:
    return (
        f"{task.instance_id}"
        f"(patch={len(task.patch.splitlines())},"
        f"f2p={len(task.fail_to_pass)},"
        f"p2p={len(task.pass_to_pass)})"
    )


def _workspace_key(cfg: CompareStrategy, instance_id: str) -> str:
    safe = cfg.name.replace("/", "_")
    return f"{safe}_{instance_id}"


def _truncate_turn_traces(
    traces: list[dict] | None, max_turns: int, max_chars: int
) -> list[dict] | None:
    """Truncate turn traces to max_turns entries and bash_digest to max_chars."""
    if traces is None:
        return None
    trimmed = traces[-max_turns:] if len(traces) > max_turns else traces
    for t in trimmed:
        digest = t.get("bash_digest")
        if isinstance(digest, str) and len(digest) > max_chars:
            t["bash_digest"] = digest[:max_chars]
    return trimmed


def _run_one(
    task,
    *,
    cfg: CompareStrategy,
    batch_budget_cap: float,
    governor: BudgetGovernor,
    ledger: WorkflowLedgerStore,
    task_index: int,
    step_limit: int,
    trace_console: TraceConsoleLevel = "quiet",
    progress_box: dict[str, str] | None = None,
    budget_pressure: float | None = None,
    pressure_max: float | None = None,
    adaptive_registry: AdaptiveRoutingRegistry | None = None,
    enable_turn_trace: bool = False,
    trace_max_turns: int = 200,
    trace_truncate_chars: int = 120,
    budget_estimate: BudgetEstimate | None = None,
) -> dict:
    started = time.time()
    workspace_key = _workspace_key(cfg, task.instance_id)
    adaptive = None
    if adaptive_registry is not None:
        adaptive = adaptive_registry.for_strategy(cfg.name, cfg.routing)
    if adaptive is not None:
        adaptive.reset_task_runtime()
    result = run_mini_swe_task(
        task,
        strategy=cfg.routing,
        strategy_label=cfg.name,
        step_limit=step_limit,
        trace_console=trace_console,
        progress_box=progress_box,
        agent_heartbeat=False,
        governor=governor,
        ledger=ledger,
        workspace_key=workspace_key,
        budget_pressure=budget_pressure,
        pressure_max=pressure_max,
        adaptive=adaptive,
        enable_turn_trace=enable_turn_trace,
    )
    batch_snapshot = governor.budget_snapshot()
    record = {
        "instance_id": result.instance_id,
        "strategy": cfg.name,
        "routing": cfg.routing,
        "w_i_profile": _w_i_profile_for_record(cfg.routing),
        "budget_tier": cfg.budget_tier or "uncapped",
        "batch_budget_cap": None if cfg.budget_tier is None else batch_budget_cap,
        "batch_spent": batch_snapshot.get("spent_budget"),
        "batch_available": batch_snapshot.get("available_budget"),
        "batch_snapshot": batch_snapshot,
        "task_cost": result.total_cost,
        "budget_spent": result.total_cost,
        "budget_available": batch_snapshot.get("available_budget"),
        "budget_snapshot": batch_snapshot,
        "task_index_in_batch": task_index,
        "workspace_key": workspace_key,
        "harness_resolved": result.harness_resolved,
        "patch_extracted": bool(result.patch_text),
        "patch_source": result.patch_source,
        "submitted_patch": result.submitted_patch_path,
        "exit_status": result.exit_status,
        "exit_reason": result.exit_reason,
        "total_cost": result.total_cost,
        "backend_picks": list(result.backend_picks),
        "llm_turns": result.llm_turns,
        "violations": list(result.violations),
        "detail": result.harness_detail,
        "agent_gold_edited": result.agent_gold_edited,
        "agent_gold_files": list(result.agent_gold_files),
        "agent_attempted_submit": result.agent_attempted_submit,
        "agent_submitted": result.agent_submitted,
        "prompt_tokens_total": result.prompt_tokens_total,
        "completion_tokens_total": result.completion_tokens_total,
        "elapsed_s": round(time.time() - started, 1),
        "agent_summary": {
            "gold_edited": result.agent_gold_edited,
            "gold_files": list(result.agent_gold_files),
            "attempted_submit": result.agent_attempted_submit,
            "submitted": result.agent_submitted,
        },
        "turn_trace_count": result.turn_trace_count,
        "turn_traces": _truncate_turn_traces(result.turn_traces, trace_max_turns, trace_truncate_chars)
        if enable_turn_trace and result.turn_traces else None,
    }
    record["failure_class"] = classify_failure(record)
    record["forensic_summary"] = build_forensic_summary(record)
    # Auto-budget metadata.
    if budget_estimate is not None:
        record["auto_budget_enabled"] = True
        record["estimated_task_cap"] = budget_estimate.cap
        record["estimated_task_cost"] = budget_estimate.estimated_cost
        record["budget_prior_source"] = budget_estimate.source
        record["budget_prior_confidence"] = budget_estimate.confidence
        record["budget_estimator_version"] = "v1"
        record["budget_memory_used"] = budget_estimate.source.startswith("memory_")
        record["budget_memory_neighbors"] = budget_estimate.memory_neighbors
        record["auto_budget_features"] = budget_estimate.features
    return record


def _print_run_done(record: dict, *, done: int, total: int, strategy: str) -> None:
    gold_file = (record.get("agent_gold_files") or ["-"])[0]
    resolved = record["harness_resolved"]
    banner = status_pass(f"PASS [{done}/{total}]") if resolved else status_fail(f"FAIL [{done}/{total}]")
    picks = record.get("backend_picks") or []
    tier_line = ""
    if picks:
        t1 = _tier_ratio(picks, 1) * 100
        t2 = _tier_ratio(picks, 2) * 100
        t3 = _tier_ratio(picks, 3) * 100
        last = backend_tier_label(picks[-1])
        tier_line = f" models: last={last} mix T1={t1:.0f}% T2={t2:.0f}% T3={t3:.0f}%"
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


def _spark_ratio(picks: list[str]) -> float:
    return _tier_ratio(picks, 1)


def _tier_ratio(picks: list[str], tier: int) -> float:
    if not picks:
        return 0.0
    needle = f"tier{tier}"
    return sum(1 for p in picks if p.lower() == needle.lower()) / len(picks)


def _append_summary(lines: list[str], record: dict, *, index: int, total: int) -> None:
    status = "PASS" if record["harness_resolved"] else "FAIL"
    cap = record.get("batch_budget_cap")
    cap_s = _fmt_usd(cap)
    task_cost = float(record.get("task_cost") or record.get("total_cost") or 0.0)
    picks = record.get("backend_picks") or []
    spark_pct = _spark_ratio(picks) * 100.0
    flash_pct = _tier_ratio(picks, 2) * 100.0
    pro_pct = _tier_ratio(picks, 3) * 100.0
    lines.append(
        f"[{index}/{total}] DONE strategy={record['strategy']} task={record['instance_id']} {status} "
        f"exit={record.get('exit_status')} reason={record.get('exit_reason')} turns={record.get('llm_turns')} "
        f"class={record.get('failure_class', classify_failure(record))} "
        f"axis={(record.get('forensic_summary') or {}).get('primary_axis', '-')} "
        f"task_cost={_fmt_usd(task_cost)} batch_cap={cap_s} batch_avail={_fmt_usd(record.get('batch_available'))} "
        f"batch_spent={_fmt_usd(record.get('batch_spent'))} T1={spark_pct:.0f}% T2={flash_pct:.0f}% "
        f"T3={pro_pct:.0f}% elapsed={record.get('elapsed_s')}s"
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
    spark_by_strategy: dict[str, list[float]],
    flash_by_strategy: dict[str, list[float]],
    pro_by_strategy: dict[str, list[float]],
    failure_by_strategy: dict[str, dict[str, int]],
    batch_caps: dict[str, float | None],
) -> list[str]:
    lines = ["=== BATCH RESOLVED + COST BY STRATEGY (governor units, shared pool) ==="]
    header = (
        f"{'strategy':<28} {'resolved':>8} {'batch_spent':>11} {'batch_cap':>10} "
        f"{'avg_task':>9} {'avg_turns':>10} {'T1':>5} {'T2':>5} {'T3':>5}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for key in strategy_names:
        flags = resolved_by_strategy.get(key, [])
        costs = task_cost_by_strategy.get(key, [])
        turns = turns_by_strategy.get(key, [])
        spark = spark_by_strategy.get(key, [])
        flash = flash_by_strategy.get(key, [])
        pro = pro_by_strategy.get(key, [])
        failures = failure_by_strategy.get(key, {})
        resolved_n = sum(1 for f in flags if f)
        batch_spent = batch_spent_by_strategy.get(key, 0.0)
        cap = batch_caps.get(key)
        cap_s = _fmt_usd(cap)
        cap_flag = ""
        if cap is not None and batch_spent > cap + 0.01:
            cap_flag = " OVER_CAP"
        avg_cost = sum(costs) / len(costs) if costs else 0.0
        avg_turns = sum(turns) / len(turns) if turns else 0.0
        avg_spark = sum(spark) / len(spark) if spark else 0.0
        avg_flash = sum(flash) / len(flash) if flash else 0.0
        avg_pro = sum(pro) / len(pro) if pro else 0.0
        lines.append(
            f"{key:<28} {resolved_n}/{len(flags):<7} {_fmt_usd(batch_spent):>11} {cap_s:>10}{cap_flag} "
            f"{_fmt_usd(avg_cost):>9} {avg_turns:10.1f} {avg_spark * 100:4.0f}% "
            f"{avg_flash * 100:4.0f}% {avg_pro * 100:4.0f}%"
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
    spark_by_strategy: dict[str, list[float]],
    flash_by_strategy: dict[str, list[float]],
    pro_by_strategy: dict[str, list[float]],
    batch_spent_by_strategy: dict[str, float],
    batch_caps: dict[str, float | None],
    runs_done: int,
    total_runs: int,
    tasks_per_strategy: int,
    started: float,
    out_path: Path,
    global_line: str | None = None,
    failure_by_strategy: dict[str, dict[str, int]] | None = None,
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
        f"{'avg_cost':>8} {'avg_turn':>7} {'T1':>5} {'T2':>5} {'T3':>5} "
        f"{'batch_spent':>11} {'batch_cap':>10}"
    )
    lines.append("-" * 110)
    for name in strategy_names:
        flags = resolved_by_strategy.get(name, [])
        costs = task_cost_by_strategy.get(name, [])
        turns = turns_by_strategy.get(name, [])
        spark = spark_by_strategy.get(name, [])
        flash = flash_by_strategy.get(name, [])
        pro = pro_by_strategy.get(name, [])
        failures = (failure_by_strategy or {}).get(name, {})
        done_n = len(flags)
        pass_n = sum(1 for flag in flags if flag)
        fail_n = done_n - pass_n
        rate = f"{100*pass_n/done_n:.0f}%" if done_n else "-"
        avg_cost = sum(costs) / len(costs) if costs else 0.0
        avg_turns = sum(turns) / len(turns) if turns else 0.0
        avg_spark = sum(spark) / len(spark) if spark else 0.0
        avg_flash = sum(flash) / len(flash) if flash else 0.0
        avg_pro = sum(pro) / len(pro) if pro else 0.0
        batch_spent = batch_spent_by_strategy.get(name, 0.0)
        cap = batch_caps.get(name)
        cap_s = _fmt_usd(cap)
        lines.append(
            f"{name:<28} {done_n:>4} {tasks_per_strategy:>4} {pass_n:>5} {fail_n:>5} {rate:>6} "
            f"{_fmt_usd(avg_cost):>8} {avg_turns:>7.1f} {avg_spark*100:>4.0f}% "
            f"{avg_flash*100:>4.0f}% {avg_pro*100:>4.0f}% "
            f"{_fmt_usd(batch_spent):>11} {cap_s:>10}"
        )
        if failures:
            fail_s = ", ".join(f"{k}={v}" for k, v in sorted(failures.items()))
            lines.append(f"{'':<28} failures: {fail_s}")
    lines.append(f"jsonl={out_path}")
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
    spark_by_strategy: dict[str, list[float]],
    flash_by_strategy: dict[str, list[float]],
    pro_by_strategy: dict[str, list[float]],
    failure_by_strategy: dict[str, dict[str, int]],
    batch_caps: dict[str, float | None],
    started: float,
    out_path: Path,
    runs_done: int,
    total_runs: int,
    tasks_per_strategy: int,
    global_line: str | None = None,
) -> None:
    live = _format_live_snapshot(
        strategy_names=strategy_names,
        resolved_by_strategy=resolved_by_strategy,
        task_cost_by_strategy=task_cost_by_strategy,
        turns_by_strategy=turns_by_strategy,
        spark_by_strategy=spark_by_strategy,
        flash_by_strategy=flash_by_strategy,
        pro_by_strategy=pro_by_strategy,
        failure_by_strategy=failure_by_strategy,
        batch_spent_by_strategy=batch_spent_by_strategy,
        batch_caps=batch_caps,
        runs_done=runs_done,
        total_runs=total_runs,
        tasks_per_strategy=tasks_per_strategy,
        started=started,
        out_path=out_path,
        global_line=global_line,
    )
    lines = live + list(summary_lines)
    path.write_text("\n".join(lines) + "\n")


def _governor_avail(batch_records: list[dict]) -> float:
    if not batch_records:
        return 0.0
    return float(batch_records[-1].get("batch_available") or 0.0)


def _run_strategy_batch(
    cfg: CompareStrategy,
    tasks: list,
    *,
    batch_budget_cap: float,
    per_task_cap: float | None = None,
    soft_budget: float | None = None,
    max_overrun: float = 0.0,
    step_limit: int,
    trace_console: TraceConsoleLevel,
    heartbeat: float,
    global_progress: GlobalRunProgress,
    scoreboard: StrategyScoreboard | None,
    print_lock: threading.Lock | None,
    budget_pressure: float | None = None,
    pressure_max: float | None = None,
    initial_spent: float = 0.0,
    checkpoint: CompareCheckpointStore | None = None,
    on_task_complete: Callable[[dict], None] | None = None,
    run_guards: CompareRunGuards | None = None,
    adaptive_registry: AdaptiveRoutingRegistry | None = None,
    enable_turn_trace: bool = False,
    trace_max_turns: int = 200,
    trace_truncate_chars: int = 120,
    task_caps: dict[str, float] | None = None,
    budget_estimates: dict[str, BudgetEstimate] | None = None,
) -> tuple[list[dict], float]:
    def _log(msg: str) -> None:
        if print_lock:
            with print_lock:
                print(msg, flush=True)
        else:
            print(msg, flush=True)

    use_per_task = cfg.budget_tier is not None and (
        (per_task_cap is not None and per_task_cap > 0) or (task_caps is not None)
    )
    ledger = WorkflowLedgerStore()
    governor: BudgetGovernor | None = None
    if not use_per_task:
        governor = BudgetGovernor(
            GovernorConfig(
                total_budget=batch_budget_cap,
                default_max_output_tokens=4096,
                soft_budget=soft_budget,
                max_overrun=max_overrun if soft_budget is not None else 0.0,
            ),
            ledger,
        )
        if initial_spent > 0:
            governor.state.spent_budget = initial_spent
            governor.state.available_budget = max(0.0, governor.state.total_budget - initial_spent)

    if use_per_task:
        if task_caps is not None:
            cap_label = "auto_budget_per_task"
        else:
            cap_label = f"per_task_cap={_fmt_usd(per_task_cap)}" if per_task_cap else "per_task"
        if max_overrun > 0:
            cap_label += f"+overrun={_fmt_usd(max_overrun)}"
    else:
        cap_label = f"shared_cap={_fmt_usd(batch_budget_cap)}"
        if soft_budget is not None:
            cap_label += f" soft={_fmt_usd(soft_budget)}+overrun={_fmt_usd(max_overrun)}"
    _log(
        f"{tag('batch', bold=False)} strategy={cfg.name} tasks={len(tasks)} "
        f"{cap_label} spent_resume={_fmt_usd(initial_spent)} mode=serial_tasks"
    )

    records: list[dict] = []
    for task_index, task in enumerate(tasks, start=1):
        if run_guards is not None and run_guards.is_strategy_halted(cfg.name):
            _log(f"{tag('guard', bold=False)} skip strategy={cfg.name} task={task.instance_id} (policy halted)")
            continue
        if run_guards is not None and run_guards.is_aborted():
            _log(f"{tag('guard', bold=False)} skip strategy={cfg.name} (global halt: {run_guards.abort_reason()})")
            break

        global_progress.start_task()
        if checkpoint is not None:
            cap_for_ckpt = per_task_cap if use_per_task and per_task_cap else batch_budget_cap
            checkpoint.mark_in_flight(cfg.name, task.instance_id, cap_for_ckpt)
        banner = global_progress.format_banner(scoreboard)
        _log(
            f"\n======== {banner} ========\n"
            f"{tag('start', bold=False)} task={task.instance_id} strategy={cfg.name}"
        )

        status_box: dict[str, str] = {
            "phase": "prep",
            "status": f"strategy={cfg.name} task={task.instance_id} prep",
        }
        label = f"{cfg.name} {task.instance_id}"

        def _status() -> str:
            base = status_box.get("status", f"strategy={cfg.name} phase={status_box['phase']}")
            return f"{global_progress.format_global(scoreboard)} | {base}"

        def _execute() -> dict:
            status_box["phase"] = "agent"
            task_governor = governor
            task_ledger = ledger
            effective_batch_cap = batch_budget_cap
            # Resolve per-task cap: task_caps dict (auto-budget) takes precedence.
            # Only budget strategies get per-task caps; all_pro stays uncapped.
            task_cap: float | None = None
            if cfg.budget_tier is not None:
                if task_caps is not None:
                    task_cap = task_caps.get(task.instance_id)
                elif per_task_cap is not None and per_task_cap > 0:
                    task_cap = per_task_cap
            if task_cap is not None:
                task_ledger = WorkflowLedgerStore()
                task_governor = BudgetGovernor(
                    GovernorConfig(
                        total_budget=task_cap,
                        default_max_output_tokens=4096,
                        soft_budget=task_cap if max_overrun > 0 else None,
                        max_overrun=max_overrun,
                    ),
                    task_ledger,
                )
                effective_batch_cap = task_governor.state.total_budget
            return _run_one(
                task,
                cfg=cfg,
                batch_budget_cap=effective_batch_cap,
                governor=task_governor,
                ledger=task_ledger,
                task_index=task_index,
                step_limit=step_limit,
                trace_console=trace_console,
                progress_box=status_box,
                budget_pressure=budget_pressure,
                pressure_max=pressure_max,
                adaptive_registry=adaptive_registry,
                enable_turn_trace=enable_turn_trace,
                trace_max_turns=trace_max_turns,
                trace_truncate_chars=trace_truncate_chars,
                budget_estimate=budget_estimates.get(task.instance_id) if budget_estimates else None,
            )

        try:
            if heartbeat > 0:
                record = run_with_heartbeat(label, _execute, interval_s=heartbeat, status_fn=_status)
            else:
                record = _execute()
        finally:
            done_n = global_progress.finish_task()

        if print_lock:
            with print_lock:
                _print_run_done(record, done=done_n, total=global_progress.total, strategy=cfg.name)
        else:
            _print_run_done(record, done=done_n, total=global_progress.total, strategy=cfg.name)
        records.append(record)
        if checkpoint is not None:
            task_spent = float(record.get("task_cost") or record.get("total_cost") or 0)
            checkpoint.mark_task_done(
                cfg.name,
                task.instance_id,
                batch_spent=task_spent if use_per_task else float(governor.state.spent_budget),
                batch_cap=per_task_cap if use_per_task else batch_budget_cap,
            )
        if on_task_complete is not None:
            on_task_complete(record)
        if adaptive_registry is not None:
            adaptive_registry.record_task(cfg.name, cfg.routing, record)

        if run_guards is not None:
            action = run_guards.record_task(record)
            run_guards.log_action(action)
            if action.halt_all or action.halt_strategy:
                break

    if use_per_task:
        batch_spent_total = sum(float(r.get("task_cost") or r.get("total_cost") or 0) for r in records)
    else:
        assert governor is not None
        batch_spent_total = governor.state.spent_budget
    return records, batch_spent_total


@dataclass
class _CompareState:
    summary_lines: list[str]
    resolved_by_strategy: dict[str, list[bool]]
    task_cost_by_strategy: dict[str, list[float]]
    batch_spent_by_strategy: dict[str, float]
    turns_by_strategy: dict[str, list[int]]
    spark_by_strategy: dict[str, list[float]]
    flash_by_strategy: dict[str, list[float]]
    pro_by_strategy: dict[str, list[float]]
    failure_by_strategy: dict[str, dict[str, int]]
    runs_done: int = 0


def _rebuild_state_from_jsonl(path: Path, header_lines: list[str]) -> _CompareState:
    state = _CompareState(
        summary_lines=list(header_lines),
        resolved_by_strategy={},
        task_cost_by_strategy={},
        batch_spent_by_strategy={},
        turns_by_strategy={},
        spark_by_strategy={},
        flash_by_strategy={},
        pro_by_strategy={},
        failure_by_strategy={},
    )
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = _normalize_strategy(record.get("strategy") or "")
        if not name:
            continue
        # Skip known garbage:欠费 BadRequestError records with no real work done
        if record.get("exit_status") == "BadRequestError" and record.get("total_cost", 1) == 0:
            continue
        state.runs_done += 1
        state.resolved_by_strategy.setdefault(name, []).append(bool(record.get("harness_resolved")))
        state.task_cost_by_strategy.setdefault(name, []).append(float(record.get("task_cost") or 0.0))
        state.turns_by_strategy.setdefault(name, []).append(int(record.get("llm_turns") or 0))
        picks = record.get("backend_picks") or []
        state.spark_by_strategy.setdefault(name, []).append(_spark_ratio(picks))
        state.flash_by_strategy.setdefault(name, []).append(_tier_ratio(picks, 2))
        state.pro_by_strategy.setdefault(name, []).append(_tier_ratio(picks, 3))
        failure_class = str(record.get("failure_class") or classify_failure(record))
        failures = state.failure_by_strategy.setdefault(name, {})
        failures[failure_class] = failures.get(failure_class, 0) + 1
        state.batch_spent_by_strategy[name] = float(record.get("batch_spent") or 0.0)
    return state


def _write_budget_memory(memory: AutoBudgetMemory, record: dict) -> None:
    """Build a memory record from a run record and write it to the learning memory."""
    forensic = record.get("forensic_summary") or {}
    mem = AutoBudgetMemory.build_record(
        instance_id=str(record.get("instance_id", "")),
        repo=str(record.get("instance_id", "")).rsplit("__", 1)[0].replace("__", "/"),
        strategy=str(record.get("strategy", "")),
        routing=str(record.get("routing", "")),
        resolved=bool(record.get("harness_resolved")),
        harness_resolved=bool(record.get("harness_resolved")),
        failure_class=str(record.get("failure_class") or ""),
        forensic_primary_axis=str(forensic.get("primary_axis") or record.get("failure_class") or ""),
        total_cost=float(record.get("task_cost") or 0.0),
        estimated_task_cap=record.get("estimated_task_cap"),
        estimated_task_cost=record.get("estimated_task_cost"),
        patch_extracted=bool(record.get("patch_extracted")),
        agent_gold_edited=bool(record.get("agent_gold_edited")),
        llm_turns=int(record.get("llm_turns") or 0),
        patch_lines=int((record.get("auto_budget_features") or {}).get("patch_lines", 0)),
        f2p_count=int((record.get("auto_budget_features") or {}).get("f2p_count", 0)),
        p2p_count=int((record.get("auto_budget_features") or {}).get("p2p_count", 0)),
        problem_length=len(str(record.get("problem_statement") or "")),
        gold_file_count=len(record.get("agent_gold_files") or []),
        run_series=str(record.get("run_series", "")),
        run_id=str(record.get("run_id", "")),
        dominant_tier=str(record.get("dominant_tier") or ""),
        exit_status=str(record.get("exit_status") or ""),
        detail=str(record.get("detail") or ""),
    )
    memory.write_record(mem)


def _persist_task_record(
    state: _CompareState,
    record: dict,
    *,
    handle,
    io_lock: threading.Lock,
    total_runs: int,
    tasks_per_strategy: int,
    global_progress: GlobalRunProgress,
    scoreboard: StrategyScoreboard | None,
    summary_path: Path,
    strategy_names: list[str],
    batch_caps: dict[str, float | None],
    started: float,
    out_path: Path,
    auto_budget_memory: AutoBudgetMemory | None = None,
    no_auto_budget_learn: bool = False,
) -> None:
    with io_lock:
        # Write auto-budget memory record (before JSONL so memory is updated first).
        if auto_budget_memory is not None and not no_auto_budget_learn and record.get("auto_budget_enabled"):
            _write_budget_memory(auto_budget_memory, record)
            record["budget_learning_update_written"] = True
        elif auto_budget_memory is not None and not no_auto_budget_learn:
            record["budget_learning_update_written"] = False

        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        state.runs_done += 1
        _, done, _ = global_progress.snapshot()
        _append_summary(state.summary_lines, record, index=done, total=total_runs)
        name = record["strategy"]
        state.resolved_by_strategy.setdefault(name, []).append(record["harness_resolved"])
        state.task_cost_by_strategy.setdefault(name, []).append(float(record.get("task_cost") or 0.0))
        state.turns_by_strategy.setdefault(name, []).append(int(record.get("llm_turns") or 0))
        picks = record.get("backend_picks") or []
        state.spark_by_strategy.setdefault(name, []).append(_spark_ratio(picks))
        state.flash_by_strategy.setdefault(name, []).append(_tier_ratio(picks, 2))
        state.pro_by_strategy.setdefault(name, []).append(_tier_ratio(picks, 3))
        failure_class = str(record.get("failure_class") or classify_failure(record))
        failures = state.failure_by_strategy.setdefault(name, {})
        failures[failure_class] = failures.get(failure_class, 0) + 1
        state.batch_spent_by_strategy[name] = float(record.get("batch_spent") or 0.0)
        if scoreboard is not None:
            scoreboard.record(name, resolved=bool(record.get("harness_resolved")))
        _write_summary_file(
            summary_path,
            summary_lines=state.summary_lines,
            strategy_names=strategy_names,
            resolved_by_strategy=state.resolved_by_strategy,
            task_cost_by_strategy=state.task_cost_by_strategy,
            batch_spent_by_strategy=state.batch_spent_by_strategy,
            turns_by_strategy=state.turns_by_strategy,
            spark_by_strategy=state.spark_by_strategy,
            flash_by_strategy=state.flash_by_strategy,
            pro_by_strategy=state.pro_by_strategy,
            failure_by_strategy=state.failure_by_strategy,
            batch_caps=batch_caps,
            started=started,
            out_path=out_path,
            runs_done=state.runs_done,
            total_runs=total_runs,
            tasks_per_strategy=tasks_per_strategy,
            global_line=global_progress.format_global(scoreboard),
        )


def _completed_keys(jsonl_path: Path, *, skip_bad: bool = False) -> set[tuple[str, str]]:
    if not jsonl_path.is_file():
        return set()
    done: set[tuple[str, str]] = set()
    bad_exits = frozenset({"BadRequestError"})
    for line in jsonl_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        # When resuming, don't count billing-error tasks as done — re-run them.
        if skip_bad and record.get("exit_status") in bad_exits:
            continue
        # Also skip records with 0 cost and 1 turn (API reject before any work).
        if skip_bad and record.get("total_cost", 1) == 0 and record.get("llm_turns", 0) <= 1:
            continue
        strategy = _normalize_strategy(record.get("strategy") or "")
        task = record.get("instance_id")
        if strategy and task:
            done.add((strategy, task))
    return done


def _ingest_batch_footer(
    state: _CompareState,
    cfg: CompareStrategy,
    batch_records: list[dict],
    batch_spent: float,
    batch_cap: float,
    *,
    strategy_names: list[str],
    batch_caps: dict[str, float | None],
    summary_path: Path,
    started: float,
    out_path: Path,
    total_runs: int,
    tasks_per_strategy: int,
    io_lock: threading.Lock,
    global_progress: GlobalRunProgress,
) -> None:
    if not batch_records:
        return
    with io_lock:
        state.summary_lines.append(f"=== BATCH START strategy={cfg.name} shared_cap={_fmt_usd(batch_cap)} ===")
        state.batch_spent_by_strategy[cfg.name] = batch_spent
        state.summary_lines.append(
            f"=== BATCH END strategy={cfg.name} resolved="
            f"{sum(1 for r in batch_records if r['harness_resolved'])}/{len(batch_records)} "
            f"batch_spent={_fmt_usd(batch_spent)} batch_avail={_fmt_usd(_governor_avail(batch_records))} ==="
        )
        state.summary_lines.append("")
        _write_summary_file(
            summary_path,
            summary_lines=state.summary_lines,
            strategy_names=strategy_names,
            resolved_by_strategy=state.resolved_by_strategy,
            task_cost_by_strategy=state.task_cost_by_strategy,
            batch_spent_by_strategy=state.batch_spent_by_strategy,
            turns_by_strategy=state.turns_by_strategy,
            spark_by_strategy=state.spark_by_strategy,
            flash_by_strategy=state.flash_by_strategy,
            pro_by_strategy=state.pro_by_strategy,
            failure_by_strategy=state.failure_by_strategy,
            batch_caps=batch_caps,
            started=started,
            out_path=out_path,
            runs_done=state.runs_done,
            total_runs=total_runs,
            tasks_per_strategy=tasks_per_strategy,
            global_line=global_progress.format_global(),
        )


PRESET_TASKS = {"3x3": 3, "3x5": 3, "5x5": 5}
DIAGNOSTIC_3X3_IDS = (
    "sympy__sympy-13480",
    "sympy__sympy-20212",
    "sympy__sympy-16988",
)
DIAGNOSTIC_3X3_STRATEGIES = (
    "budget_only_tight",
    "budgetflow_full_tight",
    "budgetflow_equal_weight_tight",
)


def _compare_paths(tasks_n: int, strategies_n: int, *, stem: str | None = None) -> tuple[Path, Path]:
    base = stem or f"compare_{tasks_n}x{strategies_n}"
    return RUNS_DIR / f"{base}.jsonl", RUNS_DIR / f"{base}.summary.log"


def main() -> None:
    load_env_file()
    if not os.environ.get("NO_COLOR"):
        os.environ.setdefault("FORCE_COLOR", "1")
    parser = argparse.ArgumentParser(description="N tasks × strategies — shared batch budget per policy")
    parser.add_argument(
        "--preset",
        choices=sorted(PRESET_TASKS),
        default="3x3",
        help="3x3=diagnostic 3 policies × 3 tasks, 3x5=legacy fast smoke, 5x5=legacy full compare",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="task count (default from --preset)",
    )
    parser.add_argument("--loose", type=float, default=None, help="shared batch budget for *_loose strategies")
    parser.add_argument("--tight", type=float, default=None, help="shared batch budget for *_tight strategies")
    parser.add_argument(
        "--read-frozen-caps",
        action="store_true",
        dest="read_frozen_caps",
        help="read loose/tight batch caps from data/frozen_caps.json for current task count",
    )
    parser.add_argument(
        "--read-protocol",
        action="store_true",
        dest="read_frozen_caps",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--step-limit",
        type=int,
        default=150,
        help="agent step cap per task (default 150; raise for hard localization tasks)",
    )
    parser.add_argument("--heartbeat", type=float, default=30.0)
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="parallel policy batches (each policy still runs tasks serially on one shared pool)",
    )
    parser.add_argument(
        "--trace-quiet",
        action="store_true",
        help="suppress per-step trace boards (jsonl/steps.jsonl still written)",
    )
    parser.add_argument(
        "--trace-verbose",
        action="store_true",
        help="print every agent step (default: milestones on gold/submit/test phase changes)",
    )
    parser.add_argument(
        "--strategies",
        type=str,
        default=None,
        help="comma-separated strategy names subset (e.g. all_spark_tight,budget_only_loose,budgetflow_full_tight)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="append to existing jsonl instead of overwriting",
    )
    parser.add_argument(
        "--skip-completed",
        action="store_true",
        help="with --append, skip (strategy,task) pairs already in jsonl",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="continue run: append jsonl, skip completed pairs, restore per-policy spent from checkpoint",
    )
    parser.add_argument(
        "--task-set",
        choices=("easy", "medium"),
        default="easy",
        help="easy=5 compare_easy tasks; medium=15 sympy medium-hard (fixed list)",
    )
    parser.add_argument(
        "--ids",
        type=str,
        default=None,
        help="comma-separated instance IDs (e.g. sympy__sympy-12419,...); overrides --task-set/--limit",
    )
    parser.add_argument(
        "--out-stem",
        type=str,
        default=None,
        help="optional explicit basename (overrides auto series); refuses overwrite unless --resume",
    )
    parser.add_argument(
        "--run-series",
        type=str,
        default=None,
        metavar="BASE",
        help="series prefix for auto IDs (default policy_15x7 / compare_5x7 from task×strategy shape)",
    )
    parser.add_argument(
        "--pressure-init",
        type=float,
        default=None,
        help=f"override BUDGET_PRESSURE_INIT (default {BUDGET_PRESSURE_INIT}; frozen caps used when --read-frozen-caps)",
    )
    parser.add_argument(
        "--pressure-max",
        type=float,
        default=None,
        help=f"override PRESSURE_MAX ceiling (default {PRESSURE_MAX}; frozen caps used when --read-frozen-caps)",
    )
    parser.add_argument(
        "--tight-scale",
        type=float,
        default=1.0,
        help="multiply tight batch cap after --read-frozen-caps or --tight (diagnostic sweeps)",
    )
    parser.add_argument(
        "--loose-scale",
        type=float,
        default=1.0,
        help="multiply loose batch cap after --read-frozen-caps or --loose",
    )
    parser.add_argument(
        "--no-run-guards",
        action="store_true",
        help="disable global/policy/upstream auto-halt guards",
    )
    parser.add_argument(
        "--no-provider-signature-check",
        action="store_true",
        help="skip preflight minimal chat completion checks for required providers",
    )
    parser.add_argument(
        "--trace-turns",
        action="store_true",
        default=False,
        help="collect per-turn routing decision traces in JSONL output (off by default; enable for diagnostics)",
    )
    parser.add_argument(
        "--trace-max-turns",
        type=int,
        default=200,
        help="max turn traces to keep per task (default 200)",
    )
    parser.add_argument(
        "--trace-truncate-chars",
        type=int,
        default=120,
        help="max chars for bash command digest in turn traces (default 120)",
    )
    parser.add_argument(
        "--per-task-cap",
        type=float,
        default=None,
        help="if set, each task gets a fresh governor with this cap (avoids shared-pool starvation); "
        "batch --tight/--loose caps are ignored for budgeting",
    )
    parser.add_argument(
        "--auto-budget",
        action="store_true",
        default=False,
        help="enable automatic per-task budget estimation from historical prior",
    )
    parser.add_argument(
        "--auto-budget-scale",
        type=float,
        default=1.5,
        help="multiply estimated cost by this scale (default 1.5)",
    )
    parser.add_argument(
        "--auto-budget-min",
        type=float,
        default=0.10,
        help="minimum per-task cap in USD (default 0.10)",
    )
    parser.add_argument(
        "--auto-budget-max",
        type=float,
        default=10.0,
        help="maximum per-task cap in USD (default 10.0)",
    )
    parser.add_argument(
        "--auto-budget-mode",
        choices=("per_task",),
        default="per_task",
        help="budget mode (currently only per_task; shared auto may be added later)",
    )
    parser.add_argument(
        "--auto-budget-memory",
        type=str,
        default=None,
        help="path to auto-budget memory file for continuous learning (default data/auto_budget_memory.jsonl)",
    )
    parser.add_argument(
        "--no-auto-budget-learn",
        action="store_true",
        default=False,
        help="disable writing new records to auto-budget memory after run",
    )
    parser.add_argument(
        "--auto-budget-k",
        type=int,
        default=3,
        help="k for kNN fallback in auto-budget (default 3)",
    )
    parser.add_argument(
        "--soft-budget",
        type=float,
        default=None,
        help="optional soft budget for shared mode; absolute cap is soft budget plus --max-overrun",
    )
    parser.add_argument(
        "--max-overrun",
        type=float,
        default=0.0,
        help="bounded overrun above --soft-budget or --per-task-cap (default 0)",
    )
    parser.add_argument(
        "--w-profile",
        choices=("repair_heavy", "validation_heavy", "flat"),
        default=None,
        help="w_i ordering for budgetflow_full (stage_blind still forces 1.0); default repair_heavy",
    )
    args = parser.parse_args()
    if args.w_profile:
        os.environ["BF_W_PROFILE"] = args.w_profile
    max_overrun = max(0.0, args.max_overrun)
    if args.resume:
        args.append = True
        args.skip_completed = True
    tasks_n = args.limit if args.limit is not None else PRESET_TASKS[args.preset]
    if args.task_set == "medium":
        tasks_n = args.limit if args.limit is not None else 15

    loose = args.loose
    tight = args.tight
    pressure_init = args.pressure_init
    pressure_max = args.pressure_max
    if args.read_frozen_caps:
        caps = read_protocol_caps(tasks_n)
        loose = caps.loose_batch
        tight = caps.tight_batch
        if pressure_init is None:
            pressure_init = caps.pressure_init
        if pressure_max is None:
            pressure_max = caps.pressure_max
        print(
            f"{tag('frozen-caps', bold=False)} read n={tasks_n} "
            f"loose_batch={loose:.4f} tight_batch={tight:.4f} "
            f"pressure_init={pressure_init:.4f} pressure_max={pressure_max:.4f}",
            flush=True,
        )
    if pressure_init is None:
        pressure_init = BUDGET_PRESSURE_INIT
    if pressure_max is None:
        pressure_max = PRESSURE_MAX
    if args.tight_scale != 1.0:
        tight = (tight or 100.0) * args.tight_scale
    if args.loose_scale != 1.0:
        loose = (loose or 400.0) * args.loose_scale
    if loose is None:
        loose = 400.0
    if tight is None:
        tight = 100.0

    if args.trace_verbose:
        trace_console: TraceConsoleLevel = "verbose"
    elif args.trace_quiet:
        trace_console = "quiet"
    else:
        trace_console = "milestones"

    all_strategies = _strategy_catalog()
    if args.strategies:
        wanted_raw = {s.strip() for s in args.strategies.split(",") if s.strip()}
    elif args.preset == "3x3":
        wanted_raw = set(DIAGNOSTIC_3X3_STRATEGIES)
    else:
        wanted_raw = set()
    if wanted_raw:
        wanted = {_STRATEGY_ALIASES.get(name, name) for name in wanted_raw}
        strategies = tuple(s for s in all_strategies if s.name in wanted)
        missing = wanted_raw - {s.name for s in strategies} - set(_STRATEGY_ALIASES)
        if missing:
            raise SystemExit(f"unknown strategies: {sorted(missing)}")
        if not strategies:
            raise SystemExit("no strategies selected")
    else:
        strategies = all_strategies
    if not args.no_provider_signature_check:
        signature_results = check_required_signatures(_required_backends_for_strategies(strategies))
        for result in signature_results:
            state = "PASS" if result.ok else "FAIL"
            print(
                f"{tag('preflight', bold=False)} {state} backend={result.backend} "
                f"provider={result.provider} model={result.model} latency_ms={result.latency_ms} "
                f"status={result.status_code or '-'} error={result.error_type or '-'}",
                flush=True,
            )
        failed = [r for r in signature_results if not r.ok]
        if failed:
            raise SystemExit(
                "provider signature check failed: "
                + ", ".join(f"{r.backend}:{r.error_type or r.status_code}" for r in failed)
            )

    budget_caps = {"loose": loose, "tight": tight}
    if args.ids:
        ids = tuple(s.strip() for s in args.ids.split(",") if s.strip())
        tasks = load_swebench_lite_tasks(instance_ids=ids)
    elif args.preset == "3x3":
        tasks = load_swebench_lite_tasks(instance_ids=DIAGNOSTIC_3X3_IDS)
    elif args.task_set == "medium":
        tasks = load_compare_medium_tasks(tasks_n)
    else:
        tasks = load_compare_easy_tasks(tasks_n)
    tasks = _order_tasks_easy_first(tasks, task_set=args.task_set)

    # Auto-budget: compute per-task caps from historical prior + online memory.
    auto_budget_estimates: dict[str, BudgetEstimate] = {}
    auto_budget_task_caps: dict[str, float] | None = None
    auto_budget_memory: AutoBudgetMemory | None = None
    if args.auto_budget:
        memory_path: Path | None = None
        if args.auto_budget_memory:
            memory_path = Path(args.auto_budget_memory)
        else:
            default_memory = RUNS_DIR / "auto_budget_memory.jsonl"
            memory_path = default_memory
        auto_budget_memory = AutoBudgetMemory(memory_path if memory_path.is_file() else None)
        # Always set path so we can write new records.
        if auto_budget_memory._path is None:
            auto_budget_memory._path = memory_path

        estimator = AutoBudgetEstimator(memory=auto_budget_memory, k=args.auto_budget_k)
        for task in tasks:
            est = estimator.estimate(
                task,
                scale=args.auto_budget_scale,
                min_cap=args.auto_budget_min,
                max_cap=args.auto_budget_max,
            )
            auto_budget_estimates[task.instance_id] = est
            auto_budget_task_caps = {iid: est.cap for iid, est in auto_budget_estimates.items()}
            print(
                f"{tag('auto-budget', bold=False)} {est.instance_id} "
                f"est={_fmt_usd(est.estimated_cost)} cap={_fmt_usd(est.cap)} "
                f"source={est.source} confidence={est.confidence}"
                + (f" neighbors={est.memory_neighbors}" if est.memory_neighbors else ""),
                flush=True,
            )
        # Auto-budget implies per_task mode.
        if args.per_task_cap is None:
            args.per_task_cap = -1.0  # Sentinel: per-task with varying caps.

    total_runs = len(tasks) * len(strategies)
    series = args.run_series or default_series_base(
        tasks_n=len(tasks),
        strategies_n=len(strategies),
        task_set=args.task_set,
    )
    out_stem, stem_mode = resolve_compare_stem(
        RUNS_DIR,
        series=series,
        resume=args.resume,
        total_runs=total_runs,
        explicit_stem=args.out_stem,
    )
    out_path, summary_path = _compare_paths(len(tasks), len(strategies), stem=out_stem)
    checkpoint_path = checkpoint_path_for(out_stem, RUNS_DIR)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    strategy_names = [s.name for s in strategies]
    completed = _completed_keys(out_path, skip_bad=args.skip_completed) if args.skip_completed else set()
    if args.skip_completed and completed:
        print(f"{tag('resume', bold=False)} skip {len(completed)} completed (strategy,task) pairs", flush=True)
    checkpoint = CompareCheckpointStore(checkpoint_path, stem=out_stem, total_runs=total_runs)
    use_per_task_cap = args.per_task_cap is not None and args.per_task_cap > 0
    batch_caps: dict[str, float | None] = {
        s.name: (
            args.per_task_cap
            if use_per_task_cap
            else None if s.budget_tier is None else budget_caps[s.budget_tier]
        )
        for s in strategies
    }

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"{tag('run_id', bold=False)} {out_stem} "
        f"series={series} mode={stem_mode}"
        + (" (resume latest)" if stem_mode == "resume" else " (new run)"),
        flush=True,
    )
    from budgetflow.console_log import format_tier_pool_line  # noqa: E402

    print(
        f"{tag('compare', bold=False)} task_set={args.task_set} preset={args.preset} tasks={len(tasks)} "
        f"strategies={len(strategies)} batches={len(strategies)} runs={total_runs} loose={loose} tight={tight} "
        f"pressure_init={pressure_init} pressure_max={pressure_max} "
        f"policy_jobs={args.jobs} heartbeat={args.heartbeat}s hard_cap=settle_clamp",
        flush=True,
    )
    print(f"  pool: {format_tier_pool_line()}", flush=True)
    print(f"{dim('tasks=' + ','.join(t.instance_id for t in tasks))}", flush=True)
    print(f"{dim('task_order=' + ', '.join(_task_descriptor(t) for t in tasks))}", flush=True)
    print(f"{dim('strategies=' + ','.join(strategy_names))}", flush=True)
    budget_mode = (
        f"per_task_cap={args.per_task_cap}" + (f"+overrun={max_overrun}" if max_overrun else "")
        if args.per_task_cap
        else "shared_batch_budget" + (
            f" soft_budget={args.soft_budget}+overrun={max_overrun}" if args.soft_budget is not None else ""
        )
    )
    print(
        f"{dim('mode=' + budget_mode + '; tasks serial within policy; policies parallel with --jobs')}",
        flush=True,
    )
    if args.w_profile:
        print(f"{dim('w_i_profile=' + args.w_profile)}", flush=True)
    print(f"{dim('trace_console=' + trace_console + '; heartbeat every ' + str(args.heartbeat) + 's')}", flush=True)
    print(f"{dim('run_id=' + out_stem)}", flush=True)
    print(f"{dim('out=' + str(out_path))}", flush=True)
    print(f"{dim('checkpoint=' + str(checkpoint_path))}", flush=True)
    print(f"{dim('trace= data/runs/trace_<id>_<strategy>/steps.jsonl')}", flush=True)
    print(f"{dim('FORCE_COLOR=1 if piping to tee/nohup for ANSI colors')}", flush=True)

    adaptive_registry = AdaptiveRoutingRegistry()
    if args.append and out_path.is_file():
        adaptive_registry.rebuild_from_jsonl(out_path)

    header_lines = [
        f"compare_{len(tasks)}x{len(strategies)} task_set={args.task_set} preset={args.preset} "
        f"tasks={len(tasks)} strategies={strategy_names}",
        f"budget_mode={'per_task_cap=' + str(args.per_task_cap) if args.per_task_cap else 'shared'} "
        f"soft_budget={args.soft_budget} max_overrun={max_overrun} "
        f"loose={loose} tight={tight} w_i_profile={args.w_profile or active_w_i_profile_name()} "
        f"pressure_init={pressure_init} pressure_max={pressure_max} "
        f"policy_jobs={args.jobs} hard_cap=settle_clamp",
        f"tasks={[t.instance_id for t in tasks]}",
        f"task_order={[_task_descriptor(t) for t in tasks]}",
        "adaptive_routing=always_on_for_budgetflow_full",
        "",
    ]
    adapt_summary = adaptive_registry.summary_lines()
    header_lines.extend(adapt_summary)
    if adapt_summary:
        header_lines.append("")
    if args.append and out_path.is_file():
        state = _rebuild_state_from_jsonl(out_path, header_lines)
        print(f"{tag('resume', bold=False)} rebuilt state from jsonl runs={state.runs_done}", flush=True)
    else:
        state = _CompareState(
            summary_lines=header_lines,
            resolved_by_strategy={},
            task_cost_by_strategy={},
            batch_spent_by_strategy={},
            turns_by_strategy={},
            spark_by_strategy={},
            flash_by_strategy={},
            pro_by_strategy={},
            failure_by_strategy={},
        )
    started = time.time()
    io_lock = threading.Lock()
    print_lock = threading.Lock() if args.jobs > 1 else None
    global_progress = GlobalRunProgress(total_runs)
    scoreboard = StrategyScoreboard(strategy_names)
    if completed:
        global_progress.seed_done(len(completed))
    if args.append and state.resolved_by_strategy:
        scoreboard.seed_from_resolved(state.resolved_by_strategy)

    _write_summary_file(
        summary_path,
        summary_lines=state.summary_lines,
        strategy_names=strategy_names,
        resolved_by_strategy=state.resolved_by_strategy,
        task_cost_by_strategy=state.task_cost_by_strategy,
        batch_spent_by_strategy=state.batch_spent_by_strategy,
        turns_by_strategy=state.turns_by_strategy,
        spark_by_strategy=state.spark_by_strategy,
        flash_by_strategy=state.flash_by_strategy,
        pro_by_strategy=state.pro_by_strategy,
        failure_by_strategy=state.failure_by_strategy,
        batch_caps=batch_caps,
        started=started,
        out_path=out_path,
        runs_done=state.runs_done,
        total_runs=total_runs,
        tasks_per_strategy=len(tasks),
        global_line=global_progress.format_global(scoreboard),
    )

    run_guards: CompareRunGuards | None = None if args.no_run_guards else CompareRunGuards()
    set_active_guard(run_guards)

    def _run_one_batch(cfg: CompareStrategy) -> tuple[CompareStrategy, list[dict], float, float]:
        if run_guards is not None and run_guards.is_aborted():
            print(
                f"{tag('guard', bold=False)} skip strategy={cfg.name} batch (global halt: {run_guards.abort_reason()})",
                flush=True,
            )
            batch_cap = _batch_budget_cap(cfg, budget_caps)
            return cfg, [], checkpoint.initial_spent(cfg.name) if args.resume else 0.0, batch_cap
        batch_cap = _batch_budget_cap(cfg, budget_caps)
        batch_tasks = list(tasks)
        if completed:
            batch_tasks = [t for t in tasks if (cfg.name, t.instance_id) not in completed]
            if not batch_tasks:
                print(f"{tag('skip', bold=False)} strategy={cfg.name} all tasks already done", flush=True)
                return cfg, [], 0.0, batch_cap
        initial_spent = checkpoint.initial_spent(cfg.name) if args.resume else 0.0

        def _on_task(record: dict) -> None:
            _persist_task_record(
                state,
                record,
                handle=handle,
                io_lock=io_lock,
                total_runs=total_runs,
                tasks_per_strategy=len(tasks),
                global_progress=global_progress,
                scoreboard=scoreboard,
                summary_path=summary_path,
                strategy_names=strategy_names,
                batch_caps=batch_caps,
                started=started,
                out_path=out_path,
                auto_budget_memory=auto_budget_memory,
                no_auto_budget_learn=args.no_auto_budget_learn,
            )

        records, batch_spent = _run_strategy_batch(
            cfg,
            batch_tasks,
            batch_budget_cap=batch_cap,
            per_task_cap=args.per_task_cap if args.per_task_cap and args.per_task_cap > 0 else None,
            soft_budget=args.soft_budget,
            max_overrun=max_overrun,
            step_limit=args.step_limit,
            trace_console=trace_console,
            heartbeat=args.heartbeat,
            global_progress=global_progress,
            scoreboard=scoreboard,
            print_lock=print_lock,
            budget_pressure=pressure_init,
            pressure_max=pressure_max,
            initial_spent=initial_spent,
            checkpoint=checkpoint,
            on_task_complete=_on_task,
            run_guards=run_guards,
            adaptive_registry=adaptive_registry,
            enable_turn_trace=args.trace_turns,
            trace_max_turns=args.trace_max_turns,
            trace_truncate_chars=args.trace_truncate_chars,
            task_caps=auto_budget_task_caps,
            budget_estimates=auto_budget_estimates,
        )
        return cfg, records, batch_spent, batch_cap

    file_mode = "a" if args.append else "w"
    try:
        with out_path.open(file_mode) as handle:
            if args.jobs <= 1:
                for cfg in strategies:
                    if run_guards is not None and run_guards.is_aborted():
                        break
                    cfg, batch_records, batch_spent, batch_cap = _run_one_batch(cfg)
                    _ingest_batch_footer(
                        state,
                        cfg,
                        batch_records,
                        batch_spent,
                        batch_cap,
                        strategy_names=strategy_names,
                        batch_caps=batch_caps,
                        summary_path=summary_path,
                        started=started,
                        out_path=out_path,
                        total_runs=total_runs,
                        tasks_per_strategy=len(tasks),
                        io_lock=io_lock,
                        global_progress=global_progress,
                    )
            else:
                with ThreadPoolExecutor(max_workers=min(args.jobs, len(strategies))) as pool:
                    futures = {pool.submit(_run_one_batch, cfg): cfg for cfg in strategies}
                    for future in as_completed(futures):
                        cfg, batch_records, batch_spent, batch_cap = future.result()
                        if run_guards is not None and run_guards.is_aborted():
                            for pending in futures:
                                pending.cancel()
                            break
                        _ingest_batch_footer(
                            state,
                            cfg,
                            batch_records,
                            batch_spent,
                            batch_cap,
                            strategy_names=strategy_names,
                            batch_caps=batch_caps,
                            summary_path=summary_path,
                            started=started,
                            out_path=out_path,
                            total_runs=total_runs,
                            tasks_per_strategy=len(tasks),
                            io_lock=io_lock,
                            global_progress=global_progress,
                        )
    finally:
        set_active_guard(None)

    if run_guards is not None and run_guards.is_aborted():
        print(f"\n{tag('guard', bold=False)} run stopped early: {run_guards.abort_reason()}", flush=True)

    _write_summary_file(
        summary_path,
        summary_lines=state.summary_lines,
        strategy_names=strategy_names,
        resolved_by_strategy=state.resolved_by_strategy,
        task_cost_by_strategy=state.task_cost_by_strategy,
        batch_spent_by_strategy=state.batch_spent_by_strategy,
        turns_by_strategy=state.turns_by_strategy,
        spark_by_strategy=state.spark_by_strategy,
        flash_by_strategy=state.flash_by_strategy,
        pro_by_strategy=state.pro_by_strategy,
        failure_by_strategy=state.failure_by_strategy,
        batch_caps=batch_caps,
        started=started,
        out_path=out_path,
        runs_done=state.runs_done,
        total_runs=total_runs,
        tasks_per_strategy=len(tasks),
        global_line=global_progress.format_global(scoreboard),
    )

    print(
        f"\n{tag('final', bold=False)}\n{global_progress.format_banner(scoreboard)}\n"
        f"elapsed={time.time() - started:.1f}s",
        flush=True,
    )
    for line in _format_strategy_totals(
        strategy_names=strategy_names,
        resolved_by_strategy=state.resolved_by_strategy,
        task_cost_by_strategy=state.task_cost_by_strategy,
        batch_spent_by_strategy=state.batch_spent_by_strategy,
        turns_by_strategy=state.turns_by_strategy,
        spark_by_strategy=state.spark_by_strategy,
        flash_by_strategy=state.flash_by_strategy,
        pro_by_strategy=state.pro_by_strategy,
        failure_by_strategy=state.failure_by_strategy,
        batch_caps=batch_caps,
    ):
        print(f"  {line}", flush=True)
    print(f"jsonl={out_path}")
    print(f"summary={summary_path}")


if __name__ == "__main__":
    main()
