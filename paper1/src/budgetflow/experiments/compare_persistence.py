"""Artifact state and JSONL persistence for compare runs."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from budgetflow.compare_checkpoint import GlobalRunProgress, StrategyScoreboard
from budgetflow.experiment_observability import enrich_routing_observability
from budgetflow.experiments.compare_config import CompareStrategy, fmt_usd as _fmt_usd
from budgetflow.experiments.compare_summary import (
    _append_summary,
    _tier_ratios,
    _write_summary_file,
)
from budgetflow.failure_classification import classify_failure
from budgetflow.run_series import completed_scoreable_keys

_PLANNED_CAP_MODES = frozenset({"per_task_cap", "budgetflow_planned_task_budget"})


@dataclass
class CompareRunState:
    summary_lines: list[str]
    resolved_by_strategy: dict[str, list[bool]]
    score_status_by_strategy: dict[str, list[str]]
    task_cost_by_strategy: dict[str, list[float]]
    batch_spent_by_strategy: dict[str, float]
    turns_by_strategy: dict[str, list[int]]
    tier_mix_by_strategy: dict[str, list[dict[int, float]]]
    failure_by_strategy: dict[str, dict[str, int]]
    resolved_value_by_strategy: dict[str, list[float]] | None = None
    task_value_by_strategy: dict[str, list[float]] | None = None
    runs_done: int = 0

    @classmethod
    def empty(cls, header_lines: list[str]) -> "CompareRunState":
        return cls(
            summary_lines=list(header_lines),
            resolved_by_strategy={},
            score_status_by_strategy={},
            task_cost_by_strategy={},
            batch_spent_by_strategy={},
            turns_by_strategy={},
            tier_mix_by_strategy={},
            failure_by_strategy={},
            resolved_value_by_strategy={},
            task_value_by_strategy={},
        )

    def ingest_record(self, record: dict[str, Any], *, strategy_name: str | None = None) -> None:
        name = strategy_name or str(record.get("strategy") or "")
        if not name:
            return
        score_status = str(record.get("score_status") or "")
        if score_status not in {"pass", "true_fail", "abort"}:
            return
        self.runs_done += 1
        self.resolved_by_strategy.setdefault(name, []).append(score_status == "pass")
        self.score_status_by_strategy.setdefault(name, []).append(score_status)
        self.task_cost_by_strategy.setdefault(name, []).append(float(record.get("total_cost") or 0.0))
        self.turns_by_strategy.setdefault(name, []).append(int(record.get("llm_turns") or 0))
        picks = record.get("backend_picks") or []
        self.tier_mix_by_strategy.setdefault(name, []).append(_tier_ratios(picks))
        failure_class = str(record.get("failure_class") or classify_failure(record))
        failures = self.failure_by_strategy.setdefault(name, {})
        failures[failure_class] = failures.get(failure_class, 0) + 1
        self.batch_spent_by_strategy[name] = sum(self.task_cost_by_strategy.get(name, []))
        if self.resolved_value_by_strategy is not None:
            self.resolved_value_by_strategy.setdefault(name, []).append(float(record.get("resolved_value") or 0.0))
        if self.task_value_by_strategy is not None:
            self.task_value_by_strategy.setdefault(name, []).append(float(record.get("task_value") or 1.0))


def rebuild_state_from_jsonl(
    path: Path,
    header_lines: list[str],
    *,
    normalize_strategy: Callable[[str], str],
    enrich_value: Callable[[dict[str, Any]], dict[str, Any]],
) -> CompareRunState:
    state = CompareRunState.empty(header_lines)
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = normalize_strategy(str(record.get("strategy") or ""))
        if not name:
            continue
        # Skip known garbage: provider reject records with no real work done.
        if record.get("exit_status") == "BadRequestError" and record.get("total_cost", 1) == 0:
            continue
        if record.get("task_value_profile") is None:
            enrich_value(record)
        state.ingest_record(record, strategy_name=name)
    return state


def persist_task_record(
    state: CompareRunState,
    record: dict[str, Any],
    *,
    handle: TextIO,
    io_lock: threading.Lock,
    total_runs: int,
    tasks_per_strategy: int,
    global_progress: GlobalRunProgress,
    scoreboard: StrategyScoreboard | None,
    summary_path: Path,
    strategy_names: list[str],
    batch_caps: dict[str, float | None],
    budget_modes: dict[str, str],
    started: float,
    out_path: Path,
    value_profile: str,
    enrich_value: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    with io_lock:
        enrich_value(record)
        enrich_routing_observability(record)

        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        _, done, _ = global_progress.snapshot()
        _append_summary(state.summary_lines, record, index=done, total=total_runs)
        state.ingest_record(record, strategy_name=str(record.get("strategy") or ""))
        if scoreboard is not None:
            scoreboard.record(
                str(record.get("strategy") or ""),
                score_status=str(record.get("score_status") or ""),
                resolved=bool(record.get("harness_resolved")),
            )
        write_summary_snapshot(
            summary_path,
            state=state,
            strategy_names=strategy_names,
            batch_caps=batch_caps,
            budget_modes=budget_modes,
            started=started,
            out_path=out_path,
            total_runs=total_runs,
            tasks_per_strategy=tasks_per_strategy,
            global_line=global_progress.format_global(scoreboard),
            value_profile=value_profile,
        )


def completed_keys(
    jsonl_path: Path,
    *,
    normalize_strategy: Callable[[str], str],
    skip_bad: bool = False,
) -> set[tuple[str, str]]:
    # Resume idempotency is defined by unique scoreable policy-task pairs.
    # Bad zero-cost provider rows and abort rows are intentionally retryable.
    if not skip_bad:
        return completed_scoreable_keys(jsonl_path, normalize_strategy=normalize_strategy)
    if not jsonl_path.is_file():
        return set()
    done: set[tuple[str, str]] = set()
    for line in jsonl_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        strategy = normalize_strategy(str(record.get("strategy") or ""))
        task = record.get("instance_id")
        if not strategy or not task:
            continue
        score_status = str(record.get("score_status") or "")
        if record.get("exit_status") == "BadRequestError":
            continue
        if score_status in {"pass", "true_fail"}:
            done.add((strategy, str(task)))
    return done


def ingest_batch_footer(
    state: CompareRunState,
    cfg: CompareStrategy,
    batch_records: list[dict[str, Any]],
    batch_spent: float,
    batch_cap: float,
    *,
    strategy_names: list[str],
    batch_caps: dict[str, float | None],
    budget_modes: dict[str, str],
    summary_path: Path,
    started: float,
    out_path: Path,
    total_runs: int,
    tasks_per_strategy: int,
    io_lock: threading.Lock,
    global_progress: GlobalRunProgress,
    value_profile: str,
) -> None:
    if not batch_records:
        return
    with io_lock:
        mode = budget_modes.get(cfg.name, "shared")
        cap_label = (
            "per_task_cap" if mode == "per_task_cap"
            else "planned_task_budget" if mode == "budgetflow_planned_task_budget"
            else "shared_cap"
        )
        display_cap = batch_caps.get(cfg.name) if mode in _PLANNED_CAP_MODES else batch_cap
        state.summary_lines.append(
            f"=== BATCH START strategy={cfg.name} {cap_label}={_fmt_usd(display_cap)} ==="
        )
        state.batch_spent_by_strategy[cfg.name] = batch_spent
        batch_avail = (
            max(0.0, float(display_cap or 0.0) - batch_spent)
            if mode in _PLANNED_CAP_MODES and display_cap is not None
            else governor_avail(batch_records)
        )
        state.summary_lines.append(
            f"=== BATCH END strategy={cfg.name} "
            f"pass={sum(1 for r in batch_records if (str(r.get('score_status') or '') == 'pass' or (not r.get('score_status') and r.get('harness_resolved') is True)))} "
            f"true_fail={sum(1 for r in batch_records if str(r.get('score_status') or '') == 'true_fail')} "
            f"abort={sum(1 for r in batch_records if str(r.get('score_status') or '') == 'abort')} "
            f"rows={len(batch_records)} "
            f"batch_spent={_fmt_usd(batch_spent)} batch_avail={_fmt_usd(batch_avail)} ==="
        )
        state.summary_lines.append("")
        write_summary_snapshot(
            summary_path,
            state=state,
            strategy_names=strategy_names,
            batch_caps=batch_caps,
            budget_modes=budget_modes,
            started=started,
            out_path=out_path,
            total_runs=total_runs,
            tasks_per_strategy=tasks_per_strategy,
            global_line=global_progress.format_global(),
            value_profile=value_profile,
        )


def write_summary_snapshot(
    path: Path,
    *,
    state: CompareRunState,
    strategy_names: list[str],
    batch_caps: dict[str, float | None],
    budget_modes: dict[str, str],
    started: float,
    out_path: Path,
    total_runs: int,
    tasks_per_strategy: int,
    global_line: str | None,
    value_profile: str,
) -> None:
    _write_summary_file(
        path,
        summary_lines=state.summary_lines,
        strategy_names=strategy_names,
        resolved_by_strategy=state.resolved_by_strategy,
        task_cost_by_strategy=state.task_cost_by_strategy,
        batch_spent_by_strategy=state.batch_spent_by_strategy,
        turns_by_strategy=state.turns_by_strategy,
        tier_mix_by_strategy=state.tier_mix_by_strategy,
        failure_by_strategy=state.failure_by_strategy,
        batch_caps=batch_caps,
        budget_modes=budget_modes,
        started=started,
        out_path=out_path,
        runs_done=state.runs_done,
        total_runs=total_runs,
        tasks_per_strategy=tasks_per_strategy,
        global_line=global_line,
        resolved_value_by_strategy=state.resolved_value_by_strategy,
        task_value_by_strategy=state.task_value_by_strategy,
        value_profile=value_profile,
        score_status_by_strategy=state.score_status_by_strategy,
    )


def governor_avail(batch_records: list[dict[str, Any]]) -> float:
    if not batch_records:
        return 0.0
    return float(batch_records[-1].get("batch_available") or 0.0)
