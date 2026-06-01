from __future__ import annotations

import argparse
import json
from pathlib import Path

from .lite_tasks import load_compare_easy_tasks, load_swebench_lite_tasks
from .local_harness import evaluate_local_harness

RUNS_DIR = Path(__file__).resolve().parents[2] / "data" / "runs"


def _load_tasks(args: argparse.Namespace):
    if args.ids:
        ids = tuple(part.strip() for part in args.ids.split(",") if part.strip())
        return load_swebench_lite_tasks(instance_ids=ids)
    return load_compare_easy_tasks(args.limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate local harness by replaying SWE-bench gold patches.")
    parser.add_argument("--ids", type=str, default=None, help="comma-separated SWE-bench instance IDs")
    parser.add_argument("--limit", type=int, default=5, help="compare_easy task count when --ids is omitted")
    parser.add_argument("--out", type=Path, default=RUNS_DIR / "gold_harness_probe.jsonl")
    args = parser.parse_args()

    tasks = _load_tasks(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    passed = 0
    with args.out.open("w") as handle:
        for task in tasks:
            print(f"[gold] {task.instance_id}", flush=True)
            result = evaluate_local_harness(
                task,
                task.patch,
                workspace_key=f"gold_probe_{task.instance_id}",
            )
            record = {
                "instance_id": task.instance_id,
                "gold_resolved": result.harness_resolved,
                "test_patch_ok": result.test_patch_ok,
                "fail_before": result.fail_before,
                "model_patch_ok": result.model_patch_ok,
                "fail_after": result.fail_after,
                "pass_to_pass": result.pass_to_pass_passed,
                "detail": result.detail,
                "repo_dir": result.repo_dir,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            if result.harness_resolved:
                passed += 1
            status = "PASS" if result.harness_resolved else "FAIL"
            print(
                f"[gold] {task.instance_id} {status} "
                f"fail_before={result.fail_before} fail_after={result.fail_after} "
                f"p2p={result.pass_to_pass_passed}",
                flush=True,
            )
    print(f"[gold] resolved={passed}/{len(tasks)} out={args.out}", flush=True)
    if passed != len(tasks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
