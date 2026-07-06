"""Gold sanity for 8 Django candidates.

Usage: PYTHONPATH=src python scripts/django_gold_sanity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PAPER1_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PAPER1_ROOT / "src"))

from budgetflow.lite_tasks import build_lite_task_record, parse_test_list
from budgetflow.local_harness_adapters import DjangoHAdapter, harness_python
from budgetflow.local_harness import clone_or_checkout, apply_patch, test_paths_for  # noqa: E402

CANDIDATES = [
    "django__django-10924",
    "django__django-12113",
    "django__django-16046",
    "django__django-15388",
    "django__django-11099",
    "django__django-11049",
    "django__django-11001",
    "django__django-10914",
]

# Minimal failure classification.
CLASS_HARNESS_UNSUPPORTED = "harness_unsupported"
CLASS_OFFICIAL_TASK_ISSUE = "official_task_issue"
CLASS_LOCAL_DEPENDENCY = "local_dependency_issue"
CLASS_GOLD_PATCH_FAIL = "real_gold_patch_failure"


def load_task(instance_id: str) -> dict:
    test_jsonl = PAPER1_ROOT / "data" / "swebench_lite_export" / "test.jsonl"
    for line in test_jsonl.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("instance_id") == instance_id:
            return d
    raise KeyError(instance_id)


def main() -> None:
    import subprocess
    import os

    results: list[dict] = []

    for iid in CANDIDATES:
        print(f"\n{'='*70}")
        print(f"  {iid}")
        print(f"{'='*70}")

        result = {
            "instance_id": iid,
            "test_patch_ok": False,
            "fail_before_pass": False,
            "fail_after_pass": False,
            "pass_to_pass_pass": False,
            "resolved": False,
            "classification": None,
            "detail": "",
        }

        try:
            raw = load_task(iid)
        except KeyError:
            result["classification"] = CLASS_OFFICIAL_TASK_ISSUE
            result["detail"] = "not found in local export"
            results.append(result)
            print(f"  SKIP: not in local export")
            continue

        task = build_lite_task_record(raw)
        adapter = DjangoHAdapter()

        # Setup worktree
        try:
            repo_dir = clone_or_checkout(task, workspace_key=f"gold_{iid}")
        except Exception as exc:
            result["classification"] = CLASS_LOCAL_DEPENDENCY
            result["detail"] = f"clone/checkout failed: {exc}"
            results.append(result)
            print(f"  FAIL: {result['detail']}")
            continue

        # Apply compat
        compat = adapter.apply_compat(repo_dir)
        print(f"  compat: {compat}")

        test_paths = test_paths_for(task)

        # Apply test_patch
        if task.test_patch:
            ok, msg = apply_patch(repo_dir, task.test_patch, "test_patch")
            result["test_patch_ok"] = ok
            print(f"  test_patch: {'OK' if ok else msg}")
            if not ok:
                result["classification"] = CLASS_GOLD_PATCH_FAIL
                result["detail"] = f"test_patch failed: {msg}"
                results.append(result)
                continue

        # Run fail_to_pass (should FAIL before model patch)
        fail_before_names = list(task.fail_to_pass)
        print(f"  fail_to_pass names: {fail_before_names[:3]}...")

        # Convert to Django labels and build command
        from budgetflow.local_harness_adapters import build_pytest_node_ids
        node_ids, missing = build_pytest_node_ids(repo_dir, tuple(fail_before_names), test_paths, adapter=adapter)
        print(f"  node_ids: {node_ids}")
        if missing:
            print(f"  missing: {missing}")

        if not node_ids:
            result["classification"] = CLASS_HARNESS_UNSUPPORTED
            result["detail"] = f"no node ids from fail_to_pass: {missing}"
            results.append(result)
            print(f"  FAIL: {result['detail']}")
            continue

        cmd = adapter.build_test_command(repo_dir, node_ids)
        print(f"  cmd: {' '.join(cmd[:6])}...")

        env = {**os.environ, "PYTHONPATH": str(repo_dir)}
        proc = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True, env=env)
        output = (proc.stdout + "\n" + proc.stderr).strip()
        # fail_before should FAIL (returncode != 0 means tests failed = correct)
        fail_before = proc.returncode != 0
        result["fail_before_pass"] = fail_before
        print(f"  fail_before: {'PASS (tests failed as expected)' if fail_before else 'UNEXPECTED PASS'}")

        # Apply model patch (gold patch)
        if task.patch:
            ok, msg = apply_patch(repo_dir, task.patch, "model_patch")
            print(f"  model_patch: {'OK' if ok else msg}")
            if not ok:
                result["classification"] = CLASS_GOLD_PATCH_FAIL
                result["detail"] = f"model_patch failed: {msg}"
                results.append(result)
                continue

        # Run fail_to_pass again (should PASS after model patch)
        proc2 = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True, env=env)
        output2 = (proc2.stdout + "\n" + proc2.stderr).strip()
        fail_after = proc2.returncode == 0
        result["fail_after_pass"] = fail_after
        print(f"  fail_after: {'PASS' if fail_after else 'FAIL'}")
        if not fail_after:
            tail = output2[-500:] if len(output2) > 500 else output2
            print(f"  fail_after output: {tail[:300]}")

        # Run pass_to_pass
        pass_names = list(task.pass_to_pass) if task.pass_to_pass else []
        if pass_names:
            pt_node_ids, pt_missing = build_pytest_node_ids(repo_dir, tuple(pass_names), test_paths, adapter=adapter)
            if pt_node_ids:
                pt_cmd = adapter.build_test_command(repo_dir, pt_node_ids)
                pt_proc = subprocess.run(pt_cmd, cwd=repo_dir, capture_output=True, text=True, env=env)
                pt_ok = pt_proc.returncode == 0
                result["pass_to_pass_pass"] = pt_ok
                print(f"  pass_to_pass: {'PASS' if pt_ok else 'FAIL'}")
                if not pt_ok:
                    pt_out = (pt_proc.stdout + "\n" + pt_proc.stderr).strip()
                    print(f"  pass_to_pass output: {pt_out[-300:]}")
        else:
            result["pass_to_pass_pass"] = True
            print(f"  pass_to_pass: SKIP (none)")

        resolved = fail_before and fail_after and result["pass_to_pass_pass"]
        result["resolved"] = resolved

        if not resolved:
            if not fail_before:
                result["classification"] = CLASS_OFFICIAL_TASK_ISSUE
                result["detail"] = "fail_to_pass tests pass without fix"
            elif not fail_after:
                result["classification"] = CLASS_GOLD_PATCH_FAIL
                result["detail"] = "fail_to_pass tests still fail after gold patch"
            elif not result["pass_to_pass_pass"]:
                result["classification"] = CLASS_HARNESS_UNSUPPORTED
                result["detail"] = "pass_to_pass tests fail"

        print(f"  RESOLVED: {resolved}")
        results.append(result)

    # Summary table
    print("\n\n" + "="*70)
    print("  SUMMARY")
    print("="*70)
    print(f"{'Task':<30} {'Resolved':<10} {'Classification':<30}")
    print("-"*70)
    for r in results:
        print(f"{r['instance_id']:<30} {str(r['resolved']):<10} {r['classification'] or 'N/A':<30}")

    resolved_n = sum(1 for r in results if r["resolved"])
    print(f"\n{resolved_n}/{len(results)} RESOLVED")


if __name__ == "__main__":
    main()
