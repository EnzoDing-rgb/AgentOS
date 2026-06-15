import json
from pathlib import Path

from budgetflow.learning_context import (
    default_policy_memory_source,
    default_policy_memory_sources,
    load_policy_memory_context,
    looks_like_policy_memory_source,
)


def _run_record(**kw) -> dict:
    record = {
        "instance_id": "r__t-a",
        "strategy": "budgetflow_segment",
        "routing": "segment_value_aware",
        "harness_resolved": True,
        "score_status": "pass",
        "total_cost": 0.1,
        "backend_picks": ["tier2", "tier3"],
        "turn_traces": [{"workflow_segment": "Action", "backend_tier": 3}],
        "routing_decision_schema": "v1",
        "task_set_kind": "familiar",
        "policy_kind": "bootstrap",
        "learn_policy_input_views": ["routing", "escalation"],
        "harness_trust": "trusted",
    }
    record.update(kw)
    return record


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def test_default_policy_memory_source_skips_auto_budget_memory(tmp_path) -> None:
    _write_jsonl(tmp_path / "auto_budget_memory.jsonl", [_run_record()])
    source_path = tmp_path / "065_value_triggered_escalation_3x3.jsonl"
    _write_jsonl(source_path, [_run_record()])

    source = default_policy_memory_source(tmp_path)

    assert source == source_path


def test_default_policy_memory_sources_returns_recent_usable_runs(tmp_path) -> None:
    _write_jsonl(tmp_path / "auto_budget_memory.jsonl", [_run_record()])
    old = tmp_path / "old.jsonl"
    new = tmp_path / "new.jsonl"
    _write_jsonl(old, [_run_record(instance_id="r__old")])
    _write_jsonl(new, [_run_record(instance_id="r__new")])

    sources = default_policy_memory_sources(tmp_path, limit=2)

    assert set(sources) == {old, new}


def test_looks_like_policy_memory_source_requires_routing_evidence(tmp_path) -> None:
    cap_memory = tmp_path / "auto_budget_memory.jsonl"
    _write_jsonl(cap_memory, [_run_record()])
    no_routing = tmp_path / "run.jsonl"
    _write_jsonl(no_routing, [{"instance_id": "r__t-a", "routing": "segment_value_aware"}])
    with_routing = tmp_path / "run2.jsonl"
    _write_jsonl(with_routing, [_run_record()])

    assert looks_like_policy_memory_source(cap_memory) is False
    assert looks_like_policy_memory_source(no_routing) is False
    assert looks_like_policy_memory_source(with_routing) is True


def test_default_policy_memory_source_skips_old_schema_runs(tmp_path) -> None:
    old_schema = tmp_path / "old_schema.jsonl"
    current_schema = tmp_path / "current_schema.jsonl"
    old_record = _run_record()
    old_record.pop("routing_decision_schema")
    old_record.pop("score_status")
    _write_jsonl(old_schema, [old_record])
    _write_jsonl(current_schema, [_run_record(instance_id="r__current")])

    assert looks_like_policy_memory_source(old_schema) is False
    assert default_policy_memory_source(tmp_path) == current_schema


def test_policy_memory_source_requires_score_status_schema(tmp_path) -> None:
    old_score_schema = tmp_path / "old_score_schema.jsonl"
    record = _run_record()
    record.pop("score_status")
    _write_jsonl(old_score_schema, [record])

    assert looks_like_policy_memory_source(old_score_schema) is False


