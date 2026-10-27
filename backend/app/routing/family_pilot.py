"""Read-only accounting fences for operator-run paired family pilots."""

import json
from decimal import Decimal
from pathlib import Path


def checkpoint_spend(directory: Path, candidate_sha256: str) -> Decimal:
    """Inspect ALL previous dispatches before allowing any new paid request."""
    for marker in directory.glob("*.dispatch.json"):
        result = marker.with_name(marker.name.removesuffix(".dispatch.json") + ".result.json")
        if not result.exists():
            raise ValueError("Unresolved pilot dispatch: stop without replay")
    total = Decimal(0)
    for path in directory.glob("*.result.json"):
        record = json.loads(path.read_text())
        if record.get("candidate_sha256") != candidate_sha256:
            raise ValueError("Pilot checkpoint belongs to another candidate")
        amount = Decimal(record["usd"])
        if not amount.is_finite() or amount < 0:
            raise ValueError("Invalid pilot checkpoint cost")
        calls = record["calls"]
        if not calls or any(
            c["cost"].get("serving_usd") is None
            or c["cost"]["status"] == "unknown"
            or c.get("dispatch_state") == "unknown"
            for c in calls
        ):
            raise ValueError("Unresolved pilot call cost/dispatch")
        costs = [Decimal(c["cost"]["serving_usd"]) for c in calls]
        if any(not c.is_finite() or c < 0 for c in costs) or sum(costs) != amount:
            raise ValueError("Pilot checkpoint does not match call billing")
        total += amount
    return total
