from __future__ import annotations

import json
from types import SimpleNamespace

from budgetflow.auto_budget import AutoBudgetEstimator


def _task(instance_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        instance_id=instance_id,
        repo="sympy/sympy",
        patch="diff --git a/x.py b/x.py\n+line\n",
        fail_to_pass=("tests/test_x.py::test_y",),
        pass_to_pass=(),
    )


def test_default_auto_budget_estimator_uses_clean_fallback_not_embedded_prior() -> None:
    estimate = AutoBudgetEstimator().estimate(_task("sympy__sympy-13480"))

    assert estimate.source == "global_fallback"
    assert estimate.confidence == "low"


def test_auto_budget_estimator_uses_explicit_prior_when_selected(tmp_path) -> None:
    prior = tmp_path / "prior.jsonl"
    prior.write_text(
        json.dumps({"instance_id": "sympy__sympy-13480", "total_cost": 0.07}) + "\n"
    )

    estimate = AutoBudgetEstimator.from_history(prior).estimate(_task("sympy__sympy-13480"))

    assert estimate.source == "explicit_prior_exact"
    assert estimate.estimated_cost == 0.07
