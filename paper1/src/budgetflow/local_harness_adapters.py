from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from .console_log import _BRIGHT_GREEN, paint, tag
from .harness_contamination import isolated_repo_pythonpath
from .runtime import get_runtime_root


class RepoHarnessAdapter:
    """Per-repo local-harness adapter.

    Adapters keep repository-specific evaluation quirks out of the shared
    harness flow. They may patch the ephemeral harness worktree or translate SWE-bench
    test names into pytest node ids.
    """

    repo_slug: str

    def apply_compat(self, repo_dir: Path) -> list[str]:
        return []

    def map_test_name(self, raw_name: str) -> str | None:
        return None

    def pytest_env(self) -> dict[str, str]:
        return {}

    def build_test_command(self, repo_dir: Path, test_node_ids: list[str]) -> list[str]:
        """Return the shell command to run *test_node_ids*.

        Default implementation uses pytest.  Adapters for repositories whose
        test suite needs a custom runner (e.g. Django's DiscoverRunner) override
        this method.
        """
        return [harness_python(), "-m", "pytest", "-x"] + test_node_ids

    @staticmethod
    def for_task(task) -> "RepoHarnessAdapter":
        repo = getattr(task, "repo", "")
        slug = repo.replace("/", "__") if repo else ""
        if slug == "sympy__sympy":
            return SymPyHAdapter()
        if slug == "django__django":
            return DjangoHAdapter()
        if slug == "psf__requests":
            return RequestsHAdapter()
        if slug == "sphinx-doc__sphinx":
            return SphinxHAdapter()
        if slug == "pallets__flask":
            return FlaskHAdapter()
        return DefaultHAdapter()


class SymPyHAdapter(RepoHarnessAdapter):
    repo_slug = "sympy__sympy"

    def apply_compat(self, repo_dir: Path) -> list[str]:
        changed: list[str] = []

        latex_py = repo_dir / "sympy" / "printing" / "latex.py"
        if latex_py.is_file():
            original = latex_py.read_text(encoding="utf-8", errors="ignore")
            patched = original.replace(
                'elif str_real == "+inf":\n            return r"\\infty"',
                'elif str_real in ("+inf", "inf"):\n            return r"\\infty"',
            )
            if patched != original:
                latex_py.write_text(patched)
                changed.append("sympy/printing/latex.py")

        pytest_py = repo_dir / "sympy" / "utilities" / "pytest.py"
        if pytest_py.is_file():
            original = pytest_py.read_text(encoding="utf-8", errors="ignore")
            if "py.test.mark." in original:
                patched = original.replace("py.test.mark.xfail", "pytest.mark.xfail")
                patched = patched.replace("py.test.mark.slow", "pytest.mark.slow")
                if "import pytest" not in patched:
                    patched = patched.replace(
                        "try:\n    import py\n",
                        "import pytest\n\ntry:\n    import py\n",
                        1,
                    )
                if patched != original:
                    pytest_py.write_text(patched)
                    changed.append("sympy/utilities/pytest.py")

        importtools_py = repo_dir / "sympy" / "external" / "importtools.py"
        if importtools_py.is_file():
            original = importtools_py.read_text(encoding="utf-8", errors="ignore")
            patched = original.replace(
                "__import__kwargs={}, catch=()):",
                "__import__kwargs={}, catch=(Exception,)):",
            )
            if patched != original:
                importtools_py.write_text(patched)
                changed.append("sympy/external/importtools.py")

        return changed


_DJANGO_TEST_NAME_RE = re.compile(r"^(\w+)\s+\((.+)\.(\w+)\)$")


