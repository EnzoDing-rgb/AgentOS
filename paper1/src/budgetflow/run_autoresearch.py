#!/usr/bin/env python3
"""AutoResearch CLI — create, run, status, list, next, mark-complete, mark-failed.

Usage:
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch create --issue-id ID --prompt-file PATH
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch run --issue-id ID [--dry-run | --manual | --worker-cmd CMD]
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch status --issue-id ID
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch list [--status STATUS] [--paused-only]
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch next --issue-id ID
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch mark-complete --issue-id ID
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch mark-failed --issue-id ID --reason TEXT

Security: --worker-cmd executes a trusted local shell command. Only use with
commands you control. The {prompt} and {output} placeholders are required and
are substituted as filesystem paths.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Sequence

from .autoresearch_coordinator import AutoResearchCoordinator, PauseReason

DEFAULT_PAPER1 = Path(__file__).resolve().parents[2]


def _make_worker_cmd(template: str) -> Callable[[Path, Path], int]:
    def _worker(prompt_path: Path, output_path: Path) -> int:
        cmd = template.format(prompt=prompt_path, output=output_path)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode

    return _worker


def _validate_worker_cmd(template: str) -> None:
    """Reject worker-cmd missing required {prompt} or {output} placeholders."""
    missing = []
    if "{prompt}" not in template:
        missing.append("{prompt}")
    if "{output}" not in template:
        missing.append("{output}")
    if missing:
        print(
            f"--worker-cmd must contain {' and '.join(missing)} placeholder(s). "
            f"Got: {template}",
            file=sys.stderr,
        )
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="run_autoresearch")
    p.add_argument("--paper1-root", type=Path, default=None, help="Override paper1 root directory")
    sub = p.add_subparsers(dest="command", required=True)

    # create
    c = sub.add_parser("create", help="Create a new workflow from a prompt file")
    c.add_argument("--issue-id", required=True, help="Issue identifier (e.g. 042-fix-bug)")
    c.add_argument("--prompt-file", required=True, type=Path, help="Path to markdown prompt file")

    # run
    r = sub.add_parser("run", help="Execute one step of the workflow")
    r.add_argument("--issue-id", required=True)
    mode = r.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Write prompts/state, skip Worker")
    mode.add_argument("--manual", action="store_true", help="Print prompt paths for manual execution")
    r.add_argument("--worker-cmd", help="Shell command template with {prompt} and {output} placeholders")
    # Pause condition flags
    r.add_argument("--paid-3x10", nargs=2, type=int, metavar=("P", "T"), help="Paid experiment scale (policies tasks)")
    r.add_argument("--northstar-change", action="store_true")
    r.add_argument("--large-refactor", action="store_true")
    r.add_argument("--data-migration", action="store_true")
    r.add_argument("--swebench-docker", action="store_true")
    r.add_argument("--higher-risk", action="store_true")

    # status
    s = sub.add_parser("status", help="Show workflow status")
    s.add_argument("--issue-id", required=True)

    # list
    lst = sub.add_parser("list", help="List all workflows")
    lst.add_argument("--status", help="Filter by workflow status (pending, running, paused, complete, failed)")
    lst.add_argument("--paused-only", action="store_true", help="Show only paused workflows")

    # next
    nxt = sub.add_parser("next", help="Show next action for a workflow")
    nxt.add_argument("--issue-id", required=True)

    # mark-complete
    mc = sub.add_parser("mark-complete", help="Mark workflow as complete")
    mc.add_argument("--issue-id", required=True)
    mc.add_argument("--owner-override", help="Override reason (required when review is WARN)")

    # mark-failed
    mf = sub.add_parser("mark-failed", help="Mark workflow as failed")
    mf.add_argument("--issue-id", required=True)
    mf.add_argument("--reason", default="", help="Failure reason")

    # review
    rv = sub.add_parser("review", help="Deterministic Codex gate review of an issue")
    rv.add_argument("--issue-id", required=True, help="Issue identifier")

    # goal-review
    grv = sub.add_parser("goal-review", help="Review all issues in a Goal")
    grv.add_argument("--goal-id", required=True, help="Goal identifier")

    # ── Goal commands ─────────────────────────────────────────────────────

    # goal-create
    gc = sub.add_parser("goal-create", help="Create a new Goal")
    gc.add_argument("--goal-id", required=True, help="Goal identifier")
    gc.add_argument("--title", required=True, help="Goal title")
    gc.add_argument("--budget-cap-usd", type=float, default=0.0, help="Real API budget cap in USD")

    # goal-add-issue
    gai = sub.add_parser("goal-add-issue", help="Add an issue to a Goal")
    gai.add_argument("--goal-id", required=True)
    gai.add_argument("--issue-id", required=True)

    # goal-status
    gs = sub.add_parser("goal-status", help="Show Goal status with issue breakdown")
    gs.add_argument("--goal-id", required=True)

    # goal-run
    gr = sub.add_parser("goal-run", help="Run one step of a Goal")
    gr.add_argument("--goal-id", required=True)
    gmode = gr.add_mutually_exclusive_group()
    gmode.add_argument("--dry-run", action="store_true", help="Write prompts/state, skip Worker")
    gmode.add_argument("--manual", action="store_true", help="Print prompt paths for manual execution")
    gr.add_argument("--worker-cmd", help="Shell command template with {prompt} and {output} placeholders")
    # Pause flags for goal-run
    gr.add_argument("--paid-3x10", nargs=2, type=int, metavar=("P", "T"))
    gr.add_argument("--northstar-change", action="store_true")
    gr.add_argument("--large-refactor", action="store_true")
    gr.add_argument("--data-migration", action="store_true")
    gr.add_argument("--swebench-docker", action="store_true")
    gr.add_argument("--higher-risk", action="store_true")

    return p


def cmd_create(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    prompt_text = args.prompt_file.read_text()
    state = coordinator.create_workflow(args.issue_id, prompt_text)
    print(f"Created workflow: {state.issue_id}")
    print(f"  status: {state.status}")
    print(f"  dir: {coordinator.workflow_dir(state.issue_id)}")
    return 0


def cmd_run(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    state = coordinator.load_state(args.issue_id)
    if state is None:
        print(f"No workflow found for {args.issue_id}", file=sys.stderr)
        return 1

    manual_mode = args.manual
    dry_run = args.dry_run

    if args.worker_cmd:
        _validate_worker_cmd(args.worker_cmd)
        coordinator.worker_fn = _make_worker_cmd(args.worker_cmd)
        manual_mode = False
        dry_run = False
    elif not dry_run and not manual_mode:
        # Default: manual mode when no worker-cmd, dry-run, or manual flag.
        manual_mode = True

    paid_scale = tuple(args.paid_3x10) if args.paid_3x10 else None

    state = coordinator.run(
        state=state,
        dry_run=dry_run,
        manual_mode=manual_mode,
        paid_experiment_scale=paid_scale,
        northstar_change=args.northstar_change,
        large_refactor=args.large_refactor,
        data_migration=args.data_migration,
        swebench_docker=args.swebench_docker,
        higher_risk=args.higher_risk,
    )

    if state.status == "paused":
        print(f"Workflow paused: {state.paused_reason_label}", file=sys.stderr)
        return 2
    if state.status == "failed":
        return 1
    return 0


def cmd_status(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    state = coordinator.load_state(args.issue_id)
    if state is None:
        print(f"No workflow found for {args.issue_id}")
        return 1
    coordinator.print_status(args.issue_id)
    return 0


def _iter_workflow_states(coordinator: AutoResearchCoordinator):
    """Yield (issue_id, WorkflowState) for all on-disk workflows."""
    wdir = coordinator.workflows_dir
    if not wdir.is_dir():
        return
    for wf_dir in sorted(wdir.iterdir()):
        if not wf_dir.is_dir():
            continue
        sp = wf_dir / "state.json"
        if not sp.is_file():
            continue
        state = coordinator.load_state(wf_dir.name)
        if state is not None:
            yield state


def cmd_list(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    states_list = list(_iter_workflow_states(coordinator))

    if args.status:
        states_list = [s for s in states_list if s.status == args.status]
    if args.paused_only:
        states_list = [s for s in states_list if s.status == "paused"]

    if not states_list:
        filter_desc = ""
        if args.status:
            filter_desc = f" with status={args.status}"
        if args.paused_only:
            filter_desc = " (paused only)"
        print(f"No workflows{filter_desc}.")
        return 0

    labels = PauseReason.all_labels()
    print(f"{'ISSUE':<30} {'STATUS':<12} {'ATTEMPT':<10} {'PAUSED':<40}")
    print("-" * 92)
    for state in states_list:
        paused = (
            labels.get(state.paused_reason or "", state.paused_reason or "")
            if state.paused_reason
            else ""
        )
        print(
            f"{state.issue_id:<30} {state.status:<12} "
            f"{f'{state.attempt}/{state.max_retries}':<10} {paused:<40}"
        )

    # Summary counts (from all workflows, not filtered)
    all_states = list(_iter_workflow_states(coordinator))
    counts: dict[str, int] = {}
    for s in all_states:
        counts[s.status] = counts.get(s.status, 0) + 1
    print()
    print(f"Total: {sum(counts.values())} workflows — " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0


def cmd_next(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    state = coordinator.load_state(args.issue_id)
    if state is None:
        print(f"No workflow found for {args.issue_id}")
        return 1

    actions = {
        "pending": "run — start the first attempt with: run --issue-id {id} [--dry-run | --manual | --worker-cmd CMD]",
        "running": "inspect worker_output and write codex_review — see: {review}",
        "failed": _next_for_failed,
        "paused": "owner/Codex approval required — pause reason: {reason}",
        "complete": "no action — workflow is complete",
    }

    label = actions.get(state.status, "unknown status: {status}")
    if callable(label):
        label = label(state)
    label = label.format(
        id=state.issue_id,
        review=state.codex_review_path,
        reason=state.paused_reason_label or state.paused_reason or "unknown",
        status=state.status,
    )
    print(f"Next action for {state.issue_id} (status={state.status}): {label}")
    return 0


def _next_for_failed(state) -> str:
    if state.attempt < state.max_retries:
        return "retry allowed — run --issue-id {id} [--worker-cmd CMD] (attempt {attempt}/{max})".format(
            id=state.issue_id, attempt=state.attempt, max=state.max_retries,
        )
    return "retry exhausted — mark-failed --issue-id {id} or escalate to owner".format(
        id=state.issue_id,
    )


def cmd_mark_complete(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    state = coordinator.load_state(args.issue_id)
    if state is None:
        print(f"No workflow found for {args.issue_id}", file=sys.stderr)
        return 1

    # Check codex_review.md before allowing mark-complete.
    review_path = coordinator.workflow_dir(args.issue_id) / "codex_review.md"
    if review_path.is_file():
        review_text = review_path.read_text()
        if "VERDICT: FAIL" in review_text:
            print(f"Cannot mark complete: codex review verdict is FAIL for {args.issue_id}", file=sys.stderr)
            return 1
        if "VERDICT: WARN" in review_text:
            if not getattr(args, "owner_override", None):
                print(f"Cannot mark complete: codex review verdict is WARN for {args.issue_id}. "
                      f"Use --owner-override REASON.", file=sys.stderr)
                return 1

    state = coordinator.mark_complete(state)

    # Record owner override reason if provided.
    override = getattr(args, "owner_override", None)
    if override:
        final_path = Path(state.final_path)
        existing = final_path.read_text() if final_path.is_file() else ""
        override_note = f"\n## Owner Override\n\nReason: {override}\nOverride at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        final_path.write_text(existing + override_note)

    print(f"Marked complete: {state.issue_id}")
    return 0


def cmd_mark_failed(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    state = coordinator.load_state(args.issue_id)
    if state is None:
        print(f"No workflow found for {args.issue_id}", file=sys.stderr)
        return 1
    state = coordinator.mark_failed(state, reason=args.reason)
    label = f" ({args.reason})" if args.reason else ""
    print(f"Marked failed: {state.issue_id}{label}")
    return 0


# ── Codex gate handlers ────────────────────────────────────────────────────

def cmd_review(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    from .autoresearch_codex_gate import review_issue, write_codex_review

    state = coordinator.load_state(args.issue_id)
    if state is None:
        print(f"No workflow found for {args.issue_id}", file=sys.stderr)
        return 1

    wf_dir = coordinator.workflow_dir(args.issue_id)
    result = review_issue(wf_dir)
    review_path = wf_dir / "codex_review.md"
    write_codex_review(result, review_path)

    print(f"Review complete for {args.issue_id}")
    print(f"  VERDICT: {result.verdict}")
    print(f"  SCORE: {result.score}/100")
    for w in result.warnings:
        print(f"  WARNING: {w}")
    print(f"  review: {review_path}")

    if result.verdict == "FAIL":
        return 1
    return 0


def cmd_goal_review(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    from .autoresearch_goal import GoalManager
    from .autoresearch_codex_gate import review_goal, write_codex_review

    gm = GoalManager(paper1_root=coordinator.paper1_root, coordinator=coordinator)
    goal = gm.load_goal(args.goal_id)
    if goal is None:
        print(f"No goal found for {args.goal_id}", file=sys.stderr)
        return 1

    results = review_goal(goal, coordinator)
    has_fail = False
    has_warn = False
    for issue_id, result in results.items():
        wf_dir = coordinator.workflow_dir(issue_id)
        review_path = wf_dir / "codex_review.md"
        write_codex_review(result, review_path)
        if result.verdict == "FAIL":
            has_fail = True
        elif result.verdict == "WARN":
            has_warn = True
        print(f"  {issue_id}: {result.verdict} ({result.score}/100)")

    # Write fresh goal summary with aggregated metadata.
    gm.write_goal_summary(args.goal_id)

    print(f"Goal review complete: {args.goal_id}")
    if has_fail:
        return 1
    if has_warn:
        return 2
    return 0


# ── Goal command handlers ──────────────────────────────────────────────────

def cmd_goal_create(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    from .autoresearch_goal import GoalManager
    gm = GoalManager(paper1_root=coordinator.paper1_root, coordinator=coordinator)
    goal = gm.create_goal(args.goal_id, args.title, budget_cap_usd=args.budget_cap_usd)
    print(f"Created goal: {goal.goal_id} — {goal.title}")
    print(f"  status: {goal.status}")
    print(f"  budget_cap: ${goal.real_api_budget_cap_usd:.2f}")
    print(f"  path: {gm._goal_path(goal.goal_id)}")
    return 0


def cmd_goal_add_issue(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    from .autoresearch_goal import GoalManager
    gm = GoalManager(paper1_root=coordinator.paper1_root, coordinator=coordinator)
    goal = gm.add_issue(args.goal_id, args.issue_id)
    if goal is None:
        print(f"Goal not found: {args.goal_id}", file=sys.stderr)
        return 1
    print(f"Added issue {args.issue_id} to goal {goal.goal_id}")
    print(f"  issues: {goal.issue_ids}")
    return 0


def cmd_goal_status(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    from .autoresearch_goal import GoalManager
    gm = GoalManager(paper1_root=coordinator.paper1_root, coordinator=coordinator)
    goal = gm.load_goal(args.goal_id)
    if goal is None:
        print(f"No goal found for {args.goal_id}")
        return 1
    gm.print_goal_status(args.goal_id)
    return 0


def cmd_goal_run(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    from .autoresearch_goal import GoalManager
    gm = GoalManager(paper1_root=coordinator.paper1_root, coordinator=coordinator)
    goal = gm.load_goal(args.goal_id)
    if goal is None:
        print(f"No goal found for {args.goal_id}", file=sys.stderr)
        return 1

    paid_scale = tuple(args.paid_3x10) if args.paid_3x10 else None

    result = gm.run_goal(
        args.goal_id,
        dry_run=args.dry_run,
        manual_mode=args.manual,
        worker_cmd=args.worker_cmd,
        paid_experiment_scale=paid_scale,
        northstar_change=args.northstar_change,
        large_refactor=args.large_refactor,
        data_migration=args.data_migration,
        swebench_docker=args.swebench_docker,
        higher_risk=args.higher_risk,
    )

    print(f"Goal run: {result.get('goal_status')}")
    if "issue_id" in result:
        print(f"  issue: {result['issue_id']} status={result.get('issue_status', '?')}")
    if "pause_reason" in result:
        print(f"  paused: {result['pause_reason']}", file=sys.stderr)
    if "action" in result:
        print(f"  action: {result['action']}")
    if "error" in result:
        print(f"  error: {result['error']}", file=sys.stderr)

    if result.get("goal_status") == "paused":
        return 2
    if result.get("goal_status") == "review_required":
        return 2
    if result.get("goal_status") == "error":
        return 1
    if result.get("goal_status") == "failed":
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    paper1_root = Path(args.paper1_root or DEFAULT_PAPER1)
    coordinator = AutoResearchCoordinator(paper1_root=paper1_root)

    handlers = {
        "create": cmd_create,
        "run": cmd_run,
        "status": cmd_status,
        "list": cmd_list,
        "next": cmd_next,
        "mark-complete": cmd_mark_complete,
        "mark-failed": cmd_mark_failed,
        "goal-create": cmd_goal_create,
        "goal-add-issue": cmd_goal_add_issue,
        "goal-status": cmd_goal_status,
        "goal-run": cmd_goal_run,
        "review": cmd_review,
        "goal-review": cmd_goal_review,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args, coordinator)


if __name__ == "__main__":
    sys.exit(main())
