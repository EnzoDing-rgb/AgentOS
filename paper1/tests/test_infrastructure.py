"""Infrastructure tests: worktree root, file locks, heartbeat dead-pid, gate-only."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import pytest
from budgetflow import local_harness
from budgetflow.check_run_observability import (
    _pid_is_alive,
    _rows_stuck,
    check_jsonl,
)
from budgetflow.observability import HeartbeatWriter


# ── worktree root tests ────────────────────────────────────────────────────


def _reset_worktree_root():
    """Reset module-level globals for test isolation."""
    local_harness._worktree_root = None
    local_harness._worktree_root_source = "default"


class TestWorktreeRootDefault:
    def test_default_prefers_tmp_writable(self, monkeypatch):
        _reset_worktree_root()
        monkeypatch.delenv("BUDGETFLOW_WORKTREE_ROOT", raising=False)
        root, source = local_harness._resolve_worktree_root()
        assert source in ("tmp", "nfs-fallback")
        if source == "tmp":
            assert root == Path("/tmp/budgetflow_worktrees")

    def test_env_var_override(self, monkeypatch, tmp_path):
        _reset_worktree_root()
        custom = tmp_path / "custom_worktrees"
        monkeypatch.setenv("BUDGETFLOW_WORKTREE_ROOT", str(custom))
        root, source = local_harness._resolve_worktree_root()
        assert source == "env"
        assert root == custom
        assert root.exists()

    def test_set_worktree_root_cli(self, tmp_path):
        _reset_worktree_root()
        custom = tmp_path / "cli_worktrees"
        local_harness.set_worktree_root(str(custom))
        root, source = local_harness._resolve_worktree_root()
        assert source == "cli"
        assert root == custom
        assert root.exists()

    def test_set_worktree_root_none_resets(self):
        _reset_worktree_root()
        local_harness.set_worktree_root(None)
        assert local_harness._worktree_root is None
        assert local_harness._worktree_root_source == "default"

    def test_get_worktree_root_source(self, monkeypatch, tmp_path):
        _reset_worktree_root()
        custom = tmp_path / "env_test"
        monkeypatch.setenv("BUDGETFLOW_WORKTREE_ROOT", str(custom))
        source = local_harness.get_worktree_root_source()
        assert source == "env"

    def test_cli_priority_over_env(self, monkeypatch, tmp_path):
        _reset_worktree_root()
        env_dir = tmp_path / "env_dir"
        cli_dir = tmp_path / "cli_dir"
        monkeypatch.setenv("BUDGETFLOW_WORKTREE_ROOT", str(env_dir))
        local_harness.set_worktree_root(str(cli_dir))
        root, source = local_harness._resolve_worktree_root()
        assert source == "cli"
        assert root == cli_dir

    def test_fallback_to_nfs_when_tmp_unwritable(self, monkeypatch, tmp_path):
        _reset_worktree_root()
        monkeypatch.delenv("BUDGETFLOW_WORKTREE_ROOT", raising=False)

        unwritable = tmp_path / "unwritable_tmp"
        unwritable.mkdir(parents=True, exist_ok=True)

        with patch.object(local_harness, "Path") as mock_path:
            mock_path.side_effect = lambda p: Path(p) if p != "/tmp/budgetflow_worktrees" else unwritable
            with patch.object(os, "statvfs", side_effect=OSError("no statvfs")):
                root, source = local_harness._resolve_worktree_root()
                assert source == "nfs-fallback"
                assert root == local_harness.NFS_WORKTREE_ROOT


# ── file lock tests ────────────────────────────────────────────────────────


class TestRepoGitLock:
    """All lock tests use tmp_path to avoid NFS fcntl.flock issues."""

    def _lock_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / ".locks"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_lock_acquire_release(self, tmp_path):
        """Single process: lock can be acquired and released."""
        lock_dir = self._lock_dir(tmp_path)
        lock_path = lock_dir / "test_repo.lock"
        # Use the same fcntl.flock pattern as _repo_git_lock
        import fcntl as fcntl_mod
        with open(str(lock_path), "w") as lf:
            fcntl_mod.flock(lf.fileno(), fcntl_mod.LOCK_EX)
            assert lock_path.exists()

    def test_lock_exclusive_within_process(self, tmp_path):
        """Two threads serialize via separate fds to the same lock file."""
        import fcntl as fcntl_mod
        import threading

        lock_dir = self._lock_dir(tmp_path)
        lock_path = lock_dir / "exclusive_test.lock"
        results = []

        def hold_and_record(hold_time, label):
            with open(str(lock_path), "w") as lf:
                fcntl_mod.flock(lf.fileno(), fcntl_mod.LOCK_EX)
                results.append(f"{label}_enter")
                time.sleep(hold_time)
                results.append(f"{label}_exit")

        t1 = threading.Thread(target=hold_and_record, args=(0.3, "A"))
        t2 = threading.Thread(target=hold_and_record, args=(0.1, "B"))
        t1.start()
        time.sleep(0.05)
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert "A_enter" in results
        assert "A_exit" in results
        assert "B_enter" in results
        assert "B_exit" in results

    def test_lock_cross_process_serializes(self, tmp_path):
        """Two subprocesses contend for same lock — second blocks until first releases.

        File-marker protocol (deterministic, no timing assumptions):
        1. p1 acquires lock, writes "p1_entered", holds lock
        2. p2 starts, blocks on lock — writes nothing until it acquires
        3. Main process sees p1_entered but not p2_entered → confirms blocking
        4. Main process writes "release" signal → p1 releases
        5. p2 acquires lock, writes "p2_entered" → confirms serialization
        """
        lock_dir = self._lock_dir(tmp_path)
        lock_path = lock_dir / "test.lock"
        signal_dir = tmp_path / "signals"
        signal_dir.mkdir(parents=True, exist_ok=True)

        p1_script = (
            "import fcntl, time, os\n"
            "from pathlib import Path\n"
            f"lock_path = {str(lock_path)!r}\n"
            f"signal_dir = Path({str(signal_dir)!r})\n"
            "with open(lock_path, 'w') as lf:\n"
            "    fcntl.flock(lf.fileno(), fcntl.LOCK_EX)\n"
            "    (signal_dir / 'p1_entered').write_text(str(os.getpid()))\n"
            "    while not (signal_dir / 'release').exists():\n"
            "        time.sleep(0.05)\n"
        )

        p2_script = (
            "import fcntl, os\n"
            "from pathlib import Path\n"
            f"lock_path = {str(lock_path)!r}\n"
            f"signal_dir = Path({str(signal_dir)!r})\n"
            "with open(lock_path, 'w') as lf:\n"
            "    fcntl.flock(lf.fileno(), fcntl.LOCK_EX)\n"
            "    (signal_dir / 'p2_entered').write_text(str(os.getpid()))\n"
        )

        # Start p1
        p1 = subprocess.Popen(
            [sys.executable, "-c", p1_script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        # Wait for p1 to acquire lock
        for _ in range(50):
            if p1.poll() is not None:
                out = p1.stdout.read().decode(errors="replace")
                err = p1.stderr.read().decode(errors="replace")
                pytest.fail(f"p1 exited early rc={p1.returncode} stdout={out} stderr={err}")
            if (signal_dir / "p1_entered").exists():
                break
            time.sleep(0.05)
        assert (signal_dir / "p1_entered").exists(), "p1 should have entered lock"

        # Start p2 — should block
        p2 = subprocess.Popen(
            [sys.executable, "-c", p2_script],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )

        # Confirm p2 is blocked
        time.sleep(0.3)
        assert not (signal_dir / "p2_entered").exists(), (
            "p2 should be blocked waiting for lock"
        )

        # Release p1
        (signal_dir / "release").write_text("go")
        p1.wait(timeout=5)
        assert p1.returncode == 0, f"p1 failed rc={p1.returncode}"

        # p2 should now acquire lock
        p2.wait(timeout=5)
        assert p2.returncode == 0, f"p2 failed rc={p2.returncode}"
        assert (signal_dir / "p2_entered").exists(), (
            "p2 should have entered lock after p1 released"
        )


# ── heartbeat dead-pid tests ───────────────────────────────────────────────


class TestPidIsAlive:
    def test_zero_pid_is_dead(self):
        assert not _pid_is_alive(0)

    def test_negative_pid_is_dead(self):
        assert not _pid_is_alive(-1)

    def test_current_pid_is_alive(self):
        assert _pid_is_alive(os.getpid())

    def test_nonexistent_pid_is_dead(self):
        # Find a PID that doesn't exist
        pid = 999999
        # Make sure it really doesn't exist
        while _pid_is_alive(pid):
            pid += 1
        assert not _pid_is_alive(pid)


class TestRowsStuck:
    def test_completed_but_incomplete(self):
        hb = {
            "rows_done": 5, "total_expected": 10,
            "status": "completed",
            "updated_at": time.time(), "started_at": time.time() - 100,
        }
        stuck, reason = _rows_stuck(hb, 600)
        assert stuck
        assert "completed" in reason
        assert "5/10" in reason

    def test_aborted_incomplete(self):
        hb = {
            "rows_done": 3, "total_expected": 10,
            "status": "aborted: something",
            "updated_at": time.time(), "started_at": time.time() - 100,
        }
        stuck, reason = _rows_stuck(hb, 600)
        assert stuck
        assert "aborted" in reason

    def test_fresh_heartbeat_not_stuck(self):
        hb = {
            "rows_done": 5, "total_expected": 10,
            "status": "running",
            "updated_at": time.time(), "started_at": time.time() - 100,
        }
        stuck, reason = _rows_stuck(hb, 600)
        assert not stuck

    def test_stale_heartbeat_stuck(self):
        hb = {
            "rows_done": 5, "total_expected": 10,
            "status": "running",
            "updated_at": time.time() - 901, "started_at": time.time() - 1000,
        }
        stuck, reason = _rows_stuck(hb, 600)
        assert stuck
        assert "no update" in reason

    def test_completed_all_done_not_stuck(self):
        hb = {
            "rows_done": 10, "total_expected": 10,
            "status": "completed",
            "updated_at": time.time() - 901, "started_at": time.time() - 1000,
        }
        stuck, reason = _rows_stuck(hb, 600)
        assert not stuck

    def test_zero_progress_rows_done_zero_active_fresh_heartbeat(self):
        """rows_done=0 + running + elapsed > stale + active_elapsed_s=0 => stuck."""
        hb = {
            "rows_done": 0, "total_expected": 10,
            "status": "running",
            "updated_at": time.time(),  # fresh heartbeat
            "started_at": time.time() - 901,
            "active_elapsed_s": 0.0,
            "active_strategy": "budget_tight_dummy",
            "active_instance": "django__django-10924",
        }
        stuck, reason = _rows_stuck(hb, 600)
        assert stuck, f"zero-progress fresh heartbeat should be stuck: {reason}"
        assert "ZERO_PROGRESS" in reason
        assert "rows=0/10" in reason

    def test_zero_progress_no_active_task_blocked_setup(self):
        """rows_done=0 + elapsed > stale + no active task => stuck (setup blocked)."""
        hb = {
            "rows_done": 0, "total_expected": 10,
            "status": "preparing",
            "updated_at": time.time(),
            "started_at": time.time() - 901,
            "active_elapsed_s": 0.0,
            "active_strategy": "",
            "active_instance": "",
        }
        stuck, reason = _rows_stuck(hb, 600)
        assert stuck, f"zero-progress no active should be stuck: {reason}"
        assert "ZERO_PROGRESS" in reason
        assert "no active task" in reason

    def test_zero_progress_single_task_stuck_too_long(self):
        """rows_done=0 + active_elapsed_s > stale => single task stuck."""
        hb = {
            "rows_done": 0, "total_expected": 10,
            "status": "running",
            "updated_at": time.time(),
            "started_at": time.time() - 2000,
            "active_elapsed_s": 1500.0,
            "active_strategy": "budget_tight_dummy",
            "active_instance": "django__django-10924",
        }
        stuck, reason = _rows_stuck(hb, 600)
        assert stuck, f"single task stuck for too long should be stuck: {reason}"
        assert "ZERO_PROGRESS" in reason
        assert "single task stuck" in reason

    def test_zero_progress_under_threshold_not_stuck(self):
        """rows_done=0 but elapsed < stale => not stuck yet (still in startup)."""
        hb = {
            "rows_done": 0, "total_expected": 10,
            "status": "running",
            "updated_at": time.time(),
            "started_at": time.time() - 100,
            "active_elapsed_s": 50.0,
            "active_strategy": "budget_tight_dummy",
            "active_instance": "django__django-10924",
        }
        stuck, reason = _rows_stuck(hb, 600)
        assert not stuck, f"under threshold should not be stuck: {reason}"

    def test_completed_heartbeat_not_stale_with_all_done(self):
        """Completed heartbeat with all rows done should never be stale."""
        hb = {
            "rows_done": 10, "total_expected": 10,
            "status": "completed",
            "updated_at": time.time() - 901,
            "started_at": time.time() - 2000,
            "active_elapsed_s": 0.0,
            "active_strategy": "",
            "active_instance": "",
        }
        stuck, reason = _rows_stuck(hb, 600)
        assert not stuck, f"completed all done should not be stuck: {reason}"


class TestCheckJsonlHeartbeat:
    def test_dead_pid_detected(self, tmp_path):
        """check_jsonl detects a dead PID in heartbeat file."""
        rs = "test_dead_pid_run"
        hb_path = tmp_path / f"{rs}.heartbeat.json"

        # Write heartbeat with a dead PID
        dead_pid = 999999
        while _pid_is_alive(dead_pid):
            dead_pid += 1
        hb = {
            "started_at": time.time() - 300,
            "updated_at": time.time() - 10,
            "total_expected": 10,
            "rows_done": 3,
            "current_pid": dead_pid,
            "status": "running",
            "run_series": rs,
        }
        hb_path.write_text(json.dumps(hb))

        # Create a JSONL with matching run_series
        jsonl_path = tmp_path / "test.jsonl"
        jsonl_path.write_text(json.dumps({
            "instance_id": "sympy__sympy-10001",
            "strategy": "test",
            "routing": "budgetflow_full",
            "harness_resolved": False,
            "exit_status": "StagnationExit",
            "exit_reason": "stagnation_no_progress",
            "total_cost": 0.05,
            "llm_turns": 5,
            "elapsed_s": 120.0,
            "detail": "",
            "turn_trace_count": 5,
            "run_series": rs,
            "policy_lane": "warm",
            "task_order_index": 0,
            "row_started_at": time.time() - 130,
            "row_finished_at": time.time() - 10,
            "harness_evidence": {},
            "observability_status": {},
        }) + "\n")

        result = check_jsonl(jsonl_path, heartbeat_stale_s=600)
        assert result["heartbeat_suspicious"]
        assert any("HEARTBEAT_DEAD_PID" in i for i in result["issues"])
        assert result["errors"] > 0

    def test_stuck_rows_detected(self, tmp_path):
        """check_jsonl detects stuck rows (no progress + stale)."""
        rs = "test_stuck_run"
        hb_path = tmp_path / f"{rs}.heartbeat.json"

        hb = {
            "started_at": time.time() - 2000,
            "updated_at": time.time() - 901,  # stale: >600s
            "total_expected": 10,
            "rows_done": 2,
            "current_pid": os.getpid(),
            "status": "running",
            "run_series": rs,
        }
        hb_path.write_text(json.dumps(hb))

        jsonl_path = tmp_path / "test.jsonl"
        jsonl_path.write_text(json.dumps({
            "instance_id": "sympy__sympy-10001",
            "strategy": "test",
            "routing": "budgetflow_full",
            "harness_resolved": False,
            "exit_status": "StagnationExit",
            "exit_reason": "stagnation_no_progress",
            "total_cost": 0.05,
            "llm_turns": 5,
            "elapsed_s": 120.0,
            "detail": "",
            "turn_trace_count": 5,
            "run_series": rs,
            "policy_lane": "warm",
            "task_order_index": 0,
            "row_started_at": time.time() - 130,
            "row_finished_at": time.time() - 10,
            "harness_evidence": {},
            "observability_status": {},
        }) + "\n")

        result = check_jsonl(jsonl_path, heartbeat_stale_s=600)
        assert result["heartbeat_stale"]
        assert any("HEARTBEAT_STUCK" in i for i in result["issues"])

    def test_zero_progress_fresh_heartbeat_detected(self, tmp_path):
        """check_jsonl detects zero-progress stuck even with fresh heartbeat."""
        rs = "test_zero_progress_run"
        hb_path = tmp_path / f"{rs}.heartbeat.json"

        hb = {
            "started_at": time.time() - 2000,
            "updated_at": time.time() - 5,  # fresh
            "total_expected": 10,
            "rows_done": 0,
            "current_pid": os.getpid(),
            "status": "running",
            "run_series": rs,
            "active_elapsed_s": 0.0,
            "active_strategy": "budget_tight_dummy",
            "active_instance": "django__django-10924",
        }
        hb_path.write_text(json.dumps(hb))

        jsonl_path = tmp_path / "test.jsonl"
        jsonl_path.write_text("")  # 0 rows

        result = check_jsonl(jsonl_path, heartbeat_stale_s=600)
        assert result["heartbeat_suspicious"]
        assert any("ZERO_PROGRESS" in i for i in result["issues"])

    def test_preparing_with_active_task_detected(self, tmp_path):
        """check_jsonl detects status=preparing with active_elapsed_s > 60s."""
        rs = "test_preparing_active_run"
        hb_path = tmp_path / f"{rs}.heartbeat.json"

        hb = {
            "started_at": time.time() - 300,
            "updated_at": time.time() - 5,
            "total_expected": 10,
            "rows_done": 0,
            "current_pid": os.getpid(),
            "status": "preparing",
            "run_series": rs,
            "active_elapsed_s": 270.0,
            "active_strategy": "budget_tight_dummy",
            "active_instance": "django__django-10924",
        }
        hb_path.write_text(json.dumps(hb))

        jsonl_path = tmp_path / "test.jsonl"
        jsonl_path.write_text("")

        result = check_jsonl(jsonl_path, heartbeat_stale_s=600)
        assert result["heartbeat_suspicious"]
        assert any("PREPARING_WITH_ACTIVE_TASK" in i for i in result["issues"])

    def test_ok_heartbeat_not_suspicious(self, tmp_path):
        """Healthy heartbeat should not trigger any issues."""
        rs = "test_ok_run"
        hb_path = tmp_path / f"{rs}.heartbeat.json"

        hb = {
            "started_at": time.time() - 300,
            "updated_at": time.time() - 5,
            "total_expected": 10,
            "rows_done": 5,
            "current_pid": os.getpid(),
            "status": "running",
            "run_series": rs,
        }
        hb_path.write_text(json.dumps(hb))

        jsonl_path = tmp_path / "test.jsonl"
        record = {
            "instance_id": "sympy__sympy-10001",
            "strategy": "test",
            "routing": "budgetflow_full",
            "harness_resolved": True,
            "exit_status": "Submitted",
            "exit_reason": "submitted",
            "total_cost": 0.05,
            "llm_turns": 5,
            "elapsed_s": 120.0,
            "detail": "test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=pass",
            "turn_trace_count": 5,
            "run_series": rs,
            "policy_lane": "warm",
            "task_order_index": 0,
            "row_started_at": time.time() - 130,
            "row_finished_at": time.time() - 10,
            "harness_evidence": {"evidence_complete": True},
            "observability_status": {},
        }
        jsonl_path.write_text(json.dumps(record) + "\n")

        result = check_jsonl(jsonl_path, heartbeat_stale_s=600)
        assert not result.get("heartbeat_suspicious")
        assert not any("HEARTBEAT" in i for i in result["issues"])


# ── gate-only tests ─────────────────────────────────────────────────────────


class TestGateOnlyNoApiCalls:
    """Gate-only runs should exit without making any API calls or creating run files."""

    def _run_gate_only(self, tmp_path):
        """Run gate_only subprocess, return (returncode, stdout, stderr)."""
        jsonl = tmp_path / "test_pm.jsonl"
        lines = []
        task_ids = [
            "sympy__sympy-10001", "sympy__sympy-14774", "django__django-10924",
            "django__django-11490", "psf__requests-863", "psf__requests-1724",
            "astropy__astropy-12945", "astropy__astropy-14182", "pytest-dev__pytest-5221",
            "scikit-learn__scikit-learn-10297",
        ]
        strategies = [
            "budgetflow_full_tight", "budgetflow_full_low",
            "budgetflow_equal_weight_tight", "budget_only_tight",
            "all_pro",
        ]
        for i, tid in enumerate(task_ids):
            lines.append(json.dumps({
                "instance_id": tid,
                "strategy": strategies[i % len(strategies)],
                "routing": "budgetflow_full",
                "harness_resolved": i < 4,  # 4 resolved, 6 failed
                "total_cost": 0.05 + i * 0.01,
                "failure_class": "pass" if i < 4 else "repair_fail",
                "exit_status": "Submitted" if i < 4 else "StagnationExit",
                "exit_reason": "submitted" if i < 4 else "stagnation_no_progress",
                "backend_picks": ["tier2", "tier3"],
                "turn_traces": [
                    {"stage": "LOCALIZATION", "backend_tier": 2, "has_progress": True, "cache_hit": False, "provider_actual_cost": 0.02},
                    {"stage": "REPAIR", "backend_tier": 3, "has_progress": i < 4, "cache_hit": False, "provider_actual_cost": 0.03},
                ],
                "turn_trace_count": 2,
                "policy_lane": "warm",
            }))
        jsonl.write_text("\n".join(lines) + "\n")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC) + (os.pathsep + env.get("PYTHONPATH", "") if env.get("PYTHONPATH") else "")
        cmd = [
            sys.executable, "-m", "budgetflow.run_mini_swe_compare",
            "--policy-memory", str(jsonl),
            "--policy-memory-gate-only",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=str(ROOT), env=env)
        return proc.returncode, proc.stdout, proc.stderr

    def test_gate_only_exits_0_with_valid_pm(self, tmp_path):
        returncode, stdout, stderr = self._run_gate_only(tmp_path)
        assert returncode == 0, (
            f"gate_only should exit 0. "
            f"stdout: {stdout[:500]} "
            f"stderr: {stderr[:500]}"
        )
        combined = stdout + stderr
        assert "WARM-UP GATE" in combined

    def test_gate_only_no_run_files_created(self, tmp_path):
        """Gate-only should not create run directories or files."""
        runs_before = set(Path(ROOT / "data" / "runs").glob("*")) if (ROOT / "data" / "runs").exists() else set()
        self._run_gate_only(tmp_path)
        runs_after = set(Path(ROOT / "data" / "runs").glob("*")) if (ROOT / "data" / "runs").exists() else set()
        assert runs_before == runs_after, "Gate-only should not create run files"

    def test_gate_only_no_provider_check(self, tmp_path):
        """Gate-only must not trigger provider signature checks."""
        _, stdout, stderr = self._run_gate_only(tmp_path)
        combined = stdout + stderr
        assert "provider preflight" not in combined.lower()
        assert "checking provider" not in combined.lower()
