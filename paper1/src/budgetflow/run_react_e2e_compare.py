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
from budgetflow.local_harness import write_predictions
from budgetflow.monolithic_react_agent import run_monolithic_react_agent
from budgetflow.run_deepseek_compare import FROZEN_BUDGET_PRESSURE
from budgetflow.staged_react_agent import ReActRunResult, run_staged_react_agent

DEFAULT_INSTANCE_IDS = ("sympy__sympy-24152", "sympy__sympy-24213")
STRATEGIES = (
    "monolithic_react_all_pro",
    "monolithic_react_budgetflow",
    "budgetflow_staged_react",
)
RUNS_DIR = Path("/Lishun/_archive/.local_env_bak/research/AgentOS/paper1/data/runs")


def report(message: str) -> None:
    print(message, flush=True)


@dataclass(frozen=True)
class ReActE2ESummary:
    instance_id: str
    strategy: str
    patch_extracted: bool
    harness_resolved: bool
    total_cost: float
    backend_picks: tuple[str, ...]
    llm_turns: int
    tool_calls: int
    stop_reason: str
    last_failure_class: str
    model_patch: str | None
    detail: str


def run_one(task, strategy: str) -> ReActE2ESummary:
    if strategy == "budgetflow_staged_react":
        result: ReActRunResult = run_staged_react_agent(task, strategy=strategy)
    else:
        result = run_monolithic_react_agent(task, strategy=strategy)
    detail = result.stop_reason if not result.harness_resolved else f"resolved ({result.stop_reason})"
    return ReActE2ESummary(
        instance_id=result.instance_id,
        strategy=result.strategy,
        patch_extracted=result.patch_extracted,
        harness_resolved=result.harness_resolved,
        total_cost=result.total_cost,
        backend_picks=result.backend_picks,
        llm_turns=result.llm_turns,
        tool_calls=result.tool_calls,
        stop_reason=result.stop_reason,
        last_failure_class=result.last_failure_class,
        model_patch=result.model_patch,
        detail=detail,
    )


def main() -> None:
    load_env_file()
    args = sys.argv[1:]
    instance_ids = list(DEFAULT_INSTANCE_IDS)
    strategies = list(STRATEGIES)
    if args:
        if args[0] in STRATEGIES:
            strategies = [args[0]]
            instance_ids = args[1:] or instance_ids
        else:
            instance_ids = args

    run_id = time.strftime("react_e2e_%Y%m%d_%H%M%S")
    run_dir = RUNS_DIR / run_id
    summary_path = run_dir / "summary.json"

    tasks = load_swebench_lite_tasks(instance_ids=tuple(instance_ids))
    report(f"ReAct E2E: tasks={len(tasks)} strategies={len(strategies)} pressure={FROZEN_BUDGET_PRESSURE}")
    report("Arms: monolithic ReAct vs staged L-ReAct + R-ReAct + harness @ same budget B")
    report("")

    summaries: list[ReActE2ESummary] = []
    started = time.time()
    for index, task in enumerate(tasks, start=1):
        report(f"=== task [{index}/{len(tasks)}] {task.instance_id} ===")
        for strategy in strategies:
            run_started = time.time()
            summary = run_one(task, strategy)
            summaries.append(summary)
            picks = "/".join(name.replace("deepseek_", "") for name in summary.backend_picks[:8])
            if len(summary.backend_picks) > 8:
                picks += "/..."
            report(
                f"  {strategy:28s} resolved={summary.harness_resolved} extracted={summary.patch_extracted} "
                f"turns={summary.llm_turns} tools={summary.tool_calls} fail={summary.last_failure_class} "
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
    report(f"{'strategy':28s} {'resolved':>10s} {'extracted':>10s} {'cost':>10s}")
    for strategy in strategies:
        rows = [item for item in summaries if item.strategy == strategy]
        resolved = sum(1 for item in rows if item.harness_resolved)
        extracted = sum(1 for item in rows if item.patch_extracted)
        cost = sum(item.total_cost for item in rows)
        report(f"{strategy:28s} {resolved}/{len(rows):>8d} {extracted}/{len(rows):>8d} {cost:10.4f}")
    report(f"elapsed={time.time() - started:.1f}s")
    report(f"artifacts={run_dir}")
    summary_path.write_text(json.dumps([asdict(item) for item in summaries], indent=2))


if __name__ == "__main__":
    main()
