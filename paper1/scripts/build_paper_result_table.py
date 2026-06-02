#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StrategySummary:
    group: str
    strategy: str
    tasks: int
    passed: int
    cost: float
    turns: int
    failures: Counter[str]

    @property
    def avg_cost(self) -> float:
        return self.cost / self.tasks if self.tasks else 0.0


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []

    rows: list[dict] = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSONL row") from exc
    return rows


def _cost(row: dict) -> float:
    value = row.get("task_cost")
    if value is None:
        value = row.get("total_cost")
    return float(value or 0.0)


def _turns(row: dict) -> int:
    return int(row.get("llm_turns") or row.get("turns") or 0)


def _failure_class(row: dict) -> str:
    failure = row.get("failure_class")
    if failure:
        return str(failure)
    return "pass" if row.get("harness_resolved") else "unknown"


def summarize_rows(rows: list[dict], group: str) -> list[StrategySummary]:
    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_strategy[str(row.get("strategy") or row.get("routing") or "unknown")].append(row)

    summaries: list[StrategySummary] = []
    for strategy, items in sorted(by_strategy.items()):
        failures = Counter(_failure_class(row) for row in items)
        summaries.append(
            StrategySummary(
                group=group,
                strategy=strategy,
                tasks=len(items),
                passed=sum(1 for row in items if bool(row.get("harness_resolved"))),
                cost=sum(_cost(row) for row in items),
                turns=sum(_turns(row) for row in items),
                failures=failures,
            )
        )
    return summaries


def format_failure_classes(failures: Counter[str]) -> str:
    if not failures:
        return "-"
    return ", ".join(f"{name}={count}" for name, count in sorted(failures.items()))


def next_action(summary: StrategySummary) -> str:
    if summary.tasks == 0:
        return "rerun missing data"
    if summary.passed == summary.tasks:
        return "keep / scale cautiously"
    if summary.failures.get("infra_fail") or summary.failures.get("auth_fail"):
        return "fix infra before conclusions"
    if summary.failures.get("extract_fail") or summary.failures.get("format_fail"):
        return "fix protocol / patch extraction"
    if summary.failures.get("repair_fail"):
        return "inspect repair failures"
    if summary.failures.get("localization_fail"):
        return "improve localization / escalate earlier"
    if summary.passed == 0:
        return "do not scale yet"
    return "compare on more gold-pass tasks"


def build_markdown_table(
    run_dir: Path,
    stems: list[str],
    labels: dict[str, str] | None = None,
) -> str:
    labels = labels or {}
    summaries: list[StrategySummary] = []

    for stem in stems:
        group = labels.get(stem, stem)
        summaries.extend(summarize_rows(load_rows(run_dir / f"{stem}.jsonl"), group=group))

    lines = [
        "| group | strategy | tasks | pass | cost | avg_cost | turns | failure_classes | next_action |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for summary in summaries:
        lines.append(
            "| "
            f"{summary.group} | `{summary.strategy}` | {summary.tasks} | "
            f"{summary.passed}/{summary.tasks} | {summary.cost:.1f} | {summary.avg_cost:.1f} | "
            f"{summary.turns} | {format_failure_classes(summary.failures)} | {next_action(summary)} |"
        )
    return "\n".join(lines) + "\n"


def _parse_label(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("labels must use stem=label")
    stem, label = raw.split("=", 1)
    if not stem or not label:
        raise argparse.ArgumentTypeError("labels must use non-empty stem=label")
    return stem, label


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a paper-ready BudgetFlow result table.")
    parser.add_argument("stems", nargs="+", help="JSONL stems under --run-dir, without .jsonl")
    parser.add_argument("--run-dir", type=Path, default=Path(__file__).resolve().parents[1] / "data" / "runs")
    parser.add_argument("--label", action="append", type=_parse_label, default=[], help="Group label as stem=label")
    parser.add_argument("--out", type=Path, help="Write Markdown table to this path")
    args = parser.parse_args()

    text = build_markdown_table(
        run_dir=args.run_dir,
        stems=args.stems,
        labels=dict(args.label),
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
