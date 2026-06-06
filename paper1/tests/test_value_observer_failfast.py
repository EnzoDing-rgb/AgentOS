"""Phase X: P0 value observer fail-fast tests."""

import json
import sys
import tempfile

import pytest

sys.path.insert(0, "src")


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset module-level state before each test."""
    import budgetflow.run_mini_swe_compare as mod
    mod._VALUE_LOOKUP = None
    mod._VALUE_PROFILE = "equal"
    mod._VALUE_MATRIX_PATH = None
    yield
    mod._VALUE_LOOKUP = None
    mod._VALUE_PROFILE = "equal"
    mod._VALUE_MATRIX_PATH = None


def _mod():
    import budgetflow.run_mini_swe_compare as mod
    return mod


def _make_matrix(profiles: dict) -> str:
    """Create a temporary value matrix JSON file. Returns path."""
    artifact = {"tasks": {}}
    for profile, tasks in profiles.items():
        for task_id, value in tasks.items():
            artifact["tasks"].setdefault(task_id, {}).setdefault("values", {})[profile] = value
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(artifact, f)
    return f.name


class TestFailFast:
    def test_equal_profile_no_matrix_ok(self):
        """--value-profile=equal without --value-matrix is always OK."""
        mod = _mod()
        mod._init_value_observability(value_profile="equal", value_matrix_path=None)
        record = mod._enrich_record_with_value({"instance_id": "test", "harness_resolved": True, "task_cost": 0.1})
        assert record["value_source"] == "default_equal"
        assert record["task_value"] == 1.0

    def test_non_equal_without_matrix_fails_init(self):
        """--value-profile=difficulty without --value-matrix leaves _VALUE_LOOKUP=None."""
        mod = _mod()
        mod._init_value_observability(value_profile="difficulty", value_matrix_path=None)
        assert mod._VALUE_LOOKUP is None

    def test_non_equal_with_valid_matrix_loads(self):
        """Valid matrix with correct profile should load task values."""
        mod = _mod()
        path = _make_matrix({"discriminative_rarity": {"sympy__sympy-13480": 0.1234}})
        mod._init_value_observability(value_profile="discriminative_rarity", value_matrix_path=path)
        assert mod._VALUE_LOOKUP is not None
        assert mod._VALUE_LOOKUP["sympy__sympy-13480"] == 0.1234

    def test_non_equal_missing_task_fails_enrich(self):
        """Missing task in matrix for non-equal profile must raise SystemExit."""
        mod = _mod()
        path = _make_matrix({"difficulty": {"sympy__sympy-99999": 0.5}})
        mod._init_value_observability(value_profile="difficulty", value_matrix_path=path)
        with pytest.raises(SystemExit, match="FATAL"):
            mod._enrich_record_with_value({"instance_id": "sympy__sympy-13480", "harness_resolved": True, "task_cost": 0.1})

    def test_legacy_schema_still_works(self):
        """Legacy matrix → profile → instance_id schema should work."""
        mod = _mod()
        artifact = {"matrix": {"difficulty": {"sympy__sympy-13480": {"value": 0.66}}}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(artifact, f)
            path = f.name
        mod._init_value_observability(value_profile="difficulty", value_matrix_path=path)
        assert mod._VALUE_LOOKUP is not None
        assert mod._VALUE_LOOKUP["sympy__sympy-13480"] == 0.66

    def test_non_equal_profile_not_in_matrix(self):
        """Requesting a profile not in the matrix leaves _VALUE_LOOKUP=None (CLI checks)."""
        mod = _mod()
        path = _make_matrix({"some_other_profile": {"sympy__sympy-13480": 0.5}})
        mod._init_value_observability(value_profile="difficulty", value_matrix_path=path)
        assert mod._VALUE_LOOKUP is None

    def test_enrich_adds_all_value_fields(self):
        """_enrich_record_with_value must add all 6 value observability fields."""
        mod = _mod()
        path = _make_matrix({"difficulty": {"sympy__sympy-13480": 0.0662}})
        mod._init_value_observability(value_profile="difficulty", value_matrix_path=path)
        record = mod._enrich_record_with_value({
            "instance_id": "sympy__sympy-13480",
            "harness_resolved": True,
            "task_cost": 0.1,
        })
        assert record["task_value_profile"] == "difficulty"
        assert record["task_value"] == 0.0662
        assert record["resolved_value"] == 0.0662
        assert record["value_source"] == "value_matrix"
        assert record["value_matrix_artifact"] == path
        assert record["resolved_value_per_dollar"] > 0

    def test_unresolved_task_has_zero_resolved_value(self):
        """Unresolved tasks should have resolved_value=0 regardless of task_value."""
        mod = _mod()
        path = _make_matrix({"difficulty": {"sympy__sympy-16988": 0.2879}})
        mod._init_value_observability(value_profile="difficulty", value_matrix_path=path)
        record = mod._enrich_record_with_value({
            "instance_id": "sympy__sympy-16988",
            "harness_resolved": False,
            "task_cost": 0.5,
        })
        assert record["task_value"] == 0.2879
        assert record["resolved_value"] == 0.0
        assert record["resolved_value_per_dollar"] == 0.0
