from budgetflow.adapter.bash_stage import bash_has_progress, classify_bash_stage, classify_routing_stage
from budgetflow.types import Stage


def test_bash_stage_validation():
    assert classify_bash_stage("pytest -x tests/test_foo.py", "") is Stage.VALIDATION
    assert classify_bash_stage("python -c \"print(1)\"", "") is Stage.VALIDATION


def test_bash_stage_repair():
    assert classify_bash_stage("sed -i 's/a/b/' src/foo.py", "") is Stage.REPAIR
    assert classify_bash_stage("perl -0777 -i -pe 's/a/b/g' src/foo.py", "") is Stage.REPAIR
    assert classify_bash_stage("apply_patch<<'PATCH'\n*** Begin Patch", "") is Stage.REPAIR


def test_bash_has_progress():
    assert bash_has_progress("sed -i 's/a/b/' src/foo.py") is True
    assert bash_has_progress("pytest -x tests/test_foo.py") is True
    assert bash_has_progress("grep -R pattern src") is False
    assert bash_has_progress("") is False


def test_bash_stage_localization():
    assert classify_bash_stage("grep -R pattern src", "") is Stage.LOCALIZATION
    assert classify_bash_stage("python setup.py install", "") is Stage.LOCALIZATION


def test_routing_stage_uses_agent_phase():
    assert classify_routing_stage("grep -R x", "", agent_phase="edit_gold") is Stage.REPAIR
    assert classify_routing_stage("grep -R x", "", agent_phase="test") is Stage.VALIDATION
    assert classify_routing_stage("grep -R x", "", agent_phase="explore") is Stage.LOCALIZATION
