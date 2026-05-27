"""Compare N tasks × 5 strategies: shared batch budget per policy.

Each policy runs its task list serially on one BudgetGovernor (shared pool).
Different policies may run in parallel (--jobs) using git worktrees for repo isolation.

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

from budgetflow.adapter.runner import run_mini_swe_task  # noqa: E402
from budgetflow.console_log import dim, format_run_verdict, tag  # noqa: E402
from budgetflow.deepseek_backend import load_env_file  # noqa: E402
from budgetflow.governor import BudgetGovernor, GovernorConfig  # noqa: E402
from budgetflow.heartbeat import run_with_heartbeat  # noqa: E402
from budgetflow.ledger import WorkflowLedgerStore  # noqa: E402
from budgetflow.lite_tasks import load_compare_easy_tasks  # noqa: E402
from budgetflow.protocol_caps import read_protocol_caps  # noqa: E402
from budgetflow.run_trace import TraceConsoleLevel  # noqa: E402

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


def _batch_budget_cap(cfg: CompareStrategy, budget_caps: dict[str, float]) -> float:
    if cfg.budget_tier is None:
        return UNCAPPED_BUDGET
    return budget_caps[cfg.budget_tier]


def _workspace_key(cfg: CompareStrategy, instance_id: str) -> str:
    safe = cfg.name.replace("/", "_")
    return f"{safe}_{instance_id}"


def _run_id(strategy_index: int, task_index: int, tasks_per_batch: int) -> int:
    return strategy_index * tasks_per_batch + task_index


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
) -> dict:
    started = time.time()
    workspace_key = _workspace_key(cfg, task.instance_id)
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
    )
    batch_snapshot = governor.budget_snapshot()
    return {
        "instance_id": result.instance_id,
        "strategy": cfg.name,
        "routing": cfg.routing,
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
        "agent_summary": {
            "gold_edited": result.agent_gold_edited,
            "gold_files": list(result.agent_gold_files),
            "submitted": result.agent_submitted,
        },
    }


def _print_run_done(record: dict, *, index: int, total: int, strategy: str) -> None:
    gold_file = (record.get("agent_gold_files") or ["-"])[0]
    verdict = format_run_verdict(
        harness_resolved=record["harness_resolved"],
        patch_extracted=record.get("patch_extracted", False),
        gold_edited=record.get("agent_gold_edited", False),
        gold_file=gold_file,
        detail=str(record.get("detail", "")),
    )
    print(
        f"{tag('done', bold=False)} [{index}/{total}] {record['instance_id']} {strategy} "
        f"turns={record.get('llm_turns')} task_cost={record.get('task_cost', record.get('total_cost', 0)):.1f} "
        f"batch_avail={float(record.get('batch_available') or 0):.1f} elapsed={record.get('elapsed_s')}s",
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
    cap = record.get("batch_budget_cap")
    cap_s = "uncapped" if cap is None else f"{cap:.1f}"
    task_cost = float(record.get("task_cost") or record.get("total_cost") or 0.0)
    picks = record.get("backend_picks") or []
    flash_pct = _flash_ratio(picks) * 100.0
    lines.append(
        f"[{index}/{total}] DONE strategy={record['strategy']} task={record['instance_id']} {status} "
        f"exit={record.get('exit_status')} reason={record.get('exit_reason')} turns={record.get('llm_turns')} "
        f"task_cost={task_cost:.2f} batch_cap={cap_s} batch_avail={record.get('batch_available')} "
        f"batch_spent={record.get('batch_spent')} flash={flash_pct:.0f}% elapsed={record.get('elapsed_s')}s"
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
    flash_by_strategy: dict[str, list[float]],
    batch_caps: dict[str, float | None],
) -> list[str]:
    lines = ["=== BATCH RESOLVED + COST BY STRATEGY (governor units, shared pool) ==="]
    header = (
        f"{'strategy':<28} {'resolved':>8} {'batch_spent':>11} {'batch_cap':>10} "
        f"{'avg_task':>9} {'avg_turns':>10} {'flash%':>7}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for key in strategy_names:
        flags = resolved_by_strategy.get(key, [])
        costs = task_cost_by_strategy.get(key, [])
        turns = turns_by_strategy.get(key, [])
        flash = flash_by_strategy.get(key, [])
        resolved_n = sum(1 for f in flags if f)
        batch_spent = batch_spent_by_strategy.get(key, 0.0)
        cap = batch_caps.get(key)
        cap_s = f"{cap:.1f}" if cap is not None else "uncapped"
        cap_flag = ""
        if cap is not None and batch_spent > cap + 0.01:
            cap_flag = " OVER_CAP"
        avg_cost = sum(costs) / len(costs) if costs else 0.0
        avg_turns = sum(turns) / len(turns) if turns else 0.0
        avg_flash = sum(flash) / len(flash) if flash else 0.0
        lines.append(
            f"{key:<28} {resolved_n}/{len(flags):<7} {batch_spent:11.2f} {cap_s:>10}{cap_flag} "
            f"{avg_cost:9.2f} {avg_turns:10.1f} {avg_flash * 100:6.0f}%"
        )
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
    flash_by_strategy: dict[str, list[float]],
    batch_caps: dict[str, float | None],
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
            task_cost_by_strategy=task_cost_by_strategy,
            batch_spent_by_strategy=batch_spent_by_strategy,
            turns_by_strategy=turns_by_strategy,
            flash_by_strategy=flash_by_strategy,
            batch_caps=batch_caps,
        )
    )
    lines.append(f"PROGRESS {runs_done}/{total_runs} elapsed={time.time() - started:.1f}s")
    lines.append(f"jsonl={out_path}")
    path.write_text("\n".join(lines) + "\n")


def _governor_avail(batch_records: list[dict]) -> float:
    if not batch_records:
        return 0.0
    return float(batch_records[-1].get("batch_available") or 0.0)


def _run_strategy_batch(
    cfg: CompareStrategy,
    tasks: list,
    *,
    strategy_index: int,
    batch_budget_cap: float,
    step_limit: int,
    trace_console: TraceConsoleLevel,
    heartbeat: float,
    total_runs: int,
    print_lock: threading.Lock | None,
) -> tuple[list[dict], float]:
    ledger = WorkflowLedgerStore()
    governor = BudgetGovernor(
        GovernorConfig(total_budget=batch_budget_cap, default_max_output_tokens=4096),
        ledger,
    )

    def _log(msg: str) -> None:
        if print_lock:
            with print_lock:
                print(msg, flush=True)
        else:
            print(msg, flush=True)

    _log(
        f"{tag('batch', bold=False)} strategy={cfg.name} tasks={len(tasks)} "
        f"shared_cap={batch_budget_cap:.1f} mode=serial_tasks"
    )

    records: list[dict] = []
    for task_index, task in enumerate(tasks, start=1):
        global_index = _run_id(strategy_index, task_index, len(tasks))
        _log(f"\n======== RUN {global_index}/{total_runs} ========")
        _log(f"{tag('start', bold=False)} task={task.instance_id} strategy={cfg.name}")

        status_box: dict[str, str] = {
            "phase": "prep",
            "status": f"strategy={cfg.name} task={task.instance_id} prep",
        }
        label = f"{cfg.name} {task.instance_id}"

        def _status() -> str:
            return status_box.get("status", f"strategy={cfg.name} phase={status_box['phase']}")

        def _execute() -> dict:
            status_box["phase"] = "agent"
            return _run_one(
                task,
                cfg=cfg,
                batch_budget_cap=batch_budget_cap,
                governor=governor,
                ledger=ledger,
                task_index=task_index,
                step_limit=step_limit,
                trace_console=trace_console,
                progress_box=status_box,
            )

        if heartbeat > 0:
            record = run_with_heartbeat(label, _execute, interval_s=heartbeat, status_fn=_status)
        else:
            record = _execute()

        if print_lock:
            with print_lock:
                _print_run_done(record, index=global_index, total=total_runs, strategy=cfg.name)
        else:
            _print_run_done(record, index=global_index, total=total_runs, strategy=cfg.name)
        records.append(record)

    return records, governor.state.spent_budget


@dataclass
class _CompareState:
    summary_lines: list[str]
    resolved_by_strategy: dict[str, list[bool]]
    task_cost_by_strategy: dict[str, list[float]]
    batch_spent_by_strategy: dict[str, float]
    turns_by_strategy: dict[str, list[int]]
    flash_by_strategy: dict[str, list[float]]
    runs_done: int = 0


def _ingest_batch(
    state: _CompareState,
    cfg: CompareStrategy,
    batch_records: list[dict],
    batch_spent: float,
    batch_cap: float,
    *,
    handle,
    strategy_names: list[str],
    batch_caps: dict[str, float | None],
    summary_path: Path,
    started: float,
    out_path: Path,
    total_runs: int,
    io_lock: threading.Lock,
) -> None:
    with io_lock:
        state.summary_lines.append(f"=== BATCH START strategy={cfg.name} shared_cap={batch_cap:.1f} ===")
        state.batch_spent_by_strategy[cfg.name] = batch_spent
        state.summary_lines.append(
            f"=== BATCH END strategy={cfg.name} resolved="
            f"{sum(1 for r in batch_records if r['harness_resolved'])}/{len(batch_records)} "
            f"batch_spent={batch_spent:.2f} batch_avail={_governor_avail(batch_records):.2f} ==="
        )
        state.summary_lines.append("")

        for record in batch_records:
            state.runs_done += 1
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            _append_summary(state.summary_lines, record, index=state.runs_done, total=total_runs)
            name = cfg.name
            state.resolved_by_strategy.setdefault(name, []).append(record["harness_resolved"])
            state.task_cost_by_strategy.setdefault(name, []).append(float(record.get("task_cost") or 0.0))
            state.turns_by_strategy.setdefault(name, []).append(int(record.get("llm_turns") or 0))
            state.flash_by_strategy.setdefault(name, []).append(_flash_ratio(record.get("backend_picks") or []))

        handle.flush()
        _write_summary_file(
            summary_path,
            summary_lines=state.summary_lines,
            strategy_names=strategy_names,
            resolved_by_strategy=state.resolved_by_strategy,
            task_cost_by_strategy=state.task_cost_by_strategy,
            batch_spent_by_strategy=state.batch_spent_by_strategy,
            turns_by_strategy=state.turns_by_strategy,
            flash_by_strategy=state.flash_by_strategy,
            batch_caps=batch_caps,
            started=started,
            out_path=out_path,
            runs_done=state.runs_done,
            total_runs=total_runs,
        )


PRESET_TASKS = {"3x5": 3, "5x5": 5}


def _compare_paths(tasks_n: int) -> tuple[Path, Path]:
    stem = f"compare_{tasks_n}x5"
    return RUNS_DIR / f"{stem}.jsonl", RUNS_DIR / f"{stem}.summary.log"


def main() -> None:
    load_env_file()
    parser = argparse.ArgumentParser(description="N tasks × 5 strategies — shared batch budget per policy")
    parser.add_argument(
        "--preset",
        choices=sorted(PRESET_TASKS),
        default="3x5",
        help="3x5=3 tasks (fast smoke), 5x5=5 tasks (full compare); sets --limit unless overridden",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="task count (default from --preset: 3x5→3, 5x5→5)",
    )
    parser.add_argument("--loose", type=float, default=None, help="shared batch budget for *_loose strategies")
    parser.add_argument("--tight", type=float, default=None, help="shared batch budget for *_tight strategies")
    parser.add_argument(
        "--read-protocol",
        action="store_true",
        help="read loose/tight batch caps from docs/protocol.md for current task count",
    )
    parser.add_argument(
        "--step-limit",
        type=int,
        default=80,
        help="agent step cap per task (smoke default 80; formal runs may raise after pilot)",
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
    args = parser.parse_args()
    tasks_n = args.limit if args.limit is not None else PRESET_TASKS[args.preset]

    loose = args.loose
    tight = args.tight
    if args.read_protocol:
        caps = read_protocol_caps(tasks_n)
        loose = caps.loose_batch
        tight = caps.tight_batch
        print(
            f"{tag('protocol', bold=False)} read n={tasks_n} M={caps.m:.4f} "
            f"loose={loose:.4f} tight={tight:.4f}",
            flush=True,
        )
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

    strategies = DEFAULT_STRATEGIES
    budget_caps = {"loose": loose, "tight": tight}
    tasks = load_compare_easy_tasks(tasks_n)
    total_runs = len(tasks) * len(strategies)
    out_path, summary_path = _compare_paths(len(tasks))
    strategy_names = [s.name for s in strategies]
    batch_caps: dict[str, float | None] = {
        s.name: None if s.budget_tier is None else budget_caps[s.budget_tier] for s in strategies
    }

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"{tag('compare', bold=False)} preset={args.preset} tasks={len(tasks)} strategies={len(strategies)} "
        f"batches={len(strategies)} runs={total_runs} loose={loose} tight={tight} "
        f"policy_jobs={args.jobs} heartbeat={args.heartbeat}s hard_cap=settle_clamp",
        flush=True,
    )
    print(f"{dim('tasks=' + ','.join(t.instance_id for t in tasks))}", flush=True)
    print(f"{dim('strategies=' + ','.join(strategy_names))}", flush=True)
    print(f"{dim('mode=shared_batch_budget; tasks serial within policy; policies parallel with --jobs')}", flush=True)
    print(f"{dim('trace_console=' + trace_console + '; heartbeat every ' + str(args.heartbeat) + 's')}", flush=True)
    print(f"{dim('out=' + str(out_path))}", flush=True)
    print(f"{dim('trace= data/runs/trace_<id>_<strategy>/steps.jsonl')}", flush=True)
    print(f"{dim('FORCE_COLOR=1 if piping to tee/nohup for ANSI colors')}", flush=True)

    state = _CompareState(
        summary_lines=[
            f"compare_{len(tasks)}x5 preset={args.preset} tasks={len(tasks)} strategies={strategy_names}",
            f"shared_batch_budget loose={loose} tight={tight} policy_jobs={args.jobs} hard_cap=settle_clamp",
            f"tasks={[t.instance_id for t in tasks]}",
            "",
        ],
        resolved_by_strategy={},
        task_cost_by_strategy={},
        batch_spent_by_strategy={},
        turns_by_strategy={},
        flash_by_strategy={},
    )
    started = time.time()
    io_lock = threading.Lock()
    print_lock = threading.Lock() if args.jobs > 1 else None

    def _run_one_batch(strategy_index: int, cfg: CompareStrategy) -> tuple[CompareStrategy, list[dict], float, float]:
        batch_cap = _batch_budget_cap(cfg, budget_caps)
        records, batch_spent = _run_strategy_batch(
            cfg,
            tasks,
            strategy_index=strategy_index,
            batch_budget_cap=batch_cap,
            step_limit=args.step_limit,
            trace_console=trace_console,
            heartbeat=args.heartbeat,
            total_runs=total_runs,
            print_lock=print_lock,
        )
        return cfg, records, batch_spent, batch_cap

    with out_path.open("w") as handle:
        if args.jobs <= 1:
            for strategy_index, cfg in enumerate(strategies):
                cfg, batch_records, batch_spent, batch_cap = _run_one_batch(strategy_index, cfg)
                _ingest_batch(
                    state,
                    cfg,
                    batch_records,
                    batch_spent,
                    batch_cap,
                    handle=handle,
                    strategy_names=strategy_names,
                    batch_caps=batch_caps,
                    summary_path=summary_path,
                    started=started,
                    out_path=out_path,
                    total_runs=total_runs,
                    io_lock=io_lock,
                )
        else:
            with ThreadPoolExecutor(max_workers=min(args.jobs, len(strategies))) as pool:
                futures = {
                    pool.submit(_run_one_batch, strategy_index, cfg): cfg
                    for strategy_index, cfg in enumerate(strategies)
                }
                for future in as_completed(futures):
                    cfg, batch_records, batch_spent, batch_cap = future.result()
                    _ingest_batch(
                        state,
                        cfg,
                        batch_records,
                        batch_spent,
                        batch_cap,
                        handle=handle,
                        strategy_names=strategy_names,
                        batch_caps=batch_caps,
                        summary_path=summary_path,
                        started=started,
                        out_path=out_path,
                        total_runs=total_runs,
                        io_lock=io_lock,
                    )

    _write_summary_file(
        summary_path,
        summary_lines=state.summary_lines,
        strategy_names=strategy_names,
        resolved_by_strategy=state.resolved_by_strategy,
        task_cost_by_strategy=state.task_cost_by_strategy,
        batch_spent_by_strategy=state.batch_spent_by_strategy,
        turns_by_strategy=state.turns_by_strategy,
        flash_by_strategy=state.flash_by_strategy,
        batch_caps=batch_caps,
        started=started,
        out_path=out_path,
        runs_done=state.runs_done,
        total_runs=total_runs,
    )

    print(f"\n{tag('final', bold=False)} elapsed={time.time() - started:.1f}s")
    for line in _format_strategy_totals(
        strategy_names=strategy_names,
        resolved_by_strategy=state.resolved_by_strategy,
        task_cost_by_strategy=state.task_cost_by_strategy,
        batch_spent_by_strategy=state.batch_spent_by_strategy,
        turns_by_strategy=state.turns_by_strategy,
        flash_by_strategy=state.flash_by_strategy,
        batch_caps=batch_caps,
    ):
        print(f"  {line}", flush=True)
    print(f"jsonl={out_path}")
    print(f"summary={summary_path}")


if __name__ == "__main__":
    main()
