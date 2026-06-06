"""Continual-learning source selection for BudgetFlow runs.

Cap learning and routing learning use different artifacts:

- ``auto_budget_memory.jsonl`` stores cap/value-cost priors.
- run JSONL files store routing outcomes and per-turn traces.

Keeping this distinction behind one module prevents the runner from treating a
cap-memory artifact as routing-memory evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .policy_memory import PolicyMemory


ROUTING_MEMORY_ROUTINGS = frozenset(
    {
        "budgetflow_full",
        "budgetflow_conservative",
        "budgetflow_value_aware",
        "budgetflow_equal_weight",
        "stage_blind",
        "budget_only",
    }
)


@dataclass(frozen=True)
class PolicyMemoryContext:
    memory: PolicyMemory | None
    source: Path | None
    source_kind: str
    enabled: bool
    reason: str = ""


def looks_like_policy_memory_source(path: Path) -> bool:
    """Return True for run JSONL that can teach routing priors."""
    if not path.is_file() or path.name.startswith("auto_budget"):
        return False
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return False
    for line in lines[:50]:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        routing = str(record.get("routing") or "")
        if routing not in ROUTING_MEMORY_ROUTINGS:
            continue
        if not record.get("instance_id"):
            continue
        if record.get("backend_picks") or record.get("turn_traces"):
            return True
    return False


def default_policy_memory_source(runs_dir: Path, *, exclude: Path | None = None) -> Path | None:
    """Pick the latest usable run JSONL for routing-memory continual learning."""
    candidates: list[Path] = []
    exclude_resolved = exclude.resolve() if exclude is not None else None
    for path in runs_dir.glob("*.jsonl"):
        if exclude_resolved is not None and path.resolve() == exclude_resolved:
            continue
        if looks_like_policy_memory_source(path):
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p.stat().st_mtime_ns, p.name))


def load_policy_memory_context(
    *,
    runs_dir: Path,
    repo_root: Path,
    explicit_path: str | None,
    resume: bool,
    resume_path: Path | None,
    disable: bool,
    regret_threshold: float | None,
    exclude: Path | None = None,
) -> PolicyMemoryContext:
    """Resolve and load routing PolicyMemory for a compare run."""
    if disable:
        return PolicyMemoryContext(None, None, "disabled", False, "disabled_by_flag")

    source: Path | None = None
    source_kind = ""
    if explicit_path:
        source = Path(explicit_path)
        if not source.is_absolute():
            source = repo_root / source
        source_kind = "explicit"
    elif resume and resume_path is not None and resume_path.is_file():
        source = resume_path
        source_kind = "resume"
    else:
        source = default_policy_memory_source(runs_dir, exclude=exclude)
        source_kind = "default_recent" if source is not None else ""

    if source is None:
        return PolicyMemoryContext(None, None, "", False, "no_usable_run_jsonl")
    if not source.is_file():
        return PolicyMemoryContext(None, source, source_kind, False, "file_not_found")
    if not looks_like_policy_memory_source(source):
        return PolicyMemoryContext(None, source, source_kind, False, "not_routing_run_jsonl")

    memory = PolicyMemory(regret_threshold=regret_threshold)
    memory.rebuild_from_jsonl(source)
    return PolicyMemoryContext(memory, source, source_kind, True)
