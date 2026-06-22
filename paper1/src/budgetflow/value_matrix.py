"""Value Matrix and Progress Calibration — offline, defensible foundation.

Value Matrix:
  Generates a multi-profile value assignment for each task in the clean JSONL
  universe. No BF-specific signals. All profiles are pre-registered or cross-strategy.

  Profiles:
    equal              — 1.0 for every task (baseline)
    difficulty         — avg_cost × failure_penalty (cost + hardness proxy)
    discriminative_rarity — peak at moderate rarity (best strategy-separator)
    unsolved_difficulty — high for expensive, unsolved tasks (ceiling candidate)
    combined           — log1p(difficulty) + discriminative_rarity
    custom             — user-provided instance_id → value mapping

Progress Calibration:
  Read-only (stage, tier) progress summary from existing turn_traces.
  Reports observed progress rates with selection-bias caveats.

Usage:
  PYTHONPATH=src python3 -m budgetflow.value_matrix \\
    --data-dir data/runs \\
    --output docs/reports/046_value_matrix.json

  PYTHONPATH=src python3 -m budgetflow.value_matrix \\
    --data-dir data/runs \\
    --manifest docs/reports/value_matrix_clean_runs.json \\
    --output -
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# ═══════════════════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class TaskRecord:
    instance_id: str
    repo: str
    total_rows: int = 0
    resolved_rows: int = 0
    total_cost: float = 0.0
    strategies_seen: set[str] = field(default_factory=set)
    strategies_resolved: set[str] = field(default_factory=set)

    @property
    def resolve_rate(self) -> float:
        return self.resolved_rows / self.total_rows if self.total_rows > 0 else 0.0

    @property
    def avg_cost(self) -> float:
        return self.total_cost / self.total_rows if self.total_rows > 0 else 0.0

    @property
    def solve_rarity(self) -> float:
        """Fraction of strategies that solved this task. 0 = unsolved, 1 = all solved."""
        n = len(self.strategies_seen)
        return len(self.strategies_resolved) / n if n > 0 else 0.0

    @property
    def repo_name(self) -> str:
        return self.instance_id.split("__")[0] if "__" in self.instance_id else "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# Value profiles
# ═══════════════════════════════════════════════════════════════════════════════

# Each profile is a Callable[[str, TaskRecord], float].
# The function signature is (instance_id, TaskRecord) so custom profiles
# can use cross-strategy stats or ignore them.

ValueFn = Callable[[str, TaskRecord], float]


def profile_equal(_iid: str, _rec: TaskRecord) -> float:
    """Equal value: every task counts 1.0."""
    return 1.0


def profile_difficulty(rec: TaskRecord) -> float:
    """Difficulty proxy: value ∝ avg_cost × (1 + failure_penalty).

    Rationale: tasks that consume more budget across ALL strategies and are
    harder to solve are more likely to contain deep bugs worth fixing.
    Cross-strategy stats avoid BF-specific tuning.

    Failure penalty: unresolved tasks get a 1.5× multiplier on the cost
    component to reflect that difficult-to-solve tasks are more valuable
    to solve correctly.

    This is an pre-registered proxy — it uses only historical stats that exist
    before any single strategy is evaluated.
    """
    base = rec.avg_cost
    if rec.resolve_rate < 1.0:
        base *= (1.0 + 0.5 * (1.0 - rec.resolve_rate))
    # Floor at 0.01 to avoid zero-value tasks
    return max(base, 0.01)


def profile_discriminative_rarity(rec: TaskRecord) -> float:
    """Discriminative rarity: peak value at moderate rarity (0.5).

    Rationale: tasks that some strategies solve and others don't are the
    most discriminating — they separate good routers from bad ones. Tasks
    that everyone solves (rarity=1.0) and tasks that no one solves
    (rarity=0.0) are both less informative for comparing strategies.

    Formula: value = 1.0 + 4.0 × rarity × (1.0 - rarity)
    - Everyone solves (rarity=1.0): value = 1.0
    - No one solves (rarity=0.0): value = 1.0
    - Exactly half solve (rarity=0.5): value = 2.0  ← peak

    The quadratic form r×(1-r) is symmetric around 0.5 and zero at both
    extremes. This makes the formula/narrative consistent: no-one-solved
    tasks are NOT automatically high-value.

    Contrast with unsolved_difficulty, which separately captures the
    "hard/unsolved task" signal.
    """
    rarity = rec.solve_rarity
    return 1.0 + 4.0 * rarity * (1.0 - rarity)


def profile_unsolved_difficulty(rec: TaskRecord) -> float:
    """Unsolved difficulty: high value for expensive, unsolved tasks.

    This is a ceiling-candidate / hard-task proxy, NOT a discriminative
    value. Tasks that no strategy can solve (high avg_cost, low resolve_rate)
    get higher values — they may represent valuable hard bugs worth solving
    if a strategy CAN solve them.

    Formula: value = max(avg_cost, 0.01) × (2.0 - resolve_rate)
    - Fully solved/resolved (rate=1.0): avg_cost × 1.0
    - Never resolved (rate=0.0): avg_cost × 2.0 (max penalty)

    Explicitly labeled as a ceiling/hardness candidate. It answers "which
    tasks are hardest?" not "which tasks discriminate between strategies?"
    """
    base = max(rec.avg_cost, 0.01)
    penalty = 2.0 - rec.resolve_rate
    return round(base * penalty, 6)


def profile_combined(rec: TaskRecord) -> float:
    """Combined difficulty + discriminative_rarity proxy (log-scaled).

    Uses log1p on difficulty to compress extreme values. Adds discriminative
    rarity for the strategy-separation signal.

    Caveat: unsolved tasks get low discriminative value (∼1.0) but may have
    high difficulty. The combined score reflects both signals without letting
    either dominate by default.
    """
    diff = profile_difficulty(rec)
    disc = profile_discriminative_rarity(rec)
    import math
    return round(math.log1p(diff) + disc, 4)


def make_custom_profile(mapping: dict[str, float]) -> ValueFn:
    """Build a profile from an explicit instance_id → value mapping."""
    return lambda iid, _rec: mapping.get(iid, 1.0)


# Registry: name → (factory or direct function)
# For profiles that need TaskRecord, we wrap them.
def _wrap_record(fn: Callable[[TaskRecord], float]) -> ValueFn:
    return lambda _iid, rec: fn(rec)


PROFILES: dict[str, ValueFn] = {
    "equal": profile_equal,
    "difficulty": _wrap_record(profile_difficulty),
    "discriminative_rarity": _wrap_record(profile_discriminative_rarity),
    "unsolved_difficulty": _wrap_record(profile_unsolved_difficulty),
    "combined": _wrap_record(profile_combined),
}


def bootstrap_task_features(task) -> dict[str, int]:
    """Extract pre-registered task features used by the bootstrap value profile."""
    return {
        "patch_lines": len(str(getattr(task, "patch", "") or "").splitlines()),
        "f2p_count": len(getattr(task, "fail_to_pass", ()) or ()),
        "p2p_count": len(getattr(task, "pass_to_pass", ()) or ()),
        "problem_words": len(str(getattr(task, "problem_statement", "") or "").split()),
        "gold_file_count": len(getattr(task, "gold_files", ()) or ()),
    }


def bootstrap_task_effort(task) -> dict[str, float | str | dict[str, int]]:
    """No-outcome bootstrap effort heuristic from task text/patch/test metadata.

    This is a Task Effort diagnostic, NOT Task Value.  It estimates runway /
    expected work based on patch lines, test counts, problem length, and gold
    file count.  It must not be presented as Claim 1 value.
    """
    features = bootstrap_task_features(task)
    import math

    raw = (
        1.0
        + features["patch_lines"]
        + 2.0 * features["f2p_count"]
        + math.log1p(features["p2p_count"])
        + 0.01 * features["problem_words"]
        + 1.5 * features["gold_file_count"]
    )
    base_task_effort = round(raw, 4)
    return {
        "base_task_effort": base_task_effort,
        "task_effort_multiplier": 1.0,
        "final_task_effort": base_task_effort,
        "source": "task_metadata_formula",
        "features": features,
    }


def apply_criticality_override(
    entry: dict[str, Any],
    *,
    level: str,
    source: str,
    reason: str,
) -> None:
    """Apply a pre-run human/business criticality override to a matrix entry."""
    if level not in CRITICALITY_VALUE_MAP:
        raise ValueError(f"unknown criticality_level={level!r}")
    previous = str(entry.get("criticality_level") or "normal")
    entry["criticality_level"] = level
    entry["criticality_source"] = source
    entry["criticality_override"] = {
        "from": previous,
        "to": level,
        "source": source,
        "reason": reason,
    }
    task_value = entry.setdefault("task_value", {})
    task_value["criticality_value"] = CRITICALITY_VALUE_MAP[level]


def apply_task_effort_override(
    entry: dict[str, Any],
    *,
    multiplier: float,
    source: str,
    reason: str,
) -> None:
    """Apply a pre-run task-effort multiplier override to a matrix entry."""
    if multiplier <= 0:
        raise ValueError("task_effort_multiplier must be positive")
    task_effort = entry.setdefault("task_effort", {})
    if "bootstrap_heuristic" in task_effort and "base_task_effort" not in task_effort:
        raise ValueError(
            "retired task_effort.bootstrap_heuristic cannot be used as override base; "
            "expected task_effort.base_task_effort"
        )
    base = float(task_effort.get("base_task_effort") or task_effort.get("final_task_effort") or 1.0)
    previous = float(task_effort.get("task_effort_multiplier") or 1.0)
    task_effort["base_task_effort"] = base
    task_effort["task_effort_multiplier"] = float(multiplier)
    task_effort["final_task_effort"] = round(base * float(multiplier), 4)
    entry["task_effort_override"] = {
        "from": previous,
        "to": float(multiplier),
        "source": source,
        "reason": reason,
    }


CRITICALITY_VALUE_MAP = {
    "normal": 1.0,
    "high": 1.5,
    "critical": 2.5,
}

CRITICALITY_FORMULA_V1 = (
    "criticality_v1: critical when f2p_count>=20 or p2p_count>=400; "
    "high when f2p_count>=5 or p2p_count>=50; normal otherwise. "
    "Task Value mapping: normal=1.0, high=1.5, critical=2.5."
)


def bootstrap_criticality_level(features: dict[str, int]) -> str:
    """Pre-registered criticality level from verifier breadth only.

    This is outcome-free: it uses fail-to-pass and pass-to-pass test breadth,
    not model outcomes, costs, repo names, or task IDs.
    """
    f2p_count = int(features["f2p_count"])
    p2p_count = int(features["p2p_count"])
    if f2p_count >= 20 or p2p_count >= 400:
        return "critical"
    if f2p_count >= 5 or p2p_count >= 50:
        return "high"
    return "normal"


def build_bootstrap_value_matrix(
    tasks: list,
    *,
    task_source: str,
    include_criticality_value: bool = False,
) -> dict[str, Any]:
    """Build value matrix for a selected task set without historical outcomes.

    Schema (North Star aligned):
      - ``task_value``: Claim 1 value profiles (equal, criticality_value, ...).
      - ``task_effort``: Task Effort diagnostic (final_task_effort).
      - ``model_fit``: reserved, null for bootstrap matrices.

    The ``final_task_effort`` is a metadata-based effort proxy.  It is NOT
    a Task Value profile and must not be selected via --value-profile.
    """
    import math as _math

    task_value_profiles = ["equal", "criticality_value"] if include_criticality_value else ["equal"]
    matrix: dict[str, Any] = {
        "meta": {
            "task_count": len(tasks),
            "task_value_profiles": task_value_profiles,
            "task_effort_source": "task_metadata_formula",
            "source": task_source,
            "source_class": (
                "pre_registered_formula_plus_metadata"
                if include_criticality_value else "bootstrap_pre_registered_metadata"
            ),
            "outcome_free": True,
            "note": (
                "Task Value profiles use only pre-registered task metadata. "
                "Task Effort uses a bootstrap heuristic from pre-registered "
                "SWE-bench task metadata: patch lines, fail/pass test counts, "
                "problem words, and gold file count. "
                "No strategy outcome, cost, solve rarity, or BudgetFlow signal is used."
            ),
            "effort_formula": (
                "base_task_effort = 1 + patch_lines + 2*f2p_count + "
                "log1p(p2p_count) + 0.01*problem_words + 1.5*gold_file_count"
            ),
        },
        "tasks": {},
    }
    if include_criticality_value:
        matrix["meta"]["value_source_kind"] = "pre_registered_manual"
        matrix["meta"]["criticality_formula"] = CRITICALITY_FORMULA_V1
        matrix["meta"]["criticality_value_map"] = CRITICALITY_VALUE_MAP
    for task in tasks:
        features = bootstrap_task_features(task)
        effort = bootstrap_task_effort(task)
        task_value = {"equal": 1.0}
        entry: dict[str, Any] = {
            "instance_id": task.instance_id,
            "repo": task.repo,
            "task_value": task_value,
            "task_effort": effort,
            "model_fit": None,
            "features": features,
        }
        if include_criticality_value:
            criticality_level = bootstrap_criticality_level(features)
            task_value["criticality_value"] = CRITICALITY_VALUE_MAP[criticality_level]
            entry["criticality_level"] = criticality_level
            entry["criticality_source"] = "criticality_v1"
            entry["value_formula"] = "criticality_v1"
        matrix["tasks"][task.instance_id] = {
            **entry,
        }
    matrix["rankings"] = {}
    # Equal profile: every task has value 1.0, ranking is alphabetical.
    ranked_equal = sorted(
        matrix["tasks"].items(),
        key=lambda item: item[0],
    )
    matrix["rankings"]["equal"] = [
        {"rank": index + 1, "instance_id": iid, "value": 1.0}
        for index, (iid, entry) in enumerate(ranked_equal)
    ]
    # Effort ranking: by final_task_effort (diagnostic only, not Claim 1).
    ranked_effort = sorted(
        matrix["tasks"].items(),
        key=lambda item: item[1]["task_effort"]["final_task_effort"],
        reverse=True,
    )
    matrix["rankings"]["final_task_effort"] = [
        {
            "rank": index + 1,
            "instance_id": iid,
            "effort": entry["task_effort"]["final_task_effort"],
        }
        for index, (iid, entry) in enumerate(ranked_effort)
    ]
    if include_criticality_value:
        ranked_manual = sorted(
            matrix["tasks"].items(),
            key=lambda item: item[1]["task_value"]["criticality_value"],
            reverse=True,
        )
        matrix["rankings"]["criticality_value"] = [
            {
                "rank": index + 1,
                "instance_id": iid,
                "criticality_level": entry["criticality_level"],
                "value": entry["task_value"]["criticality_value"],
            }
            for index, (iid, entry) in enumerate(ranked_manual)
        ]
    return matrix


# ═══════════════════════════════════════════════════════════════════════════════
# Robustness sensitivity
# ═══════════════════════════════════════════════════════════════════════════════


def sensitivity_variants(rec: TaskRecord) -> dict[str, float]:
    """Generate sensitivity variants of the difficulty profile.

    Returns a dict of profile_name → value for sensitivity analysis.
    The goal: show that conclusions don't hinge on a single magic number.
    """
    base_cost = rec.avg_cost
    base_rate = rec.resolve_rate
    # Three variants:
    # - cost_only: value = avg_cost (ignore solve rate)
    # - rate_only: value = 2.0 - resolve_rate (inverted: hard=high)
    # - cost_heavy: value = avg_cost * (2 - resolve_rate)
    # - rate_heavy: value = (1 + avg_cost) * (2 - resolve_rate)
    # - original: as per profile_difficulty
    return {
        "cost_only": max(base_cost, 0.01),
        "rate_only": max(2.0 - base_rate, 0.01),
        "cost_heavy": max(base_cost * (2.0 - base_rate), 0.01),
        "rate_heavy": max((1.0 + base_cost) * (2.0 - base_rate), 0.01),
        "difficulty_default": profile_difficulty(rec),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Build value matrix from JSONL
# ═══════════════════════════════════════════════════════════════════════════════


def load_manifest(manifest_path: str | Path) -> dict[str, Any]:
    """Load a clean-run manifest JSON file.

    Returns the parsed manifest with validated structure.
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    if "runs" not in manifest:
        raise ValueError("Manifest missing 'runs' key")
    return manifest


