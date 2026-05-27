"""Compare mini-SWE: no BudgetFlow vs BF Full vs BF Budget-Only × loose/tight caps.

Usage (from paper1/):
  PYTHONPATH=src:../external/mini-swe-agent/src python -m budgetflow.run_mini_swe_compare
  python -m budgetflow.run_mini_swe_compare --limit 5 --arms no_bf,budgetflow_full,budget_only
  python -m budgetflow.run_mini_swe_compare --budget tight   # BF arms only

Outputs:
  data/runs/compare_easy{n}_{tag}.jsonl
  data/runs/compare_easy{n}_{tag}.summary.log
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
MINI_SWE_SRC = REPO_ROOT.parent / "external" / "mini-swe-agent" / "src"
for path in (str(SRC), str(MINI_SWE_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from budgetflow.adapter.runner import run_mini_swe_task  # noqa: E402
from budgetflow.console_log import dim, fail_label, ok_label, paint, tag  # noqa: E402
from budgetflow.deepseek_backend import load_env_file  # noqa: E402
from budgetflow.lite_tasks import load_compare_easy_tasks  # noqa: E402
from budgetflow.run_mini_swe_baseline import run_baseline_task  # noqa: E402

RUNS_DIR = REPO_ROOT / "data" / "runs"
PILOT_SUMMARY_PATH = RUNS_DIR / "pilot_b0_summary.json"


def _load_budget_caps() -> tuple[float, float, float]:
    if not PILOT_SUMMARY_PATH.is_file():
        raise RuntimeError(
            f"Missing {PILOT_SUMMARY_PATH}. Run: python -m budgetflow.run_pilot"
        )
    summary = json.loads(PILOT_SUMMARY_PATH.read_text())
    m = float(summary["M"])
    loose = float(summary["loose_per_task"])
    tight = float(summary["tight_per_task"])
    return m, loose, tight


BF_STRATEGIES = ("budgetflow_full", "budget_only")
BUDGET_ARMS = ("loose", "tight")


def _run_arm(
    task,
    *,
    arm: str,
    strategy: str,
    budget_arm: str | None,
    step_limit: int,
    budget_caps: dict[str, float],
) -> dict:
    run_key = f"{strategy}" if budget_arm is None else f"{strategy}_{budget_arm}"
    started = time.time()
    if arm == "no_bf":
        record = run_baseline_task(task, step_limit=step_limit)
        record["arm"] = arm
        record["strategy"] = "all_pro"
        record["budget_arm"] = "none"
        record["budget_cap"] = None
        record["backend_picks"] = ["deepseek_pro"]
        record["violations"] = []
    else:
        cap = budget_caps[budget_arm or "loose"]
        result = run_mini_swe_task(
            task,
            strategy=strategy,
            budget_per_task=cap,
            step_limit=step_limit,
        )
        record = {
            "instance_id": result.instance_id,
            "arm": arm,
            "strategy": result.strategy,
            "budget_arm": budget_arm,
            "budget_cap": cap,
            "harness_resolved": result.harness_resolved,
            "patch_extracted": bool(result.patch_text),
            "exit_status": result.exit_status,
            "total_cost": result.total_cost,
            "backend_picks": list(result.backend_picks),
            "llm_turns": result.llm_turns,
            "violations": list(result.violations),
            "detail": result.harness_detail,
        }
    record["elapsed_s"] = round(time.time() - started, 1)
    record["run_key"] = run_key
    return record


def _append_summary(lines: list[str], record: dict, *, index: int, total: int) -> None:
    status = "OK" if record["harness_resolved"] else "FAIL"
    cap = record.get("budget_cap")
    cap_s = "none" if cap is None else f"{cap:.1f}"
    lines.append(
        f"[{index}/{total}] DONE {record['run_key']} {record['instance_id']} {status} "
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


def _build_run_plan(arms: tuple[str, ...], budgets: tuple[str, ...]) -> list[tuple[str, str, str | None]]:
    plan: list[tuple[str, str, str | None]] = []
    for arm in arms:
        if arm == "no_bf":
            plan.append((arm, "all_pro", None))
            continue
        if arm not in BF_STRATEGIES:
            raise ValueError(f"unknown arm {arm!r}; use no_bf, budgetflow_full, budget_only")
        for budget_arm in budgets:
            plan.append((arm, arm, budget_arm))
    return plan


def main() -> None:
    load_env_file()
    parser = argparse.ArgumentParser(description="mini-SWE compare: no BF vs BF Full vs BF Only")
    parser.add_argument("--limit", type=int, default=5, help="easy sympy tasks (max 5)")
    parser.add_argument(
        "--arms",
        default="no_bf,budgetflow_full,budget_only",
        help="comma-separated: no_bf, budgetflow_full, budget_only",
    )
    parser.add_argument(
        "--budget",
        default="both",
        choices=("loose", "tight", "both"),
        help="budget cap for BF arms (no_bf ignores)",
    )
    parser.add_argument("--step-limit", type=int, default=250)
    args = parser.parse_args()

    arms = tuple(part.strip() for part in args.arms.split(",") if part.strip())
    if args.budget == "both":
        budgets: tuple[str, ...] = BUDGET_ARMS
    else:
        budgets = (args.budget,)

    tasks = load_compare_easy_tasks(args.limit)
    plan = _build_run_plan(arms, budgets)
    m, loose_per_task, tight_per_task = _load_budget_caps()
    budget_caps = {"loose": loose_per_task, "tight": tight_per_task}

    tag_parts = ["_".join(arms), args.budget if "no_bf" not in arms or len(arms) > 1 else ""]
    run_tag = "_".join(part for part in tag_parts if part) or "default"
    out_path = RUNS_DIR / f"compare_easy{len(tasks)}_{run_tag}.jsonl"
    summary_path = RUNS_DIR / f"compare_easy{len(tasks)}_{run_tag}.summary.log"

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    total_runs = len(tasks) * len(plan)
    print(
        f"{tag('compare', color='\033[95m')} n={len(tasks)} runs={total_runs} "
        f"arms={arms} budget={budgets} "
        f"M={m:.4f} loose={loose_per_task:.4f} tight={tight_per_task:.4f}",
        flush=True,
    )
    print(f"{dim('tasks=' + ','.join(t.instance_id for t in tasks))}", flush=True)
    print(f"{dim('out=' + str(out_path))}", flush=True)

    summary_lines = [
        f"compare_easy n={len(tasks)} arms={arms} budget={budgets}",
        f"pilot M={m:.4f} loose={loose_per_task:.4f} tight={tight_per_task:.4f}",
        f"tasks={[t.instance_id for t in tasks]}",
        "",
    ]
    resolved_by_key: dict[str, list[bool]] = {}
    started = time.time()
    run_index = 0

    with out_path.open("w") as handle:
        for task in tasks:
            for arm, strategy, budget_arm in plan:
                run_index += 1
                run_key = f"{strategy}" if budget_arm is None else f"{strategy}_{budget_arm}"
                banner = paint(f"{'=' * 8} RUN {run_index}/{total_runs} {'=' * 8}", "\033[1m", "\033[95m")
                print(f"\n{banner}", flush=True)
                print(
                    f"{tag('start')} {task.instance_id} arm={arm} budget={budget_arm or 'none'}",
                    flush=True,
                )
                summary_lines.append(
                    f"[{run_index}/{total_runs}] START {run_key} {task.instance_id}"
                )
                record = _run_arm(
                    task,
                    arm=arm,
                    strategy=strategy,
                    budget_arm=budget_arm,
                    step_limit=args.step_limit,
                    budget_caps=budget_caps,
                )
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                _append_summary(summary_lines, record, index=run_index, total=total_runs)
                resolved_by_key.setdefault(run_key, []).append(record["harness_resolved"])
                status = ok_label("PASS") if record["harness_resolved"] else fail_label("FAIL")
                print(
                    f"{tag('done')} {run_key} {task.instance_id} {status} "
                    f"turns={record.get('llm_turns')} cost={record.get('total_cost')} "
                    f"elapsed={record['elapsed_s']}s",
                    flush=True,
                )

    summary_lines.append("")
    summary_lines.append("=== RESOLVED BY ARM ===")
    for key, flags in sorted(resolved_by_key.items()):
        summary_lines.append(f"{key}: {sum(flags)}/{len(flags)}")
    summary_lines.append(f"TOTAL elapsed={time.time() - started:.1f}s")
    summary_lines.append(f"jsonl={out_path}")
    summary_path.write_text("\n".join(summary_lines) + "\n")

    print(f"\n{tag('final', color='\033[93m')} elapsed={time.time() - started:.1f}s")
    for key, flags in sorted(resolved_by_key.items()):
        print(f"  {key}: resolved={sum(flags)}/{len(flags)}", flush=True)
    print(f"jsonl={out_path}")
    print(f"summary={summary_path}")


if __name__ == "__main__":
    main()
