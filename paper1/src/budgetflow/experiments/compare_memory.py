"""Learning-memory setup and no-provider gates for compare runs."""

from __future__ import annotations

import json
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

from budgetflow.auto_budget import AutoBudgetEstimator, AutoBudgetMemory, BudgetEstimate
from budgetflow.budget_memory import BudgetMemory, BudgetEstimate as BudgetMemoryEstimate
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


@dataclass
class BudgetMemoryPlan:
    enabled: bool
    estimates: dict[str, BudgetMemoryEstimate]
    source_paths: str
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
        print("  WARNING: early_rescue on a task with known all_pro failures may waste T3 budget")

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
            print("    EXCEEDS threshold: cap_t3 would be triggered")
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


def run_budget_memory_gate_only(args: Namespace, *, repo_root: Path, exclude_ids: set[str] | None) -> int:
    paths = _resolve_budget_memory_paths(args.budget_memory, repo_root, "--budget-memory-gate-only")
    memory = BudgetMemory.from_jsonl(paths, exclude_ids=exclude_ids)
    print("budget_memory gate-only: OK", flush=True)
    print(f"  records={memory.record_count} tasks={memory.task_count} repos={memory.repo_count}")
    print(f"  sources: {memory._source_paths}")
    for line in memory.summary_lines():
        print(f"  {line}")
    return 0


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
    print(f"  {'task':<40} {'source':<20} {'est_cost':>10} {'cap':>10} {'confidence':<10} {'neighbors':>9}", flush=True)
    print(f"  {'-'*105}", flush=True)
    for task in tasks:
        estimate = auto_budget_plan.estimates[task.instance_id]
        print(
            f"  {task.instance_id:<40} {estimate.source:<20} {fmt_usd(estimate.estimated_cost):>10} "
            f"{fmt_usd(estimate.cap):>10} {estimate.confidence:<10} {estimate.memory_neighbors:>9}",
            flush=True,
        )
    return 0


def run_budget_memory_dry_run(
    args: Namespace,
    *,
    tasks: list,
    repo_root: Path,
    exclude_ids: set[str] | None,
    auto_budget_task_caps: dict[str, float] | None,
) -> int:
    paths = _resolve_budget_memory_paths(args.budget_memory, repo_root, "--budget-memory-dry-run")
    memory = BudgetMemory.from_jsonl(paths, exclude_ids=exclude_ids)
    print("=== BudgetMemory dry-run ===")
    print(f"records={memory.record_count} tasks={memory.task_count} repos={memory.repo_count}")
    print(f"sources: {memory._source_paths}")
    print()

    historical_caps = _historical_caps(memory._source_paths)
    per_task_hard = args.per_task_cap if args.per_task_cap and args.per_task_cap > 0 else None
    print(
        f"  {'task':<40} {'strategy':<28} {'old_cap_src':<16} {'old_cap':>10} "
        f"{'bm_cap':>10} {'actual_median':>13} {'verdict':>16}"
    )
    print(f"  {'-'*125}")

    under_count = over_count = ok_count = not_comp = 0
    for task in tasks:
        iid = task.instance_id
        estimate = memory.estimate_task_budget(iid, hard_budget=per_task_hard)
        old_cap, old_src, comparable = _old_cap_for_task(
            iid,
            auto_budget_task_caps=auto_budget_task_caps,
            historical_caps=historical_caps,
            per_task_hard=per_task_hard,
        )
        task_stats = memory.task_stats(iid)
        actual_median = task_stats.median_cost if task_stats and task_stats.median_cost > 0 else 0
        verdict = _cap_verdict(comparable=comparable, old_cap=old_cap, actual_median=actual_median)
        if verdict == "underbudget":
            under_count += 1
        elif verdict == "overbudget":
            over_count += 1
        elif verdict == "ok":
            ok_count += 1
        else:
            not_comp += 1
        old_str = f"${old_cap:.4f}" if old_cap > 0 else "N/A"
        actual_str = f"${actual_median:.4f}" if actual_median > 0 else "N/A"
        print(
            f"  {iid:<40} {'':<28} {old_src:<16} {old_str:>10} "
            f"${estimate.estimated_task_budget:>9.4f} {actual_str:>13} {verdict:>16}"
        )

    print()
    print(
        f"Summary: underbudget={under_count} overbudget={over_count} ok={ok_count} "
        f"not_comparable={not_comp} tasks={len(tasks)} auto_budget={auto_budget_task_caps is not None}"
    )
    return 0


