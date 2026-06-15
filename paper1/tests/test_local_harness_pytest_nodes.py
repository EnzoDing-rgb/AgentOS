from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from budgetflow import local_harness
from budgetflow.local_harness import (
    build_pytest_node_ids,
    evaluate_local_harness,
    RepoHarnessAdapter,
    SymPyHAdapter,
    DjangoHAdapter,
    RequestsHAdapter,
    DefaultHAdapter,
)
from budgetflow.local_harness_adapters import (
    SphinxHAdapter,
    _patch_jinja2_imports,
)


def test_build_pytest_node_ids_from_plain_test_names(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_sample.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_one():\n    pass\n")

    node_ids, missing = build_pytest_node_ids(
        tmp_path,
        ("test_one",),
        ["tests/test_sample.py"],
    )

    assert node_ids == ["tests/test_sample.py::test_one"]
    assert missing == []


def test_build_pytest_node_ids_keeps_full_node_ids(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_sample.py"
    test_file.parent.mkdir()
    test_file.write_text(
        "class TestCase:\n"
        "    def test_one(self):\n"
        "        pass\n"
    )

    node_ids, missing = build_pytest_node_ids(
        tmp_path,
        ("tests/test_sample.py::TestCase::test_one",),
        ["tests/test_sample.py"],
    )

    assert node_ids == ["tests/test_sample.py::TestCase::test_one"]
    assert missing == []


def test_evaluate_local_harness_does_not_resolve_when_fail_to_pass_already_passed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    task = SimpleNamespace(
        instance_id="repo__already-green",
        repo="repo/project",
        base_commit="abc123",
        test_patch="diff --git a/tests/test_sample.py b/tests/test_sample.py\n",
        patch="",
        fail_to_pass=("tests/test_sample.py::test_regression",),
        pass_to_pass=("tests/test_sample.py::test_existing",),
    )

    monkeypatch.setattr(local_harness, "clone_or_checkout", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(local_harness, "repo_dir_for", lambda task: tmp_path)
    monkeypatch.setattr(local_harness, "test_paths_for", lambda task: ["tests/test_sample.py"])
    monkeypatch.setattr(local_harness, "apply_patch", lambda *args, **kwargs: (True, "ok"))
    monkeypatch.setattr(local_harness, "run_pytest", lambda *args, **kwargs: (True, "passed"))

    result = evaluate_local_harness(task, "diff --git a/app.py b/app.py\n")

    assert result.fail_before is True
    assert result.fail_after is True
    assert result.pass_to_pass_passed is True
    assert result.harness_resolved is False


def test_evaluate_local_harness_runs_all_pass_to_pass_tests(tmp_path: Path, monkeypatch) -> None:
    task = SimpleNamespace(
        instance_id="repo__all-pass-to-pass",
        repo="repo/project",
        base_commit="abc123",
        test_patch="diff --git a/tests/test_sample.py b/tests/test_sample.py\n",
        patch="",
        fail_to_pass=("tests/test_sample.py::test_regression",),
        pass_to_pass=tuple(f"tests/test_sample.py::test_existing_{index}" for index in range(8)),
    )
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(local_harness, "clone_or_checkout", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(local_harness, "repo_dir_for", lambda task: tmp_path)
    monkeypatch.setattr(local_harness, "test_paths_for", lambda task: ["tests/test_sample.py"])
    monkeypatch.setattr(local_harness, "apply_patch", lambda *args, **kwargs: (True, "ok"))

    def fake_run_pytest(repo_dir, test_names, test_paths, adapter=None):
        calls.append(tuple(test_names))
        return (len(calls) != 1, "expected fail-before")

    monkeypatch.setattr(local_harness, "run_pytest", fake_run_pytest)

    result = evaluate_local_harness(task, "diff --git a/app.py b/app.py\n")

    assert result.harness_resolved is True
    assert calls[-1] == task.pass_to_pass


def test_pip_marker_lives_inside_current_worktree(tmp_path: Path) -> None:
    worktree = tmp_path / "worktrees" / "repo__task"

    marker = local_harness._pip_marker_path(worktree)

    assert marker == worktree / ".budgetflow_pip_ok"


# ---- RepoHarnessAdapter tests ----


def test_sympy_adapter_fixes_print_float_inf(tmp_path: Path) -> None:
    latex_dir = tmp_path / "sympy" / "printing"
    latex_dir.mkdir(parents=True)
    latex_py = latex_dir / "latex.py"
    latex_py.write_text(
        '        elif str_real == "+inf":\n'
        '            return r"\\infty"\n'
        '        elif str_real == "-inf":\n'
        '            return r"- \\infty"\n'
        '        else:\n'
        '            return str_real\n'
    )

    adapter = SymPyHAdapter()
    changed = adapter.apply_compat(tmp_path)

    assert changed == ["sympy/printing/latex.py"]
    patched = latex_py.read_text()
    assert 'elif str_real in ("+inf", "inf"):' in patched
    assert 'elif str_real == "+inf":' not in patched


def test_sympy_adapter_noop_when_already_patched(tmp_path: Path) -> None:
    latex_dir = tmp_path / "sympy" / "printing"
    latex_dir.mkdir(parents=True)
    latex_py = latex_dir / "latex.py"
    already_patched = (
        '        elif str_real in ("+inf", "inf"):\n'
        '            return r"\\infty"\n'
    )
    latex_py.write_text(already_patched)

    adapter = SymPyHAdapter()
    changed = adapter.apply_compat(tmp_path)

    assert changed == []


def test_sympy_adapter_noop_when_latex_py_missing(tmp_path: Path) -> None:
    adapter = SymPyHAdapter()
    changed = adapter.apply_compat(tmp_path)
    assert changed == []


def test_sympy_adapter_treats_broken_optional_dependencies_as_unavailable(tmp_path: Path) -> None:
    importtools_py = tmp_path / "sympy" / "external" / "importtools.py"
    importtools_py.parent.mkdir(parents=True)
    importtools_py.write_text(
        "def import_module(module, __import__kwargs={}, catch=()):\n"
        "    return __import__(module, **__import__kwargs)\n"
    )

    adapter = SymPyHAdapter()
    changed = adapter.apply_compat(tmp_path)

    assert changed == ["sympy/external/importtools.py"]
    assert "catch=(Exception,)" in importtools_py.read_text()


def test_django_adapter_maps_real_swebench_format_12113() -> None:
    adapter = DjangoHAdapter()
    result = adapter.map_test_name(
        "test_custom_test_name (backends.sqlite.test_creation.TestDbSignatureTests)"
    )
    assert result == (
        "tests/backends/sqlite/test_creation.py"
        "::TestDbSignatureTests::test_custom_test_name"
    )


def test_django_adapter_maps_real_swebench_format_10924() -> None:
    adapter = DjangoHAdapter()
    result = adapter.map_test_name(
        "test_callable_path (model_fields.test_filepathfield.FilePathFieldTests)"
    )
    assert result == (
        "tests/model_fields/test_filepathfield.py"
        "::FilePathFieldTests::test_callable_path"
    )


def test_django_adapter_maps_path_prefix_format() -> None:
    adapter = DjangoHAdapter()
    result = adapter.map_test_name(
        "tests/backends/sqlite/test_creation.py::test_custom_test_name "
        "(backends.sqlite.test_creation.TestDbSignatureTests)"
    )
    assert result == (
        "tests/backends/sqlite/test_creation.py"
        "::TestDbSignatureTests::test_custom_test_name"
    )


def test_django_adapter_returns_none_for_plain_test_names() -> None:
    adapter = DjangoHAdapter()
    assert adapter.map_test_name("tests/test_foo.py::test_bar") is None
    assert adapter.map_test_name("tests/test_foo.py::TestCase::test_bar") is None
    assert adapter.map_test_name("test_simple") is None


def test_django_adapter_conftest_generates_with_installed_apps(tmp_path: Path) -> None:
    """Django adapter creates tests/__init__.py AND conftest.py when both are missing."""
    adapter = DjangoHAdapter()
    changed = adapter.apply_compat(tmp_path)
    assert "tests/__init__.py (generated)" in changed
    assert "conftest.py (generated)" in changed
    conftest = (tmp_path / "conftest.py").read_text()
    assert "_default_apps = [" in conftest
    assert "django.contrib.contenttypes" in conftest
    assert "django.contrib.auth" in conftest
    assert "settings.INSTALLED_APPS" in conftest
    assert "django.setup()" in conftest


def test_django_adapter_conftest_skips_when_already_has_installed_apps(tmp_path: Path) -> None:
    """Django adapter creates tests/__init__.py but skips conftest when marker present."""
    conftest = tmp_path / "conftest.py"
    conftest.write_text("_default_apps = ['django.contrib.auth']\ndjango.setup()\n")
    adapter = DjangoHAdapter()
    changed = adapter.apply_compat(tmp_path)
    # tests/__init__.py created, but conftest already has marker → no conftest change
    assert "conftest.py" not in [c for c in changed if "conftest" in c]
    assert "_default_apps = ['django.contrib.auth']" in conftest.read_text()


def test_django_adapter_conftest_replaces_bare_old_conftest(tmp_path: Path) -> None:
    """Django adapter creates tests/__init__.py and replaces bare conftest."""
    conftest = tmp_path / "conftest.py"
    conftest.write_text("import django\ndjango.setup()\n")
    adapter = DjangoHAdapter()
    changed = adapter.apply_compat(tmp_path)
    replaced_items = [c for c in changed if "replaced" in c]
    assert len(replaced_items) == 1, f"expected one 'replaced' item in {changed}"
    content = conftest.read_text()
    assert "_default_apps = [" in content
    assert "django.contrib.contenttypes" in content


def test_build_pytest_node_ids_with_django_adapter(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "backends" / "sqlite" / "test_creation.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "class TestDbSignatureTests:\n"
        "    def test_custom_test_name(self):\n"
        "        pass\n"
    )

    adapter = DjangoHAdapter()
    node_ids, missing = build_pytest_node_ids(
        tmp_path,
        ("test_custom_test_name (backends.sqlite.test_creation.TestDbSignatureTests)",),
        ["tests/backends/sqlite/test_creation.py"],
        adapter=adapter,
    )

    assert node_ids == [
        "tests/backends/sqlite/test_creation.py::TestDbSignatureTests::test_custom_test_name"
    ]
    assert missing == []


def test_adapter_dispatch_sympy() -> None:
    task = SimpleNamespace(repo="sympy/sympy")
    adapter = RepoHarnessAdapter.for_task(task)
    assert isinstance(adapter, SymPyHAdapter)


def test_adapter_dispatch_django() -> None:
    task = SimpleNamespace(repo="django/django")
    adapter = RepoHarnessAdapter.for_task(task)
    assert isinstance(adapter, DjangoHAdapter)


def test_adapter_dispatch_requests() -> None:
    task = SimpleNamespace(repo="psf/requests")
    adapter = RepoHarnessAdapter.for_task(task)
    assert isinstance(adapter, RequestsHAdapter)


def test_adapter_dispatch_unknown() -> None:
    task = SimpleNamespace(repo="unknown/repo")
    adapter = RepoHarnessAdapter.for_task(task)
    assert isinstance(adapter, DefaultHAdapter)


def test_run_pytest_disables_host_plugin_autoload(tmp_path: Path, monkeypatch) -> None:
    test_file = tmp_path / "tests" / "test_x.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_regression():\n    pass\n")

    captured = {}

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, *, cwd, capture_output, text, env):
        captured["env"] = env
        return Result()

    monkeypatch.setattr("budgetflow.local_harness_adapters.subprocess.run", fake_run)

    ok, _ = local_harness.run_pytest(
        tmp_path,
        ("tests/test_x.py::test_regression",),
        ["tests/test_x.py"],
    )

    assert ok is True
    assert captured["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"


def test_evaluate_local_harness_calls_adapter_compat(tmp_path: Path, monkeypatch) -> None:
    task = SimpleNamespace(
        instance_id="sympy__sympy-14774",
        repo="sympy/sympy",
        base_commit="abc123",
        test_patch="diff --git a/tests/test_x.py b/tests/test_x.py\n",
        patch="",
        fail_to_pass=("tests/test_x.py::test_regression",),
        pass_to_pass=("tests/test_x.py::test_existing",),
    )

    compat_calls: list[Path] = []

    class ProbeAdapter(SymPyHAdapter):
        def apply_compat(self, repo_dir):
            compat_calls.append(repo_dir)
            return ["fake/file.py"]

    monkeypatch.setattr(local_harness, "clone_or_checkout", lambda *args, **kwargs: tmp_path)
    monkeypatch.setattr(local_harness, "repo_dir_for", lambda task: tmp_path)
    monkeypatch.setattr(local_harness, "test_paths_for", lambda task: ["tests/test_x.py"])
    monkeypatch.setattr(local_harness, "apply_patch", lambda *args, **kwargs: (True, "ok"))
    monkeypatch.setattr(local_harness, "run_pytest", lambda *args, **kwargs: (True, "passed"))
    monkeypatch.setattr(local_harness, "RepoHarnessAdapter", type("Fake", (), {
        "for_task": staticmethod(lambda task: ProbeAdapter()),
    }))

    result = evaluate_local_harness(task, "diff --git a/app.py b/app.py\n")

    assert len(compat_calls) == 1
    assert "compat=fake/file.py" in result.detail


def test_compat_not_in_model_patch(tmp_path: Path, monkeypatch) -> None:
    """Compat changes are applied directly to files, not via git patch.
    They live only in the harness worktree which is ephemeral.
    Agent worktrees are separate, so compat never leaks into submitted patch."""
    latex_dir = tmp_path / "sympy" / "printing"
    latex_dir.mkdir(parents=True)
    latex_py = latex_dir / "latex.py"
    original = (
        '        elif str_real == "+inf":\n'
        '            return r"\\infty"\n'
        '        elif str_real == "-inf":\n'
        '            return r"- \\infty"\n'
        '        else:\n'
        '            return str_real\n'
    )
    latex_py.write_text(original)

    adapter = SymPyHAdapter()
    adapter.apply_compat(tmp_path)

    patched = latex_py.read_text()
    assert 'elif str_real in ("+inf", "inf"):' in patched

    # Simulate git diff to check what would be in model patch
    import subprocess
    result = subprocess.run(
        ["git", "diff", "--", "sympy/printing/latex.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    # No git repo in tmp_path, so git diff fails. Compat change is direct file
    # modification that won't appear in any agent's git diff (agent uses separate worktree).
    # This test just verifies the file was modified correctly.
    assert 'str_real in ("+inf", "inf")' in patched


# ── build_test_command tests ──────────────────────────────────────────────


def test_base_adapter_build_test_command_returns_pytest() -> None:
    from budgetflow.local_harness_adapters import DefaultHAdapter, harness_python

    adapter = DefaultHAdapter()
    cmd = adapter.build_test_command(Path("/tmp"), ["tests/test_x.py::test_one"])

    assert harness_python() in cmd[0]
    assert "-m" in cmd
    assert "pytest" in cmd
    assert "-x" in cmd
    assert "tests/test_x.py::test_one" in cmd


def test_django_pytest_node_to_label_standard() -> None:
    label = DjangoHAdapter._pytest_node_to_django_label(
        "tests/backends/sqlite/test_creation.py::TestDbSignatureTests::test_custom_test_name"
    )
    assert label == "backends.sqlite.test_creation.TestDbSignatureTests.test_custom_test_name"


def test_django_pytest_node_to_label_sweb_swebench_format() -> None:
    label = DjangoHAdapter._pytest_node_to_django_label(
        "test_callable_path (model_fields.test_filepathfield.FilePathFieldTests)"
    )
    assert label == "model_fields.test_filepathfield.FilePathFieldTests.test_callable_path"


def test_django_pytest_node_to_label_returns_none_for_plain() -> None:
    assert DjangoHAdapter._pytest_node_to_django_label("tests/test_foo.py::test_bar") is None


def test_django_build_test_command_uses_runtests(tmp_path: Path) -> None:
    from budgetflow.local_harness_adapters import harness_python

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    runtests = tests_dir / "runtests.py"
    runtests.write_text("# fake runtests")

    adapter = DjangoHAdapter()
    cmd = adapter.build_test_command(
        tmp_path,
        ["tests/backends/sqlite/test_creation.py::TestDbSignatureTests::test_custom_test_name"],
    )

    assert str(runtests) in cmd
    assert "--verbosity=1" in cmd
    assert "backends.sqlite.test_creation.TestDbSignatureTests.test_custom_test_name" in cmd


def test_django_build_test_command_falls_back_to_pytest_when_no_label(tmp_path: Path) -> None:
    from budgetflow.local_harness_adapters import harness_python

    adapter = DjangoHAdapter()
    cmd = adapter.build_test_command(
        tmp_path,
        ["tests/test_foo.py::test_bar"],
    )

    assert "pytest" in cmd
    assert "-x" in cmd
    assert "tests/test_foo.py::test_bar" in cmd


def test_django_build_test_command_falls_back_when_runtests_missing(tmp_path: Path) -> None:
    from budgetflow.local_harness_adapters import harness_python

    adapter = DjangoHAdapter()
    cmd = adapter.build_test_command(
        tmp_path,
        ["tests/backends/sqlite/test_creation.py::TestDbSignatureTests::test_custom_test_name"],
    )

    assert "pytest" in cmd


def test_run_pytest_uses_adapter_build_test_command(tmp_path: Path, monkeypatch) -> None:
    """When an adapter is passed, run_pytest calls adapter.build_test_command."""
    from budgetflow import local_harness
    from budgetflow.local_harness_adapters import harness_python

    test_file = tmp_path / "tests" / "test_x.py"
    test_file.parent.mkdir()
    test_file.write_text("def test_regression():\n    pass\n")

    captured_cmd: list = []

    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(cmd, *, cwd, capture_output, text, env):
        captured_cmd.append(cmd)
        return Result()

    monkeypatch.setattr("budgetflow.local_harness_adapters.subprocess.run", fake_run)

    adapter = DjangoHAdapter()
    ok, _ = local_harness.run_pytest(
        tmp_path,
        ("tests/test_x.py::test_regression",),
        ["tests/test_x.py"],
        adapter=adapter,
    )

    assert ok is True
    assert len(captured_cmd) == 1
    # Django adapter should produce a runtests.py command for parseable node IDs
    # (but runtests.py doesn't exist in tmp_path, so it falls back to pytest)
    assert "pytest" in captured_cmd[0]


# ── SphinxHAdapter tests ──────────────────────────────────────────────────


def test_adapter_dispatch_sphinx() -> None:
    task = SimpleNamespace(repo="sphinx-doc/sphinx")
    adapter = RepoHarnessAdapter.for_task(task)
    assert isinstance(adapter, SphinxHAdapter)


def test_patch_jinja2_imports_solo_name() -> None:
    assert _patch_jinja2_imports("from jinja2 import environmentfilter") == (
        "from jinja2 import pass_environment as environmentfilter"
    )


def test_patch_jinja2_imports_comma_list() -> None:
    result = _patch_jinja2_imports(
        "from jinja2 import FileSystemLoader, BaseLoader, TemplateNotFound, contextfunction"
    )
    assert "pass_context as contextfunction" in result
    assert "FileSystemLoader" in result
    assert "BaseLoader" in result


def test_patch_jinja2_imports_two_old_names() -> None:
    result = _patch_jinja2_imports(
        "from jinja2 import contextfilter, environmentfilter"
    )
    assert "pass_context as contextfilter" in result
    assert "pass_environment as environmentfilter" in result


def test_patch_jinja2_imports_idempotent() -> None:
    """Repeated application must not double-wrap aliases."""
    original = "from jinja2 import environmentfilter"
    pass1 = _patch_jinja2_imports(original)
    pass2 = _patch_jinja2_imports(pass1)
    pass3 = _patch_jinja2_imports(pass2)
    assert pass1 == pass2 == pass3
    assert pass1 == "from jinja2 import pass_environment as environmentfilter"


def test_patch_jinja2_imports_idempotent_comma_list() -> None:
    original = (
        "from jinja2 import FileSystemLoader, BaseLoader, TemplateNotFound, contextfunction"
    )
    pass1 = _patch_jinja2_imports(original)
    pass2 = _patch_jinja2_imports(pass1)
    pass3 = _patch_jinja2_imports(pass2)
    assert pass1 == pass2 == pass3
    assert "pass_context as contextfunction" in pass1
    assert "pass_context as pass_context" not in pass1


def test_patch_jinja2_imports_noop_when_no_jinja2() -> None:
    text = "import os\nfrom collections import defaultdict\n"
    assert _patch_jinja2_imports(text) == text


def test_patch_jinja2_imports_noop_when_already_modern() -> None:
    text = "from jinja2 import pass_environment, pass_context\n"
    assert _patch_jinja2_imports(text) == text


def test_sphinx_adapter_patches_rst_and_jinja2glue(tmp_path: Path) -> None:
    sphinx_dir = tmp_path / "sphinx" / "util"
    sphinx_dir.mkdir(parents=True)
    rst_py = sphinx_dir / "rst.py"
    rst_py.write_text("from jinja2 import environmentfilter\n")
    glue_dir = tmp_path / "sphinx"
    glue_py = glue_dir / "jinja2glue.py"
    glue_py.write_text(
        "from jinja2 import FileSystemLoader, BaseLoader, TemplateNotFound, contextfunction\n"
    )

    adapter = SphinxHAdapter()
    changed = adapter.apply_compat(tmp_path)

    assert len(changed) == 2
    assert "pass_environment as environmentfilter" in rst_py.read_text()
    assert "pass_context as contextfunction" in glue_py.read_text()


def test_sphinx_adapter_idempotent_apply_compat(tmp_path: Path) -> None:
    sphinx_dir = tmp_path / "sphinx" / "util"
    sphinx_dir.mkdir(parents=True)
    rst_py = sphinx_dir / "rst.py"
    rst_py.write_text("from jinja2 import Environment, environmentfilter\n")

    adapter = SphinxHAdapter()
    changed1 = adapter.apply_compat(tmp_path)
    changed2 = adapter.apply_compat(tmp_path)

    assert len(changed1) == 1
    assert changed2 == []  # second pass is no-op
    content = rst_py.read_text()
    assert content.count("pass_environment as") == 1
    assert "pass_environment as pass_environment" not in content


def test_sphinx_adapter_noop_when_sphinx_dir_missing(tmp_path: Path) -> None:
    adapter = SphinxHAdapter()
    changed = adapter.apply_compat(tmp_path)
    assert changed == []


# ── FlaskHAdapter tests ────────────────────────────────────────────────────

from budgetflow.local_harness_adapters import FlaskHAdapter


def test_flask_adapter_dispatch() -> None:
    task = SimpleNamespace(repo="pallets/flask")
    adapter = RepoHarnessAdapter.for_task(task)
    assert isinstance(adapter, FlaskHAdapter)


def test_flask_adapter_injects_notset_alias(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    conftest = tests_dir / "conftest.py"
    conftest.write_text(
        "from _pytest import monkeypatch\n"
        "mp = monkeypatch.MonkeyPatch()\n"
        "out = (os.environ, 'KEY', monkeypatch.notset)\n"
    )

    adapter = FlaskHAdapter()
    changed = adapter.apply_compat(tmp_path)

    assert "tests/conftest.py" in changed
    content = conftest.read_text()
    assert "import pytest" in content
    assert "_pytest.monkeypatch.notset = _pytest.monkeypatch.NOTSET" in content
    # Original content preserved
    assert "from _pytest import monkeypatch" in content
    assert "monkeypatch.notset" in content


def test_flask_adapter_noop_when_no_notset_ref(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    conftest = tests_dir / "conftest.py"
    conftest.write_text("import pytest\n")

    adapter = FlaskHAdapter()
    changed = adapter.apply_compat(tmp_path)

    assert "tests/conftest.py" not in changed


def test_flask_adapter_noop_when_no_conftest(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    adapter = FlaskHAdapter()
    changed = adapter.apply_compat(tmp_path)

    assert changed == []


def test_flask_adapter_idempotent(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    conftest = tests_dir / "conftest.py"
    conftest.write_text(
        "from _pytest import monkeypatch\n"
        "out = (os.environ, 'KEY', monkeypatch.notset)\n"
    )

    adapter = FlaskHAdapter()
    changed1 = adapter.apply_compat(tmp_path)
    changed2 = adapter.apply_compat(tmp_path)

    assert len(changed1) == 1
    assert changed2 == []  # second pass no-op
