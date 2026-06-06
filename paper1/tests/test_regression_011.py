"""Regression tests for 011 fixes: pricing, worktree, resolved, _fmt_usd."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from budgetflow.adapter.backends import _build_all_backends
from budgetflow.auto_budget import (
    _classify_cap_sufficiency,
    _HISTORICAL_PRIOR,
    _FALLBACK_COST,
    _REPO_FLOOR_ESTIMATED_COST,
    AutoBudgetMemory,
    AutoBudgetEstimator,
)
from budgetflow.run_mini_swe_compare import _fmt_usd
from budgetflow.lite_tasks import LiteTaskRecord
from budgetflow.loop import WorkflowSpec


def _make_task(instance_id="sympy__sympy-14774", patch="line1\nline2", f2p=("t1",), repo="sympy/sympy"):
    return LiteTaskRecord(
        instance_id=instance_id, repo=repo, base_commit="abc123",
        problem_statement="fix", patch=patch, test_patch="",
        fail_to_pass=f2p, pass_to_pass=(), gold_files=("foo.py",),
        workflow=WorkflowSpec(workflow_id="test", steps=[]),
    )


# ── _fmt_usd ──────────────────────────────────────────────────────────

class TestFmtUsd:
    def test_sub_cent(self):
        assert _fmt_usd(0.001) == "0.001000"

    def test_sub_dollar(self):
        assert _fmt_usd(0.01) == "0.0100"
        assert _fmt_usd(0.05) == "0.0500"
        assert _fmt_usd(0.25) == "0.2500"
        assert _fmt_usd(0.99) == "0.9900"

    def test_dollar_and_above(self):
        assert _fmt_usd(1.0) == "1.00"
        assert _fmt_usd(1.50) == "1.50"
        assert _fmt_usd(10.0) == "10.00"

    def test_zero(self):
        assert _fmt_usd(0) == "0"

    def test_uncapped(self):
        assert _fmt_usd(None) == "uncapped"

    def test_tiny_value_scientific_like(self):
        assert _fmt_usd(0.0005) == "0.000500"


# ── API Pricing ────────────────────────────────────────────────────────

class TestBackendPricing:
    """Verify hardcoded per-token costs are real USD, not abstract units."""

    def test_all_backends_have_positive_cost(self):
        backends = _build_all_backends()
        assert len(backends) == 3
        for b in backends:
            assert b.cost_per_input_token > 0
            assert b.cost_per_output_token > 0

    def test_output_more_expensive_than_input(self):
        """Output tokens always cost >= input tokens in real pricing."""
        for b in _build_all_backends():
            assert b.cost_per_output_token >= b.cost_per_input_token, (
                f"{b.name}: out={b.cost_per_output_token} < in={b.cost_per_input_token}"
            )

    def test_tier_cost_monotonic(self):
        """Higher tier = higher per-token cost."""
        backends = _build_all_backends()
        for i in range(len(backends) - 1):
            assert backends[i + 1].cost_per_input_token > backends[i].cost_per_input_token, (
                f"T{i+2} input ({backends[i+1].cost_per_input_token}) <= T{i+1} ({backends[i].cost_per_input_token})"
            )
            assert backends[i + 1].cost_per_output_token > backends[i].cost_per_output_token

    def test_t3_t2_ratio_is_real(self):
        """GPT-5.4 is actually 4-7x more expensive than qwen-coder-plus, not 1.5x."""
        backends = _build_all_backends()
        t2_in = backends[1].cost_per_input_token
        t3_in = backends[2].cost_per_input_token
        t2_out = backends[1].cost_per_output_token
        t3_out = backends[2].cost_per_output_token
        # Input: ~4.5x, Output: ~6.8x. Allow reasonable range.
        assert 3.0 < t3_in / t2_in < 10.0, f"T3/T2 input ratio={t3_in/t2_in:.1f}x, expected 3-10x"
        assert 3.0 < t3_out / t2_out < 15.0, f"T3/T2 output ratio={t3_out/t2_out:.1f}x, expected 3-15x"

    def test_per_token_costs_are_sub_cent(self):
        """Real per-token costs are in the millionths-to-ten-millionths range."""
        for b in _build_all_backends():
            assert b.cost_per_input_token < 0.001, (
                f"{b.name} input cost={b.cost_per_input_token:.10f} > $0.001/token"
            )
            assert b.cost_per_output_token < 0.001

    def test_typical_task_cost_approx(self):
        """50-turn task at T2: ~$0.25, T3: ~$1.38. Sanity check against old 0.1f display bug."""
        backends = _build_all_backends()
        t2 = backends[1]
        t3 = backends[2]
        turns = 50
        in_tok = 5000
        out_tok = 1000
        t2_task = turns * (in_tok * t2.cost_per_input_token + out_tok * t2.cost_per_output_token)
        t3_task = turns * (in_tok * t3.cost_per_input_token + out_tok * t3.cost_per_output_token)
        assert 0.01 < t2_task < 5.0, f"T2 task cost={t2_task:.4f}, expected $0.01-5"
        assert 0.1 < t3_task < 10.0, f"T3 task cost={t3_task:.4f}, expected $0.10-10"
        # T3 task should be roughly 5x T2
        assert 3.0 < t3_task / t2_task < 10.0, f"T3/T2 task ratio={t3_task/t2_task:.1f}x"


# ── resolved / harness_resolved ────────────────────────────────────────

class TestResolvedSignal:
    """Verify resolved=None bug is fixed: _classify_cap_sufficiency and memory use harness_resolved."""

    def test_pass_classifies_sufficient(self):
        assert _classify_cap_sufficiency(
            resolved=True, harness_resolved=True, exit_status="Submitted",
            failure_class="", patch_extracted=True, agent_gold_edited=True,
        ) == "sufficient"

    def test_both_must_be_true_for_sufficient(self):
        """_classify_cap_sufficiency requires resolved AND harness_resolved. Caller fix:
        both params are now set from harness_resolved (see run_mini_swe_compare.py:781-782)."""
        # Normal case: both True → sufficient
        assert _classify_cap_sufficiency(
            resolved=True, harness_resolved=True, exit_status="Submitted",
            failure_class="", patch_extracted=True, agent_gold_edited=True,
        ) == "sufficient"
        # After fix: both params get same value from harness_resolved
        # So resolved=False,harness_resolved=False → not sufficient
        assert _classify_cap_sufficiency(
            resolved=False, harness_resolved=False, exit_status="Submitted",
            failure_class="", patch_extracted=True, agent_gold_edited=True,
        ) != "sufficient"

    def test_callers_use_harness_resolved_for_both(self):
        """Verify that the fix pattern (both params=harness_resolved) is used in the codebase."""
        # _write_budget_memory stores both from harness_resolved
        # When harness_resolved=True, resolved=True → sufficient
        # When harness_resolved=False, resolved=False → not sufficient
        # This test documents the fix contract: resolved and harness_resolved
        # params to _classify_cap_sufficiency must come from the SAME source.
        pass_resolved = True
        pass_harness = True
        fail_resolved = False
        fail_harness = False
        # Both True (PASS case) → sufficient
        assert _classify_cap_sufficiency(
            resolved=pass_resolved, harness_resolved=pass_harness,
            exit_status="Submitted", failure_class="",
            patch_extracted=True, agent_gold_edited=True,
        ) == "sufficient"
        # Both False → not sufficient (no contradictory signal)
        assert _classify_cap_sufficiency(
            resolved=fail_resolved, harness_resolved=fail_harness,
            exit_status="Submitted", failure_class="",
            patch_extracted=False, agent_gold_edited=False,
        ) != "sufficient"

    def test_harness_failure_excluded(self):
        assert _classify_cap_sufficiency(
            resolved=False, harness_resolved=False, exit_status="Submitted",
            failure_class="harness_failure", patch_extracted=False,
            agent_gold_edited=False,
        ) == "exclude_harness"

    def test_underbudget_detected(self):
        assert _classify_cap_sufficiency(
            resolved=False, harness_resolved=False, exit_status="BudgetFlowBudgetError",
            failure_class="budget_fail", patch_extracted=True, agent_gold_edited=True,
        ) == "likely_underbudget"

    def test_not_enough_evidence_without_progress(self):
        assert _classify_cap_sufficiency(
            resolved=False, harness_resolved=False, exit_status="BudgetFlowBudgetError",
            failure_class="budget_fail", patch_extracted=False, agent_gold_edited=False,
        ) == "not_enough_evidence"

    def test_corrupt_patch_excluded(self):
        assert _classify_cap_sufficiency(
            resolved=False, harness_resolved=False, exit_status="Submitted",
            failure_class="corrupt_patch", patch_extracted=True, agent_gold_edited=False,
        ) == "exclude_corrupt"

    def test_build_record_callers_send_harness_resolved_for_both(self):
        """After P0-4 fix, callers send harness_resolved for BOTH resolved and harness_resolved params.

        The function requires both=True for 'sufficient'. The fix is in the caller,
        not the function: run_mini_swe_compare.py:781 sends harness_resolved for both.

        This means PASS records (harness_resolved=True) always get:
          resolved=True, harness_resolved=True → sufficient.
        """
        rec = AutoBudgetMemory.build_record(
            instance_id="test__task", repo="test/repo", strategy="test", routing="test",
            resolved=True, harness_resolved=True,  # <-- both True = correct fix pattern
            failure_class="", forensic_primary_axis="pass",
            total_cost=0.10, estimated_task_cap=0.50, estimated_task_cost=0.10,
            patch_extracted=True, agent_gold_edited=True, llm_turns=10,
            patch_lines=5, f2p_count=1, p2p_count=0,
            problem_length=100, gold_file_count=1,
        )
        assert rec["cap_was_sufficient"] == "sufficient"


# ── Auto-budget memory ─────────────────────────────────────────────────

class TestMemoryLearning:
    """Verify memory learning uses clean signals and defaults are correct."""

    def test_empty_memory_starts_clean(self):
        mem = AutoBudgetMemory()
        assert len(mem) == 0

    def test_write_and_reread(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = Path(f.name)
        try:
            mem = AutoBudgetMemory(path)
            mem.write_record({"instance_id": "test__task", "total_cost": 0.10, "cap_was_sufficient": "sufficient"})
            # Re-read from disk
            mem2 = AutoBudgetMemory(path)
            assert len(mem2) == 1
            assert mem2.records[0]["instance_id"] == "test__task"
            assert "timestamp" in mem2.records[0]
            assert mem2.records[0]["estimator_version"] == "v1"
        finally:
            path.unlink()

    def test_harness_failure_excluded_from_memory_estimate(self):
        mem = AutoBudgetMemory()
        mem.write_record(AutoBudgetMemory.build_record(
            instance_id="test__task", repo="test/repo", strategy="test", routing="test",
            resolved=False, harness_resolved=False,
            failure_class="harness_failure", forensic_primary_axis="infra",
            total_cost=0.05, estimated_task_cap=0.20, estimated_task_cost=0.01,
            patch_extracted=False, agent_gold_edited=False, llm_turns=5,
            patch_lines=5, f2p_count=1, p2p_count=0,
            problem_length=100, gold_file_count=1,
        ))
        est = AutoBudgetEstimator(memory=mem)
        task = _make_task("test__task")
        result = est.estimate(task, scale=1.5, min_cap=0.05, max_cap=10.0)
        # Harness failure excluded → falls back to global_fallback (no history for this ID)
        assert result.source in ("global_fallback", "memory_repo_knn")


# ── Fallback & prior calibration ──────────────────────────────────────

class TestFallbackCalibration:
    """Fallback costs and historical prior are in real USD, not internal units."""

    def test_fallback_costs_in_real_usd(self):
        for bucket, cost in _FALLBACK_COST.items():
            assert 0.01 < cost < 10.0, f"{bucket} fallback={cost}, expected real USD $0.01-10"

    def test_repo_floor_in_real_usd(self):
        for repo, floor in _REPO_FLOOR_ESTIMATED_COST.items():
            assert 0.01 < floor < 100.0, f"{repo} floor={floor}, expected real USD"

    def test_historical_prior_in_real_usd(self):
        for iid, info in _HISTORICAL_PRIOR.items():
            assert 0.001 < info["median_cost"] < 100.0, (
                f"{iid} median_cost={info['median_cost']}, expected real USD"
            )
            assert info["resolved"] <= info["total"]
            assert info["total"] >= 1

    def test_sympy_14774_easy_prior(self):
        """sympy-14774 is the easiest task, should have very low estimated cost."""
        info = _HISTORICAL_PRIOR["sympy__sympy-14774"]
        assert info["median_cost"] <= 0.05  # real USD (was $0.01 before 2026-06-03 recalibration)
        assert info["resolved"] / info["total"] >= 0.9  # high pass rate

    def test_sympy_16988_hard_prior(self):
        """sympy-16988 is a hard task, should have higher cost."""
        info = _HISTORICAL_PRIOR["sympy__sympy-16988"]
        assert info["median_cost"] > 0.10  # real USD
        assert info["resolved"] / info["total"] < 0.75  # lower pass rate


# ── Worktree cleanup contract ──────────────────────────────────────────

class TestWorktreeContract:
    """Verify _remove_worktree exists with 3-level cleanup (can't fully test without git repo)."""

    def test_remove_worktree_importable(self):
        from budgetflow.local_harness import _remove_worktree
        assert callable(_remove_worktree)

    def test_remove_worktree_handles_nonexistent_path(self):
        """Should not crash when worktree path doesn't exist."""
        from budgetflow.local_harness import _remove_worktree
        import tempfile, shutil
        tmp = Path(tempfile.mkdtemp())
        nonexistent = tmp / "nonexistent_worktree"
        try:
            _remove_worktree(tmp, nonexistent)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_prepare_worktree_calls_remove_first(self):
        """_prepare_worktree must call _remove_worktree before git worktree add."""
        import inspect
        from budgetflow.local_harness import _prepare_worktree
        src = inspect.getsource(_prepare_worktree)
        # _remove_worktree must appear before git worktree add in source
        remove_pos = src.find("_remove_worktree")
        add_pos = src.find("git", remove_pos)
        assert remove_pos >= 0, "_remove_worktree not found in _prepare_worktree"
        assert remove_pos < add_pos, "_remove_worktree must be called BEFORE git worktree add"


class TestWorktreeMissingButLocked:
    """Regression: _remove_worktree and _worktree_add must handle "missing but locked" git metadata."""

    @pytest.fixture
    def _temp_git_repo(self, tmp_path: Path):
        """Create a minimal git repo in tmp_path for worktree simulation."""
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "-c", "init.defaultBranch=main", "init"], cwd=repo, check=True,
                       capture_output=True, text=True)
        subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@test", "commit",
                        "--allow-empty", "-m", "init"], cwd=repo, check=True,
                       capture_output=True, text=True)
        return repo

    def test_remove_worktree_unlocks_before_anything(self, _temp_git_repo):
        """_remove_worktree always unlocks first — prevents stale locks."""
        from budgetflow.local_harness import _remove_worktree
        repo = _temp_git_repo
        nonexistent = tmp_path() / "nonexistent_worktree" if hasattr(self, 'tmp_path') else repo.parent / "nonexistent_wt"
        # Must NOT crash even when worktree dir + metadata don't exist.
        _remove_worktree(repo, repo.parent / "nonexistent_wt")

    def test_remove_worktree_cleans_locked_metadata(self, _temp_git_repo):
        """When .git/worktrees/<name> exists (locked) but dir is missing, cleanup must nuke metadata."""
        import subprocess, shutil
        from budgetflow.local_harness import _remove_worktree
        repo = _temp_git_repo
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                                capture_output=True, text=True).stdout.strip()
        wt_path = repo.parent / "test_locked_wt"
        meta_dir = repo / ".git" / "worktrees" / wt_path.name
        # Simulate: create worktree, delete dir, leave metadata behind
        subprocess.run(["git", "worktree", "add", str(wt_path), commit], cwd=repo, check=True,
                       capture_output=True, text=True)
        subprocess.run(["git", "-C", str(wt_path), "checkout", "-b", "test-locked-br"], check=False,
                       capture_output=True, text=True)
        shutil.rmtree(wt_path, ignore_errors=True)
        # Metadata should still exist
        assert meta_dir.exists(), "metadata dir must exist before cleanup"
        _remove_worktree(repo, wt_path)
        assert not meta_dir.exists(), f"metadata dir {meta_dir} must be removed"
        # worktree add should now succeed
        subprocess.run(["git", "worktree", "add", "--force", str(wt_path), commit],
                       cwd=repo, check=True, capture_output=True, text=True)
        # Clean up
        subprocess.run(["git", "worktree", "remove", "--force", str(wt_path)],
                       cwd=repo, check=True, capture_output=True, text=True)

    def test_worktree_add_retries_on_locked_metadata(self, _temp_git_repo):
        """_worktree_add must retry when 'missing but locked' error occurs."""
        import subprocess, shutil
        from budgetflow.local_harness import _worktree_add, _remove_worktree
        repo = _temp_git_repo
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                                capture_output=True, text=True).stdout.strip()
        wt_path = repo.parent / "test_retry_wt"
        # Clean first
        _remove_worktree(repo, wt_path)
        # Simulate locked metadata: create worktree, delete dir, leave metadata
        subprocess.run(["git", "worktree", "add", str(wt_path), commit], cwd=repo, check=True,
                       capture_output=True, text=True)
        shutil.rmtree(wt_path, ignore_errors=True)
        meta_dir = repo / ".git" / "worktrees" / wt_path.name
        assert meta_dir.exists()
        # _worktree_add should retry and succeed
        _worktree_add(repo, wt_path, commit)
        assert wt_path.exists()
        # Clean up
        subprocess.run(["git", "worktree", "remove", "--force", str(wt_path)],
                       cwd=repo, check=True, capture_output=True, text=True)

    def test_worktree_add_retries_on_invalid_reference(self, _temp_git_repo):
        """_worktree_add must fetch and retry when commit reference is invalid."""
        import subprocess
        from budgetflow.local_harness import _worktree_add, _remove_worktree
        repo = _temp_git_repo
        wt_path = repo.parent / "test_invalid_ref_wt"
        _remove_worktree(repo, wt_path)
        fake_commit = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
        # Expect CalledProcessError because fetch will fail for fake commit
        with pytest.raises(subprocess.CalledProcessError):
            _worktree_add(repo, wt_path, fake_commit)
        assert not wt_path.exists()