def build_budget_memory_plan(
    args: Namespace,
    *,
    tasks: list,
    repo_root: Path,
    exclude_ids: set[str] | None,
    auto_budget_enabled: bool,
) -> BudgetMemoryPlan:
    if args.disable_budget_memory or not args.budget_memory:
        return BudgetMemoryPlan(enabled=False, estimates={}, source_paths="", task_caps=None)

    valid_paths: list[Path] = []
    for raw in args.budget_memory.split(","):
        path = _resolve_path(raw.strip(), repo_root)
        if path.is_file():
            valid_paths.append(path)
        else:
            print(f"WARNING: --budget-memory file not found: {path}", flush=True)
    if not valid_paths:
        print(f"{tag('budget_memory', bold=False)} disabled - no valid files found", flush=True)
        return BudgetMemoryPlan(enabled=False, estimates={}, source_paths="", task_caps=None)

    memory = BudgetMemory.from_jsonl(valid_paths, exclude_ids=exclude_ids)
    source_paths = ",".join(str(path) for path in valid_paths)
    print(
        f"{tag('budget_memory', bold=True)} loaded from {source_paths} "
        f"records={memory.record_count} tasks={memory.task_count} repos={memory.repo_count}",
        flush=True,
    )
    estimates: dict[str, BudgetMemoryEstimate] = {}
    for task in tasks:
        hard_cap = args.per_task_cap if args.per_task_cap and args.per_task_cap > 0 else None
        estimates[task.instance_id] = memory.estimate_task_budget(task.instance_id, hard_budget=hard_cap)

    task_caps = None
    if not auto_budget_enabled:
        task_caps = {iid: estimate.estimated_task_budget for iid, estimate in estimates.items()}
        print("  Per-task caps from BudgetMemory (cascade: exact_task > repo > strategy > global)", flush=True)
    else:
        print("  BudgetMemory estimates stored (Value-Driven Budget Allocation takes priority for caps)", flush=True)
    return BudgetMemoryPlan(enabled=True, estimates=estimates, source_paths=source_paths, task_caps=task_caps)


def _resolve_existing_file(raw_path: str, repo_root: Path, flag: str) -> Path:
    path = _resolve_path(raw_path, repo_root)
    if not path.is_file():
        raise SystemExit(f"ERROR: {flag} file not found: {path}")
    return path


def _resolve_budget_memory_paths(raw: str | None, repo_root: Path, flag: str) -> list[Path]:
    if not raw:
        raise SystemExit(f"ERROR: {flag} requires --budget-memory PATH[,PATH...]")
    return [_resolve_existing_file(piece.strip(), repo_root, "--budget-memory") for piece in raw.split(",") if piece.strip()]


def _resolve_path(raw_path: str, repo_root: Path) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else repo_root / path


def _historical_caps(source_paths: list[str]) -> dict[str, tuple[float, str]]:
    caps: dict[str, tuple[float, str]] = {}
    for source_path in source_paths:
        try:
            lines = Path(source_path).read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            iid = str(record.get("instance_id") or "")
            if not iid or iid in caps:
                continue
            if record.get("estimated_task_cap") is not None:
                caps[iid] = (float(record["estimated_task_cap"]), "historical")
            elif record.get("batch_budget_cap") is not None:
                caps[iid] = (float(record["batch_budget_cap"]), "historical")
    return caps


def _old_cap_for_task(
    instance_id: str,
    *,
    auto_budget_task_caps: dict[str, float] | None,
    historical_caps: dict[str, tuple[float, str]],
    per_task_hard: float | None,
) -> tuple[float, str, bool]:
    if auto_budget_task_caps is not None:
        return float(auto_budget_task_caps.get(instance_id) or 0), "auto_budget", True
    if instance_id in historical_caps:
        value, source = historical_caps[instance_id]
        return value, source, True
    if per_task_hard is not None:
        return per_task_hard, "per_task", True
    return 0.0, "standard_tight", False


def _cap_verdict(*, comparable: bool, old_cap: float, actual_median: float) -> str:
    if not comparable or old_cap <= 0 or actual_median <= 0:
        return "not_comparable"
    if actual_median > old_cap * 1.2:
        return "underbudget"
    if old_cap > actual_median * 3:
        return "overbudget"
    return "ok"
