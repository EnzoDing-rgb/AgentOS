from budgetflow.run_mini_swe_compare import _effective_policy_jobs


def test_multi_policy_jobs_auto_upgrade_from_serial_request():
    assert _effective_policy_jobs(requested_jobs=1, strategy_count=3) == 3


def test_default_jobs_matches_strategy_count():
    assert _effective_policy_jobs(requested_jobs=None, strategy_count=3) == 3


def test_single_policy_can_stay_serial():
    assert _effective_policy_jobs(requested_jobs=1, strategy_count=1) == 1


def test_requested_jobs_above_strategy_count_is_preserved():
    assert _effective_policy_jobs(requested_jobs=5, strategy_count=3) == 5
