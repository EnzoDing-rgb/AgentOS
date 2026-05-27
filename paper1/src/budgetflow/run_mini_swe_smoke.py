from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from budgetflow.adapter.runner import run_mini_swe_task
from budgetflow.deepseek_backend import load_env_file
from budgetflow.lite_tasks import load_swebench_lite_tasks

RUNS_DIR = Path("/Lishun/_archive/.local_env_bak/research/AgentOS/paper1/data/runs")


def report(message: str) -> None:
    print(message, flush=True)


def main() -> None:
    load_env_file()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    strategy = sys.argv[2] if len(sys.argv) > 2 else "all_pro"
    pool = load_swebench_lite_tasks(limit=300)
    tasks = [task for task in pool if task.repo.startswith("sympy/")][:limit]
    if not tasks:
        tasks = load_swebench_lite_tasks(limit=limit)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RUNS_DIR / f"mini_swe_smoke_{strategy}_n{limit}.jsonl"

    report(f"Step A smoke: n={limit} strategy={strategy} backend=DeepSeek Flash/Pro")
    resolved = 0
    started = time.time()

    with out_path.open("w") as handle:
        for index, task in enumerate(tasks, start=1):
            report(f"[{index}/{len(tasks)}] START {task.instance_id}")
            run_started = time.time()
            result = run_mini_swe_task(task, strategy=strategy)
            if result.harness_resolved:
                resolved += 1
            record = {
                "instance_id": result.instance_id,
                "strategy": result.strategy,
                "harness_resolved": result.harness_resolved,
                "patch_extracted": bool(result.patch_text),
                "exit_status": result.exit_status,
                "total_cost": result.total_cost,
                "backend_picks": list(result.backend_picks),
                "llm_turns": result.llm_turns,
                "violations": list(result.violations),
                "detail": result.harness_detail,
                "elapsed_s": round(time.time() - run_started, 1),
            }
            handle.write(json.dumps(record) + "\n")
            status = "OK" if result.harness_resolved else "FAIL"
            report(
                f"[{index}/{len(tasks)}] DONE {task.instance_id} {status} "
                f"exit={result.exit_status} cost={result.total_cost:.4f} "
                f"turns={result.llm_turns} elapsed={record['elapsed_s']}s"
            )
            if result.harness_detail:
                report(f"  detail: {result.harness_detail[:240]}")

    report("")
    report(f"FINAL resolved={resolved}/{len(tasks)} elapsed={time.time() - started:.1f}s")
    report(f"log={out_path}")
    if resolved == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
