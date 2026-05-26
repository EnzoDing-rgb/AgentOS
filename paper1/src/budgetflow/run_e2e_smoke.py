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
    detail: str


def main() -> None:
    load_env_file()
    args = sys.argv[1:]
    strategy = "budgetflow_full"
    instance_ids = list(DEFAULT_INSTANCE_IDS)
    if args:
        if args[0] in {"all_flash", "all_pro", "budgetflow_full"}:
            strategy = args[0]
            args = args[1:]
        if args:
            instance_ids = args

    run_id = time.strftime("e2e_%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / run_id
    predictions_path = run_dir / "predictions.jsonl"
    summary_path = run_dir / "summary.json"

    tasks = load_swebench_lite_tasks(instance_ids=tuple(instance_ids))
    report(f"E2E smoke: strategy={strategy} tasks={len(tasks)} pressure={FROZEN_BUDGET_PRESSURE}")
    report("workflow_steps_ok = API+rubric. harness_resolved = local git apply + pytest.")
    report("Docker SWE harness unavailable here; using local repo checkout fallback.")
    report("")

    summaries: list[E2ERunSummary] = []
    started = time.time()
    for index, task in enumerate(tasks, start=1):
        report(f"=== [{index}/{len(tasks)}] {task.instance_id} ===")
        patch_started = time.time()
        patch_result: PatchRunResult = run_patch_agent(task, strategy=strategy)
        picks = "/".join(name.replace("deepseek_", "") for name in patch_result.backend_picks)
        report(
            f"  patch_agent workflow_steps_ok={patch_result.workflow_steps_ok} "
            f"patch_extracted={patch_result.patch_extracted} cost={patch_result.total_cost:.4f} "
            f"picks={picks} elapsed={time.time() - patch_started:.1f}s"
        )
        if patch_result.model_patch:
            preview = patch_result.model_patch.splitlines()[:8]
            report("  patch_preview:")
            for line in preview:
                report(f"    {line}")
        else:
            report("  patch_preview: <empty>")

        harness_started = time.time()
        harness = evaluate_local_harness(task, patch_result.model_patch)
        report(
            f"  harness patch_applied={harness.patch_applied} "
            f"harness_resolved={harness.harness_resolved} elapsed={time.time() - harness_started:.1f}s"
        )
        report(f"  harness detail: {harness.detail}")

        write_predictions(
            predictions_path,
            task.instance_id,
            patch_result.model_patch,
            model_name=f"budgetflow-{strategy}",
        )
        summaries.append(
            E2ERunSummary(
                instance_id=task.instance_id,
                strategy=strategy,
                workflow_steps_ok=patch_result.workflow_steps_ok,
                patch_extracted=patch_result.patch_extracted,
                patch_applied=harness.patch_applied,
                harness_resolved=harness.harness_resolved,
                total_cost=patch_result.total_cost,
                backend_picks=patch_result.backend_picks,
                detail=harness.detail,
            )
        )
        report("")

    resolved = sum(1 for item in summaries if item.harness_resolved)
    extracted = sum(1 for item in summaries if item.patch_extracted)
    report("=== SUMMARY ===")
    report(f"strategy={strategy} harness_resolved={resolved}/{len(summaries)} patch_extracted={extracted}/{len(summaries)}")
    for item in summaries:
        report(
            f"  {item.instance_id} workflow_ok={item.workflow_steps_ok} "
            f"extracted={item.patch_extracted} applied={item.patch_applied} "
            f"resolved={item.harness_resolved} cost={item.total_cost:.4f}"
        )
    report(f"elapsed={time.time() - started:.1f}s")
    report(f"artifacts={run_dir}")

    summary_path.write_text(json.dumps([asdict(item) for item in summaries], indent=2))


if __name__ == "__main__":
    main()