_DJANGO_CONFTEST_INSTALLED_APPS = """\
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.test_sqlite')

import django
from django.conf import settings

# tests/test_sqlite.py does not set INSTALLED_APPS.  The Django test runner
# (tests/runtests.py) adds contrib apps dynamically, but pytest bypasses it.
# Without INSTALLED_APPS any test that imports a Django Model (directly or
# transitively) raises "Model class ... doesn't declare an explicit app_label
# and isn't in an application in INSTALLED_APPS".  We add the standard contrib
# set here so the harness can collect and run Django tests with pytest alone.
_default_apps = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]
if not settings.INSTALLED_APPS:
    settings.INSTALLED_APPS = _default_apps

# Older Django versions of test_sqlite.py omit the NAME key from DATABASES.
# The official test runner supplies it via runtests.py; pytest does not.
# Without NAME, any TestCase (database-requiring test) raises
# ImproperlyConfigured: "Please supply the NAME value."
for _db_alias in ('default', 'other'):
    _db = settings.DATABASES.get(_db_alias)
    if _db and not _db.get('NAME'):
        _db['NAME'] = ':memory:'

django.setup()

# Create test-database tables so TestCase subclasses can run.  The Django test
# runner (runtests.py) does this automatically; pytest alone skips it, which
# causes "no such table: <table>" failures for any test that needs the DB.
# We only run migrate when the default database is an in-memory SQLite file —
# never against a persistent database.
from django.core.management import call_command
if settings.DATABASES.get('default', {}).get('NAME') == ':memory:':
    call_command('migrate', verbosity=0, interactive=False, run_syncdb=True)
"""

# Marker substring used to detect whether a conftest.py already contains the
# INSTALLED_APPS bootstrap (avoid double-patching).
_DJANGO_CONFTEST_MARKER = "_default_apps = ["


class DjangoHAdapter(RepoHarnessAdapter):
    repo_slug = "django__django"

    def apply_compat(self, repo_dir: Path) -> list[str]:
        changed: list[str] = []

        # Ensure tests/ is a package so Django's runtests.py can import
        # test settings modules (e.g. tests.test_sqlite) on Django versions
        # that don't ship tests/__init__.py.
        tests_init = repo_dir / "tests" / "__init__.py"
        if not tests_init.exists():
            tests_init.parent.mkdir(parents=True, exist_ok=True)
            tests_init.write_text("# BudgetFlow compat: make tests a Python package\n")
            changed.append("tests/__init__.py (generated)")

        conftest = repo_dir / "conftest.py"
        if not conftest.is_file():
            conftest.write_text(_DJANGO_CONFTEST_INSTALLED_APPS)
            changed.append("conftest.py (generated)")
            return changed
        original = conftest.read_text(encoding="utf-8", errors="ignore")
        if _DJANGO_CONFTEST_MARKER in original:
            return changed
        conftest.write_text(_DJANGO_CONFTEST_INSTALLED_APPS)
        changed.append("conftest.py (replaced: added INSTALLED_APPS)")
        return changed

    def pytest_env(self) -> dict[str, str]:
        return {"DJANGO_SETTINGS_MODULE": "tests.test_sqlite"}

    def map_test_name(self, raw_name: str) -> str | None:
        match = _DJANGO_TEST_NAME_RE.match(raw_name)
        if match:
            test_name, module_path, class_name = match.group(1), match.group(2), match.group(3)
            file_path = f"tests/{module_path.replace('.', '/')}.py"
            return f"{file_path}::{class_name}::{test_name}"
        path_match = re.match(r"^(.+\.py)::(\w+)\s+\(.*?\.(\w+)\)$", raw_name)
        if path_match:
            return f"{path_match.group(1)}::{path_match.group(3)}::{path_match.group(2)}"
        return None

    @staticmethod
    def _pytest_node_to_django_label(node_id: str) -> str | None:
        """Convert a pytest node id to a Django dotted test label.

        ``tests/backends/sqlite/test_creation.py::TestDbSignatureTests::test_custom_test_name``
        becomes ``backends.sqlite.test_creation.TestDbSignatureTests.test_custom_test_name``.
        Returns *None* when *node_id* is not a recognised format.
        """
        m = re.match(r"^tests/(.+)\.py::(.+)::(.+)$", node_id)
        if m:
            module_path, class_name, test_name = m.group(1), m.group(2), m.group(3)
            return f"{module_path.replace('/', '.')}.{class_name}.{test_name}"
        m = _DJANGO_TEST_NAME_RE.match(node_id)
        if m:
            test_name, module_path, class_name = m.group(1), m.group(2), m.group(3)
            return f"{module_path}.{class_name}.{test_name}"
        return None

    def build_test_command(self, repo_dir: Path, test_node_ids: list[str]) -> list[str]:
        """Use Django's ``tests/runtests.py`` so inline test models are registered.

        Falls back to pytest when *test_node_ids* cannot be converted to
        Django test labels or when ``tests/runtests.py`` is missing.
        """
        labels: list[str] = []
        for nid in test_node_ids:
            label = self._pytest_node_to_django_label(nid)
            if label:
                labels.append(label)
        if not labels:
            return super().build_test_command(repo_dir, test_node_ids)
        runtests = repo_dir / "tests" / "runtests.py"
        if runtests.is_file():
            return [harness_python(), str(runtests), "--verbosity=1", "--failfast"] + labels
        return super().build_test_command(repo_dir, test_node_ids)


