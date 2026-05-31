"""Tier capability probe: 5 compare_easy tasks × T1/T2/T3 (all_flash / all_tier2 / all_pro).

Uncapped governor budget — measures resolve rate and governor cost per tier.

Usage (from paper1/):
  PYTHONPATH=src:../external/mini-swe-agent/src python -u -m budgetflow.run_tier_probe

Writes:
  data/runs/tier_probe.jsonl
  data/runs/tier_probe.summary.log
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
MINI_SWE_SRC = REPO_ROOT.parent / "external" / "mini-swe-agent" / "src"
for path in (str(SRC), str(MINI_SWE_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from budgetflow.adapter.runner import run_mini_swe_task  # noqa: E402
from budgetflow.console_log import format_run_verdict, status_fail, status_pass, tag  # noqa: E402
from budgetflow.deepseek_backend import load_env_file  # noqa: E402
from budgetflow.defaults import TIER1_MODEL, TIER2_MODEL, TIER3_MODEL  # noqa: E402
from budgetflow.heartbeat import run_with_heartbeat  # noqa: E402
from budgetflow.lite_tasks import load_compare_easy_tasks  # noqa: E402
from budgetflow.litellm_quiet import configure_litellm_quiet  # noqa: E402

RUNS_DIR = REPO_ROOT / "data" / "runs"
UNCAPPED_BUDGET = 1_000_000.0
PROBE_STEP_LIMIT = 80  # cap wander; tier probe compares resolve under generous budget
PROBE_HEARTBEAT_S = 45.0

PROBE_STRATEGIES: tuple[tuple[str, str, str], ...] = (
    ("all_flash_t1", "all_flash", TIER1_MODEL),
    ("all_tier2_t2", "all_tier2", TIER2_MODEL),
    ("all_pro_t3", "all_pro", TIER3_MODEL),
)


def _summarize(records: list[dict]) -> str:
    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for row in records:
        by_strategy[row["strategy_label"]].append(row)

    lines = [
        "=== Tier capability probe ===",
        f"T1={TIER1_MODEL}  T2={TIER2_MODEL}  T3={TIER3_MODEL}",
        f"budget=uncapped ({UNCAPPED_BUDGET:.0f} governor units/task)",
        "",
    ]
    for label, routing, model in PROBE_STRATEGIES:
        rows = by_strategy.get(label, [])
        if not rows:
            continue
        resolved = sum(1 for r in rows if r["harness_resolved"])
        total_cost = sum(float(r["total_cost"]) for r in rows)
        turns = sum(int(r["llm_turns"]) for r in rows)
        lines.append(f"--- {label} ({model}) routing={routing} ---")
        lines.append(f"  resolved: {resolved}/{len(rows)}")
        lines.append(f"  governor_cost_sum: {total_cost:.2f}  avg: {total_cost / len(rows):.2f}")
        lines.append(f"  llm_turns_sum: {turns}  avg: {turns / len(rows):.1f}")
        for r in rows:
            mark = status_pass("PASS") if r["harness_resolved"] else status_fail("FAIL")
            lines.append(
                f"  {r['instance_id']:24} {mark} cost={float(r['total_cost']):8.2f} "
                f"turns={int(r['llm_turns']):3} exit={r.get('exit_status', '?')}"
            )
        lines.append("")

    t1 = by_strategy.get("all_flash_t1", [])
    t2 = by_strategy.get("all_tier2_t2", [])
    t3 = by_strategy.get("all_pro_t3", [])
    if t1 and t2 and t3:
        r1 = sum(1 for r in t1 if r["harness_resolved"]) / len(t1)
        r2 = sum(1 for r in t2 if r["harness_resolved"]) / len(t2)
        r3 = sum(1 for r in t3 if r["harness_resolved"]) / len(t3)
        mono = r1 <= r2 <= r3
        lines.append(
            f"resolve_rate: T1={r1:.0%}  T2={r2:.0%}  T3={r3:.0%}  "
            f"monotonic T1≤T2≤T3: {'YES' if mono else 'NO — review tier mapping'}"
        )
    return "\n".join(lines)


def main() -> None:
    configure_litellm_quiet()
    load_env_file()
    tasks = load_compare_easy_tasks(5)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUNS_DIR / "tier_probe.jsonl"
    summary_path = RUNS_DIR / "tier_probe.summary.log"

    print(f"{tag('probe')} tier probe: {len(tasks)} tasks × 3 tiers, uncapped budget", flush=True)
    print(
        f"step_limit={PROBE_STEP_LIMIT} per run | agent heartbeat=30s | batch heartbeat={PROBE_HEARTBEAT_S:.0f}s",
        flush=True,
    )
    print("note: agent explores repo (explore/LOC) before edit — many steps != hung", flush=True)
    print(f"tasks={[t.instance_id for t in tasks]}", flush=True)
    for label, routing, model in PROBE_STRATEGIES:
        print(f"  {label}: routing={routing} model={model}", flush=True)

    records: list[dict] = []
    started = time.time()
    total_runs = len(tasks) * len(PROBE_STRATEGIES)
    run_idx = 0

    with out_path.open("w") as handle:
        for label, routing, _model in PROBE_STRATEGIES:
            for task in tasks:
                run_idx += 1
                print(
                    f"[{run_idx}/{total_runs}] START {label} {task.instance_id}",
                    flush=True,
                )
                run_started = time.time()
                batch_state = {"run": run_idx, "total": total_runs, "label": label, "task": task.instance_id}

                def _run_task():
                    return run_mini_swe_task(
                        task,
                        strategy=routing,
                        strategy_label=label,
                        budget_per_task=UNCAPPED_BUDGET,
                        step_limit=PROBE_STEP_LIMIT,
                        trace_console="heartbeat",
                    )

                result = run_with_heartbeat(
                    f"probe [{run_idx}/{total_runs}] {label}",
                    _run_task,
                    interval_s=PROBE_HEARTBEAT_S,
                    status_fn=lambda: f"task={batch_state['task']} tier={batch_state['label']}",
                )
                record = {
                    "instance_id": result.instance_id,
                    "strategy_label": label,
                    "routing": routing,
                    "model": _model,
                    "harness_resolved": result.harness_resolved,
                    "total_cost": result.total_cost,
                    "llm_turns": result.llm_turns,
                    "backend_picks": list(result.backend_picks),
                    "exit_status": result.exit_status,
                    "exit_reason": result.exit_reason,
                    "detail": result.harness_detail,
                    "elapsed_s": round(time.time() - run_started, 1),
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                records.append(record)
                verdict = format_run_verdict(result.harness_resolved)
                print(
                    f"[{run_idx}/{total_runs}] DONE {label} {task.instance_id} {verdict} "
                    f"cost={result.total_cost:.2f} turns={result.llm_turns} "
                    f"elapsed={record['elapsed_s']}s",
                    flush=True,
                )

    summary = _summarize(records)
    summary_path.write_text(summary + "\n")
    elapsed = round(time.time() - started, 1)
    print(f"\n{summary}", flush=True)
    print(f"\nFINAL elapsed={elapsed}s jsonl={out_path} summary={summary_path}", flush=True)


if __name__ == "__main__":
    main()
