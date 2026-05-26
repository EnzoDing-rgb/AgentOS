from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from budgetflow.deepseek_backend import load_env_file
from budgetflow.lite_tasks import load_swebench_lite_tasks
from budgetflow.local_harness import evaluate_local_harness, write_predictions
from budgetflow.patch_agent import PatchRunResult, run_patch_agent
from budgetflow.run_deepseek_compare import FROZEN_BUDGET_PRESSURE

DEFAULT_INSTANCE_IDS = ("sympy__sympy-24152", "sympy__sympy-24213")
STRATEGIES = ("all_flash", "all_pro", "budgetflow_full")
RUNS_DIR = Path("/Lishun/_archive/.local_env_bak/research/AgentOS/paper1/data/runs")


def report(message: str) -> None:
    print(message, flush=True)


@dataclass(frozen=True)
class E2ERunSummary:
    instance_id: str
    strategy: str
    workflow_steps_ok: bool
    patch_extracted: bool
    patch_applied: bool
    harness_resolved: bool
    total_cost: float
    backend_picks: tuple[str, ...]
    model_patch: str | None
    repair_attempts: int
    detail: str


def run_one(task, strategy: str) -> E2ERunSummary:
    patch_result: PatchRunResult = run_patch_agent(task, strategy=strategy)
    if patch_result.harness_resolved:
        detail = f"resolved in {patch_result.repair_attempts} repair attempt(s)"
        patch_applied = True
        harness_resolved = True
    else:
        harness = evaluate_local_harness(task, patch_result.model_patch)
        detail = harness.detail
        patch_applied = harness.patch_applied
        harness_resolved = harness.harness_resolved
    return E2ERunSummary(
        instance_id=task.instance_id,
        strategy=strategy,
        workflow_steps_ok=patch_result.workflow_steps_ok,
        patch_extracted=patch_result.patch_extracted,
        patch_applied=patch_applied,
        harness_resolved=harness_resolved,
        total_cost=patch_result.total_cost,
        backend_picks=patch_result.backend_picks,
        model_patch=patch_result.model_patch,
        repair_attempts=patch_result.repair_attempts,
        detail=detail,
    )


def main() -> None:
    load_env_file()
    args = sys.argv[1:]
    instance_ids = list(DEFAULT_INSTANCE_IDS)
    if args:
        instance_ids = args

    run_id = time.strftime("e2e_compare_%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / run_id
    summary_path = run_dir / "summary.json"

    tasks = load_swebench_lite_tasks(instance_ids=tuple(instance_ids))
    report(f"E2E compare: tasks={len(tasks)} strategies={len(STRATEGIES)} pressure={FROZEN_BUDGET_PRESSURE}")
    report("Multi-round repair: 1 localization + up to 5 repair attempts with apply/test feedback.")
    report("workflow_steps_ok = patch extracted. harness_resolved = local git apply + pytest.")
    report("")

    summaries: list[E2ERunSummary] = []
    started = time.time()
    for index, task in enumerate(tasks, start=1):
        report(f"=== task [{index}/{len(tasks)}] {task.instance_id} ===")
        for strategy in STRATEGIES:
            run_started = time.time()
            summary = run_one(task, strategy)
            summaries.append(summary)
            picks = "/".join(name.replace("deepseek_", "") for name in summary.backend_picks)
            report(
                f"  {strategy:16s} workflow_ok={summary.workflow_steps_ok} "
                f"extracted={summary.patch_extracted} applied={summary.patch_applied} "
                f"resolved={summary.harness_resolved} attempts={summary.repair_attempts} "
                f"cost={summary.total_cost:.4f} picks={picks} elapsed={time.time() - run_started:.1f}s"
            )
            write_predictions(
                run_dir / f"predictions_{strategy}.jsonl",
                task.instance_id,
                summary.model_patch,
                model_name=strategy,
            )
        report("")

    report("=== SUMMARY ===")
    report(f"{'strategy':16s} {'resolved':>10s} {'extracted':>10s} {'cost':>10s}")
    for strategy in STRATEGIES:
        rows = [item for item in summaries if item.strategy == strategy]
        resolved = sum(1 for item in rows if item.harness_resolved)
        extracted = sum(1 for item in rows if item.patch_extracted)
        cost = sum(item.total_cost for item in rows)
        report(f"{strategy:16s} {resolved}/{len(rows):>8d} {extracted}/{len(rows):>8d} {cost:10.4f}")
    report(f"elapsed={time.time() - started:.1f}s")
    report(f"artifacts={run_dir}")
    summary_path.write_text(json.dumps([asdict(item) for item in summaries], indent=2))


if __name__ == "__main__":
    main()