class RequestsHAdapter(RepoHarnessAdapter):
    repo_slug = "psf__requests"


# Jinja2 >= 3.1 removed environmentfilter/contextfunction/contextfilter/
# evalcontextfilter/evalcontextfunction.  Older Sphinx versions import
# these by name.  We replace them with the new names via ``as`` aliases
# so the rest of the module's usage stays valid.
_JINJA2_RENAMES = {
    "environmentfilter": "pass_environment",
    "contextfunction": "pass_context",
    "contextfilter": "pass_context",
    "evalcontextfilter": "pass_eval_context",
    "evalcontextfunction": "pass_eval_context",
}

_IMPORTANT_PYTEST_LOG_MARKERS = (
    "ModuleNotFoundError:",
    "ImportError:",
    "ConftestImportFailure",
    "ImportError while loading conftest",
    "ExtensionError:",
    "numpy.dtype size changed",
    "_ARRAY_API not found",
)


def _compact_pytest_output(output: str, *, tail_chars: int = 2000) -> str:
    if len(output) <= tail_chars:
        return output
    important_lines = [
        line for line in output.splitlines()
        if any(marker in line for marker in _IMPORTANT_PYTEST_LOG_MARKERS)
    ]
    tail = output[-tail_chars:]
    if not important_lines:
        return tail
    prefix = "\n".join(dict.fromkeys(important_lines[:12]))
    if prefix and prefix not in tail:
        return prefix + "\n...\n" + tail
    return tail


def _patch_jinja2_imports(text: str) -> str:
    """Replace removed Jinja2 names with their 3.1+ equivalents.

    Idempotent: the negative lookbehind skips names that already appear
    after ``as`` (i.e. already-patched aliases).
    """
    import re
    for old_name, new_name in _JINJA2_RENAMES.items():
        text = re.sub(
            rf"(from\s+jinja2\s+import\s+.*?)(?<!\bas\s)\b{old_name}\b(.*)",
            rf"\1{new_name} as {old_name}\2",
            text,
        )
    return text


class SphinxHAdapter(RepoHarnessAdapter):
    repo_slug = "sphinx-doc__sphinx"

    def apply_compat(self, repo_dir: Path) -> list[str]:
        changed: list[str] = []
        sphinx_pkg = repo_dir / "sphinx"
        if sphinx_pkg.is_dir():
            for py_file in sphinx_pkg.rglob("*.py"):
                original = py_file.read_text(encoding="utf-8", errors="ignore")
                patched = _patch_jinja2_imports(original)
                if patched != original:
                    py_file.write_text(patched)
                    changed.append(str(py_file.relative_to(repo_dir)))
        return changed


