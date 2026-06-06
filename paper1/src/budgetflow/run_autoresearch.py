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
import re
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

    # goal-loop
    gl = sub.add_parser("goal-loop", help="Run full AutoResearch loop for a Goal")
    gl.add_argument("--goal-id", required=True, help="Goal identifier")
    gl.add_argument("--worker-cmd", required=True, help="Shell command template with {prompt} and {output}")
    gl.add_argument("--max-steps", type=int, default=10, help="Max loop iterations (default: 10)")
    gl.add_argument("--commit-after-pass", action="store_true", help="Git commit after each PASS review")
    gl.add_argument("--push-after-commit", action="store_true", help="Git push after each commit")
    gl.add_argument("--owner-override", help="Auto-approve WARN reviews with this reason")
    # Pause flags
    gl.add_argument("--paid-3x10", nargs=2, type=int, metavar=("P", "T"))
    gl.add_argument("--northstar-change", action="store_true")
    gl.add_argument("--large-refactor", action="store_true")
    gl.add_argument("--data-migration", action="store_true")
    gl.add_argument("--swebench-docker", action="store_true")
    gl.add_argument("--higher-risk", action="store_true")

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


def _write_owner_decision(
    workflow_dir: Path,
    issue_id: str,
    why: str,
    evidence_files: list[str],
    recommendation: str,
    resume_command: str,
    what_happens_if_approved: str,
) -> Path:
    """Write owner_decision.md for a paused issue."""
    lines = [
        f"# Owner Decision Required — {issue_id}",
        "",
        "## Why Paused",
        "",
        why,
        "",
        "## Evidence Files",
        "",
    ]
    for ef in evidence_files:
        lines.append(f"- {ef}")
    lines.extend([
        "",
        "## Recommended Decision",
        "",
        recommendation,
        "",
        "## Resume Command",
        "",
        "```bash",
        resume_command,
        "```",
        "",
        "## What Happens If Approved",
        "",
        what_happens_if_approved,
        "",
        "---",
        f"Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
    ])
    dp = workflow_dir / "owner_decision.md"
    dp.write_text("\n".join(lines) + "\n")
    return dp


_DEFAULT_SECRET_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}"),
    re.compile(r"x-api-key:\s*[a-zA-Z0-9_-]{10,}"),
    re.compile(r"ANTHROPIC_API_KEY\s*=\s*[a-zA-Z0-9_-]{10,}"),
    re.compile(r"ANTHROPIC_AUTH_TOKEN\s*=\s*[a-zA-Z0-9_-]{10,}"),
]


def _scan_staged_for_secrets(repo_root: Path) -> list[str]:
    """Scan staged files for secret-like patterns. Returns list of findings."""
    import re as _re
    findings = []
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, cwd=str(repo_root),
    )
    staged = [f for f in result.stdout.strip().split("\n") if f]
    if not staged:
        return findings
    for fpath in staged:
        full = repo_root / fpath
        if not full.is_file():
            continue
        try:
            content = full.read_text()
        except Exception:
            continue
        for pat in _DEFAULT_SECRET_PATTERNS:
            if pat.search(content):
                findings.append(f"{fpath}: possible secret ({pat.pattern[:40]}...)")
    return findings


