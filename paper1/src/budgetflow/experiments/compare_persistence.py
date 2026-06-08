"""Artifact state and JSONL persistence for compare runs."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from budgetflow.auto_budget import AutoBudgetMemory
from budgetflow.compare_checkpoint import GlobalRunProgress, StrategyScoreboard
from budgetflow.experiment_observability import enrich_routing_observability
from budgetflow.experiments.compare_config import CompareStrategy, fmt_usd as _fmt_usd
from budgetflow.experiments.compare_summary import (
    _append_summary,
    _tier_ratios,
    _write_summary_file,
)
from budgetflow.failure_classification import classify_failure


@dataclass
class CompareRunState:
    summary_lines: list[str]
    resolved_by_strategy: dict[str, list[bool]]
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
        self.runs_done += 1
        self.resolved_by_strategy.setdefault(name, []).append(bool(record.get("harness_resolved")))
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


def write_auto_budget_memory(memory: AutoBudgetMemory, record: dict[str, Any]) -> None:
    forensic = record.get("forensic_summary") or {}
    features = record.get("auto_budget_features") or record.get("task_features") or {}
    mem = AutoBudgetMemory.build_record(
        instance_id=str(record.get("instance_id", "")),
        repo=str(record.get("instance_id", "")).rsplit("__", 1)[0].replace("__", "/"),
        strategy=str(record.get("strategy", "")),
        routing=str(record.get("routing", "")),
        resolved=bool(record.get("harness_resolved")),
        harness_resolved=bool(record.get("harness_resolved")),
        failure_class=str(record.get("failure_class") or ""),
        forensic_primary_axis=str(forensic.get("primary_axis") or record.get("failure_class") or ""),
        total_cost=float(record.get("total_cost") or 0.0),
        estimated_task_cap=record.get("estimated_task_cap"),
        estimated_task_cost=record.get("estimated_task_cost"),
        patch_extracted=bool(record.get("patch_extracted")),
        agent_gold_edited=bool(record.get("agent_gold_edited")),
        llm_turns=int(record.get("llm_turns") or 0),
        patch_lines=int(features.get("patch_lines", 0)),
        f2p_count=int(features.get("f2p_count", 0)),
        p2p_count=int(features.get("p2p_count", 0)),
        problem_length=int(features.get("problem_length", 0)),
        gold_file_count=len(record.get("agent_gold_files") or []),
        run_series=str(record.get("run_series", "")),
        run_id=str(record.get("run_id") or record.get("attempt_id") or record.get("run_series") or ""),
        dominant_tier=str(record.get("dominant_tier") or ""),
        exit_status=str(record.get("exit_status") or ""),
        detail=str(record.get("detail") or ""),
    )
    memory.write_record(mem)


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
    auto_budget_memory: AutoBudgetMemory | None = None,
    no_auto_budget_learn: bool = False,
) -> None:
    with io_lock:
        record["budget_learning_update_written"] = False
        record["budget_learning_memory_path"] = (
            str(auto_budget_memory._path or "") if auto_budget_memory is not None else ""
        )
        record["budget_learning_applied_to_cap"] = bool(record.get("auto_budget_enabled"))
        if auto_budget_memory is not None and not no_auto_budget_learn:
            write_auto_budget_memory(auto_budget_memory, record)
            record["budget_learning_update_written"] = True

        enrich_value(record)
        enrich_routing_observability(record)

        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.flush()
        _, done, _ = global_progress.snapshot()
        _append_summary(state.summary_lines, record, index=done, total=total_runs)
        state.ingest_record(record, strategy_name=str(record.get("strategy") or ""))
        if scoreboard is not None:
            scoreboard.record(str(record.get("strategy") or ""), resolved=bool(record.get("harness_resolved")))
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
    if not jsonl_path.is_file():
        return set()
    done: set[tuple[str, str]] = set()
    bad_exits = frozenset({"BadRequestError"})
    for line in jsonl_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if skip_bad and record.get("exit_status") in bad_exits:
            continue
        if skip_bad and record.get("total_cost", 1) == 0 and record.get("llm_turns", 0) <= 1:
            continue
        strategy = normalize_strategy(str(record.get("strategy") or ""))
        task = record.get("instance_id")
        if strategy and task:
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
        cap_label = "planned_cap" if mode == "dynamic_task_caps" else "per_task_cap" if mode == "per_task_cap" else "shared_cap"
        display_cap = batch_caps.get(cfg.name) if mode in {"per_task_cap", "dynamic_task_caps"} else batch_cap
        state.summary_lines.append(
            f"=== BATCH START strategy={cfg.name} {cap_label}={_fmt_usd(display_cap)} ==="
        )
        state.batch_spent_by_strategy[cfg.name] = batch_spent
        batch_avail = (
            max(0.0, float(display_cap or 0.0) - batch_spent)
            if mode in {"per_task_cap", "dynamic_task_caps"} and display_cap is not None
            else governor_avail(batch_records)
        )
        state.summary_lines.append(
            f"=== BATCH END strategy={cfg.name} resolved="
            f"{sum(1 for r in batch_records if r['harness_resolved'])}/{len(batch_records)} "
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
    )


def governor_avail(batch_records: list[dict[str, Any]]) -> float:
    if not batch_records:
        return 0.0
    return float(batch_records[-1].get("batch_available") or 0.0)