class FlaskHAdapter(RepoHarnessAdapter):
    repo_slug = "pallets__flask"

    def apply_compat(self, repo_dir: Path) -> list[str]:
        """Patch Flask tests for pytest >= 7.2 compatibility.

        pytest 7.2 removed ``monkeypatch.notset`` and ``_pytest.monkeypatch.notset``.
        Older Flask test suites import these directly. We inject a compat sentinel
        so conftest fixtures and test modules import correctly.
        """
        changed: list[str] = []

        # Patch conftest.py: replace ``monkeypatch.notset`` with ``_NOTSET`` sentinel
        conftest = repo_dir / "tests" / "conftest.py"
        if conftest.is_file():
            original = conftest.read_text(encoding="utf-8", errors="ignore")
            if "monkeypatch.notset" in original and "_pytest.monkeypatch.notset = _pytest.monkeypatch.NOTSET" not in original:
                patched = (
                    "import pytest\n"
                    "import _pytest.monkeypatch\n"
                    "if not hasattr(_pytest.monkeypatch, 'notset'):\n"
                    "    _pytest.monkeypatch.notset = _pytest.monkeypatch.NOTSET\n"
                    + original
                )
                conftest.write_text(patched)
                changed.append("tests/conftest.py")

        # Patch test files that import notset directly
        for py_file in sorted((repo_dir / "tests").rglob("*.py")):
            original = py_file.read_text(encoding="utf-8", errors="ignore")
            if "from _pytest.monkeypatch import notset" in original and "except ImportError:\n    notset = object()" not in original:
                patched = original.replace(
                    "from _pytest.monkeypatch import notset",
                    "try:\n    from _pytest.monkeypatch import notset\nexcept ImportError:\n    notset = object()",
                )
                py_file.write_text(patched)
                changed.append(str(py_file.relative_to(repo_dir)))

        return changed


class DefaultHAdapter(RepoHarnessAdapter):
    repo_slug = ""


_COLLECTIONS_ABC = frozenset(
    {
        "Mapping",
        "MutableMapping",
        "MutableSet",
        "Iterable",
        "Hashable",
        "Callable",
        "Sequence",
        "Container",
        "Iterator",
        "Generator",
    }
)


def harness_python() -> str:
    return os.environ.get("BUDGETFLOW_HARNESS_PYTHON", sys.executable)


def _split_collections_import_line(line: str) -> list[str] | None:
    match = re.match(r"^(\s*)from collections import (.+)$", line)
    if not match:
        return None
    indent, tail = match.group(1), match.group(2).strip()
    if tail.startswith("("):
        return None
    names = [part.strip() for part in tail.split(",") if part.strip()]
    abc = [name for name in names if name in _COLLECTIONS_ABC]
    std = [name for name in names if name not in _COLLECTIONS_ABC]
    if not abc:
        return None
    out: list[str] = []
    if std:
        out.append(f"{indent}from collections import {', '.join(std)}")
    out.append(f"{indent}from collections.abc import {', '.join(abc)}")
    return out


def _split_collections_import_block(block_lines: list[str]) -> list[str] | None:
    indent = re.match(r"^(\s*)", block_lines[0]).group(1)
    joined = " ".join(line.strip() for line in block_lines)
    inner = re.search(r"from collections import \((.+)\)", joined, re.DOTALL)
    if not inner:
        return None
    names = [part.strip() for part in inner.group(1).replace("\n", " ").split(",") if part.strip()]
    abc = [name for name in names if name in _COLLECTIONS_ABC]
    std = [name for name in names if name not in _COLLECTIONS_ABC]
    if not abc:
        return None
    out: list[str] = []
    if std:
        out.append(f"{indent}from collections import {', '.join(std)}")
    out.append(f"{indent}from collections.abc import {', '.join(abc)}")
    return out


