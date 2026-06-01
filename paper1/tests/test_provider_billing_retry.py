from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "external" / "mini-swe-agent" / "src"))

from budgetflow.adapter.mini_swe_proxy import FatalProviderBillingError  # noqa: E402
from minisweagent.models.utils.retry import retry  # noqa: E402


def test_fatal_provider_billing_error_aborts_retry() -> None:
    attempts = 0

    try:
        for attempt in retry(logger=__import__("logging").getLogger(__name__), abort_exceptions=[FatalProviderBillingError]):
            with attempt:
                attempts += 1
                raise FatalProviderBillingError(RuntimeError("overdue-payment"))
    except FatalProviderBillingError:
        pass

    assert attempts == 1
