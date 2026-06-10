"""Learn Policy memory source selection for BudgetFlow runs.

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

from .harness_contamination import has_host_dependency_contamination
from .learn_policy import LearnPolicyInputs
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
    learn_policy_inputs: LearnPolicyInputs
    source: Path | None
    sources: tuple[Path, ...]
    source_kind: str
    enabled: bool
    reason: str = ""


def looks_like_policy_memory_source(path: Path, *, require_current_schema: bool = True) -> bool:
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
        detail = str(record.get("detail") or "")
        if has_host_dependency_contamination(detail):
            return False
        routing = str(record.get("routing") or "")
        if routing not in ROUTING_MEMORY_ROUTINGS:
            continue
        if not record.get("instance_id"):
            continue
        if require_current_schema and not _record_has_current_memory_schema(record):
            continue
        if record.get("backend_picks") or record.get("turn_traces"):
            return True
    return False


def _record_has_current_memory_schema(record: dict) -> bool:
    """Default memory only consumes rows from the current auditable schema."""
    if record.get("routing_decision_schema") != "v1":
        return False
    if not record.get("task_set_kind"):
        return False
    if not record.get("policy_kind"):
        return False
    if not isinstance(record.get("learn_policy_input_views"), list):
        return False
    if str(record.get("score_status") or "") not in {"pass", "true_fail", "abort"}:
        return False
    return True


def default_policy_memory_source(runs_dir: Path, *, exclude: Path | None = None) -> Path | None:
    """Pick the latest usable run JSONL for routing-memory continual learning."""
    candidates: list[Path] = []
    exclude_resolved = exclude.resolve() if exclude is not None else None
    for path in runs_dir.glob("*.jsonl"):
        if exclude_resolved is not None and path.resolve() == exclude_resolved:
            continue
        if looks_like_policy_memory_source(path, require_current_schema=True):
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
        if looks_like_policy_memory_source(path, require_current_schema=True):
            candidates.append(path)
    candidates.sort(key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
    return tuple(candidates[:limit])


def policy_memory_source_weight(source_index: int) -> float:
    """Recency weighting for explicitly selected multi-source memory."""
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
        return PolicyMemoryContext(
            None, LearnPolicyInputs.off("disabled_by_flag"), None, (), "disabled", False, "disabled_by_flag"
        )

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
    else:
        # PolicyMemory is opt-in. Must pass --policy-memory explicitly.
        # Resume does NOT auto-enable PolicyMemory.
        return PolicyMemoryContext(
            None, LearnPolicyInputs.off("no_explicit_memory_path"), None, (), "", False, "no_explicit_memory_path"
        )

    if not sources:
        return PolicyMemoryContext(
            None, LearnPolicyInputs.off("no_usable_run_jsonl"), None, (), "", False, "no_usable_run_jsonl"
        )
    missing = [path for path in sources if not path.is_file()]
    if missing:
        return PolicyMemoryContext(
            None, LearnPolicyInputs.off("file_not_found"), missing[0], sources, source_kind, False, "file_not_found"
        )

    # Explicit paths: always load and process every row. The source-level
    # looks_like_policy_memory_source gate is for auto-detection (disabled).
    # Per-row filtering is done by _memory_skip_reason in rebuild_from_records.
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
            record["_policy_memory_schema"] = "current"
            record["_policy_memory_weight"] = weight
            record["_policy_memory_source"] = str(source)
            record["_policy_memory_source_rank"] = source_index
            records.append(record)
    memory.rebuild_from_records(records)
    memory._source_path = ",".join(str(path) for path in sources)

    if memory._records_accepted == 0:
        return PolicyMemoryContext(
            memory, LearnPolicyInputs.off("no_accepted_memory_records"),
            sources[0], sources, source_kind, False, "no_accepted_memory_records"
        )

    bundle = LearnPolicyInputs.built_in(
        routing=memory,
        escalation=memory,
        source=",".join(str(path) for path in sources),
    )
    return PolicyMemoryContext(memory, bundle, sources[0], sources, source_kind, True)
