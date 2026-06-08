from budgetflow.experiment_observability import enrich_routing_observability


def test_routing_observability_marks_value_aware_as_bootstrap_policy_role() -> None:
    record = {
        "routing": "budgetflow_value_aware",
        "value_objective": "t1_value_efficiency",
        "routing_prior_summary": {
            "learned_action": "early_rescue",
            "policy_memory_source": "data/runs/066.jsonl",
        },
    }

    enrich_routing_observability(record)

    assert record["routing_objective"] == "t1_value_efficiency"
    assert record["routing_policy_family"] == "bootstrap:value_aware_segment"
    assert record["policy_kind"] == "bootstrap"
    assert record["policy_role"] == "value_aware_segment"
    assert record["routing_learned_action"] == "early_rescue"
    assert record["routing_policy_memory_source"] == "data/runs/066.jsonl"
    assert record["routing_decision_schema"] == "v1"


def test_routing_observability_marks_conservative_as_mechanism_ablation() -> None:
    record = {
        "routing": "budgetflow_conservative",
        "task_value_profile": "equal",
    }

    enrich_routing_observability(record)

    assert record["routing_objective"] == "t2_value_source_diagnostic"
    assert record["routing_policy_family"] == "bootstrap:conservative_segment"
    assert record["policy_kind"] == "bootstrap"
    assert record["routing_learned_action"] == "none"
    assert record["routing_imitation_active"] is False


def test_routing_observability_exposes_repair_segment_learning() -> None:
    record = {
        "routing": "budgetflow_value_aware",
        "task_value_profile": "bootstrap_difficulty",
        "routing_prior_segment": "Context",
        "routing_prior_summary": {"learned_action": "default"},
        "routing_repair_prior_summary": {"learned_action": "early_rescue"},
        "routing_repair_prior_segment": "Action",
    }

    enrich_routing_observability(record)

    assert record["routing_learned_action"] == "default"
    assert record["routing_learned_action_segment"] == "Context"
    assert record["routing_repair_learned_action"] == "early_rescue"
    assert record["routing_repair_learned_action_segment"] == "Action"


def test_routing_observability_marks_equal_value_as_ablation() -> None:
    record = {
        "routing": "budgetflow_value_aware",
        "task_value_profile": "equal",
    }

    enrich_routing_observability(record)

    assert record["routing_objective"] == "t2_value_source_diagnostic"
    assert record["routing_policy_family"] == "bootstrap:value_aware_segment"


def test_routing_observability_marks_ex_ante_value_as_diagnostic() -> None:
    record = {
        "routing": "budgetflow_value_aware",
        "task_value_profile": "bootstrap_difficulty",
    }

    enrich_routing_observability(record)

    assert record["routing_objective"] == "t2_value_source_diagnostic"
    assert record["routing_policy_family"] == "bootstrap:value_aware_segment"


def test_routing_observability_marks_budget_only_as_fixed_baseline() -> None:
    record = {
        "routing": "budget_only",
        "task_value_profile": "difficulty",
        "task_value_primary_t1": True,
    }

    enrich_routing_observability(record)

    assert record["routing_objective"] == "t1_value_efficiency"
    assert record["routing_policy_family"] == "fixed_baseline:budget_only_control"
    assert record["policy_kind"] == "fixed_baseline"
