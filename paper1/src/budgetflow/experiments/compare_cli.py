"""CLI parsing for compare experiments."""

from __future__ import annotations

import argparse
from typing import Any

from budgetflow.defaults import BUDGET_PRESSURE_INIT, PRESSURE_MAX


PRESET_TASKS = {"3x3": 3, "3x5": 3, "5x5": 5, "segment-control": 3}


def parse_compare_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="N tasks x strategies - shared batch budget per policy")
    parser.add_argument(
        "--preset",
        choices=sorted(PRESET_TASKS),
        default="3x3",
        help="3x3=budget-only plus Bootstrap Policy diagnostic; segment-control=adds value-aware task-level control",
    )
    parser.add_argument("--limit", type=int, default=None, help="task count (default from --preset)")
    parser.add_argument("--loose", type=float, default=None, help="shared batch budget for *_loose strategies")
    parser.add_argument("--tight", type=float, default=None, help="shared batch budget for *_tight strategies")
    parser.add_argument(
        "--step-limit",
        type=int,
        default=150,
        help="agent step cap per task (default 150; raise for hard localization tasks)",
    )
    parser.add_argument("--heartbeat", type=float, default=30.0)
    parser.add_argument(
        "--jobs",
        type=int,
        default=None,
        help="parallel policy batches (default: one worker per policy; each policy still runs tasks serially)",
    )
    parser.add_argument("--trace-quiet", action="store_true", help="suppress per-step trace boards")
    parser.add_argument("--trace-verbose", action="store_true", help="print every agent step")
    parser.add_argument(
        "--strategies",
        type=str,
        default=None,
        help="comma-separated strategy names subset",
    )
    parser.add_argument("--append", action="store_true", help="append to existing jsonl instead of overwriting")
    parser.add_argument("--skip-completed", action="store_true", help="with --append, skip completed pairs")
    parser.add_argument("--resume", action="store_true", help="continue run from JSONL/checkpoint state")
    parser.add_argument(
        "--task-set",
        choices=("easy", "medium"),
        default="easy",
        help="easy=5 compare_easy tasks; medium=15 sympy medium-hard",
    )
    parser.add_argument("--ids", type=str, default=None, help="comma-separated instance IDs")
    parser.add_argument("--out-stem", type=str, default=None, help="optional explicit output basename")
    parser.add_argument("--run-series", type=str, default=None, metavar="BASE", help="series prefix for auto IDs")
    parser.add_argument(
        "--pressure-init",
        type=float,
        default=None,
        help=f"override BUDGET_PRESSURE_INIT (default {BUDGET_PRESSURE_INIT})",
    )
    parser.add_argument(
        "--pressure-max",
        type=float,
        default=None,
        help=f"override PRESSURE_MAX ceiling (default {PRESSURE_MAX})",
    )
    parser.add_argument("--tight-scale", type=float, default=1.0, help="multiply tight batch cap")
    parser.add_argument("--loose-scale", type=float, default=1.0, help="multiply loose batch cap")
    parser.add_argument("--no-run-guards", action="store_true", help="disable auto-halt guards")
    parser.add_argument("--no-provider-signature-check", action="store_true", help="skip provider preflight checks")
    parser.add_argument("--trace-turns", action="store_true", help="collect per-turn routing traces")
    parser.add_argument("--no-trace-turns", action="store_false", dest="trace_turns", help="disable turn traces")
    parser.set_defaults(trace_turns=True)
    parser.add_argument("--trace-max-turns", type=int, default=200, help="max turn traces to keep per task")
    parser.add_argument("--trace-truncate-chars", type=int, default=120, help="max bash digest chars")
    parser.add_argument(
        "--value-profile",
        choices=("equal", "difficulty", "discriminative_rarity", "unsolved_difficulty", "combined", "cold_start_difficulty"),
        default="equal",
        help="Value profile for task value assignment",
    )
    parser.add_argument("--value-matrix", type=str, default=None, help="path to value matrix JSON artifact")
    parser.add_argument(
        "--per-task-cap",
        type=float,
        default=None,
        help="fresh governor cap per task; avoids shared-pool starvation",
    )
    parser.add_argument("--auto-budget", action="store_true", default=False, help="enable learned per-task caps")
    parser.add_argument("--auto-budget-dry-run", action="store_true", default=False, help="print cap estimates and exit")
    parser.add_argument("--paid-readiness-only", action="store_true", default=False, help="validate paid-run setup and exit before provider calls")
    parser.add_argument("--auto-budget-scale", type=float, default=1.5, help="multiply estimated cost")
    parser.add_argument("--auto-budget-min", type=float, default=0.10, help="minimum per-task cap")
    parser.add_argument("--auto-budget-max", type=float, default=10.0, help="maximum per-task cap")
    parser.add_argument("--auto-budget-mode", choices=("per_task",), default="per_task", help="budget mode")
    parser.add_argument("--auto-budget-memory", type=str, default=None, help="Value-Driven Budget Allocation memory")
    parser.add_argument(
        "--allow-global-fallback-auto-budget",
        action="store_true",
        default=False,
        help="allow paid runs when auto-budget caps are entirely global fallback diagnostics",
    )
    parser.add_argument("--no-auto-budget-learn", action="store_true", default=False, help="disable memory writes")
    parser.add_argument("--auto-budget-k", type=int, default=3, help="k for kNN fallback")
    parser.add_argument("--runtime-root", type=str, default=None, help="runtime scratch root")
    parser.add_argument("--allow-nfs-runtime", action="store_true", default=False, help="allow NFS runtime root")
    parser.add_argument("--worktree-root", type=str, default=None, help="override worktree dir")
    parser.add_argument("--soft-budget", type=float, default=None, help="optional soft budget for shared mode")
    parser.add_argument("--max-overrun", type=float, default=0.0, help="bounded overrun above cap")
    parser.add_argument(
        "--w-profile",
        choices=("repair_heavy", "validation_heavy", "flat"),
        default=None,
        help="w_i ordering for budgetflow_full",
    )
    parser.add_argument("--policy-memory", type=str, default=None, help="JSONL source for PolicyMemory priors")
    parser.add_argument("--disable-policy-memory", action="store_true", default=False, help="disable PolicyMemory")
    parser.add_argument("--policy-memory-gate-only", action="store_true", default=False, help="print policy-memory gate")
    parser.add_argument("--regret-threshold", type=float, default=None, help="override policy regret threshold")
    return parser.parse_args(argv)