def _safe_commit_push(
    coordinator,
    goal_id: str,
    *,
    push: bool = False,
    pytest_cmd: str | None = None,
) -> tuple[int, str]:
    """Post-gate commit/push with safety checks.

    Returns (exit_code, message).
    """
    repo_root = coordinator.git_root or coordinator.paper1_root

    # 1. Stage only allowed evidence/code paths before scanning staged content.
    stage_paths = [
        ".autoresearch/",
        "docs/reports/",
        "src/",
        "tests/",
        "scripts/",
    ]
    for sp in stage_paths:
        full = repo_root / "paper1" / sp if (repo_root / "paper1").is_dir() else repo_root / sp
        if full.exists():
            stage_result = subprocess.run(
                ["git", "add", str(full.relative_to(repo_root))],
                capture_output=True, text=True, cwd=str(repo_root),
            )
            if stage_result.returncode != 0:
                return 1, f"git add failed for {sp}:\n{stage_result.stderr[:500]}"

    # 2. Check staged diff whitespace/conflict-marker health.
    diff_check = subprocess.run(
        ["git", "diff", "--cached", "--check"],
        capture_output=True, text=True, cwd=str(repo_root),
    )
    if diff_check.returncode != 0:
        return 1, f"git diff --cached --check failed:\n{diff_check.stdout[:500]}{diff_check.stderr[:500]}"

    # 3. Secret scan over the exact staged set.
    secrets = _scan_staged_for_secrets(repo_root)
    if secrets:
        return 1, f"Secret scan found issues:\n" + "\n".join(secrets)

    # 4. pytest (if provided)
    if pytest_cmd:
        pytest_result = subprocess.run(
            pytest_cmd, shell=True, capture_output=True, text=True, cwd=str(repo_root),
        )
        if pytest_result.returncode != 0:
            return 1, f"pytest failed (rc={pytest_result.returncode}):\n{pytest_result.stdout[-500:]}\n{pytest_result.stderr[-500:]}"

    # 5. Commit
    commit_msg = f"AutoResearch: complete {goal_id}\n\nCo-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
    commit_result = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        capture_output=True, text=True, cwd=str(repo_root),
    )
    if commit_result.returncode != 0:
        return 1, f"git commit failed:\n{commit_result.stderr[:500]}"

    commit_hash = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=str(repo_root),
    ).stdout.strip()[:12]

    # 6. Push
    if push:
        push_result = subprocess.run(
            ["git", "push"],
            capture_output=True, text=True, cwd=str(repo_root),
        )
        if push_result.returncode != 0:
            return 1, f"git push failed (commit={commit_hash}):\n{push_result.stderr[:500]}"
        return 0, f"committed {commit_hash} and pushed"

    return 0, f"committed {commit_hash} (not pushed)"