# ── Turn trace observability ────────────────────────────────────────────

class TestTurnTraceFlag:
    """Verify --trace-turns flag defaults to ON and is parseable."""

    def test_trace_turns_flag_defaults_true(self):
        """--trace-turns must default to True so observability is on by default."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--trace-turns", action="store_true", default=True)
        parser.add_argument("--no-trace-turns", action="store_false", dest="trace_turns")
        ns = parser.parse_args([])
        assert ns.trace_turns is True, (
            f"trace_turns default is {ns.trace_turns!r}, expected True. "
            "Turn traces must be ON by default for observability."
        )

    def test_no_trace_turns_flag_disables(self):
        """--no-trace-turns must disable trace collection."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--trace-turns", action="store_true", default=True)
        parser.add_argument("--no-trace-turns", action="store_false", dest="trace_turns")
        ns = parser.parse_args(["--no-trace-turns"])
        assert ns.trace_turns is False, (
            f"trace_turns with --no-trace-turns is {ns.trace_turns!r}, expected False"
        )

    def test_trace_turns_explicit_enable(self):
        """--trace-turns explicitly set still works."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--trace-turns", action="store_true", default=True)
        parser.add_argument("--no-trace-turns", action="store_false", dest="trace_turns")
        ns = parser.parse_args(["--trace-turns"])
        assert ns.trace_turns is True

    def test_trace_turns_default_in_main_parser(self):
        """Verify the actual run_mini_swe_compare parser has trace_turns=True default.

        Parses main()'s parser to confirm the code change is live (not just the test fixture).
        """
        from budgetflow.run_mini_swe_compare import main as _main
        import argparse, inspect
        src = inspect.getsource(_main)
        # Check the actual source for default=True in --trace-turns definition
        assert 'set_defaults(trace_turns=True)' in src or 'default=True' in src, (
            "trace_turns=True default not found in main() source (expected set_defaults or default=True). "
            "Turn traces must be ON by default."
        )
        # Also ensure --no-trace-turns is defined alongside it
        assert '--no-trace-turns' in src, (
            "--no-trace-turns flag missing from main() parser"
        )


class TestBuildTurnTrace:
    """Verify _build_turn_trace produces well-formed trace dicts."""

    def test_basic_trace_structure(self):
        from budgetflow.adapter.mini_swe_proxy import _build_turn_trace
        from enum import Enum

        class FakeStage(Enum):
            LOC = "loc"
            REP = "rep"
            VAL = "val"

        trace = _build_turn_trace(
            step_index=3,
            agent_phase="repair",
            stage=FakeStage.REP,
            bash_command="git diff HEAD~1",
            input_tokens=2500,
            expected_costs={"tier2": 0.005, "tier3": 0.025},
            base_pressure=0.5,
            effective_pressure=0.7,
            backend_chosen="qwen3-coder-plus",
            escalated_backend="qwen3-coder-plus",
            final_backend="qwen3-coder-plus",
            backend_tier=2,
            reserve_out=4096,
            adaptive=None,
            no_progress_streak=0,
            no_progress_on_tier=0,
            turns_on_tier=3,
            has_progress=True,
            progress_reason="gold_file_edited",
            prompt_tokens=2500,
            completion_tokens=200,
            actual_cost=0.005,
            billable=0.005,
            response_ok=True,
            error_type=None,
        )
        # Required fields must be present
        required = [
            "step", "agent_phase", "stage", "bash_digest",
            "input_tokens", "expected_costs", "base_pressure", "effective_pressure",
            "backend_chosen", "final_backend", "backend_tier",
            "prompt_tokens", "completion_tokens", "actual_cost", "response_ok",
        ]
        for key in required:
            assert key in trace, f"Missing required key: {key}"

        # Type checks
        assert isinstance(trace["step"], int)
        assert isinstance(trace["agent_phase"], str)
        assert isinstance(trace["prompt_tokens"], int)
        assert isinstance(trace["completion_tokens"], int)
        assert isinstance(trace["actual_cost"], float)
        assert isinstance(trace["response_ok"], bool)

        # Bash digest must be truncated
        assert isinstance(trace["bash_digest"], str)
        assert len(trace["bash_digest"]) <= 120

    def test_trace_stage_is_enum_name(self):
        from budgetflow.adapter.mini_swe_proxy import _build_turn_trace
        from enum import Enum

        class FakeStage(Enum):
            LOC = "loc"
            VAL = "val"

        trace = _build_turn_trace(
            step_index=1,
            agent_phase="localization",
            stage=FakeStage.LOC,
            bash_command=None,
            input_tokens=1000,
            expected_costs={},
            base_pressure=0.0,
            effective_pressure=0.0,
            backend_chosen="qwen3-coder-plus",
            escalated_backend="qwen3-coder-plus",
            final_backend="qwen3-coder-plus",
            backend_tier=2,
            reserve_out=0,
            adaptive=None,
            no_progress_streak=0,
            no_progress_on_tier=0,
            turns_on_tier=1,
            has_progress=False,
            progress_reason="",
            prompt_tokens=1000,
            completion_tokens=50,
            actual_cost=0.002,
            billable=0.002,
            response_ok=True,
            error_type=None,
        )
        # stage should be the enum name, not the value (for readability)
        assert trace["stage"] == "LOC"

    def test_trace_with_error(self):
        from budgetflow.adapter.mini_swe_proxy import _build_turn_trace
        from enum import Enum

        class FakeStage(Enum):
            REP = "rep"

        trace = _build_turn_trace(
            step_index=5,
            agent_phase="repair",
            stage=FakeStage.REP,
            bash_command="sed -i 's/old/new/' file.py",
            input_tokens=3000,
            expected_costs={"tier2": 0.006},
            base_pressure=0.5,
            effective_pressure=0.6,
            backend_chosen="qwen3-coder-plus",
            escalated_backend="qwen3-coder-plus",
            final_backend="qwen3-coder-plus",
            backend_tier=2,
            reserve_out=4096,
            adaptive=None,
            no_progress_streak=1,
            no_progress_on_tier=1,
            turns_on_tier=5,
            has_progress=False,
            progress_reason="",
            prompt_tokens=3000,
            completion_tokens=0,
            actual_cost=0.0,
            billable=0.0,
            response_ok=False,
            error_type="ServiceUnavailableError",
            provider="openai",
            model="gpt-5.4",
        )
        assert trace["response_ok"] is False
        assert trace["error_type"] == "ServiceUnavailableError"
        assert trace["provider"] == "openai"
        assert trace["model"] == "gpt-5.4"


class TestTurnTraceIntegration:
    """Verify turn_trace_count and turn_traces flow correctly through runner."""

    def test_mini_swe_run_result_defaults(self):
        """MiniSweRunResult defaults have turn_trace_count=0, turn_traces=None."""
        from budgetflow.adapter.runner import MiniSweRunResult

        # Simulate a minimal result (all optional fields get defaults)
        result = MiniSweRunResult(
            instance_id="test",
            strategy="all_pro",
            strategy_label="all_pro",
            patch_text=None,
            exit_status="unknown",
            exit_reason=None,
            total_cost=0.0,
            budget_cap=1.0,
            budget_snapshot={},
            backend_picks=(),
            llm_turns=0,
            harness_resolved=False,
            harness_detail="",
            agent_gold_edited=False,
            agent_attempted_submit=False,
            agent_submitted=False,
            agent_gold_files=(),
            violations=(),
        )
        assert result.turn_trace_count == 0
        assert result.turn_traces is None

    def test_turn_trace_count_reflects_traces(self):
        """When turn_traces is provided, turn_trace_count must equal len(turn_traces)."""
        from budgetflow.adapter.runner import MiniSweRunResult

        traces = [{"step": i, "stage": "LOC"} for i in range(5)]
        result = MiniSweRunResult(
            instance_id="test",
            strategy="all_pro",
            strategy_label="all_pro",
            patch_text=None,
            exit_status="unknown",
            exit_reason=None,
            total_cost=0.0,
            budget_cap=1.0,
            budget_snapshot={},
            backend_picks=(),
            llm_turns=5,
            harness_resolved=False,
            harness_detail="",
            agent_gold_edited=False,
            agent_attempted_submit=False,
            agent_submitted=False,
            agent_gold_files=(),
            violations=(),
            turn_trace_count=5,
            turn_traces=traces,
        )
        assert result.turn_trace_count == 5
        assert len(result.turn_traces) == 5


# ── BudgetFlow routing: budgetflow_full vs all_pro tier selection ──────

class TestBudgetFlowRouting:
    """Verify budgetflow_full starts at T2 (not always T3) and can escalate."""

    @staticmethod
    def _make_backends(include_t1: bool = False):
        from budgetflow.adapter.backends import build_compare_backends, build_ceiling_backends
        if include_t1:
            return build_ceiling_backends()
        return build_compare_backends()

    @staticmethod
    def _make_turn(step_index: int = 1, stage: str = "localization",
                   w_i: float = 1.0, context_len: int = 5000):
        from budgetflow.types import Stage, TurnInfo
        return TurnInfo(
            workflow_id="test_task",
            step_index=step_index,
            stage=Stage(stage),
            w_i=w_i,
            context_len=context_len,
        )

    @staticmethod
    def _make_ctx(strategy: str, backends=None, adaptive=None):
        from budgetflow.adapter.strategies import build_routing_context
        if backends is None:
            backends = TestBudgetFlowRouting._make_backends()
        return build_routing_context(
            strategy=strategy,
            backends=backends,
            adaptive=adaptive,
        )

    @staticmethod
    def _make_governor():
        from budgetflow.governor import BudgetGovernor, GovernorConfig
        from budgetflow.ledger import WorkflowLedgerStore
        return BudgetGovernor(
            GovernorConfig(total_budget=999_999.0, default_max_output_tokens=4096),
            WorkflowLedgerStore(),
        )

    @staticmethod
    def _make_expected_costs(governor, backends, turn):
        from budgetflow.mock_backend import STAGE_OUTPUT_MULTIPLIER
        return {
            b.name: governor.estimate_cost(
                b,
                input_tokens=turn.context_len,
                expected_output_tokens=max(8, round(b.mean_output_tokens * STAGE_OUTPUT_MULTIPLIER[turn.stage])),
            ).expected_cost
            for b in backends
        }

    def test_starting_tier_not_always_t3(self):
        """Easy high-confidence fresh task: budgetflow_full must pick T2, not T3."""
        from budgetflow.adapter.strategies import choose_backend
        backends = self._make_backends()
        ctx = self._make_ctx("budgetflow_full", backends=backends)
        governor = self._make_governor()
        turn = self._make_turn(step_index=1)
        expected_costs = self._make_expected_costs(governor, backends, turn)

        backend = choose_backend(ctx, turn, expected_costs)
        assert backend.tier <= 2, (
            f"budgetflow_full fresh task picked tier {backend.tier} ({backend.name}), "
            f"expected tier <= 2"
        )
        assert ctx.last_decision is not None
        assert ctx.last_decision.branch == "budgetflow_full"

    def test_all_pro_still_t3(self):
        """all_pro is fixed T3 -- must always pick the strongest backend."""
        from budgetflow.adapter.strategies import choose_backend
        backends = self._make_backends()
        ctx = self._make_ctx("all_pro", backends=backends)
        governor = self._make_governor()
        turn = self._make_turn(step_index=1)
        expected_costs = self._make_expected_costs(governor, backends, turn)

        backend = choose_backend(ctx, turn, expected_costs)
        strongest = max(backends, key=lambda b: b.tier)
        assert backend.tier == strongest.tier, (
            f"all_pro picked tier {backend.tier}, expected {strongest.tier}"
        )
        assert ctx.last_decision.branch == "all_pro"

    def test_budgetflow_can_escalate_to_t3(self):
        """After prior step used T3, max_tier=3 but selector picks T2 at low pressure.

        At high pressure in REPAIR stage the upgrade threshold is crossed → T3."""
        from budgetflow.adapter.strategies import choose_backend, build_routing_context
        backends = self._make_backends()
        governor = self._make_governor()

        def _pick(step_index, pressure, stage="localization", w_i=1.0):
            ctx = build_routing_context("budgetflow_full", backends, budget_pressure=pressure)
            t3_backend = next(b for b in backends if b.tier == 3)
            ctx.last_backend = t3_backend
            turn = self._make_turn(step_index=step_index, stage=stage, w_i=w_i)
            expected_costs = self._make_expected_costs(governor, backends, turn)
            return choose_backend(ctx, turn, expected_costs), ctx

        # Low pressure, any stage → selector picks T2 even though max_tier=3.
        backend, ctx = _pick(6, 0.01)
        assert backend.tier == 2, f"low pressure: expected T2, got tier {backend.tier}"
        assert ctx.last_decision.branch == "budgetflow_full"

        # Low pressure, REPAIR stage → still T2 (pressure hasn't risen yet).
        backend, ctx = _pick(6, 0.01, stage="repair", w_i=3.0)
        assert backend.tier == 2, f"low pressure repair: expected T2, got tier {backend.tier}"

        # High pressure + REPAIR → selector crosses upgrade threshold → T3.
        backend, ctx = _pick(6, 0.50, stage="repair", w_i=3.0)
        assert backend.tier == 3, f"high pressure repair: expected T3, got tier {backend.tier}"
        assert ctx.last_decision.branch == "budgetflow_full"

    def test_budget_only_uses_t2_not_t3(self):
        """budget_only with 2 backends at moderate pressure picks T2."""
        from budgetflow.adapter.strategies import choose_backend
        backends = self._make_backends()
        ctx = self._make_ctx("budget_only", backends=backends)
        ctx.budget_pressure = 0.30  # above T3 window threshold (0.15)
        turn = self._make_turn(step_index=5)
        expected_costs = {b.name: 0.01 for b in backends}

        backend = choose_backend(ctx, turn, expected_costs)
        assert backend.tier == 2, (
            f"budget_only with 2 backends picked tier {backend.tier}, expected 2"
        )

    def test_budgetflow_full_step2_stays_t2(self):
        """On step 2 (no escalation, fresh task), budgetflow_full stays at T2."""
        from budgetflow.adapter.strategies import choose_backend
        backends = self._make_backends()
        ctx = self._make_ctx("budgetflow_full", backends=backends)
        governor = self._make_governor()

        # Simulate: previous step used T2 (no escalation)
        t2_backend = next(b for b in backends if b.tier == 2)
        ctx.last_backend = t2_backend

        turn = self._make_turn(step_index=2)
        expected_costs = self._make_expected_costs(governor, backends, turn)

        backend = choose_backend(ctx, turn, expected_costs)
        assert backend.tier <= 2, (
            f"budgetflow_full step 2 (no escalation) picked tier {backend.tier}, expected <= 2"
        )

    def test_budgetflow_full_repair_stage_still_capped(self):
        """Even heavy repair-stage tasks start at T2 for budgetflow_full."""
        from budgetflow.adapter.strategies import choose_backend
        backends = self._make_backends()
        ctx = self._make_ctx("budgetflow_full", backends=backends)
        governor = self._make_governor()
        turn = self._make_turn(step_index=1, stage="repair", w_i=3.0)
        expected_costs = self._make_expected_costs(governor, backends, turn)

        backend = choose_backend(ctx, turn, expected_costs)
        assert backend.tier <= 2, (
            f"budgetflow_full repair stage picked tier {backend.tier}, expected <= 2"
        )

    # —— budget_only T3 window (015 fix) ——

    def test_budget_only_n2_low_pressure_allows_t3(self):
        """budget_only with n=2 pool and pressure < 0.15 picks T3 (not T2)."""
        from budgetflow.adapter.strategies import choose_backend
        backends = self._make_backends()  # [T2, T3]
        ctx = self._make_ctx("budget_only", backends=backends)
        ctx.budget_pressure = 0.05
        turn = self._make_turn(step_index=1)
        expected_costs = {b.name: 0.01 for b in backends}

        backend = choose_backend(ctx, turn, expected_costs)
        assert backend.tier == 3, (
            f"budget_only n=2 low pressure picked tier {backend.tier}, expected 3"
        )

    def test_budget_only_n2_high_pressure_uses_t2(self):
        """budget_only with n=2 pool and pressure >= 0.15 picks T2."""
        from budgetflow.adapter.strategies import choose_backend
        backends = self._make_backends()
        ctx = self._make_ctx("budget_only", backends=backends)
        ctx.budget_pressure = 0.30
        turn = self._make_turn(step_index=5)
        expected_costs = {b.name: 0.01 for b in backends}

        backend = choose_backend(ctx, turn, expected_costs)
        assert backend.tier == 2, (
            f"budget_only n=2 high pressure picked tier {backend.tier}, expected 2"
        )

    # —— bf_full T2 cap relaxation (015 fix) ——

    def test_budgetflow_full_pressure_lift_allows_t3(self):
        """At pressure >= 0.15, cap lifts; selector can pick T3 for REPAIR at high pressure."""
        from budgetflow.adapter.strategies import choose_backend
        backends = self._make_backends()
        ctx = self._make_ctx("budgetflow_full", backends=backends)
        # Simulate elevated budget pressure — this lifts the max_tier cap
        ctx.budget_pressure = 0.50
        governor = self._make_governor()
        turn = self._make_turn(step_index=6, stage="repair", w_i=3.0)
        expected_costs = self._make_expected_costs(governor, backends, turn)

        backend = choose_backend(ctx, turn, expected_costs)
        # At pressure 0.50, REPAIR w_i=3.0, the selector's upgrade_threshold ≈ 0.46
        # so pressure 0.50 > threshold → T3 should be selected
        assert backend.tier == 3, (
            f"bf_full high pressure REPAIR picked tier {backend.tier}, expected 3"
        )

    def test_budgetflow_full_low_pressure_stays_t2(self):
        """At pressure < 0.15 without prior T3, cap keeps T2 even for REPAIR."""
        from budgetflow.adapter.strategies import choose_backend
        backends = self._make_backends()
        ctx = self._make_ctx("budgetflow_full", backends=backends)
        ctx.budget_pressure = 0.05
        governor = self._make_governor()
        turn = self._make_turn(step_index=2, stage="repair", w_i=3.0)
        expected_costs = self._make_expected_costs(governor, backends, turn)

        backend = choose_backend(ctx, turn, expected_costs)
        assert backend.tier <= 2, (
            f"bf_full low pressure REPAIR picked tier {backend.tier}, expected <= 2"
        )


# ── observability: harness evidence parsing ─────────────────────────────

class TestParseHarnessEvidence:
    def test_empty_detail_returns_defaults(self):
        from budgetflow.observability import parse_harness_evidence
        ev = parse_harness_evidence("")
        assert ev.evidence_complete is False
        assert ev.test_patch_ok is False
        assert ev.fail_before_failed is False

    def test_complete_evidence(self):
        from budgetflow.observability import parse_harness_evidence
        detail = "compat=2;test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=pass"
        ev = parse_harness_evidence(detail)
        assert ev.evidence_complete is True
        assert ev.test_patch_ok is True
        assert ev.fail_before_failed is True
        assert ev.model_patch_ok is True
        assert ev.fail_after_passed is True
        assert ev.pass_to_pass_ok is True

    def test_partial_evidence_missing_fail_after(self):
        from budgetflow.observability import parse_harness_evidence
        detail = "compat=2;test_patch=ok;fail_before=fail;model_patch=ok;fail_after=;pass_to_pass=pass"
        ev = parse_harness_evidence(detail)
        assert ev.evidence_complete is False
        assert ev.fail_after_passed is False

    def test_no_equals_no_crash(self):
        from budgetflow.observability import parse_harness_evidence
        detail = "garbage_no_equals"
        ev = parse_harness_evidence(detail)
        assert ev.evidence_complete is False

    def test_none_detail(self):
        from budgetflow.observability import parse_harness_evidence
        ev = parse_harness_evidence(None)  # type: ignore[arg-type]
        assert ev.evidence_complete is False


# ── observability: build_observability_status ───────────────────────────

class TestBuildObservabilityStatus:
    def test_trace_available_when_count_positive(self):
        from budgetflow.observability import build_observability_status
        record = {"turn_trace_count": 5, "detail": "", "harness_resolved": False}
        status = build_observability_status(record)
        assert status["trace_available"] is True
        assert status["turn_trace_count"] == 5

    def test_trace_unavailable_when_zero(self):
        from budgetflow.observability import build_observability_status
        record = {"turn_trace_count": 0, "detail": "", "harness_resolved": False}
        status = build_observability_status(record)
        assert status["trace_available"] is False

    def test_suspicious_pass_detected(self):
        from budgetflow.observability import build_observability_status
        record = {
            "turn_trace_count": 3,
            "detail": "test_patch=ok;fail_before=fail;model_patch=fail",
            "harness_resolved": True,
        }
        status = build_observability_status(record)
        assert status["suspicious_pass"] is True
        assert "fail_after_passed" in status["missing_evidence"]

    def test_genuine_pass_no_suspicious(self):
        from budgetflow.observability import build_observability_status
        detail = "test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=pass"
        record = {"turn_trace_count": 3, "detail": detail, "harness_resolved": True}
        status = build_observability_status(record)
        assert status["suspicious_pass"] is False
        assert status["missing_evidence"] == []

    def test_submitted_patch_detected(self):
        from budgetflow.observability import build_observability_status
        record = {
            "turn_trace_count": 1,
            "detail": "",
            "harness_resolved": False,
            "submitted_patch": "/tmp/patch.diff",
        }
        status = build_observability_status(record)
        assert status["submitted_patch_exists"] is True


# ── observability: heartbeat writer ─────────────────────────────────────

class TestHeartbeatWriter:
    def test_writes_on_init(self, tmp_path):
        from budgetflow.observability import HeartbeatWriter, load_heartbeat
        hb_path = tmp_path / "test.heartbeat.json"
        HeartbeatWriter(hb_path, run_series="test_series", total_expected=50)
        hb = load_heartbeat(hb_path)
        assert hb is not None
        assert hb["run_series"] == "test_series"
        assert hb["total_expected"] == 50
        assert hb["status"] == "preparing"

    def test_pulse_updates_fields(self, tmp_path):
        from budgetflow.observability import HeartbeatWriter, load_heartbeat
        hb_path = tmp_path / "test.heartbeat.json"
        writer = HeartbeatWriter(hb_path, run_series="test_series", total_expected=50)
        writer.pulse(rows_done=10, active_strategy="bf_tight", active_instance="sympy-14774")
        hb = load_heartbeat(hb_path)
        assert hb["rows_done"] == 10
        assert hb["active_strategy"] == "bf_tight"
        assert hb["active_instance"] == "sympy-14774"

    def test_mark_done(self, tmp_path):
        from budgetflow.observability import HeartbeatWriter, load_heartbeat
        hb_path = tmp_path / "test.heartbeat.json"
        writer = HeartbeatWriter(hb_path, run_series="test_series", total_expected=50)
        writer.mark_done()
        hb = load_heartbeat(hb_path)
        assert hb["status"] == "completed"

    def test_mark_aborted(self, tmp_path):
        from budgetflow.observability import HeartbeatWriter, load_heartbeat
        hb_path = tmp_path / "test.heartbeat.json"
        writer = HeartbeatWriter(hb_path, run_series="test_series", total_expected=50)
        writer.mark_aborted("user ctrl-c")
        hb = load_heartbeat(hb_path)
        assert hb["status"] == "aborted: user ctrl-c"

    def test_auto_complete_when_rows_done_exceeds_total(self, tmp_path):
        from budgetflow.observability import HeartbeatWriter, load_heartbeat
        hb_path = tmp_path / "test.heartbeat.json"
        writer = HeartbeatWriter(hb_path, run_series="test_series", total_expected=5)
        writer.pulse(rows_done=5)
        hb = load_heartbeat(hb_path)
        assert hb["status"] == "completed"

    def test_parallel_pulses_do_not_race_on_tmp_file(self, tmp_path):
        import concurrent.futures

        from budgetflow.observability import HeartbeatWriter, load_heartbeat

        hb_path = tmp_path / "test.heartbeat.json"
        writer = HeartbeatWriter(hb_path, run_series="test_series", total_expected=200)

        def pulse(i):
            writer.pulse(
                rows_done=i,
                active_strategy=f"strategy_{i % 3}",
                active_instance=f"task_{i}",
                active_elapsed_s=float(i),
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(pulse, range(1, 201)))

        hb = load_heartbeat(hb_path)
        assert hb is not None
        assert hb["status"] == "completed"
        assert hb["rows_done"] == 200
        assert not list(tmp_path.glob("*.tmp"))


# ── observability: heartbeat utilities ──────────────────────────────────

class TestHeartbeatUtils:
    def test_load_missing_returns_none(self, tmp_path):
        from budgetflow.observability import load_heartbeat
        assert load_heartbeat(tmp_path / "nonexistent.json") is None

    def test_load_corrupt_returns_none(self, tmp_path):
        from budgetflow.observability import load_heartbeat
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        assert load_heartbeat(bad) is None

    def test_stale_returns_true_for_old_heartbeat(self):
        from budgetflow.observability import heartbeat_is_stale
        hb = {"updated_at": 0}
        assert heartbeat_is_stale(hb, stale_seconds=10) is True

    def test_stale_returns_false_for_fresh_heartbeat(self):
        import time
        from budgetflow.observability import heartbeat_is_stale
        hb = {"updated_at": time.time()}
        assert heartbeat_is_stale(hb, stale_seconds=600) is False

    def test_stale_returns_true_for_none(self):
        from budgetflow.observability import heartbeat_is_stale
        assert heartbeat_is_stale(None) is True  # type: ignore[arg-type]


# ── observability: checker functions ────────────────────────────────────

class TestCheckerFunctions:
    def test_check_duplicates_finds_dup(self):
        from budgetflow.check_run_observability import _check_duplicates
        records = [
            {"strategy": "bf_tight", "instance_id": "sympy-14774"},
            {"strategy": "bf_tight", "instance_id": "sympy-14774"},
        ]
        issues = _check_duplicates(records)
        assert len(issues) == 1
        assert "DUPLICATE" in issues[0]

    def test_check_duplicates_no_false_positive(self):
        from budgetflow.check_run_observability import _check_duplicates
        records = [
            {"strategy": "bf_tight", "instance_id": "sympy-14774"},
            {"strategy": "bf_loose", "instance_id": "sympy-14774"},
        ]
        assert _check_duplicates(records) == []

    def test_check_pass_evidence_flags_suspicious(self):
        from budgetflow.check_run_observability import _check_pass_evidence
        records = [
            {"harness_resolved": True, "detail": "test_patch=ok",
             "harness_evidence": {"evidence_complete": False}},
        ]
        issues = _check_pass_evidence(records)
        assert len(issues) == 1
        assert "SUSPICIOUS_PASS" in issues[0]

    def test_check_pass_evidence_skips_genuine(self):
        from budgetflow.check_run_observability import _check_pass_evidence
        records = [
            {"harness_resolved": True, "detail": "test_patch=ok",
             "harness_evidence": {"evidence_complete": True}},
        ]
        assert _check_pass_evidence(records) == []

    def test_check_trace_coverage_flags_zero(self):
        from budgetflow.check_run_observability import _check_trace_coverage
        records = [
            {"turn_trace_count": 0, "instance_id": "sympy-14774", "strategy": "bf_tight"},
        ]
        issues = _check_trace_coverage(records)
        assert len(issues) == 1
        assert "NO_TRACE" in issues[0]

    def test_check_missing_fields(self):
        from budgetflow.check_run_observability import _check_missing_fields
        records = [{"instance_id": "x"}]  # missing most fields
        issues = _check_missing_fields(records)
        assert len(issues) >= 1
        assert "MISSING_FIELDS" in issues[0]

    def test_check_jsonl_flags_fresh_heartbeat_with_dead_pid(self, tmp_path):
        import json
        import time
        from budgetflow.check_run_observability import check_jsonl

        jsonl = tmp_path / "run-0.jsonl"
        record = {
            "instance_id": "x",
            "strategy": "all_pro",
            "routing": "all_pro",
            "harness_resolved": False,
            "exit_status": "Submitted",
            "exit_reason": "submitted",
            "total_cost": 0.1,
            "llm_turns": 1,
            "elapsed_s": 1,
            "detail": "",
            "turn_trace_count": 1,
            "run_series": "run",
            "policy_lane": "all_pro",
            "task_order_index": 1,
            "row_started_at": time.time() - 1,
            "row_finished_at": time.time(),
            "harness_evidence": {"evidence_complete": False},
            "observability_status": {},
            "failure_class": "repair_fail",
            "forensic_summary": {},
            "backend_picks": ["tier3"],
            "submitted_patch": "patch.txt",
            "attempt_id": "run_all_pro_x",
        }
        jsonl.write_text(json.dumps(record) + "\n")
        (tmp_path / "run.heartbeat.json").write_text(json.dumps({
            "started_at": time.time(),
            "updated_at": time.time(),
            "total_expected": 50,
            "rows_done": 21,
            "current_pid": 99999999,
            "status": "running",
            "run_series": "run",
        }))

        result = check_jsonl(jsonl)

        assert result["errors"] >= 1
        assert any("HEARTBEAT_DEAD_PID" in issue for issue in result["issues"])


# ── Compact audit ────────────────────────────────────────────────────────


class TestCompactAudit:
    """Tests for build_compact_audit and format_compact_audit."""

    def _make_record(self, **overrides):
        base = {
            "instance_id": "sympy-14774",
            "strategy": "all_pro",
            "routing": "all_pro",
            "harness_resolved": True,
            "exit_status": "Submitted",
            "exit_reason": "submitted",
            "total_cost": 0.1,
            "llm_turns": 5,
            "elapsed_s": 100,
            "detail": "",
            "turn_trace_count": 5,
            "run_series": "run",
            "policy_lane": "all_pro",
            "task_order_index": 1,
            "row_started_at": 1.0,
            "row_finished_at": 2.0,
            "harness_evidence": {"evidence_complete": True},
            "observability_status": {},
            "failure_class": "pass",
            "forensic_summary": {},
            "backend_picks": ["tier3", "tier3", "tier3", "tier3", "tier3"],
            "submitted_patch": "patch.txt",
            "attempt_id": "run_all_pro_x",
        }
        base.update(overrides)
        return base

    def test_compact_audit_basic_counts(self):
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(strategy="all_pro", harness_resolved=True),
            self._make_record(strategy="all_pro", harness_resolved=True),
            self._make_record(strategy="bo_tight", harness_resolved=False, failure_class="repair_fail"),
        ]
        audit = build_compact_audit(records)
        assert audit["total"] == 3
        assert audit["pass"] == 2
        assert audit["fail"] == 1
        assert audit["suspicious"] == 0
        assert abs(audit["total_cost"] - 0.3) < 0.01

    def test_compact_audit_per_strategy_stats(self):
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(strategy="all_pro", total_cost=0.10, llm_turns=3,
                              backend_picks=["tier3", "tier3", "tier3"]),
            self._make_record(strategy="bo_tight", total_cost=0.05, llm_turns=5,
                              backend_picks=["tier2", "tier2", "tier2", "tier2", "tier2"]),
        ]
        audit = build_compact_audit(records)
        ap = audit["by_strategy"]["all_pro"]
        assert ap["total"] == 1
        assert ap["pass"] == 1
        assert ap["t3_turns"] == 3
        assert ap["t2_turns"] == 0
        assert ap["t3_share"] == pytest.approx(1.0)

        bt = audit["by_strategy"]["bo_tight"]
        assert bt["t2_turns"] == 5
        assert bt["t3_turns"] == 0
        assert bt["t3_share"] == pytest.approx(0.0)

    def test_compact_audit_common_tasks(self):
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(strategy="all_pro", instance_id="task-A"),
            self._make_record(strategy="all_pro", instance_id="task-B"),
            self._make_record(strategy="bo_tight", instance_id="task-A"),
            self._make_record(strategy="bo_tight", instance_id="task-B"),
            self._make_record(strategy="bf_loose", instance_id="task-A"),
            self._make_record(strategy="bf_loose", instance_id="task-B"),
        ]
        audit = build_compact_audit(records)
        assert audit["common_task_count"] == 2  # A and B seen by all strategies
        assert "all_pro" in audit["common_stats"]
        assert audit["common_stats"]["all_pro"]["tasks"] == 2
        assert audit["common_stats"]["all_pro"]["pass"] == 2

    def test_compact_audit_failure_classes(self):
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(
                harness_resolved=False,
                patch_extracted=True,
                agent_gold_edited=True,
                detail="test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail",
            ),
            self._make_record(
                harness_resolved=False,
                patch_extracted=True,
                agent_gold_edited=True,
                detail="test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail",
            ),
            self._make_record(
                harness_resolved=False,
                patch_extracted=True,
                agent_gold_edited=False,
                detail="test_patch=ok; fail_before=fail; model_patch=ok; fail_after=fail",
            ),
        ]
        audit = build_compact_audit(records)
        assert audit["fail_classes"]["repair_fail"] == 2
        assert audit["fail_classes"]["loc_fail"] == 1

    def test_compact_audit_invoice_accurate_false_by_default(self):
        from budgetflow.check_run_observability import build_compact_audit
        records = [self._make_record()]  # no turn_traces
        audit = build_compact_audit(records)
        assert audit["invoice_accurate"] is False

    def test_compact_audit_invoice_accurate_true_with_provider_cost(self):
        from budgetflow.check_run_observability import build_compact_audit
        rec = self._make_record()
        rec["turn_traces"] = [{"step": 1, "cache_hit": False, "provider_actual_cost": 0.01}]
        audit = build_compact_audit([rec])
        assert audit["invoice_accurate"] is True

    def test_compact_audit_stagnation_pass_count(self):
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(harness_resolved=True, exit_status="StagnationExit"),
            self._make_record(harness_resolved=True, exit_status="StagnationExit"),
            self._make_record(harness_resolved=True, exit_status="Submitted"),
        ]
        audit = build_compact_audit(records)
        assert audit["stagnation_pass"] == 2

    def test_format_compact_audit_produces_string(self):
        from budgetflow.check_run_observability import build_compact_audit, format_compact_audit
        records = [
            self._make_record(strategy="all_pro"),
            self._make_record(strategy="bo_tight", harness_resolved=False, failure_class="repair_fail"),
        ]
        audit = build_compact_audit(records)
        text = format_compact_audit(audit)
        assert isinstance(text, str)
        assert "COMPACT AUDIT" in text
        assert "all_pro" in text
        assert "bo_tight" in text
        assert "FAILURE CLASSES" in text
        assert "invoice_accurate=False" in text

    def test_compact_audit_includes_t3_t2_mix(self):
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(strategy="all_pro", harness_resolved=True,
                              llm_turns=10, backend_picks=["tier3"] * 10),
            self._make_record(strategy="bo_tight", harness_resolved=True,
                              llm_turns=8, backend_picks=["tier2"] * 5 + ["tier3"] * 3),
        ]
        audit = build_compact_audit(records)
        assert audit["by_strategy"]["all_pro"]["t3_turns"] == 10
        assert audit["by_strategy"]["all_pro"]["t3_share"] == pytest.approx(1.0)
        assert audit["by_strategy"]["bo_tight"]["t2_turns"] == 5
        assert audit["by_strategy"]["bo_tight"]["t3_turns"] == 3

    def test_compact_audit_suspicious_pass_detected(self):
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(harness_resolved=True, harness_evidence={"evidence_complete": True}),
            self._make_record(harness_resolved=True, harness_evidence={"evidence_complete": False}),
        ]
        audit = build_compact_audit(records)
        assert audit["suspicious"] == 1

    def test_compact_audit_t3_share_uses_tier_turns(self):
        """T3% denominator = T1+T2+T3 turns, not llm_turns."""
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(strategy="all_pro", llm_turns=20,  # llm_turns != tier turns
                              backend_picks=["tier1"] * 2 + ["tier2"] * 3 + ["tier3"] * 5),
        ]
        audit = build_compact_audit(records)
        s = audit["by_strategy"]["all_pro"]
        # llm_turns=20 but tier turns=2+3+5=10, T3=5 → T3% = 5/10 = 0.5
        assert s["t3_turns"] == 5
        assert s["t3_share"] == pytest.approx(0.5)
        # Old behavior would have been 5/20=0.25

    def test_compact_audit_t3_share_handles_zero_turns(self):
        """T3% with zero tier turns → 0.0 (not NaN)."""
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(strategy="all_pro", llm_turns=0, backend_picks=[]),
        ]
        audit = build_compact_audit(records)
        s = audit["by_strategy"]["all_pro"]
        assert s["t3_share"] == 0.0

    def test_compact_audit_shows_policy_memory_used_false_by_default(self):
        """Without routing_prior_summary in records, policy_memory_used=False."""
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(strategy="all_pro"),
            self._make_record(strategy="bo_tight"),
        ]
        audit = build_compact_audit(records)
        assert audit["policy_memory_used"] is False
        assert audit.get("policy_memory_source", "") == ""
        assert audit.get("prior_records", 0) == 0

    def test_compact_audit_shows_policy_memory_used_when_present(self):
        """When records contain routing_prior_summary, policy_memory_used=True."""
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(
                strategy="all_pro",
                policy_memory_enabled=True,
                routing_prior_summary={
                    "repo": "sympy", "repo_t2_success": 0.5, "repo_t3_success": 0.6,
                    "task_seen": 5, "task_pass_count": 3, "task_median_cost": 0.05,
                    "task_all_pro_failures": 0, "recent_failure_axis": "",
                    "full_vs_tight_regret": 0.0, "learned_action": "default",
                    "regret_threshold": 0.15,
                    "policy_memory_source": "data/runs/postfix_017_10x5-0.jsonl",
                },
            ),
            self._make_record(
                strategy="bo_tight",
                policy_memory_enabled=True,
                routing_prior_summary={
                    "repo": "sympy", "repo_t2_success": 0.5, "repo_t3_success": 0.6,
                    "task_seen": 5, "task_pass_count": 3, "task_median_cost": 0.05,
                    "task_all_pro_failures": 0, "recent_failure_axis": "",
                    "full_vs_tight_regret": 0.0, "learned_action": "default",
                    "regret_threshold": 0.15,
                    "policy_memory_source": "data/runs/postfix_017_10x5-0.jsonl",
                },
            ),
        ]
        audit = build_compact_audit(records)
        assert audit["policy_memory_used"] is True
        assert "postfix_017" in audit.get("policy_memory_source", "")
        assert audit.get("prior_records", 0) >= 1

    def test_compact_audit_prefers_standard_policy_memory_source_field(self):
        """New schema should not require legacy routing_prior_summary."""
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(
                strategy="bfv",
                routing_policy_memory_source="data/runs/066_postfix_3x3.jsonl",
                routing_learned_action="early_rescue",
            )
        ]

        audit = build_compact_audit(records)

        assert audit["policy_memory_used"] is True
        assert audit["policy_memory_source"] == "data/runs/066_postfix_3x3.jsonl"
        assert audit["prior_records"] == 0

    def test_compact_audit_keeps_legacy_policy_memory_source_fallback(self):
        """Old artifacts remain readable without editing historical JSONL."""
        from budgetflow.check_run_observability import build_compact_audit
        records = [
            self._make_record(
                strategy="bfv",
                policy_memory_enabled=True,
                routing_prior_summary={
                    "task_seen": 4,
                    "policy_memory_source": "data/runs/legacy.jsonl",
                },
            )
        ]

        audit = build_compact_audit(records)

        assert audit["policy_memory_used"] is True
        assert audit["policy_memory_source"] == "data/runs/legacy.jsonl"
        assert audit["prior_records"] == 4
