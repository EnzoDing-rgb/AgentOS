"""Heartbeat liveness helpers for run observability."""

from __future__ import annotations

import os
import time

def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _rows_stuck(hb: dict, stale_seconds: float) -> tuple[bool, str]:
    """Check if a run has stalled: no progress despite elapsed time.

    Returns (is_stuck, reason).
    """
    rows_done = int(hb.get("rows_done") or 0)
    total = int(hb.get("total_expected") or 0)
    if total <= 0 or rows_done >= total:
        return False, ""

    status = str(hb.get("status") or "")
    updated_at = float(hb.get("updated_at") or 0)
    started_at = float(hb.get("started_at") or 0)
    active_elapsed_s = float(hb.get("active_elapsed_s") or 0)
    active_strategy = str(hb.get("active_strategy") or "")
    active_instance = str(hb.get("active_instance") or "")
    now = time.time()
    since_update = now - updated_at
    elapsed = now - started_at

    # Completed but incomplete -> crashed before finishing
    if status == "completed" and rows_done < total:
        return True, f"status=completed but rows={rows_done}/{total} (crashed?)"

    # Aborted but pid still recorded as alive -> inconsistent
    if status.startswith("aborted") and rows_done < total:
        return True, f"status={status} rows={rows_done}/{total}"

    # Zero-progress stuck: fresh heartbeat but no rows and task stuck in prep
    if rows_done == 0 and elapsed > stale_seconds:
        has_active = bool(active_strategy) or bool(active_instance)
        if has_active and active_elapsed_s == 0:
            return True, (
                f"ZERO_PROGRESS rows=0/{total} elapsed={elapsed:.0f}s "
                f"active={active_strategy}:{active_instance} active_elapsed_s=0 "
                f"(stuck in prep, no task actually started)"
            )
        if has_active and active_elapsed_s > 0 and active_elapsed_s > stale_seconds:
            return True, (
                f"ZERO_PROGRESS rows=0/{total} elapsed={elapsed:.0f}s "
                f"active_elapsed_s={active_elapsed_s:.0f}s "
                f"(single task stuck for too long)"
            )
        if not has_active and elapsed > stale_seconds:
            return True, (
                f"ZERO_PROGRESS rows=0/{total} elapsed={elapsed:.0f}s "
                f"no active task (setup or thread pool blocked?)"
            )

    # Heartbeat not updating AND run not finished -> stuck
    if since_update > stale_seconds:
        return True, (
            f"no update for {since_update:.0f}s, rows={rows_done}/{total}, "
            f"elapsed={elapsed:.0f}s"
        )

    return False, ""
