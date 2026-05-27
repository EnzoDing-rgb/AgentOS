from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


def run_with_heartbeat(
    label: str,
    fn: Callable[[], Any],
    *,
    interval_s: float = 30.0,
    status_fn: Callable[[], str] | None = None,
) -> Any:
    """Run blocking fn; print heartbeat every interval_s until fn returns."""
    stop = threading.Event()
    started = time.time()

    def _loop() -> None:
        while not stop.wait(interval_s):
            extra = f" {status_fn()}" if status_fn else ""
            print(
                f"[heartbeat] {label} alive elapsed={time.time() - started:.0f}s{extra}",
                flush=True,
            )

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    try:
        return fn()
    finally:
        stop.set()
        thread.join(timeout=1.0)
