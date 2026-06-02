from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run-nightly-paper-progress.sh"


def test_nightly_entrypoint_has_required_gates_and_resume() -> None:
    text = SCRIPT.read_text()

    assert "budgetflow.run_deepseek_smoke --tier compare" in text
    assert "scripts/run-auto-v2-goldpass5.sh" in text
    assert "--resume" in text
    assert "build_paper_result_table.py" in text
    assert "current_paper_result_table.md" in text


def test_nightly_entrypoint_avoids_docker_and_gpt55_routing() -> None:
    text = SCRIPT.read_text()

    assert "docker" not in text.lower()
    assert "all_gpt55" not in text
    assert "run-gpt55" not in text.lower()
