"""Frozen compare caps — loaded from data/frozen_caps.json (written by run_pilot.py).

Machine-readable JSON is the source of truth for --read-frozen-caps.
Pilot re-run overwrites this file; compare runs must not recompute caps ad hoc.
Human runbook lives in docs/progress.md; constants live here + defaults.py.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

PAPER1_ROOT = Path(__file__).resolve().parents[2]
FROZEN_CAPS_PATH = PAPER1_ROOT / "data" / "frozen_caps.json"
# Legacy fallback only (old repos / tests passing a temp .md path).
LEGACY_PROTOCOL_MD = PAPER1_ROOT / "docs" / "protocol.md"


@dataclass(frozen=True)
class ProtocolCaps:
    loose_batch: float
    tight_batch: float
    n_tasks: int
    pressure_max: float
    pressure_init: float


def _parse_float_table_row(text: str, key: str) -> float | None:
    pattern = rf"^\|\s*{re.escape(key)}\s*\|\s*([0-9.]+)\s*\|"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return None
    return float(match.group(1))


def _read_protocol_caps_md(n_tasks: int, path: Path) -> ProtocolCaps:
    text = path.read_text()
    loose_key = f"loose_batch_n{n_tasks}"
    tight_key = f"tight_batch_n{n_tasks}"
    loose = _parse_float_table_row(text, loose_key)
    tight = _parse_float_table_row(text, tight_key)
    if loose is None or tight is None:
        raise ValueError(f"protocol missing batch caps for n={n_tasks} ({loose_key}, {tight_key})")
    pressure_max = _parse_float_table_row(text, "PRESSURE_MAX") or 1.5
    pressure_init = _parse_float_table_row(text, "BUDGET_PRESSURE_INIT") or 0.35
    return ProtocolCaps(
        loose_batch=loose,
        tight_batch=tight,
        n_tasks=n_tasks,
        pressure_max=pressure_max,
        pressure_init=pressure_init,
    )


def _pilot_costs_from_frozen(raw: dict) -> list[float] | None:
    costs = (raw.get("pilot") or {}).get("per_task_costs_governor_units")
    if not costs:
        return None
    return [float(c) for c in costs]


def _read_protocol_caps_json(n_tasks: int, path: Path) -> ProtocolCaps:
    raw = json.loads(path.read_text())
    batch = (raw.get("batch_caps") or {}).get(str(n_tasks))
    if not batch:
        pilot_costs = _pilot_costs_from_frozen(raw)
        if pilot_costs:
            loose, tight = derive_batch_caps(pilot_costs, n_tasks)
            batch = {"loose_batch": loose, "tight_batch": tight}
        else:
            raise ValueError(
                f"frozen_caps.json missing batch_caps[{n_tasks!r}] "
                "and no pilot.per_task_costs_governor_units to derive from"
            )
    pressure = raw.get("pressure") or {}
    return ProtocolCaps(
        loose_batch=float(batch["loose_batch"]),
        tight_batch=float(batch["tight_batch"]),
        n_tasks=n_tasks,
        pressure_max=float(pressure.get("PRESSURE_MAX", 1.5)),
        pressure_init=float(pressure.get("BUDGET_PRESSURE_INIT", 0.01)),
    )


def read_protocol_caps(
    n_tasks: int,
    *,
    path: Path | None = None,
) -> ProtocolCaps:
    """Load frozen loose/tight batch caps for n serial tasks per policy."""
    if path is not None:
        if path.suffix == ".json":
            return _read_protocol_caps_json(n_tasks, path)
        return _read_protocol_caps_md(n_tasks, path)

    if FROZEN_CAPS_PATH.is_file():
        return _read_protocol_caps_json(n_tasks, FROZEN_CAPS_PATH)
    if LEGACY_PROTOCOL_MD.is_file():
        return _read_protocol_caps_md(n_tasks, LEGACY_PROTOCOL_MD)
    raise FileNotFoundError(
        f"frozen caps not found: {FROZEN_CAPS_PATH} (run python -m budgetflow.run_pilot first)"
    )


def write_frozen_caps(
    *,
    per_task_costs: list[float],
    pilot_records: list[dict],
    pinned_commit: str,
    compare_easy_ids: tuple[str, ...],
    pressure_init: float,
    pressure_max: float,
    tier_models: tuple[str, str, str],
    generated_at: str,
) -> Path:
    """Write data/frozen_caps.json after B.0 pilot (sole cap artifact for compare)."""
    pilot_ids = [r["instance_id"] for r in pilot_records]
    cap_ns = (3, 5, 7, 10, 15)
    batch_caps = {
        str(n): {
            "loose_batch": round(derive_batch_caps(per_task_costs, n)[0], 4),
            "tight_batch": round(derive_batch_caps(per_task_costs, n)[1], 4),
        }
        for n in cap_ns
    }
    outliers: list[str] = []
    if per_task_costs and tight_n3 > 0:
        scale = tight_n3 / (0.5 * 3)
        outliers = [r["instance_id"] for r in pilot_records if float(r["total_cost"]) > 3 * scale]

    payload = {
        "status": "FROZEN",
        "generated_at": generated_at,
        "generated_by": "run_pilot.py",
        "note": "Compare --read-frozen-caps reads batch_caps + pressure. Do not hand-edit during compare.",
        "scaffold": {
            "mini_swe_agent_commit": pinned_commit,
            "harness": "B — local_harness.py (Docker unavailable; not SWE-bench leaderboard comparable)",
        },
        "tier_models_at_pilot": {
            "T1": tier_models[0],
            "T2": tier_models[1],
            "T3": tier_models[2],
        },
        "pressure": {
            "BUDGET_PRESSURE_INIT": pressure_init,
            "PRESSURE_MAX": pressure_max,
            "formula": "pressure = init + used_frac * (max - init); used_frac = (spent + reserved) / total",
        },
        "pilot": {
            "tasks": pilot_ids,
            "per_task_costs_governor_units": [round(c, 4) for c in per_task_costs],
            "high_cost_tasks": outliers,
        },
        "batch_caps": batch_caps,
        "batch_cap_formula": "loose=2*median(pilot_costs)*n; tight=0.5*median(pilot_costs)*n",
        "task_lists": {
            "compare_easy_5": list(compare_easy_ids),
        },
    }
    FROZEN_CAPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    FROZEN_CAPS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return FROZEN_CAPS_PATH


def derive_batch_caps(per_task_costs: list[float], n: int) -> tuple[float, float]:
    if not per_task_costs:
        return 0.0, 0.0
    import statistics

    unit = statistics.median(per_task_costs)
    return 2.0 * unit * n, 0.5 * unit * n
