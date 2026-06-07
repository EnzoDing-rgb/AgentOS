from budgetflow.run_observability.audit import build_compact_audit


def test_compact_audit_preserves_generic_tier_counts() -> None:
    audit = build_compact_audit([
        {
            "instance_id": "repo__task",
            "strategy": "budgetflow_value_aware_tight",
            "harness_resolved": True,
            "harness_evidence": {"evidence_complete": True},
            "total_cost": 0.25,
            "llm_turns": 4,
            "turn_trace_count": 4,
            "backend_picks": ["tier2_balanced", "tier4", "tier5", "tier5"],
        }
    ])

    stats = audit["by_strategy"]["budgetflow_value_aware_tight"]

    assert stats["tier_turns"] == {2: 1, 4: 1, 5: 2}
    assert stats["t3_turns"] == 0
