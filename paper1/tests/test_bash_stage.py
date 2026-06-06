from budgetflow.adapter.bash_stage import (
    bash_has_progress,
    classify_bash_stage,
    classify_routing_stage,
    command_counts_as_progress,
    extract_touched_file_paths,
)
from budgetflow.types import Stage


def test_bash_stage_validation():
    assert classify_bash_stage("pytest -x tests/test_foo.py", "") is Stage.VALIDATION
    assert classify_bash_stage("python -c \"print(1)\"", "") is Stage.VALIDATION


def test_bash_stage_repair():
    assert classify_bash_stage("sed -i 's/a/b/' src/foo.py", "") is Stage.REPAIR
    assert classify_bash_stage("perl -0777 -i -pe 's/a/b/g' src/foo.py", "") is Stage.REPAIR
    assert classify_bash_stage("apply_patch<<'PATCH'\n*** Begin Patch", "") is Stage.REPAIR


def test_bash_has_progress():
    assert bash_has_progress("sed -i 's/a/b/' src/foo.py") == (True, "repair_pattern")
    assert bash_has_progress("pytest -x tests/test_foo.py") == (True, "validation_pattern")
    assert bash_has_progress("grep -R pattern src") == (False, "none")
    assert bash_has_progress("") == (False, "none")


def test_read_only_command_in_repair_phase_does_not_reset_stagnation():
    assert command_counts_as_progress(
        "grep -n 'FilePathField' django/db/models/fields/__init__.py",
        agent_phase="edit_gold",
    ) == (False, "none")


def test_real_repair_command_counts_as_progress_even_without_phase():
    assert command_counts_as_progress(
        "sed -i 's/self.path/path/' django/db/models/fields/__init__.py",
        agent_phase=None,
    ) == (True, "repair_pattern")


def test_validation_phase_counts_as_progress_for_stop_loss():
    assert command_counts_as_progress(
        "",
        agent_phase="test",
    ) == (True, "validation_phase")


def test_bash_stage_localization():
    assert classify_bash_stage("grep -R pattern src", "") is Stage.LOCALIZATION
    assert classify_bash_stage("python setup.py install", "") is Stage.LOCALIZATION


def test_routing_stage_uses_agent_phase():
    assert classify_routing_stage("grep -R x", "", agent_phase="edit_gold") is Stage.REPAIR
    assert classify_routing_stage("grep -R x", "", agent_phase="test") is Stage.VALIDATION
    assert classify_routing_stage("grep -R x", "", agent_phase="explore") is Stage.LOCALIZATION


# --- extract_touched_file_paths ---

def test_extract_paths_none_or_empty():
    assert extract_touched_file_paths(None) == []
    assert extract_touched_file_paths("") == []
    assert extract_touched_file_paths("   ") == []


def test_extract_paths_from_sed():
    assert extract_touched_file_paths("sed -i 's/a/b/' src/foo.py") == ["src/foo.py"]


def test_extract_paths_from_cat():
    assert extract_touched_file_paths("cat src/foo.py | head -20") == ["src/foo.py"]


def test_extract_paths_from_grep():
    paths = extract_touched_file_paths("grep -Rn 'pattern' src/main.py tests/test_main.py")
    assert paths == ["src/main.py", "tests/test_main.py"]


def test_extract_paths_from_rg():
    assert extract_touched_file_paths("rg --json 'pattern' src/utils.py") == ["src/utils.py"]


def test_extract_paths_from_find():
    # find itself doesn't produce file paths as arguments typically
    assert extract_touched_file_paths("find . -name '*.py' -exec grep pattern {} \\;") == []


def test_extract_paths_from_ls():
    assert extract_touched_file_paths("ls -la src/") == []


def test_extract_paths_from_python():
    paths = extract_touched_file_paths("python -m pytest tests/test_foo.py")
    assert "tests/test_foo.py" in paths


def test_extract_paths_from_pytest():
    paths = extract_touched_file_paths("pytest tests/test_foo.py -x -v")
    assert "tests/test_foo.py" in paths


