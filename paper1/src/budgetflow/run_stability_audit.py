"""all_pro stability audit: 7 tasks × 3 rounds, T3-only, uncapped.

Usage:
  cd paper1 && PYTHONPATH=src:../external/mini-swe-agent/src python -m budgetflow.run_stability_audit
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
MINI_SWE_SRC = REPO_ROOT.parent / "external" / "mini-swe-agent" / "src"
for path in (str(SRC), str(MINI_SWE_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from budgetflow.deepseek_backend import ensure_aicode007_proxy, load_env_file
from budgetflow.console_log import dim, fail_label, ok_label, paint, tag
from budgetflow.defaults import TIER3_MODEL
from budgetflow.failure_classification import build_forensic_summary, classify_failure
from budgetflow.heartbeat import run_with_heartbeat
from budgetflow.lite_tasks import load_swebench_lite_tasks
from budgetflow.local_harness import clone_or_checkout, evaluate_local_harness
from budgetflow.run_mini_swe_baseline import _harness_record, _resolve_model_profile

RUNS_DIR = REPO_ROOT / "data" / "runs"

AUDIT_TASKS = (
    "sympy__sympy-14774",
    "django__django-10924",
    "sympy__sympy-18189",
    "sympy__sympy-18057",
    "sympy__sympy-18621",
    "sympy__sympy-20212",
    "sympy__sympy-13480",
)
ROUNDS = 3


def _record_key(record: dict) -> tuple[int, str]:
    return int(record["round"]), str(record["instance_id"])


def _load_existing(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    records: list[dict] = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"{tag('warn', bold=False)} skip malformed jsonl line in {path}", flush=True)
    return records


def _append_record(path: Path, record: dict, lock: threading.Lock) -> None:
    with lock:
        with path.open("a") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _print_done(record: dict, lock: threading.Lock | None = None) -> None:
    status = ok_label("PASS") if record["harness_resolved"] else fail_label("FAIL")
    message = (
        f"{tag('done')} {record['instance_id']} r{record['round']} {status} "
        f"${record.get('total_cost', 0):.4f} {record.get('llm_turns', 0)}t "
        f"exit={record['exit_status']} "
        f"elapsed={record['elapsed_s']}s"
    )
    if lock:
        with lock:
            print(message, flush=True)
    else:
        print(message, flush=True)


def run_one(task, model_name: str, round_idx: int, *, heartbeat_s: float = 30.0) -> dict:
    from minisweagent.config import get_config_from_spec
    from minisweagent.environments.local import LocalEnvironment
    from minisweagent.exceptions import Submitted
    from minisweagent.models import get_model
    from minisweagent.utils.serialize import recursive_merge

    from budgetflow.litellm_quiet import configure_litellm_quiet
    from budgetflow.run_trace import (
        RunTraceLogger,
        TraceConsoleLevel,
        TracedDefaultAgent,
        patch_local_swebench_config,
    )

    configure_litellm_quiet()
    ensure_aicode007_proxy()
    profile = _resolve_model_profile(model_name)
    ws_key = f"stability_{model_name.replace('/', '_')}_{task.instance_id}_r{round_idx}"

    def _prep():
        return clone_or_checkout(task, workspace_key=ws_key)

    repo_dir = run_with_heartbeat(f"{task.instance_id}/r{round_idx}/prep", _prep, interval_s=heartbeat_s)
    print(f"{tag('prep', bold=False)} repo ready {dim(str(repo_dir))}", flush=True)

    trace_dir = RUNS_DIR / f"stability_trace_{task.instance_id}_r{round_idx}"
    trace = RunTraceLogger(
        instance_id=task.instance_id,
        repo_dir=repo_dir,
        trace_dir=trace_dir,
        target_files=task.gold_files,
        strategy_label="all_pro_stability",
        console_level="milestones",
    )

    swebench_config = MINI_SWE_SRC / "minisweagent" / "config" / "benchmarks" / "swebench.yaml"
    config = recursive_merge(
        get_config_from_spec(swebench_config),
        {
            "agent": {"cost_limit": 0.0, "step_limit": 250, "confirm_exit": False},
            "environment": {"timeout": 120},
            "model": {
                "model_name": profile["model_name"],
                "model_kwargs": {
                    "api_base": profile["api_base"],
                    "api_key": profile["api_key"],
                    "temperature": 0.0,
                    "parallel_tool_calls": True,
                    "drop_params": True,
                    "extra_body": {"thinking": {"type": "disabled"}},
                },
                "cost_tracking": "ignore_errors",
            },
        },
    )
    config = patch_local_swebench_config(config, repo_dir)
    agent_cfg = dict(config.get("agent", {}))
    agent_cfg["output_path"] = trace_dir / "trajectory.json"

    model = get_model(config=config.get("model", {}))
    env = LocalEnvironment(cwd=str(repo_dir), timeout=config.get("environment", {}).get("timeout", 120))
    run_started = time.time()
    agent = TracedDefaultAgent(model, env, trace=trace, run_started=run_started, **agent_cfg)

    patch_text: str | None = None
    exit_status = "unknown"

    def _run():
        return agent.run(task.problem_statement)

    try:
        exit_info = run_with_heartbeat(
            f"{task.instance_id} [r{round_idx}]",
            _run,
            interval_s=heartbeat_s,
            status_fn=lambda: trace.heartbeat_status(agent, elapsed_s=time.time() - run_started),
        )
        exit_status = str(exit_info.get("exit_status", "unknown"))
        patch_text = exit_info.get("submission") or None
    except Submitted as submitted:
        message = submitted.args[0] if submitted.args else {}
        exit_status = message.get("extra", {}).get("exit_status", "Submitted")
        patch_text = message.get("extra", {}).get("submission") or message.get("content")
    except Exception as exc:  # noqa: BLE001
        exit_status = type(exc).__name__

    harness = evaluate_local_harness(task, patch_text, workspace_key=ws_key)
    trace.log_harness_result(resolved=harness.harness_resolved, detail=harness.detail)
    record = _harness_record(task, harness, patch_text=patch_text, trace_dir=trace_dir)
    record["exit_status"] = exit_status
    record["llm_turns"] = agent.n_calls
    record["total_cost"] = agent.cost
    record["model"] = getattr(getattr(model, "config", None), "model_name", str(model))
    record["strategy_label"] = "all_pro_stability"
    record["round"] = round_idx
    record["backend_picks"] = ["tier3"] * agent.n_calls
    record["turn_trace_count"] = trace._steps_logged
    record["failure_class"] = classify_failure(record)
    record["forensic_summary"] = build_forensic_summary(record)
    return record


def _run_round(
    round_idx: int,
    tasks: list,
    *,
    model_name: str,
    out_path: Path,
    completed: set[tuple[int, str]],
    write_lock: threading.Lock,
    print_lock: threading.Lock | None,
    total: int,
) -> list[dict]:
    """Run one repeat lane serially.

    Parallelism is across round lanes; tasks inside a lane stay sequential so
    each repeat is comparable and avoids uncontrolled same-policy fanout.
    """
    records: list[dict] = []
    _m = "\033[95m"
    _b = "\033[1m"
    _cyan = "\033[96m"
    for task_idx, task in enumerate(tasks, start=1):
        key = (round_idx, task.instance_id)
        idx = (round_idx - 1) * len(tasks) + task_idx
        if key in completed:
            message = f"{tag('skip', bold=False)} {task.instance_id} r{round_idx} already complete"
            if print_lock:
                with print_lock:
                    print(message, flush=True)
            else:
                print(message, flush=True)
            continue

        start_msg = (
            f"\n{paint(f'==== R{round_idx} TASK {task_idx}/{len(tasks)} [{idx}/{total}] ====', _b, _m)}\n"
            f"{tag('start')} {paint(task.instance_id, _b, _cyan)} round={round_idx}"
        )
        if print_lock:
            with print_lock:
                print(start_msg, flush=True)
        else:
            print(start_msg, flush=True)

        run_started = time.time()
        record = run_one(task, model_name, round_idx)
        record["elapsed_s"] = round(time.time() - run_started, 1)
        record["instance_id"] = task.instance_id
        record["round"] = round_idx
        _append_record(out_path, record, write_lock)
        records.append(record)
        _print_done(record, print_lock)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(
        description="all_pro stability audit: rounds run in parallel, tasks inside each round stay serial",
    )
    parser.add_argument("--jobs", type=int, default=3, help="parallel repeat lanes; each lane runs tasks serially")
    parser.add_argument("--rounds", type=int, default=ROUNDS)
    parser.add_argument("--resume", action="store_true", help="append and skip completed (round, task) rows")
    parser.add_argument(
        "--ids",
        type=str,
        default=None,
        help="comma-separated task ids; default fixed 7-task audit pool",
    )
    parser.add_argument("--out", type=str, default=None, help="explicit output jsonl path")
    args = parser.parse_args()

    load_env_file()
    profile = _resolve_model_profile(TIER3_MODEL)
    task_ids = tuple(s.strip() for s in args.ids.split(",") if s.strip()) if args.ids else AUDIT_TASKS
    tasks = load_swebench_lite_tasks(instance_ids=task_ids)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    safe_model = profile["model_name"].replace("/", "_").replace(":", "_")
    out_path = Path(args.out) if args.out else RUNS_DIR / f"stability_audit_{safe_model}_n{len(tasks)}x{args.rounds}.jsonl"

    _m = '\033[95m'
    _b = '\033[1m'
    _w = '\033[97m'
    jobs = max(1, min(args.jobs, args.rounds))
    print(
        f"{tag('audit', color=_m)} all_pro stability "
        f"tasks={paint(str(len(tasks)), _b, _w)} rounds={args.rounds} jobs={jobs} "
        f"model={dim(profile['model_name'])}"
    )
    print(f"{dim('output=' + str(out_path))}")
    print(f"{dim('parallelism=round lanes parallel; tasks serial inside each round')}")

    existing = _load_existing(out_path) if args.resume else []
    completed = {_record_key(r) for r in existing}
    if args.resume and existing:
        print(f"{tag('resume', bold=False)} loaded {len(existing)} rows; skip {len(completed)} completed keys")
    elif out_path.exists():
        out_path.unlink()

    results: list[dict] = list(existing)
    total = len(tasks) * args.rounds
    started = time.time()
    write_lock = threading.Lock()
    print_lock = threading.Lock() if jobs > 1 else None

    if jobs <= 1:
        for round_idx in range(1, args.rounds + 1):
            results.extend(_run_round(
                round_idx,
                tasks,
                model_name=TIER3_MODEL,
                out_path=out_path,
                completed=completed,
                write_lock=write_lock,
                print_lock=print_lock,
                total=total,
            ))
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {
                pool.submit(
                    _run_round,
                    round_idx,
                    tasks,
                    model_name=TIER3_MODEL,
                    out_path=out_path,
                    completed=completed,
                    write_lock=write_lock,
                    print_lock=print_lock,
                    total=total,
                ): round_idx
                for round_idx in range(1, args.rounds + 1)
            }
            for future in as_completed(futures):
                round_idx = futures[future]
                try:
                    results.extend(future.result())
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"{tag('error', bold=False)} round={round_idx} "
                        f"{type(exc).__name__}: {exc}",
                        flush=True,
                    )
                    traceback.print_exception(type(exc), exc, exc.__traceback__)
                    raise

    resolved = sum(1 for r in results if r["harness_resolved"])
    elapsed = time.time() - started
    _yellow = '\033[93m'
    print(f"\n{tag('final', color=_yellow)} resolved={resolved}/{total} elapsed={elapsed:.0f}s")
    print(f"output={out_path}")

    # Per-task stability summary
    print(f"\n{paint('=== PER-TASK STABILITY ===', _b)}")
    by_task: defaultdict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_task[r["instance_id"]].append(r)
    for inst in task_ids:
        recs = by_task.get(inst, [])
        if not recs:
            print(f"  {inst}: NO DATA")
            continue
        passes = sum(1 for r in recs if r["harness_resolved"])
        costs = [r.get("total_cost", 0) for r in recs]
        turns = [r.get("llm_turns", 0) for r in recs]
        print(f"  {inst}: {passes}/{len(recs)} PASS  "
              f"cost=[{min(costs):.3f}-{max(costs):.3f}]  "
              f"turns=[{min(turns)}-{max(turns)}]  "
              f"exits={[r['exit_status'] for r in recs]}")


if __name__ == "__main__":
    main()
