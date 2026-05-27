"""Run mini-SWE-agent baseline (no BudgetFlow) on local SWE-bench Lite tasks.

Usage:
  cd paper1 && PYTHONPATH=src:../external/mini-swe-agent/src python -m budgetflow.run_mini_swe_baseline [limit] [instance_id]

Examples:
  python -m budgetflow.run_mini_swe_baseline 1          # default: sympy-20212 (easiest)
  python -m budgetflow.run_mini_swe_baseline 3          # 20212, 12171, 21614
  python -m budgetflow.run_mini_swe_baseline 1 sympy__sympy-11400 --step-limit 5
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
MINI_SWE_SRC = REPO_ROOT.parent / "external" / "mini-swe-agent" / "src"
for path in (str(SRC), str(MINI_SWE_SRC)):
    if path not in sys.path:
        sys.path.insert(0, path)

import argparse
import json
import os
import time

from minisweagent.config import get_config_from_spec  # noqa: E402
from minisweagent.environments.local import LocalEnvironment  # noqa: E402
from minisweagent.exceptions import Submitted  # noqa: E402
from minisweagent.models import get_model  # noqa: E402
from minisweagent.utils.serialize import recursive_merge  # noqa: E402

from budgetflow.deepseek_backend import load_env_file  # noqa: E402
from budgetflow.console_log import dim, fail_label, ok_label, paint, tag  # noqa: E402
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


def _harness_record(task, harness, *, patch_text: str | None, trace_dir: Path) -> dict:
    if patch_text and patch_text.strip():
        (trace_dir / "submitted.patch").write_text(patch_text if patch_text.endswith("\n") else patch_text + "\n")
    record = {
        "instance_id": task.instance_id,
        "harness_resolved": harness.harness_resolved,
        "patch_extracted": bool(patch_text),
        "detail": harness.detail,
        "fail_to_pass": list(task.fail_to_pass),
        "pass_to_pass": list(task.pass_to_pass[:5]),
        "test_patch_ok": harness.test_patch_ok,
        "fail_before": harness.fail_before,
        "model_patch_ok": harness.model_patch_ok,
        "fail_after": harness.fail_after,
        "pass_to_pass_ok": harness.pass_to_pass_passed,
        "trace_dir": str(trace_dir),
        "trace_steps": str(trace_dir / "steps.jsonl"),
        "submitted_patch": str(trace_dir / "submitted.patch") if patch_text else None,
    }
    return record


def _append_summary_line(lines: list[str], record: dict, *, index: int, total: int) -> None:
    status = "OK" if record["harness_resolved"] else "FAIL"
    lines.append(f"[{index}/{total}] DONE {record['instance_id']} {status} "
                 f"exit={record.get('exit_status', 'unknown')} turns={record.get('llm_turns')} "
                 f"cost={record.get('total_cost')} elapsed={record.get('elapsed_s')}s")
    lines.append(f"  fail_to_pass={record.get('fail_to_pass')}")
    lines.append(f"  pass_to_pass={record.get('pass_to_pass')}")
    lines.append(f"  detail: {record.get('detail', '')[:500]}")
    if record.get("submitted_patch"):
        lines.append(f"  patch: {record['submitted_patch']}")
    lines.append(json.dumps({k: v for k, v in record.items() if k not in ("trace_dir", "trace_steps", "submitted_patch")}, ensure_ascii=False))
    lines.append("")


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
    print(f"{tag('prep')} repo ready {dim(str(repo_dir))}", flush=True)

    trace_dir = RUNS_DIR / f"trace_{task.instance_id}"
    trace = RunTraceLogger(
        instance_id=task.instance_id,
        repo_dir=repo_dir,
        trace_dir=trace_dir,
        target_files=task.gold_files,
    )
    print(
        f"{tag('trace')} steps={dim(str(trace.steps_path))} "
        f"target={ok_label(','.join(task.gold_files))}",
        flush=True,
    )

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
    record = _harness_record(task, harness, patch_text=patch_text, trace_dir=trace_dir)
    record["exit_status"] = exit_status
    record["llm_turns"] = agent.n_calls
    record["total_cost"] = agent.cost
    return record


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
    summary_path = RUNS_DIR / f"mini_swe_baseline_n{len(tasks)}.summary.log"

    print(
        f"{tag('run', color='\033[95m')} mini-SWE baseline "
        f"n={paint(str(len(tasks)), '\033[1m', '\033[97m')} "
        f"model={dim(DEEPSEEK_PRO_MODEL)} step_limit={args.step_limit}"
    )
    print(f"{dim('runs_dir=' + str(RUNS_DIR))} heartbeat=30s {dim('FORCE_COLOR=1 if piping to tee')}")
    print(dim("tail -f paper1/data/runs/baseline_3task.log  |  trace: .../steps.jsonl"))
    resolved = 0
    started = time.time()
    summary_lines = [
        f"mini-SWE baseline: n={len(tasks)} model={DEEPSEEK_PRO_MODEL} step_limit={args.step_limit}",
        f"runs_dir={RUNS_DIR}",
        "",
    ]

    with out_path.open("w") as handle:
        for index, task in enumerate(tasks, start=1):
            banner = paint(f"{'=' * 16} TASK {index}/{len(tasks)} {'=' * 16}", "\033[1m", "\033[95m")
            print(f"\n{banner}", flush=True)
            print(f"{tag('start')} {paint(task.instance_id, '\033[1m', '\033[96m')}", flush=True)
            summary_lines.append(f"[{index}/{len(tasks)}] START {task.instance_id}")
            run_started = time.time()
            record = run_baseline_task(task, step_limit=args.step_limit)
            record["elapsed_s"] = round(time.time() - run_started, 1)
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            _append_summary_line(summary_lines, record, index=index, total=len(tasks))
            if record["harness_resolved"]:
                resolved += 1
            status = ok_label("PASS") if record["harness_resolved"] else fail_label("FAIL")
            print(
                f"{tag('done')} {task.instance_id} {status} "
                f"exit={record['exit_status']} turns={record.get('llm_turns')} "
                f"cost={record.get('total_cost')} elapsed={record['elapsed_s']}s",
                flush=True,
            )
            print(f"  fail_to_pass={record.get('fail_to_pass')}", flush=True)
            print(f"  {dim('detail:')} {str(record['detail'])[:240]}", flush=True)
            if record.get("submitted_patch"):
                print(f"  {dim('patch:')} {record['submitted_patch']}", flush=True)

    summary_lines.append(f"FINAL resolved={resolved}/{len(tasks)} elapsed={time.time() - started:.1f}s")
    summary_lines.append(f"jsonl={out_path}")
    summary_path.write_text("\n".join(summary_lines) + "\n")

    final = ok_label(f"resolved={resolved}/{len(tasks)}") if resolved else fail_label(f"resolved={resolved}/{len(tasks)}")
    print(f"\n{tag('final', color='\033[93m')} {final} elapsed={time.time() - started:.1f}s")
    print(f"jsonl={out_path}")
    print(f"summary={summary_path}")
    if resolved == 0 and args.step_limit >= 20:
        sys.exit(1)


if __name__ == "__main__":
    main()
