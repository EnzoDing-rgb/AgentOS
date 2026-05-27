"""Compare 5 tasks × 5 strategies (25 runs): all_pro + BF full/only × loose/tight.

Usage (from paper1/):
  PYTHONPATH=src:../external/mini-swe-agent/src python -u -m budgetflow.run_mini_swe_compare

Strategies:
  all_pro, budgetflow_full_loose, budgetflow_full_tight,
  budget_only_loose, budget_only_tight

Outputs:
  data/runs/compare_5x5.jsonl
  data/runs/compare_5x5.summary.log
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
MINI_SWE_SRC = REPO_ROOT.parent / "external" / "mini-swe-agent" / "src"
for path in (str(SRC), str(MINI_SWE_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from budgetflow.adapter.runner import run_mini_swe_task  # noqa: E402
from budgetflow.run_trace import TraceConsoleLevel  # noqa: E402
from budgetflow.console_log import (
    dim,
    format_harness_board,
    format_run_verdict,
    status_fail,
    status_no,
    status_pass,
    status_yes,
    tag,
)  # noqa: E402
from budgetflow.deepseek_backend import load_env_file  # noqa: E402
from budgetflow.heartbeat import run_with_heartbeat  # noqa: E402
from budgetflow.lite_tasks import load_compare_easy_tasks  # noqa: E402

RUNS_DIR = REPO_ROOT / "data" / "runs"
UNCAPPED_BUDGET = 1_000_000.0


@dataclass(frozen=True)
class CompareStrategy:
    name: str
    routing: str
    budget_tier: str | None  # None = uncapped (all_pro)


DEFAULT_STRATEGIES: tuple[CompareStrategy, ...] = (
    CompareStrategy("all_pro", "all_pro", None),
    CompareStrategy("budgetflow_full_loose", "budgetflow_full", "loose"),
    CompareStrategy("budgetflow_full_tight", "budgetflow_full", "tight"),
    CompareStrategy("budget_only_loose", "budget_only", "loose"),
    CompareStrategy("budget_only_tight", "budget_only", "tight"),
)


def _run_one(
    task,
    *,
    cfg: CompareStrategy,
    budget_caps: dict[str, float],
    step_limit: int,
    trace_console: TraceConsoleLevel = "quiet",
    progress_box: dict[str, str] | None = None,
) -> dict:
    started = time.time()
    cap = UNCAPPED_BUDGET if cfg.budget_tier is None else budget_caps[cfg.budget_tier]
    result = run_mini_swe_task(
        task,
        strategy=cfg.routing,
        strategy_label=cfg.name,
        budget_per_task=cap,
        step_limit=step_limit,
        trace_console=trace_console,
        progress_box=progress_box,
        agent_heartbeat=False,
    )
    agent_summary = {
        "gold_edited": result.agent_gold_edited,
        "gold_files": list(result.agent_gold_files),
        "submitted": result.agent_submitted,
    }
    return {
        "instance_id": result.instance_id,
        "strategy": cfg.name,
        "routing": cfg.routing,
        "budget_tier": cfg.budget_tier or "uncapped",
        "budget_cap": None if cfg.budget_tier is None else cap,
        "budget_spent": result.total_cost,
        "budget_available": result.budget_snapshot.get("available_budget"),
        "budget_snapshot": result.budget_snapshot,
        "harness_resolved": result.harness_resolved,
        "patch_extracted": bool(result.patch_text),
        "exit_status": result.exit_status,
        "exit_reason": result.exit_reason,
        "total_cost": result.total_cost,
        "backend_picks": list(result.backend_picks),
        "llm_turns": result.llm_turns,
        "violations": list(result.violations),
        "detail": result.harness_detail,
        "agent_gold_edited": result.agent_gold_edited,
        "agent_gold_files": list(result.agent_gold_files),
        "agent_submitted": result.agent_submitted,
        "elapsed_s": round(time.time() - started, 1),
        "agent_summary": agent_summary,
    }


def _print_run_done(record: dict, *, index: int, total: int) -> None:
    gold_file = (record.get("agent_gold_files") or ["-"])[0]
    verdict = format_run_verdict(
        harness_resolved=record["harness_resolved"],
        patch_extracted=record.get("patch_extracted", False),
        gold_edited=record.get("agent_gold_edited", False),
        gold_file=gold_file,
        detail=str(record.get("detail", "")),
    )
    print(
        f"{tag('done', bold=False)} [{index}/{total}] {record['instance_id']} {record['strategy']} "
        f"turns={record.get('llm_turns')} cost={record.get('total_cost'):.1f} "
        f"elapsed={record.get('elapsed_s')}s",
        flush=True,
    )
    print(f"  {verdict}", flush=True)


def _flash_ratio(picks: list[str]) -> float:
    if not picks:
        return 0.0
    flash = sum(1 for p in picks if "flash" in p.lower())
    return flash / len(picks)


def _append_summary(lines: list[str], record: dict, *, index: int, total: int) -> None:
    status = "PASS" if record["harness_resolved"] else "FAIL"
    cap = record.get("budget_cap")
    cap_s = "uncapped" if cap is None else f"{cap:.1f}"
    cost = float(record.get("total_cost") or 0.0)
    picks = record.get("backend_picks") or []
    flash_pct = _flash_ratio(picks) * 100.0
    lines.append(
        f"[{index}/{total}] DONE strategy={record['strategy']} task={record['instance_id']} {status} "
        f"exit={record.get('exit_status')} reason={record.get('exit_reason')} turns={record.get('llm_turns')} "
        f"cost={cost:.2f} cap={cap_s} avail={record.get('budget_available')} "
        f"flash={flash_pct:.0f}% elapsed={record.get('elapsed_s')}s"
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
    cost_by_strategy: dict[str, list[float]],
    turns_by_strategy: dict[str, list[int]],
    flash_by_strategy: dict[str, list[float]],
) -> list[str]:
    lines = ["=== RESOLVED + COST BY STRATEGY (governor units, not USD) ==="]
    header = f"{'strategy':<28} {'resolved':>8} {'total_cost':>11} {'avg_cost':>9} {'avg_turns':>10} {'flash%':>7}"
    lines.append(header)
    lines.append("-" * len(header))
    for key in strategy_names:
        flags = resolved_by_strategy.get(key, [])
        costs = cost_by_strategy.get(key, [])
        turns = turns_by_strategy.get(key, [])
        flash = flash_by_strategy.get(key, [])
        resolved_n = sum(1 for f in flags if f)
        total_cost = sum(costs)
        avg_cost = total_cost / len(costs) if costs else 0.0
        avg_turns = sum(turns) / len(turns) if turns else 0.0
        avg_flash = sum(flash) / len(flash) if flash else 0.0
        lines.append(
            f"{key:<28} {resolved_n}/{len(flags):<7} {total_cost:11.2f} {avg_cost:9.2f} "
            f"{avg_turns:10.1f} {avg_flash * 100:6.0f}%"
        )
    return lines


def _write_summary_file(
    path: Path,
    *,
    summary_lines: list[str],
    strategy_names: list[str],
    resolved_by_strategy: dict[str, list[bool]],
    cost_by_strategy: dict[str, list[float]],
    turns_by_strategy: dict[str, list[int]],
    flash_by_strategy: dict[str, list[float]],
    started: float,
    out_path: Path,
    runs_done: int,
    total_runs: int,
) -> None:
    lines = list(summary_lines)
    lines.append("")
    lines.extend(
        _format_strategy_totals(
            strategy_names=strategy_names,
            resolved_by_strategy=resolved_by_strategy,
            cost_by_strategy=cost_by_strategy,
            turns_by_strategy=turns_by_strategy,
            flash_by_strategy=flash_by_strategy,
        )
    )
    lines.append(f"PROGRESS {runs_done}/{total_runs} elapsed={time.time() - started:.1f}s")
    lines.append(f"jsonl={out_path}")
    path.write_text("\n".join(lines) + "\n")
    load_env_file()
    parser = argparse.ArgumentParser(description="5 tasks × 5 strategies compare")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--loose", type=float, default=400.0, help="per-task cap for *_loose strategies")
    parser.add_argument("--tight", type=float, default=100.0, help="per-task cap for *_tight strategies")
    parser.add_argument("--step-limit", type=int, default=250)
    parser.add_argument("--heartbeat", type=float, default=30.0)
    parser.add_argument(
        "--trace-verbose",
        action="store_true",
        help="print every agent step to console (default: quiet, jsonl only)",
    )
    args = parser.parse_args()

    trace_console: TraceConsoleLevel = "verbose" if args.trace_verbose else "quiet"

    strategies = DEFAULT_STRATEGIES
    budget_caps = {"loose": args.loose, "tight": args.tight}
    tasks = load_compare_easy_tasks(args.limit)
    total_runs = len(tasks) * len(strategies)
    out_path = RUNS_DIR / "compare_5x5.jsonl"
    summary_path = RUNS_DIR / "compare_5x5.summary.log"
    strategy_names = [s.name for s in strategies]

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"{tag('compare', bold=False)} tasks={len(tasks)} strategies={len(strategies)} "
        f"runs={total_runs} loose={args.loose} tight={args.tight} heartbeat={args.heartbeat}s",
        flush=True,
    )
    print(f"{dim('tasks=' + ','.join(t.instance_id for t in tasks))}", flush=True)
    print(f"{dim('strategies=' + ','.join(strategy_names))}", flush=True)
    print(f"{dim('out=' + str(out_path))}", flush=True)

    summary_lines = [
        f"compare_5x5 tasks={len(tasks)} strategies={strategy_names}",
        f"loose={args.loose} tight={args.tight}",
        f"tasks={[t.instance_id for t in tasks]}",
        "",
    ]
    resolved_by_strategy: dict[str, list[bool]] = {}
    cost_by_strategy: dict[str, list[float]] = {}
    turns_by_strategy: dict[str, list[int]] = {}
    flash_by_strategy: dict[str, list[float]] = {}
    started = time.time()
    run_index = 0

    with out_path.open("w") as handle:
        for task in tasks:
            for cfg in strategies:
                run_index += 1
                label = f"{run_index}/{total_runs} {task.instance_id} {cfg.name}"
                print(f"\n======== RUN {run_index}/{total_runs} ========", flush=True)
                print(f"{tag('start', bold=False)} task={task.instance_id} strategy={cfg.name}", flush=True)
                summary_lines.append(
                    f"[{run_index}/{total_runs}] START strategy={cfg.name} task={task.instance_id}"
                )

                status_box: dict[str, str] = {"phase": "prep", "status": f"strategy={cfg.name} prep"}

                def _status() -> str:
                    return status_box.get("status", f"strategy={cfg.name} phase={status_box['phase']}")

                def _execute() -> dict:
                    status_box["phase"] = "agent"
                    return _run_one(
                        task,
                        cfg=cfg,
                        budget_caps=budget_caps,
                        step_limit=args.step_limit,
                        trace_console=trace_console,
                        progress_box=status_box,
                    )

                record = run_with_heartbeat(
                    label,
                    _execute,
                    interval_s=args.heartbeat,
                    status_fn=_status,
                )
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                _append_summary(summary_lines, record, index=run_index, total=total_runs)
                name = cfg.name
                resolved_by_strategy.setdefault(name, []).append(record["harness_resolved"])
                cost_by_strategy.setdefault(name, []).append(float(record.get("total_cost") or 0.0))
                turns_by_strategy.setdefault(name, []).append(int(record.get("llm_turns") or 0))
                flash_by_strategy.setdefault(name, []).append(_flash_ratio(record.get("backend_picks") or []))
                _write_summary_file(
                    summary_path,
                    summary_lines=summary_lines,
                    strategy_names=strategy_names,
                    resolved_by_strategy=resolved_by_strategy,
                    cost_by_strategy=cost_by_strategy,
                    turns_by_strategy=turns_by_strategy,
                    flash_by_strategy=flash_by_strategy,
                    started=started,
                    out_path=out_path,
                    runs_done=run_index,
                    total_runs=total_runs,
                )
                _print_run_done(record, index=run_index, total=total_runs)

    _write_summary_file(
        summary_path,
        summary_lines=summary_lines,
        strategy_names=strategy_names,
        resolved_by_strategy=resolved_by_strategy,
        cost_by_strategy=cost_by_strategy,
        turns_by_strategy=turns_by_strategy,
        flash_by_strategy=flash_by_strategy,
        started=started,
        out_path=out_path,
        runs_done=run_index,
        total_runs=total_runs,
    )

    print(f"\n{tag('final', bold=False)} elapsed={time.time() - started:.1f}s")
    for line in _format_strategy_totals(
        strategy_names=strategy_names,
        resolved_by_strategy=resolved_by_strategy,
        cost_by_strategy=cost_by_strategy,
        turns_by_strategy=turns_by_strategy,
        flash_by_strategy=flash_by_strategy,
    ):
        print(f"  {line}", flush=True)
    print(f"jsonl={out_path}")
    print(f"summary={summary_path}")


if __name__ == "__main__":
    main()
