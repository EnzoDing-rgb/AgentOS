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

POLICY_MEMORY_SOURCE_DECAY = 0.35
POLICY_MEMORY_MIN_WEIGHT = 0.05


ROUTING_MEMORY_ROUTINGS = frozenset(
    {
        "budgetflow_full",
        "budgetflow_conservative",
        "budgetflow_value_aware",
        "value_aware_task_level",
        "budgetflow_equal_weight",
        "stage_blind",
        "budget_only",
    }
)


@dataclass(frozen=True)
class PolicyMemoryContext:
    memory: PolicyMemory | None
    source: Path | None
    sources: tuple[Path, ...]
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


def default_policy_memory_sources(runs_dir: Path, *, exclude: Path | None = None, limit: int = 5) -> tuple[Path, ...]:
    """Pick recent usable run JSONLs for routing-memory continual learning."""
    candidates: list[Path] = []
    exclude_resolved = exclude.resolve() if exclude is not None else None
    for path in runs_dir.glob("*.jsonl"):
        if exclude_resolved is not None and path.resolve() == exclude_resolved:
            continue
        if looks_like_policy_memory_source(path):
            candidates.append(path)
    candidates.sort(key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
    return tuple(candidates[:limit])


def policy_memory_source_weight(source_index: int) -> float:
    """Recency weighting: newest run dominates, older runs are weak priors."""
    return max(POLICY_MEMORY_MIN_WEIGHT, POLICY_MEMORY_SOURCE_DECAY ** max(0, source_index))


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
        return PolicyMemoryContext(None, None, (), "disabled", False, "disabled_by_flag")

    sources: tuple[Path, ...] = ()
    source_kind = ""
    if explicit_path:
        resolved: list[Path] = []
        for raw in explicit_path.split(","):
            raw = raw.strip()
            if not raw:
                continue
            path = Path(raw)
            if not path.is_absolute():
                path = repo_root / path
            resolved.append(path)
        sources = tuple(resolved)
        source_kind = "explicit"
    elif resume and resume_path is not None and resume_path.is_file():
        sources = (resume_path,)
        source_kind = "resume"
    else:
        sources = default_policy_memory_sources(runs_dir, exclude=exclude)
        source_kind = "default_recent" if sources else ""

    if not sources:
        return PolicyMemoryContext(None, None, (), "", False, "no_usable_run_jsonl")
    missing = [path for path in sources if not path.is_file()]
    if missing:
        return PolicyMemoryContext(None, missing[0], sources, source_kind, False, "file_not_found")
    unusable = [path for path in sources if not looks_like_policy_memory_source(path)]
    if unusable:
        return PolicyMemoryContext(None, unusable[0], sources, source_kind, False, "not_routing_run_jsonl")

    memory = PolicyMemory(regret_threshold=regret_threshold)
    records: list[dict] = []
    for source_index, source in enumerate(sources):
        weight = policy_memory_source_weight(source_index)
        for line in source.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            record["_policy_memory_source"] = str(source)
            record["_policy_memory_source_rank"] = source_index
            record["_policy_memory_weight"] = weight
            records.append(record)
    memory.rebuild_from_records(records)
    memory._source_path = ",".join(str(path) for path in sources)
    return PolicyMemoryContext(memory, sources[0], sources, source_kind, True)
