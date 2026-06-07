"""Step B.0 budget pilot: uncapped all_pro on pilot tasks → freeze batch caps.

Usage:
  cd paper1 && PYTHONPATH=src:../external/mini-swe-agent/src python -m budgetflow.run_pilot

Writes:
  data/runs/pilot_b0.jsonl
  data/runs/pilot_b0_summary.json
  data/frozen_caps.json  (FROZEN — compare --read-frozen-caps loads this)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
MINI_SWE_SRC = REPO_ROOT.parent / "external" / "mini-swe-agent" / "src"
for path in (str(SRC), str(MINI_SWE_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from budgetflow.deepseek_backend import ensure_direct_api, load_env_file  # noqa: E402
from budgetflow.litellm_quiet import configure_litellm_quiet  # noqa: E402

load_env_file()
ensure_direct_api()
configure_litellm_quiet()
if not os.environ.get("NO_COLOR"):
    os.environ.setdefault("FORCE_COLOR", "1")

from budgetflow.adapter.runner import run_mini_swe_task  # noqa: E402
from budgetflow.console_log import (  # noqa: E402
    bold,
    dim,
    format_run_verdict,
    format_tier_pool_line,
    status_fail,
    status_pass,
    tag,
)
from budgetflow.defaults import (  # noqa: E402
    BUDGET_PRESSURE_INIT,
    PRESSURE_MAX,
    TIER1_MODEL,
    TIER2_MODEL,
    TIER3_DISPLAY,
    TIER3_MODEL,
)
from budgetflow.lite_tasks import (  # noqa: E402
    COMPARE_EASY_INSTANCE_IDS,
    load_pilot_tasks,
    load_swebench_lite_tasks,
)
from budgetflow.protocol_caps import derive_batch_caps, write_frozen_caps  # noqa: E402

RUNS_DIR = REPO_ROOT / "data" / "runs"
PINNED_COMMIT_PATH = REPO_ROOT.parent / "external" / "PINNED_COMMIT"
UNCAPPED_BUDGET = 1_000_000.0
PILOT_STEP_LIMIT = 150
PILOT_STRATEGY = "all_pro"
PILOT_STRATEGY_LABEL = "all_pro → T3 (strongest tier)"


def _read_pinned_commit() -> str:
    if PINNED_COMMIT_PATH.is_file():
        return PINNED_COMMIT_PATH.read_text().strip()
    mini_swe_dir = REPO_ROOT.parent / "external" / "mini-swe-agent"
    if (mini_swe_dir / ".git").exists():
        import subprocess

        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=mini_swe_dir, text=True).strip()
    return "unknown"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="B.0 budget pilot (all_pro, uncapped)")
    parser.add_argument("--jobs", type=int, default=3, help="parallel pilot tasks/worktrees (default: 3)")
    parser.add_argument("--limit", type=int, default=3, help="pilot task count when --instance-ids omitted")
    parser.add_argument("--step-limit", type=int, default=PILOT_STEP_LIMIT, help="agent step limit per task")
    parser.add_argument(
        "--instance-ids",
        type=str,
        default="",
        help="comma-separated instance ids (overrides default pilot task set)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.instance_ids.strip():
        task_ids = tuple(x.strip() for x in args.instance_ids.split(",") if x.strip())
        tasks = load_swebench_lite_tasks(instance_ids=task_ids)
    else:
        tasks = load_pilot_tasks(args.limit)

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUNS_DIR / "pilot_b0.jsonl"
    summary_path = RUNS_DIR / "pilot_b0_summary.json"

    print(f"{tag('pilot')} B.0 budget pilot — {len(tasks)} tasks × {bold(PILOT_STRATEGY)}", flush=True)
    print(f"  strategy: {bold(PILOT_STRATEGY_LABEL)}  model: {bold(TIER3_DISPLAY)}", flush=True)
    print(f"  pool: {format_tier_pool_line(include_t1=True)}", flush=True)
    print(
        f"  budget: uncapped  step_limit={args.step_limit}  heartbeat=30s  jobs={max(1, args.jobs)} (worktree)",
        flush=True,
    )
    print(f"  tasks: {dim(', '.join(t.instance_id for t in tasks))}", flush=True)
    records: list[dict] = []
    started = time.time()

    def _run_one(index: int, task):
        run_started = time.time()
        result = run_mini_swe_task(
            task,
            strategy=PILOT_STRATEGY,
            strategy_label=PILOT_STRATEGY_LABEL,
            budget_per_task=UNCAPPED_BUDGET,
            step_limit=args.step_limit,
            trace_console="heartbeat",
            workspace_key=f"pilot_{index}_{task.instance_id}",
        )
        return {
            "instance_id": result.instance_id,
            "strategy": result.strategy,
            "strategy_label": PILOT_STRATEGY_LABEL,
            "model": TIER3_MODEL,
            "harness_resolved": result.harness_resolved,
            "total_cost": result.total_cost,
            "llm_turns": result.llm_turns,
            "backend_picks": list(result.backend_picks),
            "exit_status": result.exit_status,
            "detail": result.harness_detail,
            "elapsed_s": round(time.time() - run_started, 1),
            "patch_extracted": bool(result.patch_text),
            "gold_edited": result.agent_gold_edited,
            "gold_file": (result.agent_gold_files[0] if result.agent_gold_files else "-"),
        }

    with out_path.open("w") as handle:
        total = len(tasks)
        for index, task in enumerate(tasks, start=1):
            print(
                f"\n{tag('start', bold=False)} [{index}/{total}] {bold(task.instance_id)} "
                f"strategy={PILOT_STRATEGY} model={TIER3_DISPLAY}",
                flush=True,
            )
        completed = 0
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            futures = {pool.submit(_run_one, idx, task): task for idx, task in enumerate(tasks, start=1)}
            for future in as_completed(futures):
                record = future.result()
                completed += 1
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                records.append(record)
                banner = status_pass(f"PASS [{completed}/{total}]") if record["harness_resolved"] else status_fail(
                    f"FAIL [{completed}/{total}]"
                )
                print(
                    f"{banner} {record['instance_id']} {PILOT_STRATEGY_LABEL} "
                    f"cost={record['total_cost']:.2f} turns={record['llm_turns']} elapsed={record['elapsed_s']}s",
                    flush=True,
                )
                print(
                    f"  {format_run_verdict(harness_resolved=record['harness_resolved'], patch_extracted=record['patch_extracted'], gold_edited=record['gold_edited'], gold_file=record['gold_file'], detail=record['detail'])}",
                    flush=True,
                )

    costs = [float(r["total_cost"]) for r in records]
    loose_n3, tight_n3 = derive_batch_caps(costs, 3)
    loose_n5, tight_n5 = derive_batch_caps(costs, 5)
    summary = {
        "pilot_task_ids": [t.instance_id for t in tasks],
        "pilot_instance_ids": [t.instance_id for t in tasks],
        "per_task_costs": costs,
        "loose_batch_n3": loose_n3,
        "tight_batch_n3": tight_n3,
        "loose_batch_n5": loose_n5,
        "tight_batch_n5": tight_n5,
        "pressure_max": PRESSURE_MAX,
        "budget_pressure_init": BUDGET_PRESSURE_INIT,
        "elapsed_s": round(time.time() - started, 1),
        "jsonl": str(out_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    caps_path = write_frozen_caps(
        per_task_costs=costs,
        pilot_records=records,
        pinned_commit=_read_pinned_commit(),
        compare_easy_ids=COMPARE_EASY_INSTANCE_IDS,
        pressure_init=BUDGET_PRESSURE_INIT,
        pressure_max=PRESSURE_MAX,
        tier_models=(TIER1_MODEL, TIER2_MODEL, TIER3_MODEL),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    print(
        f"\n{tag('pilot', bold=False)} FROZEN "
        f"loose_batch_n5={bold(f'{loose_n5:.4f}')} tight_batch_n5={bold(f'{tight_n5:.4f}')} "
        f"elapsed={summary['elapsed_s']}s",
        flush=True,
    )
    print(f"jsonl={out_path}")
    print(f"summary={summary_path}")
    print(f"frozen_caps={caps_path} (FROZEN)")


if __name__ == "__main__":
    main()
