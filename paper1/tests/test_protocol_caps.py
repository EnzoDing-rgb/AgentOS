from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.protocol_caps import read_protocol_caps  # noqa: E402


def test_read_protocol_caps_json(tmp_path: Path) -> None:
    caps_file = tmp_path / "frozen_caps.json"
    caps_file.write_text(
        json.dumps(
            {
                "batch_caps": {
                    "5": {"loose_batch": 1130.0, "tight_batch": 282.5},
                },
                "pressure": {"BUDGET_PRESSURE_INIT": 0.35, "PRESSURE_MAX": 1.5},
            }
        )
    )
    caps = read_protocol_caps(5, path=caps_file)
    assert caps.loose_batch == 1130.0
    assert caps.tight_batch == 282.5
    assert caps.pressure_max == 1.5
    assert caps.pressure_init == 0.35


def test_read_protocol_caps_legacy_md(tmp_path: Path) -> None:
    protocol = tmp_path / "protocol.md"
    protocol.write_text(
        """# protocol
| Key | Value |
|---|---|
| loose_batch_n5 | 1130.0000 |
| tight_batch_n5 | 282.5000 |
| PRESSURE_MAX | 1.5000 |
| BUDGET_PRESSURE_INIT | 0.3500 |
"""
    )
    caps = read_protocol_caps(5, path=protocol)
    assert caps.loose_batch == 1130.0
    assert caps.tight_batch == 282.5


def test_read_repo_frozen_caps() -> None:
    caps = read_protocol_caps(5)
    assert caps.tight_batch == 5270.595
    assert caps.loose_batch == 21082.38
