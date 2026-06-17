from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from budgetflow.adapters import SwebenchTaskAdapter
from budgetflow.auto_budget import AutoBudgetEstimator, CostTaskFeatures


def _task(instance_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        instance_id=instance_id,
        repo="sympy/sympy",
        patch="diff --git a/x.py b/x.py\n+line\n",
        fail_to_pass=("tests/test_x.py::test_y",),
        pass_to_pass=(),
    )


def test_default_auto_budget_estimator_uses_clean_fallback_not_embedded_prior() -> None:
    estimate = AutoBudgetEstimator(feature_adapter=SwebenchTaskAdapter()).estimate(_task("sympy__sympy-13480"))

    assert estimate.source == "global_fallback"
    assert estimate.confidence == "low"


def test_auto_budget_estimator_uses_explicit_prior_when_selected(tmp_path) -> None:
    prior = tmp_path / "prior.jsonl"
    prior.write_text(
        json.dumps({"instance_id": "sympy__sympy-13480", "total_cost": 0.07}) + "\n"
    )

    estimate = AutoBudgetEstimator.from_history(prior, feature_adapter=SwebenchTaskAdapter()).estimate(_task("sympy__sympy-13480"))

    assert estimate.source == "explicit_prior_exact"
    assert estimate.estimated_cost == 0.07


def test_auto_budget_estimator_requires_feature_adapter() -> None:
    with pytest.raises(TypeError, match="CostFeatureAdapter"):
        AutoBudgetEstimator().estimate(_task("sympy__sympy-13480"))


def test_auto_budget_estimator_consumes_standard_cost_features_not_raw_task_fields() -> None:
    class Adapter:
        def cost_features(self, task: object) -> CostTaskFeatures:
            return CostTaskFeatures(
                instance_id="custom-task",
                repo="custom/repo",
                patch_lines=3,
                f2p_count=1,
                p2p_count=0,
            )

    estimate = AutoBudgetEstimator(feature_adapter=Adapter()).estimate(object())

    assert estimate.instance_id == "custom-task"
    assert estimate.source == "global_fallback"
    assert estimate.features["patch_lines"] == 3


def test_swebench_task_adapter_does_not_embed_repo_cost_floors() -> None:
    task = SimpleNamespace(
        instance_id="django__django-10924",
        repo="django/django",
        patch="diff --git a/x.py b/x.py\n+line\n",
        fail_to_pass=("tests/test_x.py::test_y",),
        pass_to_pass=(),
    )

    features = SwebenchTaskAdapter().cost_features(task)

    assert features.repo == "django/django"
    assert features.cost_floor == 0.0