def test_explicit_policy_memory_rejects_old_schema(tmp_path) -> None:
    """Explicit path with old-schema-only rows returns filtering summary, not None."""
    old_schema = tmp_path / "old_schema.jsonl"
    old_record = _run_record()
    old_record.pop("routing_decision_schema")
    old_record.pop("score_status")
    _write_jsonl(old_schema, [old_record])

    ctx = load_policy_memory_context(
        runs_dir=tmp_path,
        repo_root=tmp_path,
        explicit_path=str(old_schema),
        resume=False,
        resume_path=None,
        disable=False,
        regret_threshold=None,
    )

    assert ctx.enabled is False
    assert ctx.source_kind == "explicit"
    assert ctx.reason == "no_accepted_memory_records"
    # PolicyMemory exists for audit even when enabled=False.
    assert ctx.memory is not None
    mfs = ctx.memory.memory_filtering_summary
    assert mfs["records_seen"] == 1
    assert mfs["records_accepted"] == 0
    assert mfs["records_skipped"] == 1
    assert "old_schema" in mfs["skip_reasons"]
    # memory_source must be present in filtering summary.
    assert mfs["memory_source"]
    assert mfs["schema_version"] == "v1"


def test_load_policy_memory_context_from_default_recent(tmp_path) -> None:
    source_path = tmp_path / "066_postfix_3x3.jsonl"
    _write_jsonl(source_path, [_run_record()])

    ctx = load_policy_memory_context(
        runs_dir=tmp_path,
        repo_root=tmp_path,
        explicit_path=None,
        resume=False,
        resume_path=None,
        disable=False,
        regret_threshold=None,
    )

    # PolicyMemory is opt-in: no auto-detection without --policy-memory.
    assert ctx.enabled is False
    assert ctx.reason == "no_explicit_memory_path"


def test_load_policy_memory_context_merges_explicit_sources(tmp_path) -> None:
    source_a = tmp_path / "a.jsonl"
    source_b = tmp_path / "b.jsonl"
    _write_jsonl(source_a, [_run_record(instance_id="r__a")])
    _write_jsonl(source_b, [_run_record(instance_id="r__b")])

    ctx = load_policy_memory_context(
        runs_dir=tmp_path,
        repo_root=tmp_path,
        explicit_path=f"{source_a},{source_b}",
        resume=False,
        resume_path=None,
        disable=False,
        regret_threshold=None,
    )

    assert ctx.enabled is True
    assert ctx.sources == (source_a, source_b)
    assert ctx.memory is not None
    assert ctx.memory.routing_prior_summary("r__a")["task_seen"] == 1
    assert ctx.memory.routing_prior_summary("r__b")["task_seen"] == 1


# ── Memory hardening tests ────────────────────────────────────────────────


def test_policy_memory_default_off_without_explicit_path(tmp_path) -> None:
    """Without --policy-memory, PolicyMemory stays disabled even with usable JSONL."""
    source = tmp_path / "recent.jsonl"
    _write_jsonl(source, [_run_record()])
    ctx = load_policy_memory_context(
        runs_dir=tmp_path, repo_root=tmp_path,
        explicit_path=None, resume=False, resume_path=None,
        disable=False, regret_threshold=None,
    )
    assert ctx.enabled is False
    assert ctx.reason == "no_explicit_memory_path"
    assert ctx.memory is None


def test_policy_memory_disable_flag_overrides_explicit_path(tmp_path) -> None:
    """--disable-policy-memory forces off even with explicit path."""
    source = tmp_path / "explicit.jsonl"
    _write_jsonl(source, [_run_record()])
    ctx = load_policy_memory_context(
        runs_dir=tmp_path, repo_root=tmp_path,
        explicit_path=str(source), resume=False, resume_path=None,
        disable=True, regret_threshold=None,
    )
    assert ctx.enabled is False
    assert ctx.reason == "disabled_by_flag"


def test_policy_memory_rejects_old_schema_records(tmp_path) -> None:
    """Records with old routing_decision_schema are counted in filtering summary.

    Old-schema records are now passed through to rebuild_from_records so they
    appear in records_seen/records_skipped/skip_reasons. Only current-schema
    records contribute to memory priors.
    """
    source = tmp_path / "oldschema.jsonl"
    _write_jsonl(source, [
        _run_record(instance_id="r__valid", routing_decision_schema="v1"),
        _run_record(instance_id="r__old", routing_decision_schema="v0"),
    ])
    ctx = load_policy_memory_context(
        runs_dir=tmp_path, repo_root=tmp_path,
        explicit_path=str(source), resume=False, resume_path=None,
        disable=False, regret_threshold=None,
    )
    assert ctx.enabled is True
    assert ctx.memory is not None
    mfs = ctx.memory.memory_filtering_summary
    assert mfs["records_seen"] == 2
    assert mfs["records_accepted"] == 1
    assert mfs["records_skipped"] == 1
    assert "old_schema" in mfs["skip_reasons"]


