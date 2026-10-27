from __future__ import annotations

from threading import Lock
from time import monotonic


class ModelHealth:
    """Theo dõi cooldown của model và provider sau lỗi runtime."""

    def __init__(self, identities: dict[str, str] | None = None) -> None:
        self.identities = identities or {}
        self._blocked_until: dict[str, float] = {}
        self._lock = Lock()

    def _provider_key(self, config_id: str) -> str:
        if config_id in self.identities:
            return self.identities[config_id].rsplit("|", 1)[0]
        provider = config_id.split("-", maxsplit=1)[0]
        return f"provider:{provider}"

    def _is_blocked(self, key: str) -> bool:
        blocked_until = self._blocked_until.get(key, 0.0)

        if monotonic() >= blocked_until:
            self._blocked_until.pop(key, None)
            return False

        return True

    def is_available(self, config_id: str) -> bool:
        with self._lock:
            return not (
                self._is_blocked(self.identities.get(config_id, config_id))
                or self._is_blocked(self._provider_key(config_id))
            )

    def record_success(self, config_id: str) -> None:
        with self._lock:
            # A concurrent success must not cancel another request's Retry-After.
            self._is_blocked(self.identities.get(config_id, config_id))

    def record_failure(
        self,
        config_id: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        if status_code == 401:
            cooldown_seconds = 3600
            block_provider = True
        elif status_code == 429:
            cooldown_seconds = 60
            block_provider = False
        elif status_code in (502, 503, 504):
            cooldown_seconds = 30
            block_provider = False
        else:
            return

        with self._lock:
            key = self.identities.get(config_id, config_id)
            self._blocked_until[key] = max(
                self._blocked_until.get(key, 0),
                monotonic()
                + (retry_after_seconds if retry_after_seconds is not None else cooldown_seconds),
            )

            if block_provider:
                self._blocked_until[self._provider_key(config_id)] = monotonic() + cooldown_seconds
