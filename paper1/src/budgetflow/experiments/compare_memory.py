"""Learning-memory setup and no-provider gates for compare runs."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

from budgetflow.auto_budget import AutoBudgetEstimator, AutoBudgetMemory, BudgetEstimate
from budgetflow.console_log import tag
from budgetflow.experiments.compare_config import fmt_usd
from budgetflow.learning_context import load_policy_memory_context
from budgetflow.policy_memory import PolicyMemory


@dataclass
class AutoBudgetPlan:
    memory_path: Path
    memory: AutoBudgetMemory | None
    estimates: dict[str, BudgetEstimate]
    task_caps: dict[str, float] | None


def run_policy_memory_gate(policy_memory: PolicyMemory | None, source_path: str) -> bool:
    banner = "=" * 72
    print(banner)
    print("WARM-UP GATE")
    print(banner)

    all_ok = True
    loaded = policy_memory is not None
    print(f"  policy_memory_loaded = {loaded}")
    if not loaded:
        print("  FAIL: PolicyMemory not loaded. Provide --policy-memory PATH.")
        all_ok = False

    if policy_memory is None:
        print(banner)
        print("GATE RESULT: FAIL (no policy_memory)")
        return False

    records = policy_memory._record_count
    print(f"  records_loaded = {records}")
    if records < 10:
        print(f"  FAIL: Expected >= 10 records, got {records}")
        all_ok = False

    repos = len(policy_memory._repo_priors)
    print(f"  repos_loaded = {repos}")
    if repos < 1:
        print(f"  FAIL: Expected >= 1 repos, got {repos}")
        all_ok = False

    tasks_n = len(policy_memory._task_priors)
    print(f"  tasks_loaded = {tasks_n}")
    if tasks_n < 10:
        print(f"  FAIL: Expected >= 10 tasks, got {tasks_n}")
        all_ok = False

    print(f"  regret_threshold = {policy_memory.regret_threshold}")
    print(banner)
    print("PRIOR SUMMARIES (5 sample tasks)")
    print(banner)
    task_keys = sorted(policy_memory._task_priors.keys())
    for iid in task_keys[:5]:
        summary = policy_memory.routing_prior_summary(iid)
        print(f"  {iid}:")
        for key, value in summary.items():
            print(f"    {key} = {value}")
        print()

    print(banner)
    sympy_17630 = "sympy__sympy-17630"
    summary_17630 = policy_memory.routing_prior_summary(sympy_17630)
    action = summary_17630.get("learned_action", "?")
    suffix = "" if sympy_17630 in policy_memory._task_priors else " (not in priors, computed from repo)"
    print(f"  {sympy_17630} learned_action = {action}{suffix}")
    if action == "early_rescue":
        print("  WARNING: early_rescue on a task with known all_pro failures may waste strongest-tier budget")

    print(banner)
    print("FULL vs TIGHT REGRET")
    print(banner)
    for repo_key in sorted(policy_memory._policy_regrets.keys()):
        regret = policy_memory._policy_regrets[repo_key]
        print(
            f"  {repo_key}: full_avg=${regret.full_avg_cost:.4f} "
            f"tight_avg=${regret.tight_avg_cost:.4f} "
            f"regret={regret.regret:.3f} threshold={policy_memory.regret_threshold}"
        )
        if regret.regret > policy_memory.regret_threshold:
            print("    EXCEEDS threshold: cap_strongest would be triggered")
        else:
            print("    below threshold: no auto-tightening")

    print(banner)
    print("NEXT-RUN ROUTING IMPACT")
    print(banner)
    actions_seen: dict[str, int] = {}
    for iid in task_keys:
        summary = policy_memory.routing_prior_summary(iid)
        action = summary.get("learned_action", "default")
        actions_seen[action] = actions_seen.get(action, 0) + 1
    print("  Action distribution across all tasks:")
    for action, count in sorted(actions_seen.items()):
        print(f"    {action}: {count}/{tasks_n} tasks")

    print(banner)
    print("GATE RESULT: PASS" if all_ok else "GATE RESULT: FAIL")
    print(banner)
    return all_ok


def run_policy_memory_gate_only(args: Namespace, *, repo_root: Path) -> int:
    if not args.policy_memory:
        print("ERROR: --policy-memory-gate-only requires --policy-memory PATH", flush=True)
        return 1
    pm_path = _resolve_existing_file(args.policy_memory, repo_root, "--policy-memory")
    pm = PolicyMemory(regret_threshold=args.regret_threshold)
    pm.rebuild_from_jsonl(pm_path)
    return 0 if run_policy_memory_gate(pm, args.policy_memory) else 1


def build_auto_budget_plan(args: Namespace, *, tasks: list, runs_dir: Path) -> AutoBudgetPlan:
    memory_path = Path(args.auto_budget_memory) if args.auto_budget_memory else runs_dir / "auto_budget_memory.jsonl"
    memory: AutoBudgetMemory | None = None
    if not args.no_auto_budget_learn:
        memory = AutoBudgetMemory(memory_path if memory_path.is_file() else None)
        if memory._path is None:
            memory._path = memory_path

    estimates: dict[str, BudgetEstimate] = {}
    task_caps: dict[str, float] | None = None
    if args.auto_budget or args.auto_budget_dry_run:
        estimator = AutoBudgetEstimator(memory=memory, k=args.auto_budget_k)
        for task in tasks:
            estimate = estimator.estimate(
                task,
                scale=args.auto_budget_scale,
                min_cap=args.auto_budget_min,
                max_cap=args.auto_budget_max,
            )
            estimates[task.instance_id] = estimate
            print(
                f"{tag('auto-budget', bold=False)} {estimate.instance_id} "
                f"est={fmt_usd(estimate.estimated_cost)} cap={fmt_usd(estimate.cap)} "
                f"source={estimate.source} confidence={estimate.confidence}"
                + (f" neighbors={estimate.memory_neighbors}" if estimate.memory_neighbors else ""),
                flush=True,
            )
        task_caps = {iid: estimate.cap for iid, estimate in estimates.items()}
        if args.per_task_cap is None:
            args.per_task_cap = -1.0
    return AutoBudgetPlan(memory_path=memory_path, memory=memory, estimates=estimates, task_caps=task_caps)


def run_auto_budget_dry_run(
    args: Namespace,
    *,
    tasks: list,
    runs_dir: Path,
    repo_root: Path,
    auto_budget_plan: AutoBudgetPlan,
) -> int:
    policy_ctx = load_policy_memory_context(
        runs_dir=runs_dir,
        repo_root=repo_root,
        explicit_path=args.policy_memory,
        resume=False,
        resume_path=None,
        disable=args.disable_policy_memory,
        regret_threshold=args.regret_threshold,
    )
    if policy_ctx.enabled and policy_ctx.memory is not None and policy_ctx.source is not None:
        print(
            f"{tag('policy_memory', bold=True)} loaded from {policy_ctx.source} "
            f"source={policy_ctx.source_kind} records={policy_ctx.memory._record_count} "
            f"repos={len(policy_ctx.memory._repo_priors)} tasks={len(policy_ctx.memory._task_priors)} "
            f"threshold={policy_ctx.memory.regret_threshold}",
            flush=True,
        )
    else:
        print(
            f"{tag('policy_memory', bold=False)} disabled - {policy_ctx.reason or 'no usable run JSONL source found'}",
            flush=True,
        )

    memory = auto_budget_plan.memory
    print("=== AutoBudget dry-run (Value-Driven Budget Allocation) ===", flush=True)
    print(f"memory={auto_budget_plan.memory_path}", flush=True)
    print(f"records={len(memory.records) if memory is not None else 0}", flush=True)
    print(
        f"policy_memory={'on' if policy_ctx.memory is not None else 'off'}"
        + (f" source={policy_ctx.source}" if policy_ctx.source else ""),
        flush=True,
    )
    print(
        f"  {'task':<40} {'source':<20} {'est_cost':>10} {'cap':>10} "
        f"{'confidence':<10} {'neighbors':>9} {'esc':<36}",
        flush=True,
    )
    print(f"  {'-'*144}", flush=True)
    for task in tasks:
        estimate = auto_budget_plan.estimates[task.instance_id]
        if policy_ctx.memory is not None:
            prior = policy_ctx.memory.routing_prior_summary(task.instance_id)
            esc = (
                f"{prior.get('escalation_memory_source') or 'none'}:"
                f"{prior.get('value_triggered_escalation_action', 'default')}"
                f"/w={prior.get('value_triggered_escalation_window', '?')}"
                f"/t3_rate={prior.get('t3_productive_rate', 0):.2f}"
            )
        else:
            esc = "off"
        print(
            f"  {task.instance_id:<40} {estimate.source:<20} {fmt_usd(estimate.estimated_cost):>10} "
            f"{fmt_usd(estimate.cap):>10} {estimate.confidence:<10} {estimate.memory_neighbors:>9} {esc:<36}",
            flush=True,
        )
    return 0


def _resolve_existing_file(raw_path: str, repo_root: Path, flag: str) -> Path:
    path = _resolve_path(raw_path, repo_root)
    if not path.is_file():
        raise SystemExit(f"ERROR: {flag} file not found: {path}")
    return path


def _resolve_path(raw_path: str, repo_root: Path) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else repo_root / path
