from budgetflow.experiment_observability import enrich_routing_observability


def test_routing_observability_marks_value_aware_as_t1_family() -> None:
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
    assert record["routing_policy_family"] == "bootstrap_value_aware_t1"
    assert record["routing_learned_action"] == "early_rescue"
    assert record["routing_policy_memory_source"] == "data/runs/066.jsonl"
    assert record["routing_decision_schema"] == "v1"


def test_routing_observability_marks_conservative_as_mechanism_ablation() -> None:
    record = {
        "routing": "budgetflow_conservative",
        "task_value_profile": "equal",
    }

    enrich_routing_observability(record)

    assert record["routing_objective"] == "t2_equal_value_ablation"
    assert record["routing_policy_family"] == "bootstrap_conservative_t2"
    assert record["routing_learned_action"] == "none"
    assert record["routing_imitation_active"] is False


def test_routing_observability_exposes_repair_stage_learning() -> None:
    record = {
        "routing": "budgetflow_value_aware",
        "task_value_profile": "cold_start_difficulty",
        "routing_prior_stage": "localization",
        "routing_prior_summary": {"learned_action": "default"},
        "routing_repair_prior_summary": {"learned_action": "early_rescue"},
    }

    enrich_routing_observability(record)

    assert record["routing_learned_action"] == "default"
    assert record["routing_learned_action_stage"] == "localization"
    assert record["routing_repair_learned_action"] == "early_rescue"


def test_routing_observability_marks_equal_value_as_ablation() -> None:
    record = {
        "routing": "budgetflow_value_aware",
        "task_value_profile": "equal",
    }

    enrich_routing_observability(record)

    assert record["routing_objective"] == "t2_equal_value_ablation"
    assert record["routing_policy_family"] == "bootstrap_equal_value_t2"


def test_routing_observability_marks_ex_ante_value_as_diagnostic() -> None:
    record = {
        "routing": "budgetflow_value_aware",
        "task_value_profile": "cold_start_difficulty",
    }

    enrich_routing_observability(record)

    assert record["routing_objective"] == "t1_cold_start_value_diagnostic"
    assert record["routing_policy_family"] == "bootstrap_ex_ante_value_diagnostic"


def test_routing_observability_marks_bo_as_baseline() -> None:
    record = {"routing": "budget_only", "task_value_profile": "difficulty"}

    enrich_routing_observability(record)

    assert record["routing_objective"] == "t1_value_efficiency"
    assert record["routing_policy_family"] == "bo_baseline"
