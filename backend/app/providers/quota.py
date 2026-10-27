"""SQLite admission control. Reservations survive workers, restarts and uncertain dispatch.

Quota is independent of USD accounting. Unknown usage retains the conservative token
reservation until its window expires; a failed request still consumes an attempt.
"""

import json
import math
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from time import time
from urllib.parse import urlsplit
from uuid import uuid4

from app.config import Settings
from app.contracts.errors import AppError
from app.providers.catalog import ModelEntry
from app.storage.database import Database
from app.storage.models import ProviderQuotaBucket


def retry_seconds(value: str | None, now: float | None = None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(
                0.0, parsedate_to_datetime(value).timestamp() - (time() if now is None else now)
            )
        except (ValueError, TypeError, OverflowError):
            return None


def reset_seconds(value: str | None) -> float | None:
    if not value:
        return None
    import re

    parts = re.findall(r"([\d.]+)(ms|h|m|s)", value)
    if parts:
        return sum(float(n) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit] for n, unit in parts)
    return retry_seconds(value)


class ProviderQuota:
    def __init__(self, db: Database, settings: Settings, clock: Callable[[], float] = time):
        self.db, self.settings, self.clock = db, settings, clock

    def scope(self, entry: ModelEntry) -> str:
        host = urlsplit(entry.base_url or "https://api.openai.com/v1").hostname or "unknown"
        model = (
            "free-models"
            if host == "openrouter.ai"
            and (entry.model_id.endswith(":free") or entry.model_id == "openrouter/free")
            else entry.model_id
        )
        return f"{host}:{self.settings.provider_quota_account}:{model}"

    def limits(self, entry: ModelEntry) -> tuple[int, int, int | None, int | None]:
        host = urlsplit(entry.base_url or "").hostname
        s = self.settings
        if host == "api.groq.com":
            return s.groq_quota_rpm, s.groq_quota_rpd, s.groq_quota_tpm, s.groq_quota_tpd
        if host == "openrouter.ai" and (
            entry.model_id.endswith(":free") or entry.model_id == "openrouter/free"
        ):
            return s.openrouter_free_rpm, s.openrouter_free_rpd, None, None
        if host == "openrouter.ai":
            return s.openrouter_paid_rpm, 1000000, None, None
        if host == "api.openai.com":
            return s.openai_quota_rpm, 1000000, None, None
        return 1000000, 1000000, None, None

    async def free_metadata_due(self, entry: ModelEntry) -> bool:
        async with self.db.sessions() as db:
            row = await db.get(ProviderQuotaBucket, self.scope(entry))
            state = json.loads(row.state_json) if row else {}
            return bool(self.clock() - state.get("free_checked_at", 0) >= 300)

    async def sync_free_metadata(self, entry: ModelEntry, data: Mapping[str, object]) -> None:
        quota = data.get("free_model_daily_requests")
        if not isinstance(quota, dict) or any(
            type(quota.get(k)) is not int for k in ("used", "limit", "remaining")
        ):
            return
        now = self.clock()
        usable = max(0, min(quota["remaining"], int(quota["limit"] * 0.8) - quota["used"]))
        reset = (
            datetime.fromtimestamp(now, UTC)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
            + 86400
        )
        async with self.db.write() as db:
            row = await db.get(ProviderQuotaBucket, self.scope(entry))
            if row is None:
                row = ProviderQuotaBucket(scope_key=self.scope(entry), state_json="{}")
                db.add(row)
            state = json.loads(row.state_json)
            if state.get("requests_reset", 0) > now and state.get("requests_remaining") is not None:
                usable = min(usable, state["requests_remaining"])
            state.update(
                free_checked_at=now,
                observed_rpd=max(1, int(quota["limit"] * 0.8)),
                requests_remaining=usable,
                requests_reset=reset,
            )
            row.state_json = json.dumps(state)

    async def acquire(self, entry: ModelEntry, tokens: int) -> str:
        now = self.clock()
        scope = self.scope(entry)
        rpm, rpd, tpm, tpd = self.limits(entry)
        if tpm is not None and tokens > tpm or tpd is not None and tokens > tpd:
            raise AppError(
                "PROVIDER_REQUEST_TOO_LARGE",
                422,
                "Input plus output reserve exceeds provider quota profile",
                dispatch_state="not_dispatched",
            )
        async with self.db.write() as db:
            row = await db.get(ProviderQuotaBucket, scope)
            state = json.loads(row.state_json) if row else {}
            rpd = min(rpd, state.get("observed_rpd", rpd))
            tpm = min(tpm, state.get("observed_tpm", tpm)) if tpm is not None else None
            if tpm is not None and tokens > tpm:
                raise AppError(
                    "PROVIDER_REQUEST_TOO_LARGE",
                    422,
                    "Request exceeds observed provider quota",
                    dispatch_state="not_dispatched",
                )
            # OpenRouter's daily free counter resets at UTC midnight. Groq is
            # conservatively rolling 24h unless its observed reset is stricter.
            day_start = (
                datetime.fromtimestamp(now, UTC)
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .timestamp()
            )
            cutoff = day_start if scope.startswith("openrouter.ai:") else now - 86400
            events = [e for e in state.get("events", []) if e[1] > cutoff]
            recent = [e for e in events if e[1] > now - 60]
            wait = max(0.0, state.get("blocked_until", 0) - now)
            for group, cap, token_cap, window in [
                (recent, rpm, tpm, 60),
                (events, rpd, tpd, 86400),
            ]:
                if (
                    len(group) >= cap
                    or token_cap is not None
                    and sum(e[2] for e in group) + tokens > token_cap
                ):
                    wait = max(
                        wait,
                        (day_start + 86400 - now)
                        if window == 86400 and scope.startswith("openrouter.ai:")
                        else group[0][1] + window - now,
                    )
            for kind, amount in [("tokens", tokens), ("requests", 1)]:
                reset = state.get(f"{kind}_reset", 0)
                left = state.get(f"{kind}_remaining")
                if reset > now and left is not None and left < amount:
                    wait = max(wait, reset - now)
            if wait > 0:
                raise AppError(
                    "RATE_LIMITED",
                    429,
                    "Provider quota is temporarily exhausted",
                    retry_after_seconds=math.ceil(wait),
                    dispatch_state="not_dispatched",
                )
            ticket = uuid4().hex
            events.append([ticket, now, tokens])
            state["events"] = events
            for kind, amount in [("tokens", tokens), ("requests", 1)]:
                if (
                    state.get(f"{kind}_reset", 0) > now
                    and state.get(f"{kind}_remaining") is not None
                ):
                    state[f"{kind}_remaining"] = max(0, state[f"{kind}_remaining"] - amount)
            if row is None:
                row = ProviderQuotaBucket(scope_key=scope, state_json="{}")
                db.add(row)
            row.state_json = json.dumps(state)
        return ticket

    async def reconcile(self, entry: ModelEntry, ticket: str, tokens: int | None) -> None:
        if tokens is None:
            return
        async with self.db.write() as db:
            row = await db.get(ProviderQuotaBucket, self.scope(entry))
            if row:
                state = json.loads(row.state_json)
                for event in state.get("events", []):
                    if event[0] == ticket:
                        event[2] = max(0, tokens)
                row.state_json = json.dumps(state)

    async def observe(self, entry: ModelEntry, headers: Mapping[str, str], status: int) -> None:
        now = self.clock()
        async with self.db.write() as db:
            row = await db.get(ProviderQuotaBucket, self.scope(entry))
            if row is None:
                row = ProviderQuotaBucket(scope_key=self.scope(entry), state_json="{}")
                db.add(row)
            state = json.loads(row.state_json)
            if self.scope(entry).startswith("api.groq.com:"):
                for name, field in [("requests", "observed_rpd"), ("tokens", "observed_tpm")]:
                    try:
                        reported_limit = int(headers.get(f"x-ratelimit-limit-{name}", "0"))
                    except ValueError:
                        continue
                    if reported_limit > 0:
                        state[field] = max(1, int(reported_limit * 0.8))
            if status == 429:
                wait = retry_seconds(headers.get("retry-after"), now)
                state["blocked_until"] = max(
                    state.get("blocked_until", 0), now + (wait if wait is not None else 60)
                )
            for kind in ("tokens", "requests"):
                reset = reset_seconds(headers.get(f"x-ratelimit-reset-{kind}"))
                remaining = headers.get(f"x-ratelimit-remaining-{kind}")
                if reset is not None and remaining is not None:
                    try:
                        reported = max(0, int(remaining))
                    except ValueError:
                        continue
                    # Concurrent responses can arrive out of order. Never add
                    # capacity within an observed window from an older response.
                    if state.get(f"{kind}_reset", 0) > now:
                        reported = min(reported, state.get(f"{kind}_remaining", reported))
                    state[f"{kind}_remaining"] = reported
                    state[f"{kind}_reset"] = now + reset
            row.state_json = json.dumps(state)
