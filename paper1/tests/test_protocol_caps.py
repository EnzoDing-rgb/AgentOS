from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from budgetflow.protocol_caps import read_protocol_caps  # noqa: E402


def test_read_protocol_caps(tmp_path: Path) -> None:
    protocol = tmp_path / "protocol.md"
    protocol.write_text(
        """# protocol
| Key | Value |
|---|---|
| M (median per-task cost) | 113.0000 |
| loose_batch_n5 | 1130.0000 |
| tight_batch_n5 | 282.5000 |
| PRESSURE_MAX | 1.5000 |
| BUDGET_PRESSURE_INIT | 0.3500 |
"""
    )
    caps = read_protocol_caps(5, path=protocol)
    assert caps.m == 113.0
    assert caps.loose_batch == 1130.0
    assert caps.tight_batch == 282.5
    assert caps.pressure_max == 1.5
