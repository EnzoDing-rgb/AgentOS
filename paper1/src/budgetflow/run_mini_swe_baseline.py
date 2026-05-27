"""Run mini-SWE-agent baseline (no BudgetFlow) on local SWE-bench Lite tasks.

Usage:
  PYTHONPATH=src:../external/mini-swe-agent/src python src/budgetflow/run_mini_swe_baseline.py [limit] [instance_id]

Examples:
  python src/budgetflow/run_mini_swe_baseline.py 1          # default: sympy-20212 (easiest)
  python src/budgetflow/run_mini_swe_baseline.py 3          # 20212, 12171, 21614
  python src/budgetflow/run_mini_swe_baseline.py 1 sympy__sympy-11400 --step-limit 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
MINI_SWE_SRC = REPO_ROOT.parent / "external" / "mini-swe-agent" / "src"
for path in (str(SRC), str(MINI_SWE_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

from minisweagent.config import get_config_from_spec  # noqa: E402
from minisweagent.environments.local import LocalEnvironment  # noqa: E402
from minisweagent.exceptions import Submitted  # noqa: E402
from minisweagent.models import get_model  # noqa: E402
from minisweagent.utils.serialize import recursive_merge  # noqa: E402

from budgetflow.deepseek_backend import load_env_file  # noqa: E402
from budgetflow.defaults import DEEPSEEK_API_BASE, DEEPSEEK_PRO_MODEL  # noqa: E402
from budgetflow.heartbeat import run_with_heartbeat  # noqa: E402
from budgetflow.lite_tasks import load_smoke_tasks, load_swebench_lite_tasks  # noqa: E402
from budgetflow.local_harness import clone_or_checkout, evaluate_local_harness  # noqa: E402
from budgetflow.run_trace import (  # noqa: E402
    RunTraceLogger,
    TracedDefaultAgent,
    patch_local_swebench_config,
)

RUNS_DIR = REPO_ROOT / "data" / "runs"
SWEBENCH_CONFIG = MINI_SWE_SRC / "minisweagent" / "config" / "benchmarks" / "swebench.yaml"


def _load_agent_config(*, step_limit: int) -> dict:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY missing — add to repo root .env")
    return recursive_merge(
        get_config_from_spec(SWEBENCH_CONFIG),
        {
            "agent": {
                "cost_limit": 0.0,
                "step_limit": step_limit,
                "confirm_exit": False,
            },
            "environment": {
                "timeout": 120,
            },
            "model": {
                "model_name": DEEPSEEK_PRO_MODEL,
                "model_kwargs": {
                    "api_base": DEEPSEEK_API_BASE,
                    "api_key": api_key,
                    "temperature": 0.0,
                    "parallel_tool_calls": True,
                    "drop_params": True,
                    # Smoke/baseline: thinking off → ~3s/turn vs 30–90s with reasoning_effort=high
                "extra_body": {"thinking": {"type": "disabled"}},
                },
                "cost_tracking": "ignore_errors",
            },
        },
    )


def run_baseline_task(task, *, step_limit: int = 250) -> dict:
    def _prep_repo():
        return clone_or_checkout(task)

    repo_dir = run_with_heartbeat(f"{task.instance_id}/prep", _prep_repo, interval_s=30.0)
    print(f"[prep] repo ready {repo_dir}", flush=True)

    trace_dir = RUNS_DIR / f"trace_{task.instance_id}"
    trace = RunTraceLogger(
        instance_id=task.instance_id,
        repo_dir=repo_dir,
        trace_dir=trace_dir,
        target_files=task.gold_files,
    )
    print(f"[trace] steps={trace.steps_path} target_files={list(task.gold_files)}", flush=True)

    config = patch_local_swebench_config(_load_agent_config(step_limit=step_limit), repo_dir)
    agent_cfg = dict(config.get("agent", {}))
    agent_cfg["output_path"] = trace_dir / "trajectory.json"

    model_cfg = config.get("model", {})
    model = get_model(config=model_cfg)
    env = LocalEnvironment(cwd=str(repo_dir), timeout=config.get("environment", {}).get("timeout", 120))
    run_started = time.time()
    agent = TracedDefaultAgent(model, env, trace=trace, run_started=run_started, **agent_cfg)

    patch_text: str | None = None
    exit_status = "unknown"

    def _agent_run():
        return agent.run(task.problem_statement)

    try:
        exit_info = run_with_heartbeat(
            task.instance_id,
            _agent_run,
            interval_s=30.0,
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

    harness = evaluate_local_harness(task, patch_text)
    return {
        "instance_id": task.instance_id,
        "harness_resolved": harness.harness_resolved,
        "patch_extracted": bool(patch_text),
        "exit_status": exit_status,
        "detail": harness.detail,
        "llm_turns": agent.n_calls,
        "total_cost": agent.cost,
        "trace_dir": str(trace_dir),
        "trace_steps": str(trace.steps_path),
    }


def _select_tasks(limit: int, instance_id: str | None):
    if instance_id:
        return load_swebench_lite_tasks(instance_ids=(instance_id,))
    return load_smoke_tasks(limit)


def main() -> None:
    load_env_file()
    parser = argparse.ArgumentParser(description="mini-SWE baseline (no BudgetFlow)")
    parser.add_argument("limit", nargs="?", type=int, default=1)
    parser.add_argument("instance_id", nargs="?", default=None)
    parser.add_argument("--step-limit", type=int, default=250, help="Agent step cap (use 5 for quick API smoke)")
    args = parser.parse_args()

    tasks = _select_tasks(args.limit, args.instance_id)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUNS_DIR / f"mini_swe_baseline_n{len(tasks)}.jsonl"

    print(f"mini-SWE baseline: n={len(tasks)} model={DEEPSEEK_PRO_MODEL} cost_limit=0 step_limit={args.step_limit}")
    resolved = 0
    started = time.time()

    with out_path.open("w") as handle:
        for index, task in enumerate(tasks, start=1):
            print(f"[{index}/{len(tasks)}] START {task.instance_id}", flush=True)
            run_started = time.time()
            record = run_baseline_task(task, step_limit=args.step_limit)
            record["elapsed_s"] = round(time.time() - run_started, 1)
            handle.write(json.dumps(record) + "\n")
            if record["harness_resolved"]:
                resolved += 1
            status = "OK" if record["harness_resolved"] else "FAIL"
            print(
                f"[{index}/{len(tasks)}] DONE {task.instance_id} {status} "
                f"exit={record['exit_status']} turns={record.get('llm_turns')} "
                f"cost={record.get('total_cost')} elapsed={record['elapsed_s']}s",
                flush=True,
            )
            if record.get("detail"):
                print(f"  detail: {str(record['detail'])[:240]}", flush=True)
            if record.get("trace_steps"):
                print(f"  trace: {record['trace_steps']}", flush=True)

    print(f"\nFINAL resolved={resolved}/{len(tasks)} elapsed={time.time() - started:.1f}s")
    print(f"log={out_path}")
    if resolved == 0 and args.step_limit >= 20:
        sys.exit(1)


if __name__ == "__main__":
    main()
