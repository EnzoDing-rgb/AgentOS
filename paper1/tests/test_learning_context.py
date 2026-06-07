import json
from pathlib import Path

from budgetflow.learning_context import (
    default_policy_memory_source,
    load_policy_memory_context,
    looks_like_policy_memory_source,
)


def _run_record(**kw) -> dict:
    record = {
        "instance_id": "r__t-a",
        "strategy": "budgetflow_value_aware_tight",
        "routing": "budgetflow_value_aware",
        "harness_resolved": True,
        "total_cost": 0.1,
        "backend_picks": ["tier2", "tier3"],
        "turn_traces": [{"stage": "REPAIR", "backend_tier": 3}],
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


def test_looks_like_policy_memory_source_requires_routing_evidence(tmp_path) -> None:
    cap_memory = tmp_path / "auto_budget_memory.jsonl"
    _write_jsonl(cap_memory, [_run_record()])
    no_routing = tmp_path / "run.jsonl"
    _write_jsonl(no_routing, [{"instance_id": "r__t-a", "routing": "budgetflow_value_aware"}])
    with_routing = tmp_path / "run2.jsonl"
    _write_jsonl(with_routing, [_run_record()])

    assert looks_like_policy_memory_source(cap_memory) is False
    assert looks_like_policy_memory_source(no_routing) is False
    assert looks_like_policy_memory_source(with_routing) is True


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

    assert ctx.enabled is True
    assert ctx.source == source_path
    assert ctx.source_kind == "default_recent"
    assert ctx.memory is not None
    assert ctx.memory.routing_prior_summary("r__t-a")["task_seen"] == 1
