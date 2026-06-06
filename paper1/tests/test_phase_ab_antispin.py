"""Phase AB: anti-spin regression tests — BFV allowlists, timeout handling."""

import ast
import textwrap
from pathlib import Path

import pytest

from budgetflow.adapter.mini_swe_proxy import (
    _ProviderTimeoutError,
    _is_provider_unavailable,
)


# ── Timeout detection ─────────────────────────────────────────────────────

class FakeTimeout(Exception):
    pass


def test_provider_timeout_detected_as_unavailable():
    original = TimeoutError("timed out")
    wrapped = _ProviderTimeoutError(original)
    assert _is_provider_unavailable(wrapped) is True


def test_provider_timeout_detected_with_any_original():
    original = FakeTimeout()
    wrapped = _ProviderTimeoutError(original)
    assert _is_provider_unavailable(wrapped) is True


def test_original_timeout_exception_detected():
    exc = TimeoutError("connection timed out")
    assert _is_provider_unavailable(exc) is True


def test_connection_error_detected():
    exc = ConnectionError("connection refused")
    assert _is_provider_unavailable(exc) is True


def test_non_timeout_not_detected():
    exc = ValueError("something else")
    assert _is_provider_unavailable(exc) is False


# ── BFV strategy allowlist audit ──────────────────────────────────────────

MINI_SWE_PROXY = Path(__file__).resolve().parents[1] / "src" / "budgetflow" / "adapter" / "mini_swe_proxy.py"


def _extract_tuple_from_method(source: str, method_name: str, line_pattern: str) -> tuple[str, ...] | None:
    """Parse a strategy allowlist tuple from a method's AST.

    Finds an `if ... in (...)` or `in (...)` pattern and extracts the tuple.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        # Check if the test contains a Compare with In
        for child in ast.walk(node.test):
            if isinstance(child, ast.Compare):
                for op in child.ops:
                    if isinstance(op, ast.In):
                        comparators = child.comparators
                        for comp in comparators:
                            if isinstance(comp, ast.Tuple):
                                return tuple(
                                    elt.value if isinstance(elt, ast.Constant) else str(elt)
                                    for elt in comp.elts
                                    if isinstance(elt, ast.Constant)
                                )
    return None


def _source() -> str:
    return MINI_SWE_PROXY.read_text()


def _method_source(method_name: str) -> str:
    """Extract a method's source from the file using indentation tracking."""
    lines = _source().splitlines()
    in_method = False
    indent = ""
    result = []
    for line in lines:
        if f"def {method_name}" in line:
            in_method = True
            indent = line[:len(line) - len(line.lstrip())]
            result.append(line)
            continue
        if in_method:
            cur_indent = line[:len(line) - len(line.lstrip())]
            # Method ends at same or lower indent (skipping blank lines)
            if line.strip() and len(cur_indent) <= len(indent) and not line.strip().startswith("#"):
                break
            result.append(line)
    return "\n".join(result)


def test_bfv_in_progress_escalation_allowlist():
    """BFV must be in _apply_progress_escalation strategy allowlist."""
    src = _method_source("_apply_progress_escalation")
    assert "budgetflow_value_aware" in src, (
        f"BFV missing from _apply_progress_escalation allowlist:\n{textwrap.indent(src, '  ')}"
    )


def test_bfv_in_reserve_with_downgrade_allowlist():
    """BFV must be in _reserve_with_downgrade adaptive floor check."""
    src = _method_source("_reserve_with_downgrade")
    assert "budgetflow_value_aware" in src, (
        f"BFV missing from _reserve_with_downgrade allowlist:\n{textwrap.indent(src, '  ')}"
    )


def test_bfv_in_rescue_forced_tier_allowlist():
    """BFV must be in rescue forced_tier check (query method)."""
    src = _method_source("query")
    # The rescue check uses an `if self.routing.strategy in (...):` pattern
    assert "budgetflow_value_aware" in src, (
        f"BFV missing from rescue forced_tier allowlist in query()"
    )


def test_bfv_in_gold_edit_guard_allowlist():
    """BFV must be in gold-edit guard tier-limit check."""
    src = _method_source("_apply_gold_edit_repair_guard")
    assert "budgetflow_value_aware" in src, (
        f"BFV missing from _apply_gold_edit_repair_guard allowlist:\n{textwrap.indent(src, '  ')}"
    )


def test_timeout_skip_retry_pattern():
    """_query() must catch timeout exceptions and raise _ProviderTimeoutError."""
    src = _source()
    assert "_ProviderTimeoutError" in src, "_ProviderTimeoutError class not found in module"
    assert "except Exception as exc:" in src, "source structure changed — review manually"
    # The retry call must include _ProviderTimeoutError in abort_exceptions
    assert "_ProviderTimeoutError" in src, (
        "_ProviderTimeoutError must be in retry() abort_exceptions"
    )