def scan_task_universe(
    data_dir: str | Path,
    manifest: dict[str, Any] | None = None,
) -> dict[str, TaskRecord]:
    """Scan JSONL files and build TaskRecord for each unique task.

    If manifest is provided, only files listed in the manifest are scanned.
    Missing manifest entries raise FileNotFoundError. Unlisted files are
    silently skipped. Without a manifest, scans all non-auto_budget *.jsonl.
    """
    data_dir = Path(data_dir)
    records: dict[str, TaskRecord] = {}

    if manifest is not None:
        # Manifest mode: only allowlisted files
        for entry in manifest["runs"]:
            filename = entry["file"]
            fp = data_dir / filename
            if not fp.is_file():
                raise FileNotFoundError(
                    f"Manifest entry '{filename}' not found in {data_dir}"
                )
            _ingest_jsonl(fp, records)
    else:
        # Legacy directory-scan mode (backward compatible)
        jsonl_files = sorted(data_dir.glob("*.jsonl"))
        for fp in jsonl_files:
            if fp.name.startswith("auto_budget"):
                continue
            _ingest_jsonl(fp, records)

    return records


def _ingest_jsonl(fp: Path, records: dict[str, TaskRecord]) -> None:
    """Ingest one JSONL file into the records dict (mutates in place)."""
    try:
        with open(fp) as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except (json.JSONDecodeError, OSError):
        return

    for r in rows:
        iid = r.get("instance_id", "")
        if not iid:
            continue
        if iid not in records:
            records[iid] = TaskRecord(instance_id=iid, repo=r.get("repo", ""))
        rec = records[iid]
        rec.total_rows += 1
        if r.get("harness_resolved"):
            rec.resolved_rows += 1
            rec.strategies_resolved.add(r.get("strategy", "?"))
        rec.total_cost += r.get("total_cost", r.get("task_cost", 0.0)) or 0.0
        rec.strategies_seen.add(r.get("strategy", "?"))

    return records


