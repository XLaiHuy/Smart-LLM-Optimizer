"""Single-process pacing/cache helper, not an adaptive token bucket.

The minimum interval is configurable (4.2 seconds by default). Project/model/tier
quotas still require review. Only explicit 429 failures are retried here; the paid
training pipeline uses separate asynchronous metered dispatch with no auto retry.
"""

from __future__ import annotations

import hashlib
import json
import random
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_PATH = ROOT_DIR / "data" / "cache" / "gemini_eval_cache.json"


class GeminiRateLimiter:
    """Synchronous, single-process throttle/cache. Share one instance between threads.

    Actual RPM/TPM/RPD depend on project/model/tier; this is not a quota guarantee.
    Uncertain dispatch errors are never retried automatically.
    """

    def __init__(
        self,
        min_interval_seconds: float = 4.2,
        max_retries: int = 4,
        cache_path: Path | str = DEFAULT_CACHE_PATH,
    ) -> None:
        self.min_interval = min_interval_seconds
        if min_interval_seconds < 0 or max_retries < 0:
            raise ValueError("Invalid limiter configuration")
        self._lock = threading.RLock()
        self.max_retries = max_retries
        self.cache_path = Path(cache_path)
        self.last_call_timestamp: float = 0.0
        self._cache: dict[str, Any] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            temporary = self.cache_path.with_suffix(".tmp")
            with temporary.open("w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
            temporary.replace(self.cache_path)
        except OSError:
            raise

    def compute_cache_key(self, model: str, prompt: str, **kwargs: Any) -> str:
        payload = json.dumps({"model": model, "prompt": prompt, "kwargs": kwargs}, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def wait_for_slot(self) -> float:
        """Wait until at least `min_interval` seconds have passed since the last call."""
        with self._lock:
            return self._wait_for_slot()

    def _wait_for_slot(self) -> float:
        now = time.monotonic()
        elapsed = now - self.last_call_timestamp
        waited = 0.0
        if elapsed < self.min_interval and self.last_call_timestamp > 0.0:
            waited = self.min_interval - elapsed
            time.sleep(waited)
        self.last_call_timestamp = time.monotonic()
        return waited

    def execute_with_throttle(
        self,
        cache_key: str,
        call_fn: Callable[[], dict[str, Any]],
        *,
        force_refresh: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        """Executes API call with disk caching and rate limit throttling.

        Returns:
            (response_dict, was_cached)
        """
        with self._lock:
            return self._execute(cache_key, call_fn, force_refresh=force_refresh)

    def _execute(
        self, cache_key: str, call_fn: Callable[[], dict[str, Any]], *, force_refresh: bool
    ) -> tuple[dict[str, Any], bool]:
        if not force_refresh and cache_key in self._cache:
            return self._cache[cache_key], True

        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self.wait_for_slot()
            try:
                result = call_fn()
                # Check for HTTP 429 inside result if returned as dict
                status_code = result.get("status_code", 200)
                if status_code == 429:
                    error = RuntimeError("Rate limit 429 exceeded from provider")
                    error.status_code = 429  # type: ignore[attr-defined]
                    raise error
                if status_code >= 400:
                    raise RuntimeError("Provider rejected the request")

                # Store in cache
                self._cache[cache_key] = result
                self._save_cache()
                return result, False
            except Exception as e:
                last_err = e
                if getattr(e, "status_code", None) != 429:
                    raise
                if attempt < self.max_retries:
                    # Exponential backoff: min(2^attempt * 3s + jitter, 30s)
                    jitter = random.uniform(0.5, 1.5)
                    backoff = min((2**attempt) * 3.0 + jitter, 30.0)
                    time.sleep(backoff)
                else:
                    raise last_err from None

        raise RuntimeError("Exceeded max retries in GeminiRateLimiter")