def test_extract_paths_mixed_commands():
    paths = extract_touched_file_paths("grep foo src/a.py && cat src/b.py")
    assert paths == ["src/a.py", "src/b.py"]


def test_extract_paths_with_quotes():
    assert extract_touched_file_paths("cat 'src/foo bar.py'") == ["src/foo bar.py"]


def test_extract_paths_dedup_sorted():
    paths = extract_touched_file_paths("cat src/b.py src/a.py src/b.py")
    assert paths == ["src/a.py", "src/b.py"]


def test_extract_paths_no_extension_skipped():
    assert extract_touched_file_paths("cat src/README") == []


def test_extract_paths_relative_and_absolute():
    paths = extract_touched_file_paths("python ./setup.py /abs/path/tool.py")
    assert "setup.py" in paths
    assert "/abs/path/tool.py" in paths


# --- extract_text_file_paths & extract_trace_file_paths ---

from budgetflow.adapter.bash_stage import extract_text_file_paths, extract_trace_file_paths


def test_text_extract_from_assistant_content():
    """GPT text_regex snippet with file paths in content head."""
    text = 'I will edit sympy/matrices/common.py to fix the Matrix class.'
    paths = extract_text_file_paths(text)
    assert "sympy/matrices/common.py" in paths


def test_text_extract_from_parser_input():
    """Parser input snippet containing file paths."""
    text = 'Found file: sympy/functions/elementary/hyperbolic.py at line 42'
    paths = extract_text_file_paths(text)
    assert "sympy/functions/elementary/hyperbolic.py" in paths


def test_text_extract_quoted_path():
    text = 'Edit "patch.txt" and apply to src/foo.py'
    paths = extract_text_file_paths(text)
    assert "patch.txt" in paths
    assert "src/foo.py" in paths


def test_text_extract_no_path_returns_empty():
    assert extract_text_file_paths(None) == []
    assert extract_text_file_paths("") == []
    assert extract_text_file_paths("No files here, just text.") == []


def test_text_extract_no_key_leak():
    """API key-like strings should not be extracted as paths."""
    text = 'Authorization: sk-or-v1-abc123def456/api.key format'
    paths = extract_text_file_paths(text)
    # "api.key" looks like a file but "sk-or-v1-abc123def456/api.key" is URL-like
    # Ensure no key leakage
    assert all(not p.startswith("sk-") for p in paths)


def test_trace_file_paths_combines_sources():
    """extract_trace_file_paths merges from all three sources."""
    paths = extract_trace_file_paths(
        bash_command="cat src/main.py",
        assistant_content_head="I will modify tests/test_main.py",
        parser_input_snippet="Found: src/utils.py",
    )
    assert "src/main.py" in paths
    assert "tests/test_main.py" in paths
    assert "src/utils.py" in paths
    assert len(paths) == 3


def test_trace_file_paths_dedup_across_sources():
    """Same path in multiple sources appears once."""
    paths = extract_trace_file_paths(
        bash_command="sed -i 's/a/b/' src/foo.py",
        assistant_content_head="The file src/foo.py needs changes",
        parser_input_snippet="src/foo.py is the target",
    )
    assert paths == ["src/foo.py"]


def test_trace_file_paths_bash_only():
    """When only bash_command is available (error path)."""
    paths = extract_trace_file_paths(bash_command="grep -R pattern src/main.py")
    assert paths == ["src/main.py"]


def test_trace_file_paths_none_sources():
    assert extract_trace_file_paths() == []
    assert extract_trace_file_paths(bash_command=None, assistant_content_head="", parser_input_snippet=None) == []


def test_extract_paths_url_excluded():
    assert extract_touched_file_paths(
        "curl https://example.com/script.py -o local.py"
    ) == ["local.py"]


def test_extract_paths_complex_command():
    paths = extract_touched_file_paths(
        "cd src && python -c 'import foo' && pytest tests/test_a.py tests/test_b.py -x"
    )
    assert "tests/test_a.py" in paths
    assert "tests/test_b.py" in paths


def test_extract_paths_no_command_yields_empty():
    # Already covered by None/empty test but explicit for caller contract
    assert extract_touched_file_paths(None) == []
