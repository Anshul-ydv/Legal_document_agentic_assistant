"""Global rate limiter patch for google.genai models.

Applying this patch ensures *all* Gemini calls (including ADK root agent
workflows) respect the same RPM/interval limits.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from typing import Deque

_LOCK = threading.Lock()
_REQUEST_HISTORY: Deque[float] = deque()
_LAST_REQUEST_TS: float = 0.0
_MIN_INTERVAL: float = 1.0
_RPM_LIMIT: int = 60
_PATCH_INSTALLED: bool = False


def _compute_wait(now: float) -> float:
    wait_interval = (_LAST_REQUEST_TS + _MIN_INTERVAL) - now

    window_start = now - 60.0
    while _REQUEST_HISTORY and _REQUEST_HISTORY[0] < window_start:
        _REQUEST_HISTORY.popleft()

    wait_window = 0.0
    if len(_REQUEST_HISTORY) >= _RPM_LIMIT:
        oldest = _REQUEST_HISTORY[0]
        wait_window = max(0.0, 60.0 - (now - oldest))

    return max(wait_interval, wait_window, 0.0)


def _record_request(ts: float) -> None:
    global _LAST_REQUEST_TS
    _LAST_REQUEST_TS = ts
    _REQUEST_HISTORY.append(ts)


def _block_until_slot_sync() -> None:
    while True:
        with _LOCK:
            now = time.time()
            wait_for = _compute_wait(now)
            if wait_for <= 0:
                _record_request(time.time())
                return
        if wait_for > 0:
            logging.info(
                "[GlobalLLMRateLimiter] Waiting %.2fs before next LLM call (sync)",
                wait_for,
            )
            time.sleep(wait_for)


def _sleep_interval(value: float) -> float:
    return max(value, 0.01)


async def _block_until_slot_async() -> None:
    while True:
        with _LOCK:
            now = time.time()
            wait_for = _compute_wait(now)
            if wait_for <= 0:
                _record_request(time.time())
                return
        if wait_for > 0:
            logging.info(
                "[GlobalLLMRateLimiter] Waiting %.2fs before next LLM call (async)",
                wait_for,
            )
            await asyncio.sleep(_sleep_interval(wait_for))


def _wrap_sync_method(cls, method_name: str) -> None:
    if cls is None:
        return
    original = getattr(cls, method_name, None)
    if original is None or getattr(original, "_global_llm_wrapped", False):
        return

    def _wrapper(self, *args, **kwargs):
        _block_until_slot_sync()
        return original(self, *args, **kwargs)

    _wrapper._global_llm_wrapped = True  # type: ignore[attr-defined]
    setattr(cls, method_name, _wrapper)


def _wrap_async_method(cls, method_name: str) -> None:
    if cls is None:
        return
    original = getattr(cls, method_name, None)
    if original is None or getattr(original, "_global_llm_wrapped", False):
        return

    async def _wrapper(self, *args, **kwargs):
        await _block_until_slot_async()
        return await original(self, *args, **kwargs)

    _wrapper._global_llm_wrapped = True  # type: ignore[attr-defined]
    setattr(cls, method_name, _wrapper)


def install_global_llm_rate_limiter(min_interval: float, rpm_limit: int) -> None:
    """Patch google.genai.models.Models/AsyncModels to enforce global limits."""
    global _MIN_INTERVAL, _RPM_LIMIT, _PATCH_INSTALLED

    if _PATCH_INSTALLED:
        return

    try:
        import google.genai.models as genai_models  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        logging.warning("Global LLM rate limiter unavailable: %s", exc)
        return

    models_cls = getattr(genai_models, "Models", None)
    async_models_cls = getattr(genai_models, "AsyncModels", None)
    if models_cls is None and async_models_cls is None:
        logging.warning("Global LLM rate limiter unavailable: Models classes missing")
        return

    _MIN_INTERVAL = max(min_interval, 0.1)
    _RPM_LIMIT = max(int(rpm_limit), 1)

    logging.info(
        "Installing global LLM rate limiter (interval=%.2fs, rpm=%s)",
        _MIN_INTERVAL,
        _RPM_LIMIT,
    )

    _wrap_sync_method(models_cls, "generate_content")
    _wrap_async_method(async_models_cls, "generate_content")

    _PATCH_INSTALLED = True