def test_policy_memory_rejects_protocol_abort_rows(tmp_path) -> None:
    """Protocol/parser abort rows (harness_trust=incomplete) are skipped."""
    source = tmp_path / "aborts.jsonl"
    _write_jsonl(source, [
        _run_record(score_status="pass", harness_trust="incomplete"),
        _run_record(instance_id="r__b", score_status="pass", harness_trust="trusted"),
    ])
    ctx = load_policy_memory_context(
        runs_dir=tmp_path, repo_root=tmp_path,
        explicit_path=str(source), resume=False, resume_path=None,
        disable=False, regret_threshold=None,
    )
    assert ctx.enabled is True
    mfs = ctx.memory.memory_filtering_summary
    assert mfs["records_seen"] == 2
    assert mfs["records_accepted"] == 1
    assert mfs["records_skipped"] == 1
    assert "harness_incomplete" in mfs["skip_reasons"]


def test_policy_memory_rejects_abort_score_status(tmp_path) -> None:
    """Rows with score_status=abort are skipped from memory."""
    source = tmp_path / "abort_score.jsonl"
    _write_jsonl(source, [
        _run_record(score_status="abort"),
        _run_record(instance_id="r__b", score_status="pass"),
    ])
    ctx = load_policy_memory_context(
        runs_dir=tmp_path, repo_root=tmp_path,
        explicit_path=str(source), resume=False, resume_path=None,
        disable=False, regret_threshold=None,
    )
    assert ctx.enabled is True
    mfs = ctx.memory.memory_filtering_summary
    assert mfs["records_accepted"] == 1
    assert "abort_row" in mfs["skip_reasons"]


def test_policy_memory_rejects_unsupported_routing(tmp_path) -> None:
    """Records with unsupported routing are skipped with reason.

    Source-level check skips unknown routings, but per-record filtering
    also catches them in memory. Add a valid record so the file passes
    the source gate.
    """
    source = tmp_path / "bad_routing.jsonl"
    _write_jsonl(source, [
        _run_record(instance_id="r__valid"),
        _run_record(instance_id="r__bad", routing="unknown_custom_routing"),
    ])
    ctx = load_policy_memory_context(
        runs_dir=tmp_path, repo_root=tmp_path,
        explicit_path=str(source), resume=False, resume_path=None,
        disable=False, regret_threshold=None,
    )
    assert ctx.enabled is True
    mfs = ctx.memory.memory_filtering_summary
    assert mfs["records_seen"] == 2
    assert mfs["records_accepted"] == 1
    assert any("unsupported_routing" in k for k in mfs["skip_reasons"])


def test_policy_memory_skip_reasons_aggregated(tmp_path) -> None:
    """Multiple skip reasons are tracked separately.

    Old-schema records are filtered at source level (never enter memory).
    This test covers per-record skip reasons within memory.
    """
    source = tmp_path / "mixed.jsonl"
    _write_jsonl(source, [
        _run_record(instance_id="r__a", score_status="pass", harness_trust="trusted"),
        _run_record(instance_id="r__b", score_status="abort", harness_trust="trusted"),
        _run_record(instance_id="r__c", score_status="pass", harness_trust="incomplete"),
        _run_record(instance_id="r__d", score_status="pass", harness_trust="trusted"),
    ])
    ctx = load_policy_memory_context(
        runs_dir=tmp_path, repo_root=tmp_path,
        explicit_path=str(source), resume=False, resume_path=None,
        disable=False, regret_threshold=None,
    )
    mfs = ctx.memory.memory_filtering_summary
    assert mfs["records_seen"] == 4
    assert mfs["records_accepted"] == 2  # r__a and r__d
    assert mfs["records_skipped"] == 2
    reasons = mfs["skip_reasons"]
    assert "abort_row" in reasons
    assert "harness_incomplete" in reasons


