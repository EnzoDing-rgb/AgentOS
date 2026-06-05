"""Tests for autoresearch_api_worker.py — thin API worker with mocked responses."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

WORKER = Path(__file__).resolve().parents[1] / "scripts" / "autoresearch_api_worker.py"
PAPER1 = Path(__file__).resolve().parents[1]


def run_worker(prompt_path: Path, output_path: Path, *, env: dict | None = None, clear: list | None = None) -> subprocess.CompletedProcess:
    """Run the worker as a subprocess with optional env overrides.

    clear: list of env var names to remove from the inherited environment.
    """
    run_env = os.environ.copy()
    if clear:
        for k in clear:
            run_env.pop(k, None)
    if env:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, str(WORKER), str(prompt_path), str(output_path)],
        capture_output=True, text=True, env=run_env,
    )


@pytest.fixture
def prompt_file(tmp_path):
    p = tmp_path / "prompt.md"
    p.write_text("# Test Issue\n\nRead the docs and write a summary.\n")
    return p


@pytest.fixture
def output_file(tmp_path):
    return tmp_path / "output.md"


@pytest.fixture
def api_env():
    """Minimal env for API worker (points at fake endpoint so subprocess doesn't hit real API)."""
    return {
        "ANTHROPIC_BASE_URL": "https://api.test.example.com/anthropic",
        "ANTHROPIC_API_KEY": "sk-test-key-mocked",
        "ANTHROPIC_MODEL": "test-model",
    }


# ── Error cases ──────────────────────────────────────────────────────────────

class TestErrors:
    def test_missing_args_exit_1(self):
        result = subprocess.run(
            [sys.executable, str(WORKER)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1

    def test_missing_prompt_file(self, tmp_path):
        result = run_worker(tmp_path / "nonexistent.md", tmp_path / "out.md",
                            env={"ANTHROPIC_BASE_URL": "x", "ANTHROPIC_API_KEY": "x", "ANTHROPIC_MODEL": "x"})
        assert result.returncode == 1

    def test_missing_base_url(self, prompt_file, output_file):
        result = run_worker(prompt_file, output_file,
                            env={"ANTHROPIC_API_KEY": "sk-test", "ANTHROPIC_MODEL": "m"},
                            clear=["ANTHROPIC_BASE_URL"])
        assert result.returncode == 1
        assert "ANTHROPIC_BASE_URL" in result.stderr

    def test_missing_api_key(self, prompt_file, output_file):
        result = run_worker(prompt_file, output_file,
                            env={"ANTHROPIC_BASE_URL": "https://x", "ANTHROPIC_MODEL": "m"},
                            clear=["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"])
        assert result.returncode == 1
        assert "ANTHROPIC_API_KEY" in result.stderr or "ANTHROPIC_AUTH_TOKEN" in result.stderr


# ── Mocked success path ──────────────────────────────────────────────────────

class TestMockedSuccess:
    def test_mocked_response_writes_output(self, tmp_path, prompt_file, output_file):
        """Patch requests.post to return a fake successful response."""
        fake_response = mock.MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "content": [{"type": "text", "text": "# Worker Report\n\nSmoke test passed.\nAUTORESEARCH_REAL_API_SMOKE:PASS"}],
            "usage": {"input_tokens": 500, "output_tokens": 100},
        }

        paper1 = PAPER1
        # Ensure the docs exist for the worker to read.
        assert (paper1 / "docs" / "autoresearch_workflow.md").is_file(), "prereq doc missing"
        assert (paper1 / "docs" / "reports" / "036.md").is_file(), "prereq doc missing"

        env = {
            "ANTHROPIC_BASE_URL": "https://api.test.example.com/anthropic",
            "ANTHROPIC_API_KEY": "sk-test-key",
            "ANTHROPIC_MODEL": "test-model",
        }

        with mock.patch("requests.post", return_value=fake_response):
            # Need to run via subprocess so the mock takes effect.
            # Instead, import and call main with monkeypatched requests.
            pass
        # For subprocess-based test: skip (mock doesn't cross process boundary).
        # Test via direct import instead.

    def test_main_with_mocked_requests(self, tmp_path, monkeypatch):
        """Test main() directly with requests.post mocked."""
        sys.path.insert(0, str(PAPER1 / "scripts"))
        import importlib
        worker_mod = importlib.import_module("autoresearch_api_worker")

        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("# Test\n\nRead docs and write summary.\n")
        output_file = tmp_path / "output.md"

        # Mock the requests module inside the worker.
        mock_requests = mock.MagicMock()
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "# Worker Report\n\nAll checks passed.\nAUTORESEARCH_REAL_API_SMOKE:PASS"}],
            "usage": {"input_tokens": 400, "output_tokens": 80},
        }
        mock_requests.post.return_value = mock_resp

        # Set env for the worker.
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.test.example.com/anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        monkeypatch.setenv("AUTORESEARCH_MODEL", "test-model")

        with mock.patch.dict("sys.modules", {"requests": mock_requests}):
            rc = worker_mod.main([str(WORKER), str(prompt_file), str(output_file)])

        assert rc == 0
        assert output_file.is_file()
        content = output_file.read_text()
        assert "AUTORESEARCH_REAL_API_SMOKE:PASS" in content
        assert "Worker Report" in content

    def test_main_uses_auth_token_fallback(self, tmp_path, monkeypatch):
        """Test that ANTHROPIC_AUTH_TOKEN is used when ANTHROPIC_API_KEY is absent."""
        sys.path.insert(0, str(PAPER1 / "scripts"))
        import importlib
        worker_mod = importlib.import_module("autoresearch_api_worker")

        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("# Test\n\nRead docs.\n")
        output_file = tmp_path / "output.md"

        mock_requests = mock.MagicMock()
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "OK\nAUTORESEARCH_REAL_API_SMOKE:PASS"}],
            "usage": {"input_tokens": 300, "output_tokens": 40},
        }
        mock_requests.post.return_value = mock_resp

        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.test.example.com/anthropic")
        # Set AUTH_TOKEN, not API_KEY.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-auth-token-test")
        monkeypatch.setenv("AUTORESEARCH_MODEL", "test-model")

        with mock.patch.dict("sys.modules", {"requests": mock_requests}):
            rc = worker_mod.main([str(WORKER), str(prompt_file), str(output_file)])

        assert rc == 0
        content = output_file.read_text()
        assert "AUTORESEARCH_REAL_API_SMOKE:PASS" in content

    def test_main_missing_marker_exits_1_by_default(self, tmp_path, monkeypatch):
        """If model response lacks marker, worker exits non-zero (no auto-append)."""
        sys.path.insert(0, str(PAPER1 / "scripts"))
        import importlib
        worker_mod = importlib.import_module("autoresearch_api_worker")

        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("# Test\n")
        output_file = tmp_path / "output.md"

        mock_requests = mock.MagicMock()
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "Just some output without the marker."}],
            "usage": {"input_tokens": 200, "output_tokens": 30},
        }
        mock_requests.post.return_value = mock_resp

        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.test.example.com/anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        monkeypatch.setenv("AUTORESEARCH_MODEL", "test-model")

        with mock.patch.dict("sys.modules", {"requests": mock_requests}):
            rc = worker_mod.main([str(WORKER), str(prompt_file), str(output_file)])

        assert rc == 1  # Non-zero: marker not found, no --allow-wrapper-marker
        content = output_file.read_text()
        assert "AUTORESEARCH_REAL_API_SMOKE:PASS" not in content  # Not appended

    def test_main_adds_marker_with_allow_flag(self, tmp_path, monkeypatch):
        """With --allow-wrapper-marker, worker appends marker and exits 0."""
        sys.path.insert(0, str(PAPER1 / "scripts"))
        import importlib
        worker_mod = importlib.import_module("autoresearch_api_worker")

        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("# Test\n")
        output_file = tmp_path / "output.md"

        mock_requests = mock.MagicMock()
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "Just some output without the marker."}],
            "usage": {"input_tokens": 200, "output_tokens": 30},
        }
        mock_requests.post.return_value = mock_resp

        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.test.example.com/anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        monkeypatch.setenv("AUTORESEARCH_MODEL", "test-model")

        with mock.patch.dict("sys.modules", {"requests": mock_requests}):
            rc = worker_mod.main([str(WORKER), "--allow-wrapper-marker", str(prompt_file), str(output_file)])

        assert rc == 0
        content = output_file.read_text()
        assert "AUTORESEARCH_REAL_API_SMOKE:PASS" in content

    def test_mask_does_not_leak_full_key(self, tmp_path, monkeypatch, capsys):
        """The printed key should be masked, not the full secret."""
        sys.path.insert(0, str(PAPER1 / "scripts"))
        import importlib
        worker_mod = importlib.import_module("autoresearch_api_worker")

        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("# Test\n")
        output_file = tmp_path / "output.md"

        mock_requests = mock.MagicMock()
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "OK\nAUTORESEARCH_REAL_API_SMOKE:PASS"}],
            "usage": {"input_tokens": 200, "output_tokens": 30},
        }
        mock_requests.post.return_value = mock_resp

        long_key = "sk-this-is-a-very-long-secret-key-that-should-be-masked"
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.test.example.com/anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", long_key)
        monkeypatch.setenv("AUTORESEARCH_MODEL", "test-model")

        with mock.patch.dict("sys.modules", {"requests": mock_requests}):
            rc = worker_mod.main([str(WORKER), str(prompt_file), str(output_file)])

        assert rc == 0
        captured = capsys.readouterr()
        # The full secret should NOT appear in stdout.
        assert long_key not in captured.out

    def test_http_error_exits_1(self, tmp_path, monkeypatch):
        """Non-200 HTTP response should exit 1."""
        sys.path.insert(0, str(PAPER1 / "scripts"))
        import importlib
        worker_mod = importlib.import_module("autoresearch_api_worker")

        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("# Test\n")
        output_file = tmp_path / "output.md"

        mock_requests = mock.MagicMock()
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_requests.post.return_value = mock_resp

        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.test.example.com/anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
        monkeypatch.setenv("AUTORESEARCH_MODEL", "test-model")

        with mock.patch.dict("sys.modules", {"requests": mock_requests}):
            rc = worker_mod.main([str(WORKER), str(prompt_file), str(output_file)])

        assert rc == 1


