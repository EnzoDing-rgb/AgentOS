"""Value-driven token-efficiency metrics for BudgetFlow.

Tier 1 primary metric is Yield: total resolved task value at a fixed budget.
Yield per Dollar is the main efficiency diagnostic. Resolved task count and
coverage are supporting diagnostics, not the objective.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .failure_classification import is_score_abort, is_score_pass, is_score_true_fail


@dataclass(frozen=True)
class ValueSourceInfo:
    """Audit contract for task-value evidence used in a run."""

    kind: str
    evidence_role: str
    confidence: str
    primary_t1: bool


@dataclass
class ValueEfficiencyContext:
    profile: str = "equal"
    matrix_path: str | None = None
    lookup: dict[str, float] | None = None
    effort_lookup: dict[str, float] | None = None
    median_task_value: float = 1.0
    source_info: ValueSourceInfo = ValueSourceInfo(
        kind="equal_sanity",
        evidence_role="sanity_fallback",
        confidence="none",
        primary_t1=False,
    )

    @property
    def objective(self) -> str:
        return "t1_value_efficiency" if self.source_info.primary_t1 else "t2_value_source_diagnostic"

    @property
    def source_class(self) -> str:
        return self.source_info.kind

    @property
    def evidence_role(self) -> str:
        return self.source_info.evidence_role

    @property
    def confidence(self) -> str:
        return self.source_info.confidence

    @property
    def is_pre_registered_manual(self) -> bool:
        return self.source_info.kind == "pre_registered_manual"

    @property
    def is_primary_value_evidence(self) -> bool:
        return self.source_info.primary_t1

    def init(
        self,
        *,
        value_profile: str = "equal",
        value_matrix_path: str | None = None,
        value_source_kind: str | None = None,
    ) -> None:
        self.profile = value_profile
        self.matrix_path = value_matrix_path
        self.lookup = None
        self.effort_lookup = None
        self.median_task_value = 1.0
        artifact: dict | None = None
        if value_matrix_path:
            artifact = json.loads(Path(value_matrix_path).read_text())
            self.lookup = _extract_lookup(artifact, value_profile)
            if self.lookup:
                self.median_task_value = _median(self.lookup.values())
            elif value_profile != "equal":
                print(
                    f"[value_observability] WARNING: profile '{value_profile}' not found "
                    f"in value matrix {value_matrix_path}",
                    flush=True,
                )
            # Load effort heuristic (diagnostic only, not Claim 1 value).
            self.effort_lookup = _extract_effort_lookup(artifact)
        self.source_info = _resolve_value_source_info(
            profile=value_profile,
            value_matrix_path=value_matrix_path,
            value_source_kind=value_source_kind,
            artifact=artifact,
            lookup=self.lookup,
        )

    def task_value(self, instance_id: str) -> tuple[float, str]:
        if self.lookup is not None and instance_id in self.lookup:
            return float(self.lookup[instance_id]), "value_matrix"
        if self.profile == "equal":
            return 1.0, "equal_sanity"
        raise SystemExit(
            f"[value_observability] FATAL: instance_id='{instance_id}' not found "
            f"in value matrix {self.matrix_path} for profile '{self.profile}'. "
            f"Either add this task to the matrix or use --value-profile=equal."
        )

    def task_effort(self, instance_id: str) -> tuple[float | None, str]:
        """Return (effort_heuristic, effort_source) or (None, \"none\")."""
        if self.effort_lookup is not None and instance_id in self.effort_lookup:
            return float(self.effort_lookup[instance_id]), "bootstrap_heuristic"
        return None, "none"

    def missing_task_values(self, instance_ids: list[str] | tuple[str, ...]) -> list[str]:
        """Return task IDs that would fail value lookup for the active profile."""
        if self.profile == "equal":
            return []
        lookup = self.lookup or {}
        return [instance_id for instance_id in instance_ids if instance_id not in lookup]

    def enrich_record(self, record: dict) -> dict:
        """Add value-efficiency observability fields. Mutates and returns."""
        instance_id = str(record.get("instance_id", ""))
        resolved = is_score_pass(record)
        scoreable = not is_score_abort(record)
        task_cost = float(record.get("total_cost") or 0)
        task_value, value_source = self.task_value(instance_id)
        task_effort, effort_source = self.task_effort(instance_id)
        resolved_value = task_value if resolved else 0.0
        scoreable_cost = task_cost if scoreable else 0.0
        yield_per_dollar = resolved_value / scoreable_cost if scoreable_cost > 0 else 0.0

        routing = str(record.get("routing", ""))
        va_active = routing in {"segment_value_aware", "value_aware_task_level"}
        record["value_objective"] = self.objective
        record["task_value_profile"] = self.profile
        record["task_value_source_class"] = self.source_class
        record["task_value_evidence_role"] = self.evidence_role
        record["task_value_confidence"] = self.confidence
        record["task_value_primary_t1"] = self.is_primary_value_evidence
        record["task_value"] = task_value
        record["task_effort"] = task_effort
        record["task_effort_source"] = effort_source
        record["resolved_value"] = resolved_value
        record["scoreable_cost"] = scoreable_cost
        record["value_source"] = value_source
        record["value_matrix_artifact"] = self.matrix_path
        record["yield_per_dollar"] = round(yield_per_dollar, 6)
        record["va_active"] = va_active
        if va_active:
            raw = task_value / max(0.001, self.median_task_value) if self.median_task_value > 0 else 1.0
            record["task_value_multiplier"] = round(max(0.5, min(2.0, raw)), 4)
        else:
            record["task_value_multiplier"] = None

        record["budget_source"] = "budget_plan_or_static_cap"
        record["budget_source_schema"] = "shared_batch_v1"
        return record

    def summary_for_strategy(self, records: list[dict]) -> dict:
        resolved_count = sum(1 for r in records if is_score_pass(r))
        true_fail_count = sum(1 for r in records if is_score_true_fail(r))
        abort_count = sum(1 for r in records if is_score_abort(r))
        total_cost = sum(float(r.get("scoreable_cost", r.get("total_cost") or 0)) for r in records if not is_score_abort(r))
        abort_cost = sum(float(r.get("total_cost") or 0) for r in records if is_score_abort(r))
        resolved_value = sum(float(r.get("resolved_value") or 0) for r in records if not is_score_abort(r))
        total_task_value = sum(float(r.get("task_value") or 1.0) for r in records if not is_score_abort(r))
        yield_per_dollar = resolved_value / total_cost if total_cost > 0 else 0.0
        yield_coverage = resolved_value / total_task_value if total_task_value > 0 else 0.0
        return {
            "resolved_count": resolved_count,
            "true_fail_count": true_fail_count,
            "abort_count": abort_count,
            "abort_cost": round(abort_cost, 6),
            "scoreable_count": resolved_count + true_fail_count,
            "total_cost": round(total_cost, 6),
            "resolved_value": round(resolved_value, 6),
            "total_task_value": round(total_task_value, 6),
            "yield_score": round(resolved_value, 6),
            "yield_coverage": round(yield_coverage, 6),
            "yield_per_dollar": round(yield_per_dollar, 6),
            "value_profile": self.profile,
            "task_value_source_class": self.source_class,
            "task_value_evidence_role": self.evidence_role,
            "task_value_confidence": self.confidence,
            "task_value_primary_t1": self.is_primary_value_evidence,
            "value_source": self.matrix_path or "equal_sanity",
            "value_objective": self.objective,
        }


def _extract_lookup(artifact: dict, profile: str) -> dict[str, float] | None:
    tasks = artifact.get("tasks")
    if isinstance(tasks, dict) and tasks:
        lookup: dict[str, float] = {}
        for instance_id, task_data in tasks.items():
            if not isinstance(task_data, dict):
                continue
            tv = task_data.get("task_value")
            if isinstance(tv, dict) and profile in tv:
                lookup[instance_id] = float(tv[profile])
        if lookup:
            return lookup

    return None


def _extract_effort_lookup(artifact: dict) -> dict[str, float] | None:
    """Extract per-task effort heuristic from value matrix.

    Reads ``task_effort.bootstrap_heuristic`` (North Star schema).
    Returns None when no effort data is present.
    """
    tasks = artifact.get("tasks")
    if isinstance(tasks, dict) and tasks:
        lookup: dict[str, float] = {}
        for instance_id, task_data in tasks.items():
            if not isinstance(task_data, dict):
                continue
            te = task_data.get("task_effort")
            if isinstance(te, dict):
                effort = te.get("bootstrap_heuristic")
                if effort is not None:
                    lookup[instance_id] = float(effort)
        if lookup:
            return lookup
    return None


def _resolve_value_source_info(
    *,
    profile: str,
    value_matrix_path: str | None,
    value_source_kind: str | None,
    artifact: dict | None,
    lookup: dict[str, float] | None,
) -> ValueSourceInfo:
    requested = value_source_kind or _infer_value_source_kind(profile, artifact, lookup)
    valid = {
        "equal_sanity",
        "bootstrap_heuristic",
        "pre_registered_manual",
        "value_matrix_diagnostic",
        "learned_calibrated",
    }
    if requested not in valid:
        raise SystemExit(
            f"[value_observability] FATAL: unsupported value_source_kind='{requested}'. "
            f"Expected one of {sorted(valid)}."
        )
    if requested == "equal_sanity":
        if profile != "equal":
            raise SystemExit(
                "[value_observability] FATAL: value_source_kind=equal_sanity "
                "requires --value-profile=equal."
            )
        return ValueSourceInfo(
            kind="equal_sanity",
            evidence_role="sanity_fallback",
            confidence="none",
            primary_t1=False,
        )
    if requested == "bootstrap_heuristic":
        if profile == "equal" or lookup is None:
            raise SystemExit(
                "[value_observability] FATAL: value_source_kind=bootstrap_heuristic "
                "requires a non-equal profile covered by --value-matrix."
            )
        return ValueSourceInfo(
            kind="bootstrap_heuristic",
            evidence_role="heuristic_bootstrap",
            confidence="medium",
            primary_t1=False,
        )
    if requested == "pre_registered_manual":
        if profile == "equal" or not value_matrix_path or lookup is None:
            raise SystemExit(
                "[value_observability] FATAL: value_source_kind=pre_registered_manual "
                "requires a non-equal profile covered by --value-matrix."
            )
        return ValueSourceInfo(
            kind="pre_registered_manual",
            evidence_role="primary_t1",
            confidence="manual",
            primary_t1=True,
        )
    if requested == "learned_calibrated":
        if profile == "equal" or not value_matrix_path or lookup is None:
            raise SystemExit(
                "[value_observability] FATAL: value_source_kind=learned_calibrated "
                "requires a non-equal profile covered by --value-matrix."
            )
        return ValueSourceInfo(
            kind="learned_calibrated",
            evidence_role="learned_t1",
            confidence="high",
            primary_t1=True,
        )
    if profile == "equal" or lookup is None:
        raise SystemExit(
            "[value_observability] FATAL: value_source_kind=value_matrix_diagnostic "
            "requires a non-equal profile covered by --value-matrix."
        )
    return ValueSourceInfo(
        kind="value_matrix_diagnostic",
        evidence_role="value_matrix_diagnostic",
        confidence="medium",
        primary_t1=False,
    )


def _infer_value_source_kind(
    profile: str,
    artifact: dict | None,
    lookup: dict[str, float] | None,
) -> str:
    if profile == "equal":
        return "equal_sanity"
    meta = artifact.get("meta", {}) if isinstance(artifact, dict) else {}
    raw = str(
        meta.get("value_source_kind")
        or meta.get("source_kind")
        or meta.get("source_class")
        or ""
    )
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    if normalized in {"pre_registered_manual", "pre_registered_manual_value", "manual_pre_registered"}:
        return "pre_registered_manual"
    if normalized in {"learned_calibrated", "learned_value", "calibrated_value"}:
        return "learned_calibrated"
    if normalized in {"bootstrap_heuristic", "bootstrap_pre_registered_metadata"} or profile.startswith("bootstrap_"):
        return "bootstrap_heuristic"
    if lookup is not None:
        return "value_matrix_diagnostic"
    return "value_matrix_diagnostic"


def _median(values) -> float:
    vals = sorted(float(v) for v in values)
    if not vals:
        return 1.0
    n = len(vals)
    return (vals[n // 2 - 1] + vals[n // 2]) / 2.0 if n % 2 == 0 else vals[n // 2]