def test_policy_memory_resume_does_not_enable(tmp_path) -> None:
    """--resume alone must not auto-enable PolicyMemory.

    Only explicit --policy-memory PATH enables memory. Resume restores
    run state but is not a learning source.
    """
    source = tmp_path / "recent.jsonl"
    _write_jsonl(source, [_run_record()])
    ctx = load_policy_memory_context(
        runs_dir=tmp_path, repo_root=tmp_path,
        explicit_path=None, resume=True, resume_path=source,
        disable=False, regret_threshold=None,
    )
    assert ctx.enabled is False
    assert ctx.reason == "no_explicit_memory_path"
    assert ctx.memory is None


def test_explicit_old_schema_only_file_gives_filtering_summary(tmp_path) -> None:
    """Explicit file where every row is old-schema: filtering summary with skip_reasons.

    records_accepted=0 but the filtering summary is still populated so audit
    can report what happened to every row.
    """
    source = tmp_path / "all_old.jsonl"
    records = []
    for i in range(3):
        r = _run_record(instance_id=f"r__old_{i}")
        r.pop("routing_decision_schema")
        r.pop("score_status")
        records.append(r)
    _write_jsonl(source, records)

    ctx = load_policy_memory_context(
        runs_dir=tmp_path, repo_root=tmp_path,
        explicit_path=str(source), resume=False, resume_path=None,
        disable=False, regret_threshold=None,
    )
    assert ctx.enabled is False
    assert ctx.reason == "no_accepted_memory_records"
    assert ctx.memory is not None
    mfs = ctx.memory.memory_filtering_summary
    assert mfs["records_seen"] == 3
    assert mfs["records_accepted"] == 0
    assert mfs["records_skipped"] == 3
    assert mfs["skip_reasons"] == {"old_schema": 3}
    assert mfs["memory_source"]
    assert mfs["schema_version"] == "v1"


def test_explicit_abort_only_file_does_not_enter_prior(tmp_path) -> None:
    """Abort-only explicit file: records seen and skipped, zero accepted."""
    source = tmp_path / "all_abort.jsonl"
    _write_jsonl(source, [
        _run_record(instance_id="r__a", score_status="abort"),
        _run_record(instance_id="r__b", score_status="abort"),
    ])
    ctx = load_policy_memory_context(
        runs_dir=tmp_path, repo_root=tmp_path,
        explicit_path=str(source), resume=False, resume_path=None,
        disable=False, regret_threshold=None,
    )
    assert ctx.enabled is False
    assert ctx.reason == "no_accepted_memory_records"
    assert ctx.memory is not None
    mfs = ctx.memory.memory_filtering_summary
    assert mfs["records_accepted"] == 0
    assert mfs["records_skipped"] == 2
    assert "abort_row" in mfs["skip_reasons"]


def test_explicit_harness_incomplete_only_file_does_not_enter_prior(tmp_path) -> None:
    """Harness-incomplete-only explicit file: seen and skipped, zero accepted."""
    source = tmp_path / "all_incomplete.jsonl"
    _write_jsonl(source, [
        _run_record(instance_id="r__a", harness_trust="incomplete"),
        _run_record(instance_id="r__b", harness_trust="incomplete"),
    ])
    ctx = load_policy_memory_context(
        runs_dir=tmp_path, repo_root=tmp_path,
        explicit_path=str(source), resume=False, resume_path=None,
        disable=False, regret_threshold=None,
    )
    assert ctx.enabled is False
    assert ctx.reason == "no_accepted_memory_records"
    assert ctx.memory is not None
    mfs = ctx.memory.memory_filtering_summary
    assert mfs["records_accepted"] == 0
    assert mfs["records_skipped"] == 2
    assert "harness_incomplete" in mfs["skip_reasons"]
