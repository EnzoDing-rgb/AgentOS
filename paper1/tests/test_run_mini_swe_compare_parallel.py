from __future__ import annotations

import pytest

import budgetflow.run_mini_swe_compare as runner
from budgetflow.experiments.compare_config import CompareStrategy
from budgetflow.run_guards import CompareRunGuards


class _FakeFuture:
    def __init__(self, *, raises: BaseException | None = None, result=None) -> None:
        self.raises = raises
        self._result = result
        self.cancelled = False

    def result(self):
        if self.raises is not None:
            raise self.raises
        return self._result

    def done(self) -> bool:
        return False

    def cancel(self) -> None:
        self.cancelled = True


class _FakePool:
    def __init__(self, *, max_workers: int) -> None:
        self.max_workers = max_workers
        self.futures: list[_FakeFuture] = []
        self.shutdown_calls: list[dict] = []

    def submit(self, _fn, _cfg):
        future = _FakeFuture(raises=KeyboardInterrupt())
        self.futures.append(future)
        return future

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        self.shutdown_calls.append({"wait": wait, "cancel_futures": cancel_futures})


def test_parallel_batches_keyboard_interrupt_aborts_and_does_not_wait(monkeypatch) -> None:
    pool_holder: dict[str, _FakePool] = {}

    def fake_pool(*, max_workers: int):
        pool = _FakePool(max_workers=max_workers)
        pool_holder["pool"] = pool
        return pool

    monkeypatch.setattr(runner, "ThreadPoolExecutor", fake_pool)
    monkeypatch.setattr(runner, "as_completed", lambda futures: iter(futures))
    guard = CompareRunGuards()

    with pytest.raises(KeyboardInterrupt):
        runner._run_parallel_batches(
            strategies=(CompareStrategy("s1", "all_tier2"),),
            max_workers=1,
            run_one_batch=lambda cfg: (cfg, [], 0.0, 1.0),
            ingest_batch=lambda *_args: None,
            run_guards=guard,
        )

    pool = pool_holder["pool"]
    assert guard.is_aborted()
    assert guard.abort_reason() == "keyboard_interrupt"
    assert pool.shutdown_calls
    assert {"wait": False, "cancel_futures": True} in pool.shutdown_calls
    assert all(future.cancelled for future in pool.futures)


def test_parallel_batches_guard_abort_keeps_guard_alive_until_workers_stop(monkeypatch) -> None:
    pool_holder: dict[str, _FakePool] = {}

    def fake_pool(*, max_workers: int):
        pool = _FakePool(max_workers=max_workers)
        pool_holder["pool"] = pool
        return pool

    cfg = CompareStrategy("s1", "all_tier2")
    future = _FakeFuture(result=(cfg, [], 0.0, 1.0))

    monkeypatch.setattr(runner, "ThreadPoolExecutor", fake_pool)
    monkeypatch.setattr(_FakePool, "submit", lambda self, _fn, _cfg: self.futures.append(future) or future)
    monkeypatch.setattr(runner, "as_completed", lambda futures: iter(futures))

    guard = CompareRunGuards()
    guard.request_abort("protocol_guard abort strategy=s1 task=t1")

    runner._run_parallel_batches(
        strategies=(cfg,),
        max_workers=1,
        run_one_batch=lambda cfg: (cfg, [], 0.0, 1.0),
        ingest_batch=lambda *_args: None,
        run_guards=guard,
    )

    assert {"wait": True, "cancel_futures": True} in pool_holder["pool"].shutdown_calls
