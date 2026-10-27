"""One explicitly authorized, metered development chat; never run from tests/CI.

Uses the application's actual routing/ledger/provider through in-process ASGI.
The existing administrator is resolved locally; this does not test browser login.
Persist the same request before dispatch so an interrupted run cannot mint a retry.
"""

import argparse
import asyncio
import json
from decimal import Decimal
from uuid import uuid4

import httpx
from app.config import ROOT, Settings
from app.contracts.dtos import Principal
from app.routing.ml.qualification import research_acceptance_failure
from app.storage.models import User
from sqlalchemy import select


async def run(args):
    settings = Settings()
    if (
        not args.live
        or settings.app_env != "development"
        or settings.provider_mode != "live"
        or not settings.ml_router_allow_research_candidate
    ):
        raise ValueError(
            "Explicit --live and accepted development research configuration required"
        )
    from app.api.routes import principal as principal_dependency
    from app.main import app

    c = app.state.container
    problem = research_acceptance_failure(
        c.ml_router.multi, settings.ml_router_research_acceptance_path
    )
    if problem:
        raise ValueError(problem)
    directory = ROOT / "data/operator-research-verification"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        async with c.db.sessions() as db:
            row = await db.scalar(
                select(User).where(User.username == args.owner, User.role == "admin")
            )
            if row is None:
                raise ValueError("An existing administrator is required")
            owner = Principal(
                id=row.id,
                username=row.username,
                role="admin",
                quota_usd=Decimal(row.quota_usd),
            )
        request_path = directory / "request.json"
        if request_path.exists():
            saved = json.loads(request_path.read_text(encoding="utf-8"))
            if (
                saved["artifact_hash"] != c.ml_router.hash
                or saved["owner_id"] != owner.id
            ):
                raise ValueError(
                    "Stored smoke request belongs to another artifact or owner"
                )
            body = saved["body"]
        else:
            session = await c.sessions.create(
                owner, "Kiểm tra ML + Attention được chấp nhận dùng thử"
            )
            body = {
                "session_id": session.id,
                "client_request_id": "operator-research-smoke-" + str(uuid4()),
                "message": "1 + 1 = mấy? Trả lời một từ duy nhất.",
                "mode": "optimized",
                "flags": {
                    "router": True,
                    "rewrite": False,
                    "context": False,
                    "memory": False,
                },
                "constraints": {"max_total_usd": ".01", "deadline_ms": 60000},
            }
            with request_path.open("x", encoding="utf-8") as file:
                file.write(
                    json.dumps(
                        {
                            "artifact_hash": c.ml_router.hash,
                            "owner_id": owner.id,
                            "body": body,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
        app.dependency_overrides[principal_dependency] = lambda: owner
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://operator-smoke"
        ) as client:
            response = await client.post("/v1/chat", json=body)
            if response.status_code != 200:
                safe = response.json().get("error", {})
                print(
                    json.dumps(
                        {
                            "status": response.status_code,
                            "code": safe.get("code"),
                            "request_id": safe.get("request_id"),
                            "automatic_new_paid_retry": False,
                        }
                    )
                )
                return 1
            result = response.json()
            trace_response = await client.get("/v1/traces/" + result["request_id"])
            trace_response.raise_for_status()
            trace = trace_response.json()
        (directory / "response.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (directory / "trace.json").write_text(
            json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        route = result["route"]
        assert route["ml_executed"] and route["attention_executed"]
        assert "operator_accepted_research" in route["rules_matched"]
        assert len(route["attention_features"]) == 6
        assert trace["calls"][-1]["model_id"] == route["model_id"]
        print(
            json.dumps(
                {
                    "request_id": result["request_id"],
                    "response": result["response"]["content"],
                    "model": route["model_id"],
                    "reason": route["reason"],
                    "ml_executed": route["ml_executed"],
                    "attention_executed": route["attention_executed"],
                    "cost": result["cost"],
                    "proof_directory": str(directory),
                    "measurement": "live provider through actual application and in-process ASGI; browser login not exercised",
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        app.dependency_overrides.pop(principal_dependency, None)
        if c.live:
            await c.live.close()
        await c.db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--owner", default="admin")
    raise SystemExit(asyncio.run(run(parser.parse_args())))
