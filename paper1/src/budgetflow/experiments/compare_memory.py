"""Policy-memory setup and no-provider gates for compare runs."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from budgetflow.learning_context import load_policy_memory_context
from budgetflow.policy_memory import PolicyMemory


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
            f"baseline_avg=${regret.baseline_avg_cost:.4f} "
            f"regret={regret.regret:.3f} threshold={policy_memory.regret_threshold}"
        )
        if regret.regret > policy_memory.regret_threshold:
            print("    EXCEEDS threshold: cap_strongest would be triggered")
        else:
            print("    below threshold: no policy constraint")

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


def _resolve_existing_file(raw_path: str, repo_root: Path, flag: str) -> Path:
    path = _resolve_path(raw_path, repo_root)
    if not path.is_file():
        raise SystemExit(f"ERROR: {flag} file not found: {path}")
    return path


def _resolve_path(raw_path: str, repo_root: Path) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else repo_root / path
