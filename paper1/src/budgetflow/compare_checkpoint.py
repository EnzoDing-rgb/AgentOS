"""Checkpoint + resume state for run_mini_swe_compare (L1: per-task, per-policy budget)."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def checkpoint_path_for(stem: str, runs_dir: Path) -> Path:
    return runs_dir / f"{stem}.checkpoint.json"


@dataclass
class StrategyCheckpoint:
    batch_cap: float
    batch_spent: float = 0.0
    completed_tasks: list[str] = field(default_factory=list)
    in_flight_task: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_cap": self.batch_cap if self.batch_cap is not None else 0.0,
            "batch_spent": self.batch_spent,
            "completed_tasks": list(self.completed_tasks),
            "in_flight_task": self.in_flight_task,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyCheckpoint:
        raw_cap = data.get("batch_cap")
        if raw_cap is None:
            batch_cap = 0.0
        else:
            batch_cap = float(raw_cap)
        return cls(
            batch_cap=batch_cap,
            batch_spent=float(data.get("batch_spent", 0.0)),
            completed_tasks=list(data.get("completed_tasks") or []),
            in_flight_task=data.get("in_flight_task"),
        )


class CompareCheckpointStore:
    def __init__(self, path: Path, *, stem: str, total_runs: int) -> None:
        self.path = path
        self.stem = stem
        self.total_runs = total_runs
        self.strategies: dict[str, StrategyCheckpoint] = {}
        if path.is_file():
            self._load()

    def _load(self) -> None:
        raw = json.loads(self.path.read_text())
        self.stem = raw.get("stem", self.stem)
        self.total_runs = int(raw.get("total_runs", self.total_runs))
        for name, payload in (raw.get("strategies") or {}).items():
            self.strategies[name] = StrategyCheckpoint.from_dict(payload)

    def ensure_strategy(self, name: str, batch_cap: float) -> StrategyCheckpoint:
        if name not in self.strategies:
            self.strategies[name] = StrategyCheckpoint(batch_cap=batch_cap)
        else:
            self.strategies[name].batch_cap = batch_cap
        return self.strategies[name]

    def mark_in_flight(self, strategy: str, instance_id: str, batch_cap: float) -> None:
        st = self.ensure_strategy(strategy, batch_cap)
        st.in_flight_task = instance_id
        self.save()

    def mark_task_done(self, strategy: str, instance_id: str, *, batch_spent: float, batch_cap: float) -> None:
        st = self.ensure_strategy(strategy, batch_cap)
        st.batch_spent = batch_spent
        st.in_flight_task = None
        if instance_id not in st.completed_tasks:
            st.completed_tasks.append(instance_id)
        self.save()

    def initial_spent(self, strategy: str) -> float:
        return self.strategies.get(strategy, StrategyCheckpoint(0.0)).batch_spent

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "stem": self.stem,
            "total_runs": self.total_runs,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "strategies": {name: st.to_dict() for name, st in self.strategies.items()},
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


_STRATEGY_ABBREV: dict[str, str] = {
    "all_spark_tight": "as-T",
    "all_spark_loose": "as-L",
    # Backward compatibility for old run logs.
    "all_flash_tight": "as-T",
    "all_flash_loose": "as-L",
    "budget_only_tight": "bo-T",
    "budget_only_loose": "bo-L",
    "budgetflow_full_tight": "bf-T",
    "budgetflow_full_loose": "bf-L",
    "all_pro": "apro",
    "all_t3": "t3",
    "all_gpt53": "t3",
    "all_gpt54": "t3",
}


def strategy_abbrev(name: str) -> str:
    return _STRATEGY_ABBREV.get(name, name[:10])


class StrategyScoreboard:
    """Live resolved/done counts per compare policy (thread-safe)."""

    def __init__(self, strategy_names: list[str]) -> None:
        self._lock = threading.Lock()
        self._names = list(strategy_names)
        self._resolved: dict[str, int] = {n: 0 for n in strategy_names}
        self._done: dict[str, int] = {n: 0 for n in strategy_names}

    def record(self, strategy: str, *, resolved: bool) -> None:
        with self._lock:
            self._done[strategy] = self._done.get(strategy, 0) + 1
            if resolved:
                self._resolved[strategy] = self._resolved.get(strategy, 0) + 1

    def seed_from_resolved(self, resolved_by_strategy: dict[str, list[bool]]) -> None:
        with self._lock:
            for name in self._names:
                flags = resolved_by_strategy.get(name, [])
                self._done[name] = len(flags)
                self._resolved[name] = sum(1 for f in flags if f)

    def format_line(self) -> str:
        with self._lock:
            parts = [
                f"{strategy_abbrev(name)} {self._resolved.get(name, 0)}/{self._done.get(name, 0)}"
                for name in self._names
            ]
        return "strategies: " + " | ".join(parts)


class GlobalRunProgress:
    """Thread-safe global (policy×task) progress for heartbeats and PASS/FAIL lines."""

    def __init__(self, total: int) -> None:
        self.total = total
        self._lock = threading.Lock()
        self._done = 0
        self._in_flight = 0

    def start_task(self) -> None:
        with self._lock:
            self._in_flight += 1

    def finish_task(self) -> int:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._done += 1
            return self._done

    def snapshot(self) -> tuple[int, int, int]:
        with self._lock:
            return self.total, self._done, self._in_flight

    def seed_done(self, count: int) -> None:
        with self._lock:
            self._done = max(0, min(count, self.total))

    def format_global(self, scoreboard: StrategyScoreboard | None = None) -> str:
        total, done, running = self.snapshot()
        base = f"global total={total} done={done} running={running}"
        if scoreboard is None:
            return base
        return f"{base} | {scoreboard.format_line()}"

    def format_banner(self, scoreboard: StrategyScoreboard | None = None) -> str:
        """Two-line banner: global counts + per-strategy resolved/done."""
        total, done, running = self.snapshot()
        lines = [f"global total={total} done={done} running={running}"]
        if scoreboard is not None:
            lines.append(scoreboard.format_line())
        return "\n".join(lines)
