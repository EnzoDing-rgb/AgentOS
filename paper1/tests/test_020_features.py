"""Tests for 020 features: BudgetMemory integration, failure_subtype,
fallback audit, incomplete fail classification, offline replay extensions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import pytest
from budgetflow.budget_memory import BudgetMemory, BudgetEstimate
from budgetflow.failure_classification import (
    build_verdict,
    classify_failure_subtype,
)
from budgetflow.observability import (
    audit_fallback_patch,
    build_harness_trust,
    classify_incomplete_fail,
    parse_harness_evidence,
)


def _make_record(**kw):
    """Minimal valid record dict."""
    defaults = {
        "instance_id": "sympy__sympy-99999",
        "strategy": "budget_only_tight",
        "routing": "budget_only",
        "harness_resolved": False,
        "exit_status": "BudgetFlowBudgetError",
        "exit_reason": "budget_exhausted",
        "total_cost": 0.5,
        "llm_turns": 10,
        "elapsed_s": 30.0,
        "detail": "test_patch=ok;fail_before=fail;model_patch=ok;fail_after=fail;pass_to_pass=ok",
        "turn_trace_count": 5,
        "run_series": "test",
        "policy_lane": "test",
        "task_order_index": 0,
        "row_started_at": 1000.0,
        "row_finished_at": 1030.0,
        "observability_status": {},
        "harness_evidence": {"evidence_complete": True},
    }
    defaults.update(kw)
    if "harness_evidence" not in kw and "detail" in kw:
        ev = parse_harness_evidence(defaults["detail"])
        defaults["harness_evidence"] = ev.__dict__
    return defaults


# ── BudgetMemory Integration ────────────────────────────────────────────────


class TestBudgetMemoryIntegration:
    def test_hard_budget_priority(self):
        """BudgetMemory cap must be <= hard_budget when hard_budget is set."""
        bm = BudgetMemory()
        bm._learn([_make_record(instance_id="foo__bar-1", total_cost=1.0)] * 5)
        est = bm.estimate_task_budget("foo__bar-1", hard_budget=0.30)
        assert est.estimated_task_budget <= 0.30
        assert est.hard_budget_used

    def test_record_fields_written(self):
        """Verify budget_memory_* fields appear correctly in record dict."""
        est = BudgetEstimate(
            estimated_task_budget=0.25,
            budget_source="repo_median",
            budget_confidence="medium",
            budget_reason="test",
            hard_budget_used=False,
            predicted_cost=0.20,
            risk_multiplier=1.0,
        )
        rec = _make_record(
            batch_budget_cap=0.25,
            budget_memory_estimate=est,
        )
        rec["budget_memory_enabled"] = True
        rec["budget_memory_source_paths"] = "/data/runs/test.jsonl"
        rec["budget_memory_budget_source"] = est.budget_source
        rec["budget_memory_estimated_budget"] = est.estimated_task_budget
        rec["budget_memory_predicted_cost"] = est.predicted_cost
        rec["budget_memory_confidence"] = est.budget_confidence
        rec["budget_memory_reason"] = est.budget_reason
        rec["budget_memory_hard_budget_used"] = est.hard_budget_used
        rec["budget_memory_risk_multiplier"] = est.risk_multiplier
        rec["budget_memory_applied"] = True

        assert rec["budget_memory_enabled"] is True
        assert rec["budget_memory_budget_source"] == "repo_median"
        assert rec["budget_memory_source_paths"] == "/data/runs/test.jsonl"
        assert rec["budget_memory_estimated_budget"] == 0.25
        assert rec["budget_memory_applied"] is True

    def test_disabled_by_default(self):
        """BudgetMemory fields should indicate disabled when not used."""
        rec = _make_record()
        rec["budget_memory_enabled"] = False
        assert rec["budget_memory_enabled"] is False

    def test_gate_only_loads_without_api(self, tmp_path):
        """BudgetMemory gate-only: loads JSONL, prints diagnostics, no API calls."""
        jl = tmp_path / "test.jsonl"
        jl.write_text(
            json.dumps(_make_record(instance_id="django__django-1", total_cost=0.5)) + "\n"
        )
        bm = BudgetMemory.from_jsonl([jl])
        assert bm.record_count == 1
        assert bm.task_count == 1
        assert "django" in str(bm._repo_stats.keys())
        # Verify repo stats are populated
        rs = bm.repo_stats("django")
        assert rs is not None
        assert rs.count == 1


# ── Failure Subtype ─────────────────────────────────────────────────────────


class TestFailureSubtype:
    def test_budget_exhausted_no_progress(self):
        """Budget fail without patch extracted or gold edited."""
        r = _make_record(
            harness_resolved=False,
            exit_status="BudgetFlowBudgetError",
            exit_reason="budget_exhausted",
            patch_extracted=False,
            agent_gold_edited=False,
        )
        v = build_verdict(r)
        assert v["verdict_axis"] == "budget_fail"
        assert v["failure_subtype"] == "budget_exhausted_no_progress"

    def test_budget_exhausted_after_progress(self):
        """Budget fail with patch extracted — progress was made."""
        r = _make_record(
            harness_resolved=False,
            exit_status="BudgetFlowBudgetError",
            exit_reason="budget_exhausted",
            patch_extracted=True,
            agent_gold_edited=False,
            patch_source="submission",
        )
        v = build_verdict(r)
        assert v["failure_subtype"] == "budget_exhausted_after_progress"

    def test_loc_model_fail(self):
        """Model fails at localization stage (no gold edit)."""
        r = _make_record(
            harness_resolved=False,
            exit_status="StagnationExit",
            exit_reason="stagnation_repair",
            patch_extracted=True,
            agent_gold_edited=False,
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=fail;pass_to_pass=ok",
        )
        v = build_verdict(r)
        assert v["failure_subtype"] == "loc_model_fail"
        assert v["failure_owner"] == "model"

    def test_repair_model_fail(self):
        """Model fails at repair stage."""
        r = _make_record(
            harness_resolved=False,
            exit_status="AgentFinished",
            exit_reason="completed",
            patch_extracted=True,
            agent_gold_edited=True,
            detail="test_patch=ok;fail_before=fail;model_patch=fail;fail_after=fail;pass_to_pass=ok",
        )
        v = build_verdict(r)
        assert v["failure_subtype"] == "repair_model_fail"

    def test_validation_model_fail(self):
        """Model fails at validation stage (fail_after=fail)."""
        r = _make_record(
            harness_resolved=False,
            exit_status="AgentFinished",
            exit_reason="completed",
            patch_extracted=True,
            agent_gold_edited=True,
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=fail;pass_to_pass=ok",
        )
        v = build_verdict(r)
        assert v["failure_subtype"] == "validation_model_fail"

    def test_extraction_protocol_fail(self):
        """Protocol fail at extraction stage."""
        r = _make_record(
            harness_resolved=False,
            exit_status="FormatError",
            exit_reason="format_error",
            patch_extracted=False,
            agent_gold_edited=False,
            detail="",
            turn_trace_count=1,
            turn_traces=[{"error_type": "FormatError"}],
        )
        v = build_verdict(r)
        assert v["failure_subtype"] == "extraction_protocol_fail"

    def test_pass_produces_pass_subtype(self):
        """Pass records get 'pass' subtype."""
        r = _make_record(
            harness_resolved=True,
            exit_status="AgentFinished",
            exit_reason="completed",
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=pass",
            patch_extracted=True,
            agent_gold_edited=True,
            harness_evidence={"evidence_complete": True},
        )
        v = build_verdict(r)
        assert v["verdict_axis"] == "pass"
        assert v["failure_subtype"] == "pass"

    def test_standalone_classify_budget_no_progress(self):
        """classify_failure_subtype works standalone without pre-computed axis/stage."""
        r = _make_record(
            harness_resolved=False,
            exit_status="BudgetFlowBudgetError",
            exit_reason="budget_exhausted",
            patch_extracted=False,
        )
        st = classify_failure_subtype(r)
        assert st == "budget_exhausted_no_progress"

    def test_standalone_classify_with_axis_stage(self):
        """classify_failure_subtype accepts pre-computed axis and stage."""
        r = _make_record()
        st = classify_failure_subtype(r, axis="model_fail", stage="localization")
        assert st == "loc_model_fail"


# ── Fallback Patch Audit ────────────────────────────────────────────────────


class TestFallbackAudit:
    def test_no_submission(self, tmp_path):
        """Fallback exists (worktree) but no submission patch."""
        patch_file = tmp_path / "patch.diff"
        patch_file.write_text("mock diff content")
        r = _make_record(
            harness_resolved=True,
            patch_extracted=True,
            patch_source="worktree",
            submitted_patch="",
            patch_text="mock diff content",
        )
        fa = audit_fallback_patch(r)
        assert fa["submitted_vs_fallback"] == "no_submission"
        assert fa["fallback_patch_exists"]
        assert fa["fallback_audit"] == "warn"
        assert not fa["submitted_patch_exists"]

    def test_no_patch_at_all(self):
        """No patch extracted, nothing to compare."""
        r = _make_record(
            harness_resolved=False,
            patch_extracted=False,
            patch_source="none",
            submitted_patch="",
            patch_text="",
        )
        fa = audit_fallback_patch(r)
        assert fa["submitted_vs_fallback"] == "no_patch"
        assert fa["fallback_audit"] == "blocking"

    def test_submission_only(self, tmp_path):
        """Submission patch exists but no fallback (normal submission path)."""
        pf = tmp_path / "patch.diff"
        pf.write_text("diff content")
        r = _make_record(
            harness_resolved=True,
            patch_extracted=True,
            patch_source="submission",
            submitted_patch=str(pf),
            patch_text="",
        )
        fa = audit_fallback_patch(r)
        assert fa["submitted_vs_fallback"] == "no_fallback"
        assert fa["submitted_patch_exists"]

    def test_extracted_but_no_file_path(self):
        """Patch extracted but no file path for either source."""
        r = _make_record(
            harness_resolved=False,
            patch_extracted=True,
            patch_source="submission",
            submitted_patch="/nonexistent/path.patch",
        )
        fa = audit_fallback_patch(r)
        assert fa["submitted_vs_fallback"] == "no_submission"
        assert fa["fallback_audit"] == "blocking"


# ── Incomplete Fail Classification ───────────────────────────────────────────


class TestIncompleteFail:
    def test_no_patch_fail(self):
        """Fail without any patch extracted."""
        r = _make_record(
            harness_resolved=False,
            exit_status="StagnationExit",
            exit_reason="stagnation_localization",
            patch_extracted=False,
            detail="",
            harness_evidence={},
        )
        cat = classify_incomplete_fail(r)
        assert cat == "no_patch_fail"

    def test_harness_incomplete_fail(self):
        """Patch exists but harness evidence incomplete."""
        r = _make_record(
            harness_resolved=False,
            exit_status="AgentFinished",
            exit_reason="completed",
            patch_extracted=True,
            detail="test_patch=ok;fail_before=unknown;model_patch=unknown;fail_after=unknown;pass_to_pass=unknown",
            harness_evidence={"evidence_complete": False},
        )
        cat = classify_incomplete_fail(r)
        assert cat == "harness_incomplete_fail"

    def test_expected_fail_incomplete(self):
        """Fail with complete evidence — expected fail."""
        r = _make_record(
            harness_resolved=False,
            exit_status="AgentFinished",
            exit_reason="completed",
            patch_extracted=True,
            agent_gold_edited=True,
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=fail;pass_to_pass=pass",
        )
        cat = classify_incomplete_fail(r)
        assert cat == "expected_fail_incomplete"

    def test_not_applicable_pass(self):
        """Pass records are not applicable."""
        r = _make_record(
            harness_resolved=True,
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=pass",
            patch_extracted=True,
        )
        cat = classify_incomplete_fail(r)
        assert cat == "not_applicable"


# ── Offline Replay New Sections ─────────────────────────────────────────────


class TestOfflineReplayNewSections:
    def test_failure_subtypes_section(self, tmp_path):
        """Verify FAILURE SUBTYPES appears in replay output."""
        from budgetflow.offline_replay import run_replay

        def _write(path, recs):
            with open(path, "w") as f:
                for r in recs:
                    f.write(json.dumps(r) + "\n")

        # 017: minimal
        p017 = tmp_path / "017.jsonl"
        _write(p017, [
            _make_record(instance_id="django__django-1", harness_resolved=True),
        ])

        # 018: one budget fail and one model fail
        p018 = tmp_path / "018.jsonl"
        _write(p018, [
            _make_record(instance_id="django__django-1", harness_resolved=True, total_cost=0.15),
            _make_record(
                instance_id="sympy__sympy-1", harness_resolved=False,
                exit_status="BudgetFlowBudgetError", exit_reason="budget_exhausted",
                patch_extracted=False, total_cost=0.5,
            ),
            _make_record(
                instance_id="sympy__sympy-2", harness_resolved=False,
                exit_status="AgentFinished", exit_reason="completed",
                patch_extracted=True, agent_gold_edited=True,
                detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=fail;pass_to_pass=ok",
                total_cost=0.3,
            ),
        ])

        out = run_replay(p017, p018)
        assert "FAILURE SUBTYPES" in out
        assert "FAILURE OWNERSHIP" in out

    def test_fallback_audit_section(self, tmp_path):
        """Verify FALLBACK AUDIT appears in replay output."""
        from budgetflow.offline_replay import run_replay

        p017 = tmp_path / "017.jsonl"
        p017.write_text(json.dumps(_make_record(harness_resolved=True)) + "\n")

        p018 = tmp_path / "018.jsonl"
        p018.write_text(json.dumps(_make_record(
            harness_resolved=True, patch_extracted=True, patch_source="worktree",
            submitted_patch="", patch_text="diff",
        )) + "\n")

        out = run_replay(p017, p018)
        assert "FALLBACK AUDIT" in out

    def test_incomplete_fail_breakdown_section(self, tmp_path):
        """Verify INCOMPLETE FAIL BREAKDOWN appears."""
        from budgetflow.offline_replay import run_replay

        p017 = tmp_path / "017.jsonl"
        p017.write_text(json.dumps(_make_record(harness_resolved=True)) + "\n")

        p018 = tmp_path / "018.jsonl"
        p018.write_text(json.dumps(_make_record(
            harness_resolved=False, patch_extracted=False,
        )) + "\n")

        out = run_replay(p017, p018)
        assert "INCOMPLETE FAIL BREAKDOWN" in out

    def test_budget_dry_run_section(self, tmp_path):
        """Verify BUDGET DRY-RUN appears in replay output."""
        from budgetflow.offline_replay import run_replay

        p017 = tmp_path / "017.jsonl"
        p017.write_text(json.dumps(_make_record(harness_resolved=True)) + "\n")

        p018 = tmp_path / "018.jsonl"
        p018.write_text(json.dumps(_make_record(harness_resolved=True)) + "\n")

        out = run_replay(p017, p018)
        assert "BUDGET DRY-RUN" in out

    def test_old_jsonl_has_subtypes(self, tmp_path):
        """Old JSONL without failure_subtype gets subtypes via dynamic build_verdict."""
        from budgetflow.offline_replay import run_replay

        p017 = tmp_path / "017.jsonl"
        p017.write_text(json.dumps(_make_record(harness_resolved=True)) + "\n")

        # Old JSONL record without failure_subtype field
        rec = _make_record(
            instance_id="django__django-1",
            harness_resolved=False,
            exit_status="BudgetFlowBudgetError",
            exit_reason="budget_exhausted",
            patch_extracted=False,
        )
        rec.pop("failure_subtype", None)
        p018 = tmp_path / "018.jsonl"
        p018.write_text(json.dumps(rec) + "\n")

        out = run_replay(p017, p018)
        assert "FAILURE SUBTYPES" in out

    def test_compact_audit_has_failure_subtypes(self):
        """build_compact_audit includes fail_subtypes key."""
        from budgetflow.check_run_observability import build_compact_audit

        recs = [
            _make_record(
                instance_id="django__django-1",
                harness_resolved=False,
                exit_status="BudgetFlowBudgetError",
                exit_reason="budget_exhausted",
                patch_extracted=False,
                failure_subtype="budget_exhausted_no_progress",
            ),
        ]
        audit = build_compact_audit(recs)
        assert "fail_subtypes" in audit
        assert "budget_exhausted_no_progress" in audit["fail_subtypes"]


# ── P0: dry-run / gate-only must not trigger provider preflight ───────────────


class TestNoProviderPreflightForDryRun:
    """P0: --budget-memory-dry-run and --budget-memory-gate-only must NOT
    call provider signature check, create run files, or write JSONL."""

    def test_dry_run_does_not_call_provider_preflight(self, tmp_path, monkeypatch):
        """dry-run must exit before check_required_signatures is reached."""
        from budgetflow.run_mini_swe_compare import main
        from budgetflow import provider_signature

        # Create a minimal JSONL for BudgetMemory
        jl = tmp_path / "bm.jsonl"
        jl.write_text(
            json.dumps(_make_record(
                instance_id="sympy__sympy-99999",
                total_cost=0.5,
                strategy="budget_only_tight",
            )) + "\n"
        )

        preflight_called = []

        def _fake_check(backends):
            preflight_called.append(True)
            raise AssertionError("provider preflight must NOT be called during dry-run")

        monkeypatch.setattr(
            provider_signature, "check_required_signatures", _fake_check
        )

        # Also mock task loading to avoid needing real SWE-bench data
        import budgetflow.run_mini_swe_compare as rm
        from unittest.mock import MagicMock

        _fake_task = MagicMock()
        _fake_task.instance_id = "sympy__sympy-99999"
        _fake_task.repo = "sympy"

        monkeypatch.setattr(rm, "load_compare_easy_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_compare_medium_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_swebench_lite_tasks", lambda instance_ids=None: [_fake_task])

        # Save and restore sys.argv
        import sys as _sys
        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--budget-memory-dry-run",
                "--budget-memory", str(jl),
                "--preset", "3x3",
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
            assert len(preflight_called) == 0, (
                "check_required_signatures was called during dry-run!"
            )
        finally:
            _sys.argv = _orig_argv

    def test_gate_only_does_not_call_provider_preflight(self, tmp_path, monkeypatch):
        """gate-only must exit before provider check."""
        from budgetflow.run_mini_swe_compare import main
        from budgetflow import provider_signature

        jl = tmp_path / "bm.jsonl"
        jl.write_text(
            json.dumps(_make_record(
                instance_id="sympy__sympy-99999",
                total_cost=0.5,
                strategy="budget_only_tight",
            )) + "\n"
        )

        preflight_called = []

        def _fake_check(backends):
            preflight_called.append(True)
            raise AssertionError("provider preflight must NOT be called during gate-only")

        monkeypatch.setattr(
            provider_signature, "check_required_signatures", _fake_check
        )

        import sys as _sys
        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--budget-memory-gate-only",
                "--budget-memory", str(jl),
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
            assert len(preflight_called) == 0, (
                "check_required_signatures was called during gate-only!"
            )
        finally:
            _sys.argv = _orig_argv

    def test_dry_run_does_not_create_run_files(self, tmp_path, monkeypatch):
        """dry-run must not create JSONL, heartbeat, or summary files."""
        from budgetflow.run_mini_swe_compare import main
        from budgetflow import provider_signature
        from unittest.mock import MagicMock

        jl = tmp_path / "bm.jsonl"
        jl.write_text(
            json.dumps(_make_record(
                instance_id="sympy__sympy-99999",
                total_cost=0.5,
                strategy="budget_only_tight",
            )) + "\n"
        )

        # Mock provider check to no-op
        monkeypatch.setattr(
            provider_signature, "check_required_signatures", lambda backends: []
        )
        # Mock task loading
        import budgetflow.run_mini_swe_compare as rm

        _fake_task = MagicMock()
        _fake_task.instance_id = "sympy__sympy-99999"
        _fake_task.repo = "sympy"

        monkeypatch.setattr(rm, "load_compare_easy_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_compare_medium_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_swebench_lite_tasks", lambda instance_ids=None: [_fake_task])

        # Override RUNS_DIR to a temp dir so any accidental writes go there
        runs_tmp = tmp_path / "runs"
        runs_tmp.mkdir()
        monkeypatch.setattr(rm, "RUNS_DIR", runs_tmp)

        before_files = set(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())

        import sys as _sys
        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--budget-memory-dry-run",
                "--budget-memory", str(jl),
                "--preset", "3x3",
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        finally:
            _sys.argv = _orig_argv

        after_files = set(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
        new_files = after_files - before_files
        assert not new_files, (
            f"dry-run created files: {new_files}"
        )

    def test_policy_memory_gate_only_no_preflight(self, tmp_path, monkeypatch):
        """--policy-memory-gate-only also must not trigger provider preflight."""
        from budgetflow.run_mini_swe_compare import main
        from budgetflow import provider_signature

        # Create JSONL with enough records to pass the gate (needs >= 10 records/tasks)
        jl = tmp_path / "pm.jsonl"
        lines = []
        for i in range(15):
            lines.append(json.dumps(_make_record(
                instance_id=f"sympy__sympy-{10000+i}",
                strategy="budgetflow_full_tight",
                total_cost=0.5 + i * 0.02,
                harness_resolved=(i % 3 == 0),
            )))
        jl.write_text("\n".join(lines) + "\n")

        preflight_called = []

        def _fake_check(backends):
            preflight_called.append(True)
            raise AssertionError("provider preflight must NOT be called during gate-only")

        monkeypatch.setattr(
            provider_signature, "check_required_signatures", _fake_check
        )

        import sys as _sys
        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--policy-memory-gate-only",
                "--policy-memory", str(jl),
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
            assert len(preflight_called) == 0, (
                "check_required_signatures was called during policy-memory-gate-only!"
            )
        finally:
            _sys.argv = _orig_argv


# ── P1.1: Dry-run output fields ────────────────────────────────────────────────


class TestDryRunOutputFields:
    """P1.1: dry-run output includes old_cap_source, actual_median, verdict."""

    def test_dry_run_output_has_new_fields(self, tmp_path, monkeypatch):
        """dry-run output must contain old_cap_src, actual_median, verdict columns."""
        import sys as _sys
        from budgetflow.run_mini_swe_compare import main
        from budgetflow import provider_signature
        from unittest.mock import MagicMock
        import io

        jl = tmp_path / "bm.jsonl"
        jl.write_text(
            json.dumps(_make_record(
                instance_id="sympy__sympy-99999",
                total_cost=0.5,
                strategy="budget_only_tight",
            )) + "\n" +
            json.dumps(_make_record(
                instance_id="sympy__sympy-99999",
                total_cost=0.6,
                strategy="budget_only_tight",
            )) + "\n"
        )

        monkeypatch.setattr(
            provider_signature, "check_required_signatures", lambda backends: []
        )
        import budgetflow.run_mini_swe_compare as rm

        _fake_task = MagicMock()
        _fake_task.instance_id = "sympy__sympy-99999"
        _fake_task.repo = "sympy"

        monkeypatch.setattr(rm, "load_compare_easy_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_compare_medium_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_swebench_lite_tasks", lambda instance_ids=None: [_fake_task])

        captured = io.StringIO()
        monkeypatch.setattr(_sys, "stdout", captured)

        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--budget-memory-dry-run",
                "--budget-memory", str(jl),
                "--preset", "3x3",
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        finally:
            _sys.argv = _orig_argv

        output = captured.getvalue()
        assert "old_cap_src" in output, f"missing old_cap_src in:\n{output}"
        assert "verdict" in output, f"missing verdict in:\n{output}"
        assert "BudgetMemory dry-run" in output
        assert "Summary:" in output

    def test_dry_run_with_auto_budget_uses_auto_budget_source(self, tmp_path, monkeypatch):
        """With --auto-budget, old_cap_src must be 'auto_budget'."""
        import sys as _sys
        from budgetflow.run_mini_swe_compare import main
        from budgetflow import provider_signature
        from unittest.mock import MagicMock
        import io

        jl = tmp_path / "bm.jsonl"
        jl.write_text(
            json.dumps(_make_record(
                instance_id="sympy__sympy-99999",
                total_cost=0.5,
                strategy="budget_only_tight",
            )) + "\n"
        )

        monkeypatch.setattr(
            provider_signature, "check_required_signatures", lambda backends: []
        )
        import budgetflow.run_mini_swe_compare as rm

        _fake_task = MagicMock()
        _fake_task.instance_id = "sympy__sympy-99999"
        _fake_task.repo = "sympy"

        monkeypatch.setattr(rm, "load_compare_easy_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_compare_medium_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_swebench_lite_tasks", lambda instance_ids=None: [_fake_task])

        # Mock AutoBudgetEstimator to return a known cap
        from budgetflow.auto_budget import BudgetEstimate as AutoBudgetEstimate

        _fake_est = AutoBudgetEstimate(
            instance_id="sympy__sympy-99999",
            cap=0.30,
            estimated_cost=0.25,
            source="test_mock",
            confidence="medium",
            features={},
            memory_neighbors=0,
        )

        class _FakeEstimator:
            def estimate(self, task, scale=1.0, min_cap=0.1, max_cap=10.0):
                return _fake_est

        monkeypatch.setattr(rm, "AutoBudgetEstimator", lambda memory, k=3: _FakeEstimator())

        # AutoBudgetMemory needs special handling — mock it
        _fake_memory = MagicMock()
        monkeypatch.setattr(rm, "AutoBudgetMemory", lambda path: _fake_memory)

        captured = io.StringIO()
        monkeypatch.setattr(_sys, "stdout", captured)

        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--budget-memory-dry-run",
                "--budget-memory", str(jl),
                "--auto-budget",
                "--preset", "3x3",
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        finally:
            _sys.argv = _orig_argv

        output = captured.getvalue()
        assert "auto_budget" in output, f"expected auto_budget source in:\n{output}"


class TestAutoBudgetDryRun:
    def test_auto_budget_dry_run_no_provider_or_run_files(self, tmp_path, monkeypatch):
        """Auto-budget dry-run audits learned caps without API calls or run files."""
        import io
        import sys as _sys
        from unittest.mock import MagicMock

        from budgetflow import provider_signature
        from budgetflow.run_mini_swe_compare import main
        import budgetflow.run_mini_swe_compare as rm

        preflight_called = []

        def _fake_check(backends):
            preflight_called.append(True)
            raise AssertionError("provider preflight must NOT be called during auto-budget dry-run")

        monkeypatch.setattr(provider_signature, "check_required_signatures", _fake_check)

        _fake_task = MagicMock()
        _fake_task.instance_id = "sympy__sympy-99999"
        _fake_task.repo = "sympy/sympy"
        _fake_task.patch = "line1\nline2\n"
        _fake_task.fail_to_pass = ("t1",)
        _fake_task.pass_to_pass = ("p1",)
        monkeypatch.setattr(rm, "load_compare_easy_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_compare_medium_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_swebench_lite_tasks", lambda instance_ids=None: [_fake_task])

        runs_tmp = tmp_path / "runs"
        runs_tmp.mkdir()
        monkeypatch.setattr(rm, "RUNS_DIR", runs_tmp)

        mem = tmp_path / "auto_budget_memory.jsonl"
        mem.write_text(json.dumps({
            "instance_id": "sympy__sympy-99999",
            "repo": "sympy/sympy",
            "total_cost": 0.20,
            "cap_was_sufficient": "sufficient",
            "resolved": True,
            "patch_lines": 2,
            "f2p_count": 1,
            "p2p_count": 1,
        }) + "\n")

        before_files = set(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
        captured = io.StringIO()
        monkeypatch.setattr(_sys, "stdout", captured)

        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--auto-budget-dry-run",
                "--auto-budget-memory", str(mem),
                "--preset", "3x3",
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        finally:
            _sys.argv = _orig_argv

        output = captured.getvalue()
        assert "AutoBudget dry-run" in output
        assert "sympy__sympy-99999" in output
        assert "memory_exact" in output
        assert "neighbors" in output
        assert not preflight_called
        after_files = set(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file())
        assert after_files == before_files


# ── P1.2: Trusted fallback audit section ─────────────────────────────────────


class TestTrustedFallbackAudit:
    def test_trusted_fallback_section_appears(self, tmp_path):
        """TRUSTED_FALLBACK AUDIT section must appear in replay output."""
        from budgetflow.offline_replay import run_replay

        p017 = tmp_path / "017.jsonl"
        p017.write_text(json.dumps(_make_record(harness_resolved=True)) + "\n")

        # Create a trusted_fallback row: worktree patch source + complete evidence
        p018 = tmp_path / "018.jsonl"
        tf_rec = _make_record(
            instance_id="sympy__sympy-1",
            harness_resolved=True,
            patch_extracted=True,
            patch_source="worktree",
            submitted_patch="",
            patch_text="mock diff content",
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=pass",
        )
        # build_harness_trust needs to see this as trusted_fallback
        p018.write_text(json.dumps(tf_rec) + "\n")

        out = run_replay(p017, p018)
        assert "TRUSTED_FALLBACK AUDIT" in out
        assert "trusted_fallback_rows=1" in out
        assert "evidence_complete=1" in out

    def test_trusted_fallback_no_rows(self, tmp_path):
        """No trusted_fallback rows → section shows 0."""
        from budgetflow.offline_replay import run_replay

        p017 = tmp_path / "017.jsonl"
        p017.write_text(json.dumps(_make_record(harness_resolved=True)) + "\n")

        p018 = tmp_path / "018.jsonl"
        # Normal submission — not trusted_fallback
        p018.write_text(json.dumps(_make_record(
            harness_resolved=True,
            patch_extracted=True,
            patch_source="submission",
            submitted_patch="/tmp/p.diff",
            detail="test_patch=ok;fail_before=fail;model_patch=ok;fail_after=pass;pass_to_pass=pass",
        )) + "\n")

        out = run_replay(p017, p018)
        assert "TRUSTED_FALLBACK AUDIT" in out
        assert "trusted_fallback_rows=0" in out


# ── P1: Historical cap & not_comparable verdict ───────────────────────────────


class TestDryRunHistoricalCap:
    """P1.1: dry-run must prefer historical cap over standard_tight."""

    def test_historical_cap_from_jsonl(self, tmp_path, monkeypatch):
        """When source JSONL has estimated_task_cap, use it as old_cap."""
        import sys as _sys
        from budgetflow.run_mini_swe_compare import main
        from budgetflow import provider_signature
        from unittest.mock import MagicMock
        import io

        # JSONL with estimated_task_cap field
        jl = tmp_path / "bm.jsonl"
        jl.write_text(
            json.dumps({
                ** _make_record(
                    instance_id="sympy__sympy-99999",
                    total_cost=0.5,
                    strategy="budget_only_tight",
                ),
                "estimated_task_cap": 0.25,
            }) + "\n"
        )

        monkeypatch.setattr(provider_signature, "check_required_signatures", lambda backends: [])
        import budgetflow.run_mini_swe_compare as rm

        _fake_task = MagicMock()
        _fake_task.instance_id = "sympy__sympy-99999"
        _fake_task.repo = "sympy"

        monkeypatch.setattr(rm, "load_compare_easy_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_compare_medium_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_swebench_lite_tasks", lambda instance_ids=None: [_fake_task])

        captured = io.StringIO()
        monkeypatch.setattr(_sys, "stdout", captured)

        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--budget-memory-dry-run",
                "--budget-memory", str(jl),
                "--preset", "3x3",
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        finally:
            _sys.argv = _orig_argv

        output = captured.getvalue()
        assert "historical" in output, (
            f"expected historical old_cap source in:\n{output}"
        )

    def test_standard_tight_not_comparable(self, tmp_path, monkeypatch):
        """Without auto-budget, historical cap, or per-task-cap → not_comparable."""
        import sys as _sys
        from budgetflow.run_mini_swe_compare import main
        from budgetflow import provider_signature
        from unittest.mock import MagicMock
        import io

        # JSONL without estimated_task_cap or batch_budget_cap
        jl = tmp_path / "bm.jsonl"
        jl.write_text(
            json.dumps(_make_record(
                instance_id="sympy__sympy-99999",
                total_cost=0.5,
                strategy="budget_only_tight",
            )) + "\n"
        )

        monkeypatch.setattr(provider_signature, "check_required_signatures", lambda backends: [])
        import budgetflow.run_mini_swe_compare as rm

        _fake_task = MagicMock()
        _fake_task.instance_id = "sympy__sympy-99999"
        _fake_task.repo = "sympy"

        monkeypatch.setattr(rm, "load_compare_easy_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_compare_medium_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_swebench_lite_tasks", lambda instance_ids=None: [_fake_task])

        captured = io.StringIO()
        monkeypatch.setattr(_sys, "stdout", captured)

        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--budget-memory-dry-run",
                "--budget-memory", str(jl),
                "--preset", "3x3",
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        finally:
            _sys.argv = _orig_argv

        output = captured.getvalue()
        assert "not_comparable" in output, (
            f"expected not_comparable verdict in:\n{output}"
        )

    def test_historical_batch_budget_cap(self, tmp_path, monkeypatch):
        """batch_budget_cap in JSONL also qualifies as historical cap."""
        import sys as _sys
        from budgetflow.run_mini_swe_compare import main
        from budgetflow import provider_signature
        from unittest.mock import MagicMock
        import io

        jl = tmp_path / "bm.jsonl"
        jl.write_text(
            json.dumps({
                ** _make_record(
                    instance_id="sympy__sympy-99999",
                    total_cost=0.5,
                    strategy="budget_only_tight",
                ),
                "batch_budget_cap": 0.30,
            }) + "\n"
        )

        monkeypatch.setattr(provider_signature, "check_required_signatures", lambda backends: [])
        import budgetflow.run_mini_swe_compare as rm

        _fake_task = MagicMock()
        _fake_task.instance_id = "sympy__sympy-99999"
        _fake_task.repo = "sympy"

        monkeypatch.setattr(rm, "load_compare_easy_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_compare_medium_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_swebench_lite_tasks", lambda instance_ids=None: [_fake_task])

        captured = io.StringIO()
        monkeypatch.setattr(_sys, "stdout", captured)

        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--budget-memory-dry-run",
                "--budget-memory", str(jl),
                "--preset", "3x3",
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        finally:
            _sys.argv = _orig_argv

        output = captured.getvalue()
        assert "historical" in output, (
            f"expected historical source for batch_budget_cap in:\n{output}"
        )

    def test_per_task_cap_priority_over_standard(self, tmp_path, monkeypatch):
        """--per-task-cap should show per_task source (not standard_tight)."""
        import sys as _sys
        from budgetflow.run_mini_swe_compare import main
        from budgetflow import provider_signature
        from unittest.mock import MagicMock
        import io

        jl = tmp_path / "bm.jsonl"
        jl.write_text(
            json.dumps(_make_record(
                instance_id="sympy__sympy-99999",
                total_cost=0.5,
                strategy="budget_only_tight",
            )) + "\n"
        )

        monkeypatch.setattr(provider_signature, "check_required_signatures", lambda backends: [])
        import budgetflow.run_mini_swe_compare as rm

        _fake_task = MagicMock()
        _fake_task.instance_id = "sympy__sympy-99999"
        _fake_task.repo = "sympy"

        monkeypatch.setattr(rm, "load_compare_easy_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_compare_medium_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_swebench_lite_tasks", lambda instance_ids=None: [_fake_task])

        captured = io.StringIO()
        monkeypatch.setattr(_sys, "stdout", captured)

        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--budget-memory-dry-run",
                "--budget-memory", str(jl),
                "--per-task-cap", "0.15",
                "--preset", "3x3",
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        finally:
            _sys.argv = _orig_argv

        output = captured.getvalue()
        assert "per_task" in output, (
            f"expected per_task source in:\n{output}"
        )

    def test_verdict_ok_when_within_threshold(self, tmp_path, monkeypatch):
        """When actual_median is close to old_cap → verdict=ok."""
        import sys as _sys
        from budgetflow.run_mini_swe_compare import main
        from budgetflow import provider_signature
        from unittest.mock import MagicMock
        import io

        # estimated_task_cap=0.25, actual median=0.25 -> ratio=1.0 → ok
        jl = tmp_path / "bm.jsonl"
        jl.write_text(
            json.dumps({
                ** _make_record(
                    instance_id="sympy__sympy-99999",
                    total_cost=0.25,
                    strategy="budget_only_tight",
                ),
                "estimated_task_cap": 0.25,
            }) + "\n"
        )

        monkeypatch.setattr(provider_signature, "check_required_signatures", lambda backends: [])
        import budgetflow.run_mini_swe_compare as rm

        _fake_task = MagicMock()
        _fake_task.instance_id = "sympy__sympy-99999"
        _fake_task.repo = "sympy"

        monkeypatch.setattr(rm, "load_compare_easy_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_compare_medium_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_swebench_lite_tasks", lambda instance_ids=None: [_fake_task])

        captured = io.StringIO()
        monkeypatch.setattr(_sys, "stdout", captured)

        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--budget-memory-dry-run",
                "--budget-memory", str(jl),
                "--preset", "3x3",
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        finally:
            _sys.argv = _orig_argv

        output = captured.getvalue()
        assert "ok" in output, (
            f"expected ok verdict in:\n{output}"
        )


# ── Task 3: BudgetMemory record field naming ─────────────────────────────────


class TestBudgetMemoryFieldNaming:
    """budget_memory_budget_source vs budget_memory_source_paths distinction."""

    def test_budget_source_field_uses_exact_task(self):
        """budget_memory_budget_source reflects the cascade level."""
        bm = BudgetMemory()
        bm._learn([_make_record(instance_id="foo__bar-1", total_cost=0.50)] * 5)
        est = bm.estimate_task_budget("foo__bar-1", strategy="budget_only_tight")
        assert est.budget_source == "exact_task"

    def test_source_paths_distinct_from_budget_source(self):
        """budget_memory_source_paths is file paths; budget_memory_budget_source is cascade level."""
        bm = BudgetMemory()
        bm._learn([_make_record(instance_id="foo__bar-1", total_cost=0.50)] * 5)
        est = bm.estimate_task_budget("foo__bar-1", strategy="budget_only_tight")

        rec = _make_record()
        rec["budget_memory_enabled"] = True
        rec["budget_memory_source_paths"] = "/data/018.jsonl"
        rec["budget_memory_budget_source"] = est.budget_source

        assert rec["budget_memory_source_paths"] == "/data/018.jsonl"
        assert rec["budget_memory_budget_source"] == "exact_task"
        assert rec["budget_memory_source_paths"] != rec["budget_memory_budget_source"]


# ── Task 1: No litellm warning in dry-run/gate-only ──────────────────────────


class TestNoLitellmInOfflineMode:
    """Verify dry-run/gate-only output does not contain provider preflight lines."""

    def test_dry_run_output_has_no_preflight(self, tmp_path, monkeypatch):
        """dry-run stdout must not contain '[preflight]'."""
        import sys as _sys
        from budgetflow.run_mini_swe_compare import main
        from budgetflow import provider_signature
        from unittest.mock import MagicMock
        import io

        jl = tmp_path / "bm.jsonl"
        jl.write_text(
            json.dumps(_make_record(
                instance_id="sympy__sympy-99999",
                total_cost=0.5,
                strategy="budget_only_tight",
            )) + "\n"
        )

        monkeypatch.setattr(provider_signature, "check_required_signatures", lambda backends: [])
        import budgetflow.run_mini_swe_compare as rm

        _fake_task = MagicMock()
        _fake_task.instance_id = "sympy__sympy-99999"
        _fake_task.repo = "sympy"
        monkeypatch.setattr(rm, "load_compare_easy_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_compare_medium_tasks", lambda n: [_fake_task])
        monkeypatch.setattr(rm, "load_swebench_lite_tasks", lambda instance_ids=None: [_fake_task])

        captured = io.StringIO()
        monkeypatch.setattr(_sys, "stdout", captured)

        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--budget-memory-dry-run",
                "--budget-memory", str(jl),
                "--preset", "3x3",
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        finally:
            _sys.argv = _orig_argv

        output = captured.getvalue()
        assert "[preflight]" not in output, (
            f"dry-run output must NOT contain [preflight]:\n{output}"
        )

    def test_gate_only_output_has_no_preflight(self, tmp_path, monkeypatch):
        """gate-only stdout must not contain '[preflight]'."""
        import sys as _sys
        from budgetflow.run_mini_swe_compare import main
        import io

        jl = tmp_path / "bm.jsonl"
        jl.write_text(
            json.dumps(_make_record(
                instance_id="sympy__sympy-99999",
                total_cost=0.5,
                strategy="budget_only_tight",
            )) + "\n"
        )

        captured = io.StringIO()
        monkeypatch.setattr(_sys, "stdout", captured)

        _orig_argv = _sys.argv[:]
        try:
            _sys.argv = [
                "run_mini_swe_compare",
                "--budget-memory-gate-only",
                "--budget-memory", str(jl),
            ]
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        finally:
            _sys.argv = _orig_argv

        output = captured.getvalue()
        assert "[preflight]" not in output, (
            f"gate-only output must NOT contain [preflight]:\n{output}"
        )


class TestLOOBudgetMemory:
    """Leave-one-task-out BudgetMemory generalization tests."""

    def test_exclude_ids_prevents_exact_task_match(self, tmp_path):
        """When exclude_ids contains a task, its records must NOT be used for estimation."""
        from budgetflow.budget_memory import BudgetMemory

        jl = tmp_path / "data.jsonl"
        recs = [
            _make_record(instance_id="a__task1", total_cost=0.1),
            _make_record(instance_id="a__task1", total_cost=0.2),
            _make_record(instance_id="a__task2", total_cost=0.3),
            _make_record(instance_id="a__task2", total_cost=0.4),
        ]
        jl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

        # Without exclude — task1 should hit exact_task (2 records >= threshold)
        bm_full = BudgetMemory.from_jsonl([jl])
        est_full = bm_full.estimate_task_budget("a__task1")
        assert est_full.budget_source == "exact_task", f"expected exact_task, got {est_full.budget_source}"

        # With exclude — task1 should fall to repo_median or higher
        bm_excl = BudgetMemory.from_jsonl([jl], exclude_ids={"a__task1"})
        est_excl = bm_excl.estimate_task_budget("a__task1")
        assert est_excl.budget_source != "exact_task", (
            f"exclude_ids should prevent exact_task, got {est_excl.budget_source}"
        )
        assert est_excl.budget_source in ("repo_median", "strategy_median", "global_fallback")

    def test_exclude_ids_cascade_to_repo_median(self, tmp_path):
        """With a multi-task repo, excluding one task should cascade to repo_median."""
        from budgetflow.budget_memory import BudgetMemory

        jl = tmp_path / "data.jsonl"
        recs = []
        # 4 tasks in same repo, 3 records each = repo has 12 records
        for tid in range(1, 5):
            for _ in range(3):
                recs.append(_make_record(
                    instance_id=f"repo__task{tid}",
                    total_cost=0.1 + tid * 0.05,
                ))
        jl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

        bm = BudgetMemory.from_jsonl([jl], exclude_ids={"repo__task2"})
        est = bm.estimate_task_budget("repo__task2")
        # repo has 3 other tasks * 3 records = 9 records, so repo_median should trigger
        assert est.budget_source == "repo_median", f"expected repo_median, got {est.budget_source}"
        assert est.budget_confidence == "medium"

    def test_exclude_ids_cascade_to_strategy_median(self, tmp_path):
        """When repo has < 3 records after exclusion, cascade to strategy level."""
        from budgetflow.budget_memory import BudgetMemory

        jl = tmp_path / "data.jsonl"
        recs = []
        # Only 1 task in repo, but strategy has enough records
        for _ in range(5):
            recs.append(_make_record(
                instance_id="solo__onlytask",
                total_cost=0.25,
                strategy="budget_only_tight",
            ))
        # Another repo's task to provide strategy-level records
        for _ in range(3):
            recs.append(_make_record(
                instance_id="other__othertask",
                total_cost=0.15,
                strategy="budget_only_tight",
            ))
        jl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

        bm = BudgetMemory.from_jsonl([jl], exclude_ids={"solo__onlytask"})
        est = bm.estimate_task_budget("solo__onlytask", strategy="budget_only_tight")
        # solo repo has 0 records after exclusion, repo_median requires >= 3
        # strategy_median: budget_only_tight has 3 records from other__othertask >= 2
        assert est.budget_source == "strategy_median", f"expected strategy_median, got {est.budget_source}"

    def test_exclude_ids_global_fallback_when_no_data(self, tmp_path):
        """When all tiers exhausted, estimation falls to global_fallback."""
        from budgetflow.budget_memory import BudgetMemory

        jl = tmp_path / "data.jsonl"
        recs = []
        for _ in range(2):
            recs.append(_make_record(instance_id="x__t1", total_cost=0.1))
        jl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

        bm = BudgetMemory.from_jsonl([jl], exclude_ids={"x__t1"})
        est = bm.estimate_task_budget("x__t1", strategy="nonexistent")
        # 0 records after exclusion, no repo data, no strategy data
        assert est.budget_source == "global_fallback", f"expected global_fallback, got {est.budget_source}"

    def test_loo_no_exact_task_with_multiple_files(self, tmp_path):
        """LOO across multiple files must produce 0 exact_task matches."""
        from budgetflow.budget_memory import BudgetMemory

        jl1 = tmp_path / "run1.jsonl"
        jl2 = tmp_path / "run2.jsonl"

        for jl in (jl1, jl2):
            recs = []
            for tid in range(1, 4):
                for _ in range(2):
                    recs.append(_make_record(instance_id=f"pkg__task{tid}", total_cost=0.1 * tid))
            jl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

        for held_out_id in ("pkg__task1", "pkg__task2", "pkg__task3"):
            bm = BudgetMemory.from_jsonl([jl1, jl2], exclude_ids={held_out_id})
            est = bm.estimate_task_budget(held_out_id)
            assert est.budget_source != "exact_task", (
                f"LOO held-out {held_out_id} must not use exact_task, got {est.budget_source}"
            )

    def test_offline_replay_loo_cli(self, tmp_path):
        """The --loo-budget-memory CLI mode produces valid output."""
        import subprocess
        import os

        jl = tmp_path / "test_data.jsonl"
        recs = []
        for tid in range(1, 6):
            for _ in range(3):
                recs.append(_make_record(instance_id=f"test__task{tid}", total_cost=0.05 * tid))
        jl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.join(
            os.path.dirname(__file__), "..", "src"
        )
        result = subprocess.run(
            ["python", "-m", "budgetflow.offline_replay",
             "--loo-budget-memory", str(jl)],
            capture_output=True, text=True, timeout=15, env=env,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "LOO BUDGET MEMORY" in result.stdout
        assert "exact_task: 0/" in result.stdout
        assert "Source Distribution" in result.stdout
        assert "GATE A" in result.stdout


class TestRepoKeyNormalization:
    """Repo key normalization: instance_id, task.repo slug -> canonical short key."""

    def test_normalize_instance_id(self):
        from budgetflow.budget_memory import normalize_repo_key
        assert normalize_repo_key("sympy__sympy-13480") == "sympy"
        assert normalize_repo_key("django__django-10924") == "django"

    def test_normalize_repo_slug_double_underscore(self):
        from budgetflow.budget_memory import normalize_repo_key
        assert normalize_repo_key("sympy__sympy") == "sympy"

    def test_normalize_repo_slug_slash(self):
        from budgetflow.budget_memory import normalize_repo_key
        assert normalize_repo_key("sympy/sympy") == "sympy"

    def test_normalize_already_short(self):
        from budgetflow.budget_memory import normalize_repo_key
        assert normalize_repo_key("sympy") == "sympy"

    def test_repo_key_match_in_estimate(self, tmp_path):
        """estimate_task_budget with repo='sympy/sympy' must hit repo_median."""
        from budgetflow.budget_memory import BudgetMemory

        jl = tmp_path / "data.jsonl"
        recs = []
        for tid in range(1, 4):
            for _ in range(4):
                recs.append(_make_record(instance_id=f"sympy__sympy-{10000+tid}", total_cost=0.15))
        jl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

        bm = BudgetMemory.from_jsonl([jl])
        # Pass SWE-bench lite repo slug
        est = bm.estimate_task_budget("sympy__sympy-99999", repo="sympy/sympy")
        assert est.budget_source == "repo_median", (
            f"repo='sympy/sympy' should normalize to 'sympy' and hit repo_median, "
            f"got {est.budget_source}: {est.budget_reason}"
        )

    def test_repo_key_match_repo_slug_double_underscore(self, tmp_path):
        """estimate_task_budget with repo='sympy__sympy' must hit repo_median."""
        from budgetflow.budget_memory import BudgetMemory

        jl = tmp_path / "data.jsonl"
        recs = []
        for tid in range(1, 4):
            for _ in range(4):
                recs.append(_make_record(instance_id=f"sympy__sympy-{10000+tid}", total_cost=0.15))
        jl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

        bm = BudgetMemory.from_jsonl([jl])
        est = bm.estimate_task_budget("sympy__sympy-99999", repo="sympy__sympy")
        assert est.budget_source == "repo_median", (
            f"repo='sympy__sympy' should normalize to 'sympy' and hit repo_median, "
            f"got {est.budget_source}"
        )


class TestBudgetMemoryNoStrategyBias:
    """estimate_task_budget without strategy parameter must not use strategy_median."""

    def test_no_strategy_bias_for_held_out_task(self, tmp_path):
        """When strategy not passed, cascade skips strategy_median."""
        from budgetflow.budget_memory import BudgetMemory

        jl = tmp_path / "data.jsonl"
        recs = []
        # 3 tasks in same repo, all using budget_only_tight
        for tid in range(1, 4):
            for _ in range(3):
                recs.append(_make_record(
                    instance_id=f"pkg__task{tid}",
                    total_cost=0.1 * tid,
                    strategy="budget_only_tight",
                ))
        jl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

        # Exclude task2 — it should fall to repo_median, NOT strategy_median
        bm = BudgetMemory.from_jsonl([jl], exclude_ids={"pkg__task2"})
        est = bm.estimate_task_budget("pkg__task2")
        # No strategy passed -> cascade: exact_task -> repo_median -> global_fallback
        assert est.budget_source != "strategy_median", (
            f"Without strategy param, should not use strategy_median, got {est.budget_source}"
        )
        assert est.budget_source in ("repo_median", "global_fallback")

    def test_django_loo_holdout_no_strategy_median(self, tmp_path):
        """LOO holdout django without strategy must NOT hit strategy_median.

        Mirrors real scenario: django is the only task in its repo, so
        repo_median misses. cascade must fall to global_fallback, not leak
        into strategy_median.
        """
        from budgetflow.budget_memory import BudgetMemory

        jl = tmp_path / "data.jsonl"
        recs = []
        # django: single task, single repo
        for _ in range(10):
            recs.append(_make_record(
                instance_id="django__django-10924",
                total_cost=0.12,
                strategy="budget_only_tight",
            ))
        # sympy tasks provide training data
        for tid in ["17630", "18057"]:
            for _ in range(5):
                recs.append(_make_record(
                    instance_id=f"sympy__sympy-{tid}",
                    total_cost=0.10,
                    strategy="budget_only_tight",
                ))
        jl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

        bm = BudgetMemory.from_jsonl([jl], exclude_ids={"django__django-10924"})
        est = bm.estimate_task_budget("django__django-10924")
        assert est.budget_source != "strategy_median", (
            f"django LOO without strategy must not hit strategy_median, got {est.budget_source}"
        )
        assert est.budget_source == "global_fallback", (
            f"django LOO should get global_fallback (single-task repo, no strategy), got {est.budget_source}"
        )

    def test_strategy_only_used_when_explicit(self, tmp_path):
        """strategy_median should only be used when strategy is explicitly passed."""
        from budgetflow.budget_memory import BudgetMemory

        jl = tmp_path / "data.jsonl"
        recs = []
        # Single-task repo so repo_median misses. Add other tasks with same
        # strategy so strategy_median has >= 2 records.
        for _ in range(3):
            recs.append(_make_record(instance_id="solo__t1", total_cost=0.15, strategy="my_strat"))
        for _ in range(3):
            recs.append(_make_record(instance_id="other__t2", total_cost=0.10, strategy="my_strat"))
        jl.write_text("\n".join(json.dumps(r) for r in recs) + "\n")

        bm = BudgetMemory.from_jsonl([jl], exclude_ids={"solo__t1"})
        est_no_strat = bm.estimate_task_budget("solo__t1")
        assert est_no_strat.budget_source == "global_fallback", (
            f"Without strategy, should skip strategy_median, got {est_no_strat.budget_source}"
        )

        est_with_strat = bm.estimate_task_budget("solo__t1", strategy="my_strat")
        assert est_with_strat.budget_source == "strategy_median", (
            f"With explicit strategy, should use strategy_median, got {est_with_strat.budget_source}"
        )