def cmd_goal_loop(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    """Run the full AutoResearch loop for a Goal."""
    from .autoresearch_goal import GoalManager
    from .autoresearch_codex_gate import review_issue, write_codex_review

    _validate_worker_cmd(args.worker_cmd)

    gm = GoalManager(paper1_root=coordinator.paper1_root, coordinator=coordinator)
    goal = gm.load_goal(args.goal_id)
    if goal is None:
        print(f"No goal found for {args.goal_id}", file=sys.stderr)
        return 1

    owner_override = getattr(args, "owner_override", None)
    paid_scale = tuple(args.paid_3x10) if args.paid_3x10 else None

    step = 0
    while step < args.max_steps:
        step += 1
        print(f"\n--- goal-loop step {step}/{args.max_steps} ---")

        # Run one step of the goal.
        result = gm.run_goal(
            args.goal_id,
            worker_cmd=args.worker_cmd,
            paid_experiment_scale=paid_scale,
            northstar_change=args.northstar_change,
            large_refactor=args.large_refactor,
            data_migration=args.data_migration,
            swebench_docker=args.swebench_docker,
            higher_risk=args.higher_risk,
        )

        gs = result.get("goal_status", "?")
        issue_id = result.get("issue_id")

        # Handle goal-level terminal states.
        if gs == "paused":
            pause_reason = result.get("pause_reason", "unknown")
            print(f"Goal paused: {pause_reason}")
            # Write owner_decision for the paused issue or at goal level.
            if issue_id:
                wf_dir = coordinator.workflow_dir(issue_id)
            else:
                wf_dir = coordinator.paper1_root / ".autoresearch" / "goals"
            _write_owner_decision(
                wf_dir, issue_id or args.goal_id,
                why=f"AutoResearch paused: {pause_reason}",
                evidence_files=[str(gm._goal_path(args.goal_id))],
                recommendation="Review the pause reason. If safe, re-run with appropriate flags cleared.",
                resume_command=f"PYTHONPATH=src python3 -m budgetflow.run_autoresearch goal-loop --goal-id {args.goal_id} --worker-cmd '{args.worker_cmd}'",
                what_happens_if_approved="The goal-loop will resume from the current position.",
            )
            return 2

        if gs == "failed":
            print(f"Goal failed: {result.get('action', 'unknown')}")
            return 1

        if gs == "review_required":
            print(f"Goal requires review: {result.get('action', 'unknown')}")
            return 2

        if gs == "complete":
            print(f"Goal complete: {result.get('action', '')}")
            gm.write_goal_summary(args.goal_id)
            if args.commit_after_pass:
                rc, msg = _safe_commit_push(
                    coordinator, args.goal_id,
                    push=args.push_after_commit,
                )
                print(msg)
                if rc != 0:
                    return 1
            return 0

        if gs == "error":
            print(f"Goal error: {result.get('error', 'unknown')}")
            return 1

        # gs == "running": an issue was processed.
        if issue_id is None:
            print("No issue processed — continuing loop.")
            continue

        wf_dir = coordinator.workflow_dir(issue_id)
        print(f"Processed issue: {issue_id} status={result.get('issue_status', '?')}")

        # Run deterministic review.
        review_result = review_issue(wf_dir)
        review_path = wf_dir / "codex_review.md"
        write_codex_review(review_result, review_path)
        print(f"  review: {review_result.verdict} ({review_result.score}/100)")

        if review_result.verdict == "PASS":
            # Mark complete (or keep complete if already).
            state = coordinator.load_state(issue_id)
            if state and state.status != "complete":
                coordinator.mark_complete(state)
            print(f"  -> PASS, marked complete.")

            # Optional commit after each PASS.
            if args.commit_after_pass:
                rc, msg = _safe_commit_push(
                    coordinator, f"{args.goal_id}/{issue_id}",
                    push=args.push_after_commit,
                )
                print(f"  commit: {msg}")
                if rc != 0:
                    return 1

        elif review_result.verdict == "WARN":
            if owner_override:
                state = coordinator.load_state(issue_id)
                if state:
                    coordinator.mark_complete(state)
                    final_path = Path(state.final_path)
                    existing = final_path.read_text() if final_path.is_file() else ""
                    override_note = f"\n## Owner Override (goal-loop)\n\nReason: {owner_override}\nOverride at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
                    final_path.write_text(existing + override_note)
                print(f"  -> WARN overridden by owner: {owner_override}")
            else:
                _write_owner_decision(
                    wf_dir, issue_id,
                    why=f"Deterministic review returned WARN ({review_result.score}/100).\nWarnings: {'; '.join(review_result.warnings) if review_result.warnings else 'none'}",
                    evidence_files=[str(review_path), str(wf_dir / "attempts" / "001" / "worker_output.md"), str(wf_dir / "attempts" / "001" / "worker_metadata.json")],
                    recommendation="Review the warnings. If acceptable, approve with --owner-override.",
                    resume_command=f"PYTHONPATH=src python3 -m budgetflow.run_autoresearch goal-loop --goal-id {args.goal_id} --worker-cmd '{args.worker_cmd}' --owner-override 'Reviewed WARN, acceptable'",
                    what_happens_if_approved="The issue will be marked complete and the goal-loop will continue to the next issue.",
                )
                goal.status = "review_required"
                gm._write_goal(goal)
                print(f"  -> WARN: owner_decision.md written, goal set to review_required")
                return 2

        elif review_result.verdict == "FAIL":
            # Check retry state.
            state = coordinator.load_state(issue_id)
            if state and state.attempt < state.max_retries:
                print(f"  -> FAIL, retry available (attempt {state.attempt}/{state.max_retries})")
                # Leave as failed — next loop iteration will retry.
            else:
                _write_owner_decision(
                    wf_dir, issue_id,
                    why=f"Deterministic review returned FAIL ({review_result.score}/100). Retries exhausted ({state.attempt if state else '?'}/{state.max_retries if state else '?'}).",
                    evidence_files=[str(review_path), str(wf_dir / "attempts" / "001" / "worker_output.md")],
                    recommendation="Investigate the failure. May need prompt or worker fix, then retry.",
                    resume_command=f"PYTHONPATH=src python3 -m budgetflow.run_autoresearch goal-loop --goal-id {args.goal_id} --worker-cmd '{args.worker_cmd}'",
                    what_happens_if_approved="The issue will be retried with a new worker attempt.",
                )
                goal.status = "paused"
                gm._write_goal(goal)
                print(f"  -> FAIL, retries exhausted: owner_decision.md written")
                return 1

        # Write fresh goal summary.
        gm.write_goal_summary(args.goal_id)

    print(f"goal-loop: max steps ({args.max_steps}) reached.")
    return 1


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
        "goal-loop": cmd_goal_loop,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args, coordinator)


if __name__ == "__main__":
    sys.exit(main())