def _patch_collections_import_block(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*from collections import \(", line):
            block = [line]
            i += 1
            while i < len(lines) and ")" not in block[-1]:
                block.append(lines[i])
                i += 1
            split = _split_collections_import_block(block)
            if split:
                out.extend(split)
                continue
            out.extend(block)
            continue
        split = _split_collections_import_line(line)
        out.extend(split or [line])
        i += 1
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def _patch_collections_attr_usage(text: str) -> str:
    names = "|".join(sorted(_COLLECTIONS_ABC, key=len, reverse=True))
    pattern = rf"\bcollections\.(?!abc\.)({names})\b"
    return re.sub(pattern, r"collections.abc.\1", text)


def _patch_python_compat_text(text: str) -> str:
    return _patch_collections_attr_usage(_patch_collections_import_block(text))


def apply_python_compat(repo_dir: Path) -> tuple[str, ...]:
    if sys.version_info < (3, 10):
        return ()
    changed_paths: list[str] = []
    for path in repo_dir.rglob("*.py"):
        original = path.read_text(encoding="utf-8", errors="ignore")
        patched = _patch_python_compat_text(original)
        if patched != original:
            path.write_text(patched)
            changed_paths.append(str(path.relative_to(repo_dir)))
    if changed_paths:
        print(
            f"{tag('prep')} py{sys.version_info.major}.{sys.version_info.minor} "
            f"collections compat {paint(str(len(changed_paths)), _BRIGHT_GREEN)} files",
            flush=True,
        )
    return tuple(changed_paths)


def _node_path(node_id: str) -> str:
    return node_id.split("::", 1)[0]


def build_pytest_node_ids(
    repo_dir: Path,
    test_names: tuple[str, ...],
    test_paths: list[str],
    adapter: RepoHarnessAdapter | None = None,
) -> tuple[list[str], list[str]]:
    node_ids: list[str] = []
    missing: list[str] = []
    test_path_set = set(test_paths)
    resolved: set[int] = set()
    for idx, name in enumerate(test_names):
        if adapter:
            mapped = adapter.map_test_name(name)
            if mapped:
                name = mapped
                resolved.add(idx)
        if "::" not in name:
            continue
        path = _node_path(name)
        if not test_path_set or path in test_path_set or (repo_dir / path).exists():
            node_ids.append(name)
        else:
            missing.append(name)
    for path in test_paths:
        full = repo_dir / path
        text = full.read_text() if full.is_file() else ""
        for idx, name in enumerate(test_names):
            if idx in resolved or "::" in name:
                continue
            if f"def {name}(" in text:
                node_ids.append(f"{path}::{name}")
            else:
                missing.append(f"{path}::{name}")
    return list(dict.fromkeys(node_ids)), missing


def run_pytest(
    repo_dir: Path,
    test_names: tuple[str, ...],
    test_paths: list[str],
    adapter: RepoHarnessAdapter | None = None,
) -> tuple[bool, str]:
    if not test_names:
        return False, "no test names"
    node_ids, missing = build_pytest_node_ids(repo_dir, test_names, test_paths, adapter=adapter)
    if not node_ids:
        detail = ", ".join(missing[:6]) if missing else "none"
        return False, f"no pytest node ids: {detail}"
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    # Ensure repo root is on PYTHONPATH so test-directory packages
    # (e.g. Django's ``tests.test_sqlite``) are importable regardless of
    # which test command the adapter produces.
    env["PYTHONPATH"] = isolated_repo_pythonpath(
        repo_dir,
        get_runtime_root(),
        os.environ.get("PYTHONPATH", ""),
    )
    if adapter:
        extra_env = adapter.pytest_env()
        if extra_env:
            env.update(extra_env)
        cmd = adapter.build_test_command(repo_dir, node_ids)
    else:
        cmd = [harness_python(), "-m", "pytest", "-x"] + node_ids
    result = subprocess.run(
        cmd,
        cwd=repo_dir,
        capture_output=True,
        text=True,
        env=env,
    )
    output = (result.stdout + "\n" + result.stderr).strip()
    return result.returncode == 0, _compact_pytest_output(output)
