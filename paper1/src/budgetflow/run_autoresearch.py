#!/usr/bin/env python3
"""AutoResearch CLI — create, run, status, list, mark-complete, mark-failed.

Usage:
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch create --issue-id ID --prompt-file PATH
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch run --issue-id ID [--dry-run | --manual | --worker-cmd CMD]
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch status --issue-id ID
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch list
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch mark-complete --issue-id ID
  PYTHONPATH=src python3 -m budgetflow.run_autoresearch mark-failed --issue-id ID --reason TEXT
"""

from __future__ import annotations

import argparse
import subprocess
import sys
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
    sub.add_parser("list", help="List all workflows")

    # mark-complete
    mc = sub.add_parser("mark-complete", help="Mark workflow as complete")
    mc.add_argument("--issue-id", required=True)

    # mark-failed
    mf = sub.add_parser("mark-failed", help="Mark workflow as failed")
    mf.add_argument("--issue-id", required=True)
    mf.add_argument("--reason", default="", help="Failure reason")

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
    return 0


def cmd_status(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    state = coordinator.load_state(args.issue_id)
    if state is None:
        print(f"No workflow found for {args.issue_id}")
        return 1
    coordinator.print_status(args.issue_id)
    return 0


def cmd_list(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    wdir = coordinator.workflows_dir
    if not wdir.is_dir():
        print("No workflows directory found.")
        return 0

    workflows = sorted(wdir.iterdir())
    if not workflows:
        print("No workflows.")
        return 0

    labels = PauseReason.all_labels()
    print(f"{'ISSUE':<30} {'STATUS':<12} {'ATTEMPT':<10} {'PAUSED':<40}")
    print("-" * 92)
    for wf_dir in workflows:
        if not wf_dir.is_dir():
            continue
        sp = wf_dir / "state.json"
        if not sp.is_file():
            continue
        state = coordinator.load_state(wf_dir.name)
        if state is None:
            continue
        paused = (
            labels.get(state.paused_reason or "", state.paused_reason or "")
            if state.paused_reason
            else ""
        )
        print(
            f"{state.issue_id:<30} {state.status:<12} "
            f"{f'{state.attempt}/{state.max_retries}':<10} {paused:<40}"
        )

    # Summary counts
    states: dict[str, int] = {}
    for wf_dir in workflows:
        if not wf_dir.is_dir():
            continue
        sp = wf_dir / "state.json"
        if not sp.is_file():
            continue
        state = coordinator.load_state(wf_dir.name)
        if state:
            states[state.status] = states.get(state.status, 0) + 1
    print()
    print(f"Total: {sum(states.values())} workflows — " + ", ".join(f"{k}={v}" for k, v in sorted(states.items())))
    return 0


def cmd_mark_complete(args: argparse.Namespace, coordinator: AutoResearchCoordinator) -> int:
    state = coordinator.load_state(args.issue_id)
    if state is None:
        print(f"No workflow found for {args.issue_id}", file=sys.stderr)
        return 1
    state = coordinator.mark_complete(state)
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
        "mark-complete": cmd_mark_complete,
        "mark-failed": cmd_mark_failed,
    }

    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args, coordinator)


if __name__ == "__main__":
    sys.exit(main())
