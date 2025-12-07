"""Utility helpers for resilient Gemini calls."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from src.config import (
    LLM_MAX_RETRY_ATTEMPTS,
    LLM_MIN_CALL_INTERVAL,
    LLM_RPM_LIMIT,
)

try:  # Import may differ across google-genai versions
    from google.genai.errors import ClientError  # type: ignore
except Exception:  # pragma: no cover - optional dependency variations
    ClientError = Exception  # type: ignore

RETRYABLE_STATUS = {429, 500, 503}
REQUEST_LOCK = threading.Lock()
LAST_REQUEST_TS = 0.0
REQUEST_HISTORY = deque(maxlen=max(LLM_RPM_LIMIT, 10))
MIN_INTERVAL = LLM_MIN_CALL_INTERVAL
RESPONSE_CACHE: dict[str, Any] = {}


def _is_retryable(error: Exception) -> bool:
    """Return True if the exception merits a retry."""
    status = getattr(error, "status_code", None)
    if status in RETRYABLE_STATUS:
        return True
    if isinstance(error, ClientError):  # type: ignore[arg-type]
        # ClientError without status often maps to throttling as well.
        return True
    return False


def _respect_rate_limits() -> None:
    """Block until both per-request and per-minute limits are satisfied."""
    global LAST_REQUEST_TS
    now = time.time()
    wait_for_interval = LAST_REQUEST_TS + MIN_INTERVAL - now
    if wait_for_interval > 0:
        time.sleep(wait_for_interval)
        now = time.time()

    # Clean up history older than 60 seconds
    window_start = now - 60.0
    while REQUEST_HISTORY and REQUEST_HISTORY[0] < window_start:
        REQUEST_HISTORY.popleft()

    if len(REQUEST_HISTORY) >= LLM_RPM_LIMIT:
        wait_for_window = 60.0 - (now - REQUEST_HISTORY[0])
        if wait_for_window > 0:
            time.sleep(wait_for_window)
            now = time.time()
            window_start = now - 60.0
            while REQUEST_HISTORY and REQUEST_HISTORY[0] < window_start:
                REQUEST_HISTORY.popleft()

    LAST_REQUEST_TS = time.time()
    REQUEST_HISTORY.append(LAST_REQUEST_TS)


def generate_with_retry(
    model: Any,
    prompt: str,
    max_attempts: int | None = None,
    base_delay: int = 3,
    enable_cache: bool = True,
):
    """Invoke model.generate_content with exponential backoff on retryable failures."""
    import hashlib
    
    # Check cache first
    if enable_cache:
        cache_key = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        if cache_key in RESPONSE_CACHE:
            logging.info("Cache hit for prompt (key: %s)", cache_key)
            return RESPONSE_CACHE[cache_key]
    
    last_error: Exception | None = None
    attempts = max_attempts or LLM_MAX_RETRY_ATTEMPTS
    for attempt in range(1, attempts + 1):
        try:
            with REQUEST_LOCK:
                _respect_rate_limits()
            result = model.generate_content(prompt)
            
            # Cache successful response
            if enable_cache:
                RESPONSE_CACHE[cache_key] = result
            
            return result
        except Exception as exc:  # pragma: no cover - network exceptions are runtime only
            last_error = exc
            if attempt >= attempts or not _is_retryable(exc):
                raise
            sleep_for = float(base_delay ** attempt)
            logging.warning(
                "LLM call failed (attempt %s/%s): %s. Retrying in %.1fs",
                attempt,
                attempts,
                exc,
                sleep_for,
            )
            time.sleep(sleep_for)
    if last_error:
        raise last_error
    raise RuntimeError("generate_with_retry failed without executing model call")
