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
from budgetflow.console_log import dim, status_fail, status_pass, tag  # noqa: E402
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
) -> dict:
    started = time.time()
    cap = UNCAPPED_BUDGET if cfg.budget_tier is None else budget_caps[cfg.budget_tier]
    result = run_mini_swe_task(
        task,
        strategy=cfg.routing,
        strategy_label=cfg.name,
        budget_per_task=cap,
        step_limit=step_limit,
    )
    return {
        "instance_id": result.instance_id,
        "strategy": cfg.name,
        "routing": cfg.routing,
        "budget_tier": cfg.budget_tier or "uncapped",
        "budget_cap": None if cfg.budget_tier is None else cap,
        "harness_resolved": result.harness_resolved,
        "patch_extracted": bool(result.patch_text),
        "exit_status": result.exit_status,
        "total_cost": result.total_cost,
        "backend_picks": list(result.backend_picks),
        "llm_turns": result.llm_turns,
        "violations": list(result.violations),
        "detail": result.harness_detail,
        "elapsed_s": round(time.time() - started, 1),
    }


def _append_summary(lines: list[str], record: dict, *, index: int, total: int) -> None:
    status = "PASS" if record["harness_resolved"] else "FAIL"
    cap = record.get("budget_cap")
    cap_s = "uncapped" if cap is None else f"{cap:.1f}"
    lines.append(
        f"[{index}/{total}] DONE strategy={record['strategy']} task={record['instance_id']} {status} "
        f"exit={record.get('exit_status')} turns={record.get('llm_turns')} "
        f"cost={record.get('total_cost')} cap={cap_s} elapsed={record.get('elapsed_s')}s"
    )
    if record.get("backend_picks"):
        lines.append(f"  picks={record['backend_picks']}")
    if record.get("violations"):
        lines.append(f"  violations={record['violations']}")
    lines.append(f"  detail: {str(record.get('detail', ''))[:400]}")
    lines.append(json.dumps({k: v for k, v in record.items() if k != "detail"}, ensure_ascii=False))
    lines.append("")


def main() -> None:
    load_env_file()
    parser = argparse.ArgumentParser(description="5 tasks × 5 strategies compare")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--loose", type=float, default=80.0, help="per-task cap for *_loose strategies")
    parser.add_argument("--tight", type=float, default=20.0, help="per-task cap for *_tight strategies")
    parser.add_argument("--step-limit", type=int, default=250)
    parser.add_argument("--heartbeat", type=float, default=30.0)
    args = parser.parse_args()

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

                status_box = {"phase": "prep"}

                def _status() -> str:
                    return f"strategy={cfg.name} phase={status_box['phase']}"

                def _execute() -> dict:
                    status_box["phase"] = "agent"
                    return _run_one(task, cfg=cfg, budget_caps=budget_caps, step_limit=args.step_limit)

                record = run_with_heartbeat(
                    label,
                    _execute,
                    interval_s=args.heartbeat,
                    status_fn=_status,
                )
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                _append_summary(summary_lines, record, index=run_index, total=total_runs)
                resolved_by_strategy.setdefault(cfg.name, []).append(record["harness_resolved"])
                harness = status_pass("PASS") if record["harness_resolved"] else status_fail("FAIL")
                print(
                    f"{tag('done', bold=False)} strategy={cfg.name} task={task.instance_id} harness={harness} "
                    f"turns={record.get('llm_turns')} cost={record.get('total_cost')} "
                    f"elapsed={record['elapsed_s']}s",
                    flush=True,
                )

    summary_lines.append("")
    summary_lines.append("=== RESOLVED BY STRATEGY ===")
    for key in strategy_names:
        flags = resolved_by_strategy.get(key, [])
        summary_lines.append(f"{key}: {sum(flags)}/{len(flags)}")
    summary_lines.append(f"TOTAL elapsed={time.time() - started:.1f}s")
    summary_lines.append(f"jsonl={out_path}")
    summary_path.write_text("\n".join(summary_lines) + "\n")

    print(f"\n{tag('final', bold=False)} elapsed={time.time() - started:.1f}s")
    for key in strategy_names:
        flags = resolved_by_strategy.get(key, [])
        print(f"  {key}: resolved={sum(flags)}/{len(flags)}", flush=True)
    print(f"jsonl={out_path}")
    print(f"summary={summary_path}")


if __name__ == "__main__":
    main()
