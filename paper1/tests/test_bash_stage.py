from budgetflow.adapter.bash_stage import classify_bash_stage
from budgetflow.types import Stage


def test_bash_stage_validation():
    assert classify_bash_stage("pytest -x tests/test_foo.py", "") is Stage.VALIDATION


def test_bash_stage_repair():
    assert classify_bash_stage("sed -i 's/a/b/' src/foo.py", "") is Stage.REPAIR


def test_bash_stage_localization():
    assert classify_bash_stage("grep -R pattern src", "") is Stage.LOCALIZATION
