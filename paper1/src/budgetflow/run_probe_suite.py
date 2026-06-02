"""Launch parallel BudgetFlow diagnostic sweeps (pressure_max / tight_scale).

Spawns subprocess compare runs with isolated --out-stem under data/runs/sweeps/.

Usage:
  cd paper1 && PYTHONPATH=src:../external/mini-swe-agent/src \\
    python -u -m budgetflow.run_probe_suite --limit 5 --suite parallel --max-jobs 2
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
REPO_ROOT = SRC.parent
MINI_SWE_SRC = REPO_ROOT.parent / "external" / "mini-swe-agent" / "src"
PYTHONPATH = f"{SRC}:{MINI_SWE_SRC}"
SWEEPS_DIR = REPO_ROOT / "data" / "runs" / "sweeps"


def _parse_float_list(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def _compare_cmd(
    *,
    limit: int,
    stem: str,
    pressure_max: float | None = None,
    tight_scale: float = 1.0,
    strategies: str,
    jobs: int,
    step_limit: int,
) -> list[str]:
    cmd = [
        sys.executable,
        "-u",
        "-m",
        "budgetflow.run_mini_swe_compare",
        "--limit",
        str(limit),
        "--read-frozen-caps",
        "--jobs",
        str(jobs),
        "--strategies",
        strategies,
        "--trace-verbose",
        "--heartbeat",
        "30",
        "--step-limit",
        str(step_limit),
        "--out-stem",
        f"sweeps/{stem}",
        "--tight-scale",
        str(tight_scale),
    ]
    if pressure_max is not None:
        cmd.extend(["--pressure-max", str(pressure_max)])
    return cmd


def _run_job(name: str, cmd: list[str], log_path: Path) -> tuple[str, int]:
    env = os.environ.copy()
    env["PYTHONPATH"] = PYTHONPATH
    env.setdefault("FORCE_COLOR", "1")
    SWEEPS_DIR.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w") as log:
        log.write(f"# cmd: {' '.join(cmd)}\n\n")
        log.flush()
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
    return name, proc.returncode


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parallel BudgetFlow probe sweeps")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--step-limit", type=int, default=150)
    parser.add_argument("--policy-jobs", type=int, default=3, help="--jobs per compare subprocess")
    parser.add_argument("--max-jobs", type=int, default=2, help="max concurrent compare subprocesses")
    parser.add_argument(
        "--strategies",
        type=str,
        default="all_spark_tight,budget_only_tight,budgetflow_full_tight",
    )
    parser.add_argument(
        "--pressure-values",
        type=str,
        default="1.5,3.5,7,14",
        help="PRESSURE_MAX sweep values",
    )
    parser.add_argument(
        "--tight-scales",
        type=str,
        default="0.5,1,2",
        help="tight batch cap multipliers (relative to protocol)",
    )
    parser.add_argument(
        "--suite",
        choices=("pressure", "cap", "both", "parallel"),
        default="parallel",
        help="pressure=PRESSURE_MAX sweep; cap=tight_scale; both=sequential; parallel=pressure+cap together",
    )
    parser.add_argument("--skip-deepseek", action="store_true")
    parser.add_argument("--deepseek-model", type=str, default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    started = time.time()
    SWEEPS_DIR.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[str, list[str], Path]] = []

    if not args.skip_deepseek:
        ds_cmd = [
            sys.executable,
            "-u",
            "-m",
            "budgetflow.run_deepseek_probe",
            "--limit",
            str(args.limit),
            "--step-limit",
            str(args.step_limit),
            "--jobs",
            str(min(3, args.limit)),
            "--tier",
            "flash,pro",
        ]
        if args.deepseek_model:
            ds_cmd.extend(["--model", args.deepseek_model])
        jobs.append(("deepseek_uncapped", ds_cmd, SWEEPS_DIR / "deepseek_uncapped.log"))

    pressure_vals = _parse_float_list(args.pressure_values)
    tight_scales = _parse_float_list(args.tight_scales)

    if args.suite in ("pressure", "both", "parallel"):
        for pmax in pressure_vals:
            stem = f"pressure_max_{pmax:g}".replace(".", "p")
            cmd = _compare_cmd(
                limit=args.limit,
                stem=stem,
                pressure_max=pmax,
                tight_scale=1.0,
                strategies=args.strategies,
                jobs=args.policy_jobs,
                step_limit=args.step_limit,
            )
            jobs.append((stem, cmd, SWEEPS_DIR / f"{stem}.log"))

    if args.suite in ("cap", "both", "parallel"):
        for scale in tight_scales:
            stem = f"tight_scale_{scale:g}".replace(".", "p")
            cmd = _compare_cmd(
                limit=args.limit,
                stem=stem,
                pressure_max=None,
                tight_scale=scale,
                strategies=args.strategies,
                jobs=args.policy_jobs,
                step_limit=args.step_limit,
            )
            jobs.append((stem, cmd, SWEEPS_DIR / f"{stem}.log"))

    if not jobs:
        raise SystemExit("no jobs configured")

    print(f"[suite] {len(jobs)} probe jobs, max_parallel={args.max_jobs}", flush=True)
    for name, cmd, log_path in jobs:
        print(f"  - {name} -> {log_path}", flush=True)

    results: list[tuple[str, int]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.max_jobs)) as pool:
        futures = {pool.submit(_run_job, name, cmd, log): name for name, cmd, log in jobs}
        for future in as_completed(futures):
            name, code = future.result()
            results.append((name, code))
            status = "OK" if code == 0 else f"FAIL({code})"
            print(f"[suite] {status} {name}", flush=True)

    failed = [n for n, c in results if c != 0]
    print(f"\n[suite] done elapsed={time.time() - started:.1f}s failed={failed or 'none'}", flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
