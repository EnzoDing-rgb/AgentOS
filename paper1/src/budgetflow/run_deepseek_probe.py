"""DeepSeek capability probe: flash (chat) vs pro (reasoner), uncapped mini-SWE.

Parallelism:
  - Each tier (flash / pro) is a separate policy → run in parallel via --tier-jobs.
  - Tasks within one tier are always serial (shared diagnostic, same as BF compare).

Usage:
  python -u -m budgetflow.run_deepseek_probe --smoke-only
  python -u -m budgetflow.run_deepseek_probe --tier flash,pro --tier-jobs 2 --limit 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
MINI_SWE_SRC = REPO_ROOT.parent / "external" / "mini-swe-agent" / "src"
for path in (str(SRC), str(MINI_SWE_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from budgetflow.console_log import bold, dim, format_run_verdict, status_fail, status_pass, tag  # noqa: E402
from budgetflow.deepseek_backend import ensure_direct_api, load_env_file  # noqa: E402
from budgetflow.defaults import DEEPSEEK_FLASH_MODEL, DEEPSEEK_PRO_MODEL  # noqa: E402
from budgetflow.lite_tasks import load_compare_easy_tasks  # noqa: E402
from budgetflow.run_mini_swe_baseline import run_baseline_task  # noqa: E402

RUNS_DIR = REPO_ROOT / "data" / "runs" / "sweeps"

TIER_MODELS: dict[str, str] = {
    "flash": DEEPSEEK_FLASH_MODEL,
    "pro": DEEPSEEK_PRO_MODEL,
}


def _resolve_model(tier: str, explicit: str | None) -> str:
    if explicit:
        return explicit if "/" in explicit else f"deepseek/{explicit}"
    if tier in TIER_MODELS:
        return TIER_MODELS[tier]
    raise ValueError(f"unknown tier {tier!r}; use flash, pro, or --model deepseek/...")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeepSeek flash/pro probe on compare_easy")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--step-limit", type=int, default=150)
    parser.add_argument(
        "--tier-jobs",
        type=int,
        default=2,
        help="parallel tiers (flash vs pro); tasks stay serial inside each tier",
    )
    parser.add_argument(
        "--tier",
        type=str,
        default="flash,pro",
        help="flash=deepseek-chat, pro=deepseek-reasoner (comma-separated)",
    )
    parser.add_argument("--model", type=str, default=None, help="override litellm model id (single-tier only)")
    parser.add_argument("--out-stem", type=str, default=None)
    parser.add_argument("--smoke-only", action="store_true", help="delegate to run_deepseek_smoke")
    parser.add_argument("--heartbeat", type=float, default=30.0)
    parser.add_argument("--trace-verbose", action="store_true")
    return parser.parse_args()


def _print_record(
    rec: dict,
    *,
    index: int,
    total: int,
    tier: str,
    print_lock: threading.Lock | None,
) -> None:
    gold = rec.get("agent_gold_files") or rec.get("gold_files") or ["-"]
    gold_file = gold[0] if isinstance(gold, list) and gold else "-"
    resolved = bool(rec.get("harness_resolved"))
    banner = status_pass(f"PASS [{index}/{total}]") if resolved else status_fail(f"FAIL [{index}/{total}]")
    lines = [
        f"{banner} tier={bold(tier)} {rec['instance_id']} "
        f"turns={rec.get('llm_turns')} cost={rec.get('total_cost')} elapsed={rec.get('elapsed_s')}s "
        f"exit={rec.get('exit_status')}",
        f"  {format_run_verdict(harness_resolved=resolved, patch_extracted=rec.get('patch_extracted', False), gold_edited=bool(rec.get('agent_gold_edited')), gold_file=str(gold_file), detail=str(rec.get('detail', '')))}",
    ]
    if print_lock:
        with print_lock:
            for line in lines:
                print(line, flush=True)
    else:
        for line in lines:
            print(line, flush=True)


def _run_tier_serial(
    tier: str,
    model: str,
    tasks,
    *,
    step_limit: int,
    heartbeat_s: float,
    trace_console: str,
    print_lock: threading.Lock | None,
) -> list[dict]:
    def _log(msg: str) -> None:
        if print_lock:
            with print_lock:
                print(msg, flush=True)
        else:
            print(msg, flush=True)

    _log(
        f"\n{tag('batch', bold=False)} tier={bold(tier)} model={model} tasks={len(tasks)} "
        f"mode=serial_tasks worktree=per_tier"
    )
    _log(dim("tasks=" + ",".join(t.instance_id for t in tasks)))

    records: list[dict] = []
    label = f"deepseek_{tier}"
    for i, task in enumerate(tasks, 1):
        t0 = time.time()
        rec = run_baseline_task(
            task,
            step_limit=step_limit,
            model_name=model,
            strategy_label=label,
            trace_console=trace_console,  # type: ignore[arg-type]
            heartbeat_s=heartbeat_s,
            workspace_key=f"{label}_{task.instance_id}",
        )
        rec["elapsed_s"] = round(time.time() - t0, 1)
        rec["probe_tier"] = tier
        rec["probe_model"] = model
        rec["probe_kind"] = "deepseek_uncapped"
        records.append(rec)
        _print_record(rec, index=i, total=len(tasks), tier=tier, print_lock=print_lock)
    return records


def _run_tier_pipeline(
    tier: str,
    model: str,
    tasks,
    *,
    step_limit: int,
    heartbeat_s: float,
    trace_console: str,
    out_stem: str | None,
    print_lock: threading.Lock | None,
) -> dict:
    stem = out_stem or f"deepseek_{tier}_n{len(tasks)}"
    out_path = RUNS_DIR / f"{stem}.jsonl"
    summary_path = RUNS_DIR / f"{stem}.summary.log"

    records = _run_tier_serial(
        tier,
        model,
        tasks,
        step_limit=step_limit,
        heartbeat_s=heartbeat_s,
        trace_console=trace_console,
        print_lock=print_lock,
    )
    resolved = sum(1 for r in records if r.get("harness_resolved"))
    costs = [float(r.get("total_cost") or 0) for r in records]

    with out_path.open("w") as handle:
        for rec in records:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")

    summary_lines = [
        f"=== DeepSeek probe tier={tier} model={model} ===",
        f"resolved {resolved}/{len(tasks)}",
        f"per_task_costs (mini-SWE agent.cost) {costs}",
        f"total_cost_sum {sum(costs):.2f}",
        f"avg_turns {sum(int(r.get('llm_turns') or 0) for r in records) / max(1, len(records)):.1f}",
        "",
    ]
    for rec in records:
        status = "PASS" if rec.get("harness_resolved") else "FAIL"
        summary_lines.append(
            f"  {rec['instance_id']} {status} turns={rec.get('llm_turns')} cost={rec.get('total_cost')} "
            f"exit={rec.get('exit_status')}"
        )
    summary_lines.append(f"jsonl={out_path}")
    summary_path.write_text("\n".join(summary_lines) + "\n")

    msg = (
        f"{tag('summary', bold=False)} tier={tier} resolved={resolved}/{len(tasks)} "
        f"total_cost={sum(costs):.2f} -> {out_path}"
    )
    if print_lock:
        with print_lock:
            print(msg, flush=True)
    else:
        print(msg, flush=True)

    return {
        "tier": tier,
        "model": model,
        "resolved": f"{resolved}/{len(tasks)}",
        "costs": costs,
        "total_cost": sum(costs),
    }


def main() -> None:
    load_env_file()
    ensure_direct_api()
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY missing in .env")
    if not os.environ.get("NO_COLOR"):
        os.environ.setdefault("FORCE_COLOR", "1")

    args = _parse_args()
    if args.smoke_only:
        from budgetflow.run_deepseek_smoke import main as smoke_main  # noqa: E402

        sys.argv = ["run_deepseek_smoke", "--tier", args.tier, "--step-limit", str(min(5, args.step_limit))]
        smoke_main()
        return

    tiers = [t.strip() for t in args.tier.split(",") if t.strip()]
    unknown = [t for t in tiers if t not in TIER_MODELS]
    if unknown:
        raise SystemExit(f"unknown tier {unknown}; use flash, pro")

    tasks = load_compare_easy_tasks(args.limit)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    trace_level = "verbose" if args.trace_verbose else "milestones"
    tier_jobs = min(max(1, args.tier_jobs), len(tiers))
    print_lock = threading.Lock() if tier_jobs > 1 else None

    print(
        f"{tag('probe', bold=False)} tiers={tiers} tasks={len(tasks)} tier_jobs={tier_jobs} "
        f"mode=parallel_tiers_serial_tasks heartbeat={args.heartbeat}s",
        flush=True,
    )
    print(dim("tasks=" + ",".join(t.instance_id for t in tasks)), flush=True)

    tier_specs = []
    for tier in tiers:
        model = _resolve_model(tier, args.model if len(tiers) == 1 else None)
        stem = (args.out_stem or f"deepseek_{tier}_n{len(tasks)}") if len(tiers) == 1 else None
        tier_specs.append((tier, model, stem))

    matrix: list[dict] = []
    if tier_jobs <= 1:
        for tier, model, stem in tier_specs:
            matrix.append(
                _run_tier_pipeline(
                    tier,
                    model,
                    tasks,
                    step_limit=args.step_limit,
                    heartbeat_s=args.heartbeat,
                    trace_console=trace_level,
                    out_stem=stem,
                    print_lock=print_lock,
                )
            )
    else:
        with ThreadPoolExecutor(max_workers=tier_jobs) as pool:
            futures = {
                pool.submit(
                    _run_tier_pipeline,
                    tier,
                    model,
                    tasks,
                    step_limit=args.step_limit,
                    heartbeat_s=args.heartbeat,
                    trace_console=trace_level,
                    out_stem=stem,
                    print_lock=print_lock,
                ): tier
                for tier, model, stem in tier_specs
            }
            for future in as_completed(futures):
                matrix.append(future.result())

    matrix.sort(key=lambda r: r["tier"])
    print(f"\n{tag('matrix', bold=False)} DeepSeek flash vs pro (agent.cost):", flush=True)
    print(f"{'tier':<8} {'resolved':<10} {'total_cost':>12} model", flush=True)
    print("-" * 60, flush=True)
    for row in matrix:
        print(f"{row['tier']:<8} {row['resolved']:<10} {row['total_cost']:>12.2f} {row['model']}", flush=True)
    print(f"\n{dim(f'elapsed={time.time() - started:.1f}s')}", flush=True)


if __name__ == "__main__":
    main()