def build_value_matrix(
    records: dict[str, TaskRecord],
    profiles: dict[str, ValueFn] | None = None,
    manifest_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a value matrix with all profiles and sensitivity analysis.

    If manifest_meta is provided, its 'meta' and 'runs' fields are embedded
    in the output for confidence tracking.
    """
    if profiles is None:
        profiles = PROFILES

    meta: dict[str, Any] = {
        "task_count": len(records),
        "profiles": list(profiles.keys()),
        "note": "All profiles are pre-registered or cross-strategy. No BF-specific signals.",
    }
    if manifest_meta is not None:
        meta["manifest"] = manifest_meta.get("meta", {})
        meta["manifest_runs"] = [
            {"file": r["file"], "rows": r["rows"], "strategies": r["strategies"]}
            for r in manifest_meta.get("runs", [])
        ]
        meta["source"] = "manifest — clean-run allowlist"

    matrix: dict[str, Any] = {
        "meta": meta,
        "tasks": {},
    }

    for iid in sorted(records.keys()):
        rec = records[iid]
        task_entry: dict[str, Any] = {
            "instance_id": iid,
            "repo": rec.repo_name,
            "total_rows": rec.total_rows,
            "resolved_rows": rec.resolved_rows,
            "resolve_rate": round(rec.resolve_rate, 4),
            "avg_cost": round(rec.avg_cost, 6),
            "solve_rarity": round(rec.solve_rarity, 4),
            "strategies_seen": sorted(rec.strategies_seen),
            "strategies_resolved": sorted(rec.strategies_resolved),
            "values": {},
            "sensitivity": {},
        }

        for pname, pfn in profiles.items():
            task_entry["values"][pname] = round(pfn(iid, rec), 4)

        task_entry["sensitivity"] = {
            k: round(v, 4) for k, v in sensitivity_variants(rec).items()
        }

        matrix["tasks"][iid] = task_entry

    # Add per-profile rankings
    matrix["rankings"] = {}
    for pname in profiles.keys():
        ranked = sorted(
            matrix["tasks"].items(),
            key=lambda kv: kv[1]["values"][pname],
            reverse=True,
        )
        matrix["rankings"][pname] = [
            {"rank": i + 1, "instance_id": iid, "value": entry["values"][pname]}
            for i, (iid, entry) in enumerate(ranked)
        ]

    # Add rank correlation between profiles
    matrix["rank_correlations"] = _rank_correlations(matrix["rankings"])

    return matrix


def _rank_correlations(rankings: dict[str, list]) -> dict[str, dict[str, float]]:
    """Spearman-like rank correlation between profiles."""
    profile_names = list(rankings.keys())
    result: dict[str, dict[str, float]] = {}
    for p1 in profile_names:
        result[p1] = {}
        ids1 = [r["instance_id"] for r in rankings[p1]]
        for p2 in profile_names:
            if p1 == p2:
                result[p1][p2] = 1.0
                continue
            ids2 = [r["instance_id"] for r in rankings[p2]]
            # Spearman footrule: 1 - 6*sum(d^2)/(n*(n^2-1))
            n = len(ids1)
            d2_sum = sum(
                (ids1.index(iid) - ids2.index(iid)) ** 2 for iid in ids1
            )
            rho = 1.0 - (6.0 * d2_sum) / (n * (n * n - 1)) if n > 1 else 1.0
            result[p1][p2] = round(rho, 4)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Progress calibration from turn traces
# ═══════════════════════════════════════════════════════════════════════════════


def calibrate_progress_table(data_dir: str | Path) -> dict[str, Any]:
    """Read-only calibration of (stage, tier) progress from existing traces."""
    data_dir = Path(data_dir)
    jsonl_files = sorted(data_dir.glob("*.jsonl"))

    # Raw aggregation
    stage_tier: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"turns": 0, "progress_turns": 0, "costs": [], "strategies": set()}
    )

    for fp in jsonl_files:
        if fp.name.startswith("auto_budget"):
            continue
        try:
            with open(fp) as f:
                rows = [json.loads(line) for line in f if line.strip()]
        except (json.JSONDecodeError, OSError):
            continue

        for r in rows:
            traces = r.get("turn_traces", [])
            for t in traces:
                stage = str(t.get("stage", "?"))
                tier = str(t.get("backend_tier", "?"))
                has_progress = bool(t.get("has_progress", False))
                cost = t.get("billable_cost", t.get("actual_cost", 0))
                if cost is None:
                    cost = 0.0

                key = (stage, tier)
                st = stage_tier[key]
                st["turns"] += 1
                if has_progress:
                    st["progress_turns"] += 1
                st["costs"].append(float(cost))
                st["strategies"].add(r.get("strategy", "?"))

    result: dict[str, Any] = {
        "meta": {
            "note": "Selection-bias caveat: T3 turns happen when the agent is stuck or under pressure. "
            "Raw T3 progress rate may be lower than T2 even if T3 is better, because T3 faces harder turns. "
            "Use these rates for calibration direction, not as unbiased effect estimates.",
            "total_turns": sum(st["turns"] for st in stage_tier.values()),
            "total_progress_turns": sum(st["progress_turns"] for st in stage_tier.values()),
        },
        "stage_tier": {},
        "deltas": [],
    }

    for (stage, tier) in sorted(stage_tier.keys(), key=lambda x: (x[0], int(x[1]))):
        st = stage_tier[(stage, tier)]
        turns = st["turns"]
        progress = st["progress_turns"]
        rate = progress / turns if turns > 0 else 0.0
        sorted_costs = sorted(st["costs"])
        avg_cost = sum(st["costs"]) / len(st["costs"]) if st["costs"] else 0.0
        med_cost = sorted_costs[len(sorted_costs) // 2] if sorted_costs else 0.0
        p10_cost = sorted_costs[int(len(sorted_costs) * 0.1)] if len(sorted_costs) >= 10 else sorted_costs[0] if sorted_costs else 0.0
        p90_cost = sorted_costs[int(len(sorted_costs) * 0.9)] if len(sorted_costs) >= 10 else sorted_costs[-1] if sorted_costs else 0.0

        if turns >= 100:
            confidence = "HIGH"
        elif turns >= 30:
            confidence = "MEDIUM"
        elif turns >= 10:
            confidence = "LOW"
        else:
            confidence = "INSUFFICIENT"

        result["stage_tier"][f"{stage}_T{tier}"] = {
            "stage": stage,
            "tier": int(tier),
            "turns": turns,
            "progress_turns": progress,
            "progress_rate": round(rate, 4),
            "avg_cost": round(avg_cost, 6),
            "median_cost": round(med_cost, 6),
            "p10_cost": round(p10_cost, 6),
            "p90_cost": round(p90_cost, 6),
            "confidence": confidence,
            "strategies_seen": sorted(st["strategies"]),
        }

    # Tier upgrade deltas
    for stage in ["LOCALIZATION", "REPAIR", "VALIDATION"]:
        k2 = f"{stage}_T2"
        k3 = f"{stage}_T3"
        if k2 in result["stage_tier"] and k3 in result["stage_tier"]:
            s2 = result["stage_tier"][k2]
            s3 = result["stage_tier"][k3]
            if s2["turns"] >= 5 and s3["turns"] >= 5:
                delta_progress = s3["progress_rate"] - s2["progress_rate"]
                delta_cost = s3["avg_cost"] - s2["avg_cost"]
                result["deltas"].append({
                    "stage": stage,
                    "t2_rate": s2["progress_rate"],
                    "t3_rate": s3["progress_rate"],
                    "delta_progress": round(delta_progress, 4),
                    "delta_cost": round(delta_cost, 6),
                    "t2_turns": s2["turns"],
                    "t3_turns": s3["turns"],
                    "caveat": "Negative delta does NOT mean T3 is worse — T3 turns are selected on harder situations.",
                })

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Localization progress diagnostic (offline, read-only)
# ═══════════════════════════════════════════════════════════════════════════════

def diagnose_localization_progress(
    data_dir: str | Path,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Offline diagnostic for LOCALIZATION file-exploration activity.

    Uses the current runtime ``touched_file_paths`` field only.  Historical
    traces that lack this field are forensic-only and are not guessed from text.

    Returns a diagnostic summary with per-task file activity and extraction
    method breakdown.
    """
    data_dir = Path(data_dir)

    if manifest is not None:
        jsonl_files = [data_dir / entry["file"] for entry in manifest["runs"]]
    else:
        jsonl_files = sorted(data_dir.glob("*.jsonl"))

    loc_turns = 0
    loc_with_files = 0
    runtime_field_turns = 0
    missing_runtime_field_turns = 0
    task_file_activity: dict[str, dict] = defaultdict(lambda: {
        "loc_turns": 0,
        "loc_with_files": 0,
        "runtime_field_turns": 0,
        "missing_runtime_field_turns": 0,
        "unique_files": set(),
    })

    for fp in jsonl_files:
        if not fp.is_file() or fp.name.startswith("auto_budget"):
            continue
        try:
            with open(fp) as f:
                rows = [json.loads(line) for line in f if line.strip()]
        except (json.JSONDecodeError, OSError):
            continue

        for r in rows:
            iid = r.get("instance_id", "")
            if not iid:
                continue
            traces = r.get("turn_traces", [])
            for t in traces:
                if t.get("stage") != "LOCALIZATION":
                    continue
                loc_turns += 1
                task_file_activity[iid]["loc_turns"] += 1

                files_found: set[str] = set()
                tfp = t.get("touched_file_paths")
                if tfp is not None and isinstance(tfp, list):
                    runtime_field_turns += 1
                    task_file_activity[iid]["runtime_field_turns"] += 1
                    for p in tfp:
                        p_str = str(p).strip()
                        if p_str and "/tmp/" not in p_str:
                            files_found.add(p_str)
                else:
                    missing_runtime_field_turns += 1
                    task_file_activity[iid]["missing_runtime_field_turns"] += 1

                if files_found:
                    loc_with_files += 1
                    task_file_activity[iid]["loc_with_files"] += 1
                    task_file_activity[iid]["unique_files"].update(files_found)

    # Build per-task summary
    tasks_summary = {}
    for iid, activity in sorted(task_file_activity.items()):
        unique = sorted(activity["unique_files"])
        runtime_frac = (
            round(activity["runtime_field_turns"] / activity["loc_turns"], 4)
            if activity["loc_turns"] > 0 else 0.0
        )
        tasks_summary[iid] = {
            "loc_turns": activity["loc_turns"],
            "loc_with_files": activity["loc_with_files"],
            "file_activity_rate": round(
                activity["loc_with_files"] / activity["loc_turns"], 4
            ) if activity["loc_turns"] > 0 else 0.0,
            "unique_files_count": len(unique),
            "top_files": unique[:10],
            "runtime_field_fraction": runtime_frac,
            "missing_runtime_field_turns": activity["missing_runtime_field_turns"],
        }

    overall_rate = loc_with_files / loc_turns if loc_turns > 0 else 0.0
    runtime_available = runtime_field_turns > 0

    return {
        "meta": {
            "note": "Uses runtime touched_file_paths only; legacy traces without "
                    "that field are counted as missing instrumentation.",
            "caveat": "has_progress is always False for LOCALIZATION in runtime "
                      "traces because the progress signal only fires on file "
                      "modifications (REPAIR/VALIDATION), not on file exploration.",
            "total_loc_turns": loc_turns,
            "loc_turns_with_files": loc_with_files,
            "overall_file_activity_rate": round(overall_rate, 4),
            "runtime_field_available": runtime_available,
            "runtime_field_turns": runtime_field_turns,
            "missing_runtime_field_turns": missing_runtime_field_turns,
            "gold_patch_available": False,
        },
        "per_task": tasks_summary,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Matched-task progress de-bias (offline, read-only)
# ═══════════════════════════════════════════════════════════════════════════════


def matched_task_progress_summary(
    data_dir: str | Path,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute within-task T2-vs-T3 progress deltas to reduce selection bias.

    Instead of comparing raw T2 vs T3 rates across ALL tasks (which conflates
    tier effect with task difficulty), this groups turns by (stage, task) and
    computes deltas only where the same task has both T2 and T3 turns.

    Returns within-task deltas and a caveat about what this does/doesn't fix.
    """
    data_dir = Path(data_dir)

    if manifest is not None:
        jsonl_files = [data_dir / entry["file"] for entry in manifest["runs"]]
    else:
        jsonl_files = sorted(data_dir.glob("*.jsonl"))

    # (stage, task, tier) → list of has_progress bools
    cell: dict[tuple[str, str, str], list[bool]] = defaultdict(list)

    for fp in jsonl_files:
        if not fp.is_file() or fp.name.startswith("auto_budget"):
            continue
        try:
            with open(fp) as f:
                rows = [json.loads(line) for line in f if line.strip()]
        except (json.JSONDecodeError, OSError):
            continue
        for r in rows:
            iid = r.get("instance_id", "")
            if not iid:
                continue
            for t in r.get("turn_traces", []):
                stage = str(t.get("stage", "?"))
                tier = str(t.get("backend_tier", "?"))
                hp = bool(t.get("has_progress", False))
                cell[(stage, iid, tier)].append(hp)

    # Within-task deltas
    deltas = []
    stages = ["LOCALIZATION", "REPAIR", "VALIDATION"]
    for stage in stages:
        for iid in sorted({k[1] for k in cell if k[0] == stage}):
            t2_key = (stage, iid, "2")
            t3_key = (stage, iid, "3")
            if t2_key in cell and t3_key in cell:
                t2_rate = sum(cell[t2_key]) / len(cell[t2_key])
                t3_rate = sum(cell[t3_key]) / len(cell[t3_key])
                deltas.append({
                    "stage": stage,
                    "instance_id": iid,
                    "t2_turns": len(cell[t2_key]),
                    "t3_turns": len(cell[t3_key]),
                    "t2_rate": round(t2_rate, 4),
                    "t3_rate": round(t3_rate, 4),
                    "delta": round(t3_rate - t2_rate, 4),
                })

    # Count sign direction
    n_positive = sum(1 for d in deltas if d["delta"] > 0)
    n_negative = sum(1 for d in deltas if d["delta"] < 0)
    n_tie = sum(1 for d in deltas if d["delta"] == 0)

    return {
        "meta": {
            "note": "Within-task T2-vs-T3 comparison reduces (not eliminates) "
                    "selection bias. Same-task deltas control for task-level "
                    "difficulty but not for within-task turn difficulty: T3 "
                    "turns within the same task may still be harder because "
                    "the agent escalates when stuck.",
            "caveat": "Even within-task deltas may be biased if the agent "
                      "escalates selectively on harder subtask phases. Full "
                      "de-bias requires forced-tier randomization or replay.",
            "total_comparable_pairs": len(deltas),
            "n_positive": n_positive,
            "n_negative": n_negative,
            "n_tie": n_tie,
            "interpretation": (
                f"{n_positive} pairs show T3 > T2, "
                f"{n_negative} show T3 < T2, "
                f"{n_tie} ties. "
                "A balanced split (roughly equal pos/neg) suggests no "
                "consistent within-task tier effect after controlling for "
                "task identity — tier choice may not help within the same task."
            ) if deltas else "No comparable pairs found (need same task with both T2 and T3 turns).",
        },
        "deltas": deltas,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Value Matrix and Progress Calibration — offline foundation"
    )
    p.add_argument("--data-dir", default="data/runs",
                   help="Directory containing JSONL run files")
    p.add_argument("--manifest", default=None,
                   help="Path to clean-run manifest JSON (recommended)")
    p.add_argument("--output", default="-",
                   help="Output path for value matrix JSON (default: stdout)")
    p.add_argument("--progress-table", action="store_true",
                   help="Also output progress calibration table")
    p.add_argument("--localization-diag", action="store_true",
                   help="Also output offline localization diagnostic")
    p.add_argument("--matched-task", action="store_true",
                   help="Also output within-task progress de-bias summary")
    p.add_argument("--profile", choices=list(PROFILES.keys()) + ["all"],
                   default="all", help="Which profile to compute (default: all)")
    p.add_argument("--task-set", choices=("easy", "medium"), default=None,
                   help="Build a no-outcome bootstrap matrix for a compare task set")
    p.add_argument("--ids", default=None,
                   help="Comma-separated task IDs for a no-outcome bootstrap matrix")
    p.add_argument("--include-criticality-value", action="store_true",
                   help="Include outcome-free criticality_value profile from verifier breadth")
    p.add_argument("--limit", type=int, default=None,
                   help="Task count for --task-set bootstrap matrix")
    return p


def main(argv: list[str] | None = None) -> dict:
    args = _make_parser().parse_args(argv)

    if args.task_set or args.ids:
        from .lite_tasks import (
            load_compare_easy_tasks,
            load_compare_medium_tasks,
            load_swebench_lite_tasks,
        )

        if args.ids:
            ids = tuple(item.strip() for item in args.ids.split(",") if item.strip())
            if not ids:
                print("ERROR: --ids did not contain any task IDs", file=sys.stderr)
                sys.exit(1)
            tasks = load_swebench_lite_tasks(instance_ids=ids)
            task_source = f"bootstrap_ids:{','.join(ids)}"
        elif args.task_set == "medium":
            tasks = load_compare_medium_tasks(args.limit or 15)
            task_source = f"bootstrap_task_set:medium:{len(tasks)}"
        else:
            tasks = load_compare_easy_tasks(args.limit or 5)
            task_source = f"bootstrap_task_set:easy:{len(tasks)}"
        matrix = build_bootstrap_value_matrix(
            tasks,
            task_source=task_source,
            include_criticality_value=args.include_criticality_value,
        )
        output_text = json.dumps(matrix, indent=2, ensure_ascii=False)
        if args.output == "-":
            sys.stdout.write(output_text + "\n")
        else:
            out_path = Path(args.output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output_text + "\n")
            print(f"Written to {out_path}", file=sys.stderr)
        return matrix

    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        print(f"ERROR: data directory not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    # Load manifest if provided
    manifest = None
    if args.manifest:
        manifest = load_manifest(args.manifest)
        print(f"Using manifest: {args.manifest} ({len(manifest['runs'])} runs)", file=sys.stderr)

    records = scan_task_universe(data_dir, manifest=manifest)
    if not records:
        print("ERROR: no task records found", file=sys.stderr)
        sys.exit(1)

    # Select profiles
    if args.profile == "all":
        profiles = PROFILES
    else:
        profiles = {args.profile: PROFILES[args.profile]}

    matrix = build_value_matrix(records, profiles, manifest_meta=manifest)

    if args.progress_table:
        matrix["progress_calibration"] = calibrate_progress_table(data_dir)

    if args.localization_diag:
        matrix["localization_diagnostic"] = diagnose_localization_progress(
            data_dir, manifest=manifest
        )

    if args.matched_task:
        matrix["matched_task_progress"] = matched_task_progress_summary(
            data_dir, manifest=manifest
        )

    # Output
    output_text = json.dumps(matrix, indent=2, ensure_ascii=False)

    if args.output == "-":
        sys.stdout.write(output_text + "\n")
    else:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text + "\n")
        print(f"Written to {out_path}", file=sys.stderr)

    return matrix


if __name__ == "__main__":
    main()