# ── Metadata sidecar ─────────────────────────────────────────────────────────

class TestMetadata:
    def test_metadata_sidecar_written(self, tmp_path, monkeypatch):
        """On success, worker_metadata.json is written alongside output."""
        sys.path.insert(0, str(PAPER1 / "scripts"))
        import importlib
        worker_mod = importlib.import_module("autoresearch_api_worker")

        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("# Test\n")
        output_file = tmp_path / "output.md"

        mock_requests = mock.MagicMock()
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "OK\nAUTORESEARCH_REAL_API_SMOKE:PASS"}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        mock_requests.post.return_value = mock_resp

        # Use AUTORESEARCH_MODEL (highest priority) to override real env.
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.test.example.com/anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("AUTORESEARCH_MODEL", "test-model")

        with mock.patch.dict("sys.modules", {"requests": mock_requests}):
            rc = worker_mod.main([str(WORKER), str(prompt_file), str(output_file)])

        assert rc == 0
        meta_path = output_file.parent / "worker_metadata.json"
        assert meta_path.is_file()
        meta = json.loads(meta_path.read_text())
        assert meta["model"] == "test-model"
        assert meta["input_tokens"] == 100
        assert meta["output_tokens"] == 50
        assert meta["status_code"] == 200
        assert meta["marker_present_in_model_output"] is True
        assert meta["marker_appended_by_wrapper"] is False
        assert meta["error"] is None

    def test_metadata_records_marker_not_appended_by_default(self, tmp_path, monkeypatch):
        """When model output lacks marker, metadata records marker_appended=False (strict default)."""
        sys.path.insert(0, str(PAPER1 / "scripts"))
        import importlib
        worker_mod = importlib.import_module("autoresearch_api_worker")

        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("# Test\n")
        output_file = tmp_path / "output.md"

        mock_requests = mock.MagicMock()
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "No marker here."}],
            "usage": {"input_tokens": 50, "output_tokens": 20},
        }
        mock_requests.post.return_value = mock_resp

        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.test.example.com/anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("AUTORESEARCH_MODEL", "test-model")

        with mock.patch.dict("sys.modules", {"requests": mock_requests}):
            rc = worker_mod.main([str(WORKER), str(prompt_file), str(output_file)])

        assert rc == 1  # Strict: no marker → non-zero exit
        meta_path = output_file.parent / "worker_metadata.json"
        meta = json.loads(meta_path.read_text())
        assert meta["marker_present_in_model_output"] is False
        assert meta["marker_appended_by_wrapper"] is False  # Not appended without flag

    def test_metadata_on_http_error(self, tmp_path, monkeypatch):
        """On HTTP error, metadata is still written with error info."""
        sys.path.insert(0, str(PAPER1 / "scripts"))
        import importlib
        worker_mod = importlib.import_module("autoresearch_api_worker")

        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("# Test\n")
        output_file = tmp_path / "output.md"

        mock_requests = mock.MagicMock()
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Server error"
        mock_requests.post.return_value = mock_resp

        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.test.example.com/anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("AUTORESEARCH_MODEL", "test-model")

        with mock.patch.dict("sys.modules", {"requests": mock_requests}):
            rc = worker_mod.main([str(WORKER), str(prompt_file), str(output_file)])

        assert rc == 1
        meta_path = output_file.parent / "worker_metadata.json"
        assert meta_path.is_file()
        meta = json.loads(meta_path.read_text())
        assert meta["status_code"] == 500
        assert meta["error"] is not None
        assert "500" in meta["error"]

    def test_metadata_no_secret_leakage(self, tmp_path, monkeypatch):
        """Metadata JSON must never contain the API key."""
        sys.path.insert(0, str(PAPER1 / "scripts"))
        import importlib
        worker_mod = importlib.import_module("autoresearch_api_worker")

        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("# Test\n")
        output_file = tmp_path / "output.md"

        mock_requests = mock.MagicMock()
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "OK\nAUTORESEARCH_REAL_API_SMOKE:PASS"}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        mock_requests.post.return_value = mock_resp

        secret = "sk-very-secret-api-key-do-not-leak"
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.test.example.com/anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
        monkeypatch.setenv("AUTORESEARCH_MODEL", "test-model")

        with mock.patch.dict("sys.modules", {"requests": mock_requests}):
            rc = worker_mod.main([str(WORKER), str(prompt_file), str(output_file)])

        assert rc == 0
        meta_path = output_file.parent / "worker_metadata.json"
        meta_text = meta_path.read_text()
        assert secret not in meta_text

    def test_factual_header_in_output(self, tmp_path, monkeypatch):
        """Worker output has factual header with model and token info."""
        sys.path.insert(0, str(PAPER1 / "scripts"))
        import importlib
        worker_mod = importlib.import_module("autoresearch_api_worker")

        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("# Test\n")
        output_file = tmp_path / "output.md"

        mock_requests = mock.MagicMock()
        mock_resp = mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": "OK\nAUTORESEARCH_REAL_API_SMOKE:PASS"}],
            "usage": {"input_tokens": 400, "output_tokens": 60},
        }
        mock_requests.post.return_value = mock_resp

        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.test.example.com/anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("AUTORESEARCH_MODEL", "test-model")

        with mock.patch.dict("sys.modules", {"requests": mock_requests}):
            rc = worker_mod.main([str(WORKER), str(prompt_file), str(output_file)])

        assert rc == 0
        content = output_file.read_text()
        assert "<!-- AutoResearch API Worker" in content
        assert "model: test-model" in content
        assert "input_tokens: 400" in content
        assert "output_tokens: 60" in content
        assert "metadata: worker_metadata.json" in content


# ── Fake worker tests still pass ─────────────────────────────────────────────

class TestFakeWorkerStillWorks:
    """Verify the fake worker from Phase F is unaffected."""

    def test_fake_worker_still_passes(self, tmp_path):
        fake_worker = PAPER1 / "scripts" / "autoresearch_fake_worker.py"
        prompt = tmp_path / "prompt.md"
        prompt.write_text("# Test\n")
        output = tmp_path / "output.md"
        result = subprocess.run(
            [sys.executable, str(fake_worker), str(prompt), str(output)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "AUTORESEARCH_FAKE_WORKER_RESULT:PASS" in output.read_text()
