"""Value proxy noise robustness analysis.

Offline analysis: adds controlled noise to task_value and measures
whether strategy comparison conclusions (resolved_value, RVPD, winner
stability) remain stable.  Purpose is NOT to prove the proxy is the
true value — it is to show that reasonable proxy uncertainty does not
flip the qualitative conclusion.

No API calls needed.  Runs on JSONL experiment output.
"""

from __future__ import annotations

import json
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class NoiseConfig:
    """Noise level for a single robustness trial."""
    label: str
    multiplier_range: tuple[float, float]  # e.g. (0.75, 1.25) for ±25%
    seed: int = 42


@dataclass
class StrategySummary:
    strategy: str
    resolved_count: int
    total_tasks: int
    total_cost: float
    total_resolved_value: float
    rvpd: float = 0.0

    @property
    def pass_rate(self) -> float:
        return self.resolved_count / max(1, self.total_tasks)


@dataclass
class TrialResult:
    trial: int
    noise_config: NoiseConfig
    summaries: dict[str, StrategySummary] = field(default_factory=dict)
    rvpd_winner: str = ""
    resolved_value_winner: str = ""


def default_noise_configs() -> list[NoiseConfig]:
    return [
        NoiseConfig("±0% (baseline)", (1.0, 1.0), seed=42),
        NoiseConfig("±10%", (0.90, 1.10), seed=100),
        NoiseConfig("±25%", (0.75, 1.25), seed=200),
        NoiseConfig("±50%", (0.50, 1.50), seed=300),
    ]


def load_rows(jsonl_path: str | Path) -> list[dict]:
    path = Path(jsonl_path)
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def compute_summary(rows: list[dict], noise_config: NoiseConfig | None = None) -> dict[str, StrategySummary]:
    """Compute per-strategy summaries, optionally with value noise applied."""
    rng = random.Random(noise_config.seed if noise_config else 42)
    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_strategy[r["strategy"]].append(r)

    summaries: dict[str, StrategySummary] = {}
    for strategy, strategy_rows in by_strategy.items():
        resolved = 0
        total_cost = 0.0
        total_rv = 0.0
        for r in strategy_rows:
            tv = float(r.get("task_value", 1.0))
            if noise_config and noise_config.multiplier_range != (1.0, 1.0):
                scale = rng.uniform(*noise_config.multiplier_range)
                tv = tv * scale
            total_cost += float(r.get("task_cost") or r.get("total_cost") or 0)
            if r.get("harness_resolved"):
                resolved += 1
                total_rv += tv
        n = len(strategy_rows)
        summaries[strategy] = StrategySummary(
            strategy=strategy,
            resolved_count=resolved,
            total_tasks=n,
            total_cost=total_cost,
            total_resolved_value=total_rv,
            rvpd=total_rv / max(0.001, total_cost),
        )
    return summaries


def run_noise_trials(
    rows: list[dict],
    noise_configs: list[NoiseConfig] | None = None,
    trials_per_config: int = 100,
) -> list[TrialResult]:
    if noise_configs is None:
        noise_configs = default_noise_configs()

    results: list[TrialResult] = []
    for cfg in noise_configs:
        for trial in range(trials_per_config):
            trial_cfg = NoiseConfig(cfg.label, cfg.multiplier_range, seed=cfg.seed + trial * 1000)
            summaries = compute_summary(rows, noise_config=trial_cfg)
            strategies = list(summaries.values())
            if not strategies:
                continue
            rvpd_winner = max(strategies, key=lambda s: s.rvpd).strategy
            rv_winner = max(strategies, key=lambda s: s.total_resolved_value).strategy
            results.append(TrialResult(
                trial=trial,
                noise_config=trial_cfg,
                summaries=summaries,
                rvpd_winner=rvpd_winner,
                resolved_value_winner=rv_winner,
            ))
    return results


def winner_stability(trials: list[TrialResult]) -> dict[str, dict[str, float]]:
    """For each noise level, compute fraction of trials where each strategy wins."""
    by_label: dict[str, list[TrialResult]] = defaultdict(list)
    for tr in trials:
        by_label[tr.noise_config.label].append(tr)

    stability: dict[str, dict[str, float]] = {}
    for label, group in by_label.items():
        n = len(group)
        rvpd_counts: dict[str, int] = defaultdict(int)
        rv_counts: dict[str, int] = defaultdict(int)
        for tr in group:
            rvpd_counts[tr.rvpd_winner] += 1
            rv_counts[tr.resolved_value_winner] += 1
        all_strategies = set(rvpd_counts) | set(rv_counts)
        stability[label] = {
            "n_trials": n,
            "rvpd": {s: rvpd_counts.get(s, 0) / n for s in all_strategies},
            "resolved_value": {s: rv_counts.get(s, 0) / n for s in all_strategies},
        }
    return stability


def rvpd_variance(rows: list[dict], noise_configs: list[NoiseConfig] | None = None, trials: int = 100) -> dict:
    """Compute RVPD mean and std for each strategy at each noise level."""
    if noise_configs is None:
        noise_configs = default_noise_configs()

    result: dict[str, dict] = {}
    rng = random.Random(42)
    for cfg in noise_configs:
        strategy_rvpds: dict[str, list[float]] = defaultdict(list)
        for _ in range(trials):
            trial_cfg = NoiseConfig(cfg.label, cfg.multiplier_range, seed=rng.randint(0, 10**9))
            summaries = compute_summary(rows, noise_config=trial_cfg)
            for s, summary in summaries.items():
                strategy_rvpds[s].append(summary.rvpd)
        result[cfg.label] = {
            s: {"mean": statistics.mean(vals), "std": statistics.stdev(vals) if len(vals) > 1 else 0.0}
            for s, vals in strategy_rvpds.items()
        }
    return result


def noise_report(jsonl_path: str | Path, trials_per_config: int = 100) -> str:
    """Generate a human-readable noise robustness report."""
    rows = load_rows(jsonl_path)
    if not rows:
        return "ERROR: no rows loaded"

    baseline = compute_summary(rows)
    configs = default_noise_configs()

    lines = [
        "=== Value Proxy Noise Robustness ===",
        f"Rows: {len(rows)}",
        f"Trials per noise level: {trials_per_config}",
        "",
        "--- Baseline (no noise) ---",
    ]
    for s, summary in baseline.items():
        lines.append(
            f"  {s}: pass={summary.resolved_count}/{summary.total_tasks} "
            f"cost=${summary.total_cost:.4f} rv={summary.total_resolved_value:.4f} "
            f"rvpd={summary.rvpd:.4f}"
        )

    lines.append("")
    lines.append("--- RVPD stability under noise ---")
    rvpd_var = rvpd_variance(rows, configs, trials_per_config)
    for label, data in rvpd_var.items():
        lines.append(f"  {label}:")
        for strategy, stats in data.items():
            lines.append(f"    {strategy}: rvpd={stats['mean']:.4f} ± {stats['std']:.4f}")

    lines.append("")
    lines.append("--- Winner stability (fraction of trials) ---")
    trial_results = run_noise_trials(rows, configs, trials_per_config)
    stability = winner_stability(trial_results)
    for label, data in stability.items():
        lines.append(f"  {label} (n={data['n_trials']}):")
        for s in sorted(data["rvpd"]):
            lines.append(f"    RVPD  winner: {s} = {data['rvpd'][s]:.2%}")
        for s in sorted(data["resolved_value"]):
            lines.append(f"    Value winner: {s} = {data['resolved_value'][s]:.2%}")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m budgetflow.value_proxy_noise <jsonl_path>")
        sys.exit(1)
    print(noise_report(sys.argv[1]))
