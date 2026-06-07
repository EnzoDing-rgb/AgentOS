from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from .console_log import _BRIGHT_GREEN, paint, tag


class RepoHarnessAdapter:
    """Per-repo local-harness adapter.

    Adapters keep repository-specific evaluation quirks out of the core harness
    flow.  They may patch the ephemeral harness worktree or translate SWE-bench
    test names into pytest node ids.
    """

    repo_slug: str

    def apply_compat(self, repo_dir: Path) -> list[str]:
        return []

    def map_test_name(self, raw_name: str) -> str | None:
        return None

    def pytest_env(self) -> dict[str, str]:
        return {}

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

        return changed


_DJANGO_TEST_NAME_RE = re.compile(r"^(\w+)\s+\((.+)\.(\w+)\)$")


class DjangoHAdapter(RepoHarnessAdapter):
    repo_slug = "django__django"

    def apply_compat(self, repo_dir: Path) -> list[str]:
        conftest = repo_dir / "conftest.py"
        if not conftest.is_file():
            conftest.write_text(
                "import os\n"
                "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.test_sqlite')\n"
                "import django\n"
                "django.setup()\n"
            )
            return ["conftest.py (generated)"]
        original = conftest.read_text(encoding="utf-8", errors="ignore")
        if "django.setup()" not in original:
            conftest.write_text("import django\ndjango.setup()\n\n" + original)
            return ["conftest.py (patched)"]
        return []

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


class RequestsHAdapter(RepoHarnessAdapter):
    repo_slug = "psf__requests"


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
    env = None
    if adapter:
        extra_env = adapter.pytest_env()
        if extra_env:
            env = {**os.environ, **extra_env}
    result = subprocess.run(
        [harness_python(), "-m", "pytest", "-x", *node_ids],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        env=env,
    )
    output = (result.stdout + "\n" + result.stderr).strip()
    tail = output[-2000:] if len(output) > 2000 else output
    return result.returncode == 0, tail
