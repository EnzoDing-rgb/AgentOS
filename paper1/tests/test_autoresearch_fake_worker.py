"""Tests for autoresearch_fake_worker.py — no-paid smoke worker."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

WORKER = Path(__file__).resolve().parents[1] / "scripts" / "autoresearch_fake_worker.py"


def run_worker(prompt_path: Path, output_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(WORKER), str(prompt_path), str(output_path)],
        capture_output=True, text=True,
    )


@pytest.fixture
def prompt_file(tmp_path):
    p = tmp_path / "prompt.md"
    p.write_text("# Test Issue\n\nFix the imaginary bug.\n")
    return p


@pytest.fixture
def output_file(tmp_path):
    return tmp_path / "output.md"


class TestFakeWorkerSuccess:
    def test_exit_zero(self, prompt_file, output_file):
        result = run_worker(prompt_file, output_file)
        assert result.returncode == 0

    def test_output_file_created(self, prompt_file, output_file):
        run_worker(prompt_file, output_file)
        assert output_file.is_file()

    def test_output_contains_pass_marker(self, prompt_file, output_file):
        run_worker(prompt_file, output_file)
        text = output_file.read_text()
        assert "AUTORESEARCH_FAKE_WORKER_RESULT:PASS" in text

    def test_output_contains_required_sections(self, prompt_file, output_file):
        run_worker(prompt_file, output_file)
        text = output_file.read_text()
        for section in [
            "## Metadata",
            "## Files Read",
            "## Commands Run",
            "## Artifacts Produced",
            "## Verification Summary",
            "## Result",
        ]:
            assert section in text, f"missing section: {section}"

    def test_output_contains_prompt_path(self, prompt_file, output_file):
        run_worker(prompt_file, output_file)
        text = output_file.read_text()
        assert str(prompt_file) in text

    def test_output_no_src_modifications(self, prompt_file, output_file):
        """Fake worker must not claim to modify src/."""
        run_worker(prompt_file, output_file)
        text = output_file.read_text()
        assert "No src/ modifications" in text

    def test_output_no_api_calls(self, prompt_file, output_file):
        run_worker(prompt_file, output_file)
        text = output_file.read_text()
        assert "No API calls made" in text


class TestFakeWorkerErrors:
    def test_missing_args_exit_1(self):
        result = subprocess.run(
            [sys.executable, str(WORKER)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1

    def test_missing_prompt_file(self, tmp_path, output_file):
        result = run_worker(tmp_path / "nonexistent.md", output_file)
        assert result.returncode == 1

    def test_creates_output_dir_if_missing(self, prompt_file, tmp_path):
        output_file = tmp_path / "nested" / "dir" / "output.md"
        result = run_worker(prompt_file, output_file)
        assert result.returncode == 0
        assert output_file.is_file()
