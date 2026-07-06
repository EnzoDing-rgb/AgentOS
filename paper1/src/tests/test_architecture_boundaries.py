from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "src" / "budgetflow"

MECHANISM_MODULES = (
    "types.py",
    "policy_backend.py",
    "learn_policy.py",
    "adaptive_routing.py",
)

FORBIDDEN_IMPORT_PREFIXES = (
    "budgetflow.adapter",
    "budgetflow.adapters",
    "budgetflow.auto_budget",
    "budgetflow.experiments",
)

FORBIDDEN_RELATIVE_MODULES = (
    "adapter",
    "adapters",
    "auto_budget",
    "experiments",
)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                found.append("." * node.level + module)
            else:
                found.append(module)
    return found


def test_budgetflow_mechanism_modules_do_not_import_adapter_or_experiment_layers() -> None:
    violations: list[str] = []
    for module_name in MECHANISM_MODULES:
        path = ROOT / module_name
        for imported in _imports(path):
            normalized = imported.lstrip(".")
            if imported.startswith(".") and normalized.split(".", 1)[0] in FORBIDDEN_RELATIVE_MODULES:
                violations.append(f"{module_name}: {imported}")
            if normalized.startswith(FORBIDDEN_IMPORT_PREFIXES):
                violations.append(f"{module_name}: {imported}")

    assert violations == []
