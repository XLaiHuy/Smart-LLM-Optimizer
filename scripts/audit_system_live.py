"""Explicit bounded HTTP integration audit; never run from tests or CI.

Uses a short-lived owned auth session without changing the administrator password.
Requests and responses are persisted before/after dispatch. Never auto-replays an
uncertain call. Goes through the running frontend proxy and backend HTTP server.
"""

import argparse
import asyncio
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx
from app.config import ROOT, Settings
from app.storage.database import Database
from app.storage.models import AuthSession, User
from sqlalchemy import delete, select


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def cases():
    return [
        ("empty", "", {}, 422),
        ("whitespace", " \n\t ", {}, 422),
        ("over_input_limit", "x" * 50001, {}, 422),
        ("short_easy", "1 + 1 bằng mấy? Chỉ trả lời một từ.", {"router": True}, 200),
        (
            "short_hard",
            "Một giá trị giảm 2% còn 8722. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số.",
            {"router": True},
            200,
        ),
        (
            "unicode",
            "Tính (−313) + (−211). Chỉ trả lời kết quả, giữ dấu âm.",
            {"router": True},
            200,
        ),
        (
            "code",
            "Viết hàm Python tìm phần tử xuất hiện nhiều nhất; nếu hòa chọn phần tử xuất hiện trước. Cho ví dụ [2,1,1,2].",
            {"router": True},
            200,
        ),
        (
            "long_context",
            "\n".join(
                f"Dòng {i}: thông tin phụ cho bài kiểm tra tích hợp."
                for i in range(200)
            )
            + "\nMã xác nhận là OU-4729. Chỉ trả lại mã xác nhận.",
            {"router": True, "context": True},
            200,
        ),
        (
            "hybrid_rules",
            ("Vui lòng giúp tôi xem xét yêu cầu này một cách thật cẩn thận. " * 14)
            + "\nTính 125 - 200. Không đổi dấu âm. Chỉ trả lời số.",
            {"router": True, "rewrite": True, "context": True, "memory": True},
            200,
        ),
        (
            "memory_unknown",
            "Bạn có nhớ tôi tên gì, học ngành nào tại trường nào và đề tài nghiên cứu của tôi là gì không?",
            {"router": True, "context": True, "memory": True},
            200,
        ),
        (
            "memory_seed",
            "Tên tôi là Huy, học Công nghệ thông tin tại Đại học Mở TP.HCM. Đề tài của tôi là SmartLLM Router. Hãy xác nhận ngắn gọn.",
            {"router": True, "context": True, "memory": True},
            200,
        ),
        (
            "memory_recall",
            "Tôi tên gì, học ngành nào tại trường nào và đề tài nghiên cứu là gì? Trả lời ngắn.",
            {"router": True, "context": True, "memory": True},
            200,
        ),
        (
            "long_hybrid",
            (
                "Đây là đoạn dữ liệu nền để kiểm tra prompt dài. Không có dữ kiện quyết định trong đoạn này.\n\n"
                * 100
            )
            + "\nMã cuối cùng là BLUE-851. Chỉ trả lời mã này.",
            {"router": True, "rewrite": True, "context": True, "memory": True},
            200,
        ),
    ]


async def run(args):
    settings = Settings()
    if (
        not args.live
        or settings.app_env != "development"
        or settings.provider_mode != "live"
    ):
        raise ValueError("Explicit --live and development live configuration required")
    directory = ROOT / args.output
    if directory.exists():
        raise ValueError("Use a new audit directory; do not replay prior paid cases")
    directory.mkdir(parents=True)
    db = Database(settings)
    token = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(token.encode()).hexdigest()
    spent = Decimal(0)
    request_cap = Decimal(".01")
    planned_cases = cases()
    if getattr(args, "compression_cases", False):
        for language, background, task in (
            ("vi", "Cuộc họp trao đổi thông tin chung về hoạt động và kế hoạch của nhóm sinh viên.\n\n",
             "Mã xác nhận là BLUE-851. Chỉ trả lời mã xác nhận."),
            ("en", "The meeting provides general background information about university planning and student activities.\n\n",
             "The confirmation code is BLUE-851. Reply only with the code."),
        ):
            for rewrite in (False, True):
                planned_cases.append((f"compression_{language}_{'on' if rewrite else 'off'}",
                                      background * 40 + task,
                                      {"router": True, "rewrite": rewrite,
                                       "context": True, "memory": True}, 200))
    # Keep the operator's existing per-round ceiling even with extra cases.
    # Each dispatch requires room for its complete .01 USD reservation.
    cap = Decimal(".13")
    results = []
    write(
        directory / "protocol.json",
        {
            "transport": args.url,
            "max_request_usd": str(request_cap),
            "campaign_usd": str(cap),
            "case_ids": [c[0] for c in cases()],
            "no_automatic_unknown_retry": True,
            "auth": "short-lived existing-admin session; browser password login not exercised",
            "qualification": "integration/performance only; not scientific model qualification",
        },
    )
    try:
        async with db.write() as session:
            user = await session.scalar(
                select(User).where(User.username == "admin", User.role == "admin")
            )
            if user is None:
                raise ValueError("Existing admin required")
            session.add(
                AuthSession(
                    token_hash=hashed,
                    user_id=user.id,
                    expires_at=(datetime.now(UTC) + timedelta(minutes=25)).isoformat(),
                )
            )
        async with httpx.AsyncClient(
            base_url=args.url, timeout=135, cookies={"smartllm_session": token}
        ) as client:
            memory_sid = None
            for name, message, flags, expected in planned_cases:
                if spent + request_cap > cap:
                    raise ValueError("Campaign cap reached")
                if name == "memory_recall":
                    sid = memory_sid
                else:
                    response = await client.post(
                        "/sessions", json={"title": "System audit · " + name}
                    )
                    response.raise_for_status()
                    sid = response.json()["id"]
                    if name == "memory_seed":
                        memory_sid = sid
                body = {
                    "session_id": sid,
                    "client_request_id": "system-audit-" + str(uuid4()),
                    "message": message,
                    "mode": "optimized",
                    "flags": flags,
                    "constraints": {
                        "max_total_usd": str(request_cap),
                        "deadline_ms": 30000,
                    },
                }
                write(directory / (name + ".request.json"), body)
                started = perf_counter()
                try:
                    response = await client.post("/chat", json=body)
                except httpx.HTTPError as exc:
                    write(
                        directory / (name + ".transport-error.json"),
                        {
                            "type": type(exc).__name__,
                            "dispatch": "unknown; do not retry",
                        },
                    )
                    raise
                elapsed = (perf_counter() - started) * 1000
                try:
                    data = response.json()
                except ValueError:
                    write(
                        directory / (name + ".non-json-error.json"),
                        {
                            "status": response.status_code,
                            "content_type": response.headers.get("content-type"),
                            "dispatch": "check persisted request before any retry",
                        },
                    )
                    raise

                write(directory / (name + ".response.json"), data)
                entry = {
                    "case": name,
                    "status": response.status_code,
                    "expected_status": expected,
                    "http_ms": elapsed,
                    "input_chars": len(message),
                    "flags": flags,
                    "issues": [],
                }
                progress = await client.get(
                    f"/sessions/{sid}/progress",
                    params={"client_request_id": body["client_request_id"]},
                )
                if progress.status_code == 200:
                    detail = progress.json()
                    write(directory / (name + ".progress.json"), detail)
                    entry["stage_ms"] = {
                        e["stage"]: (
                            datetime.fromisoformat(e["finished_at"])
                            - datetime.fromisoformat(e["started_at"])
                        ).total_seconds()
                        * 1000
                        for e in detail["events"]
                        if e.get("finished_at")
                    }
                if response.status_code == 200:
                    route = data["route"]
                    cost = data["cost"]
                    if cost.get("serving_usd") is None:
                        raise ValueError(
                            "Unknown request cost; stop further paid calls"
                        )
                    spent += Decimal(cost["serving_usd"])
                    trace_response = await client.get("/traces/" + data["request_id"])
                    trace_response.raise_for_status()
                    trace = trace_response.json()
                    write(directory / (name + ".trace.json"), trace)
                    entry.update(
                        request_id=data["request_id"],
                        model=route["model_id"],
                        route_reason=route["reason"],
                        ml_executed=route["ml_executed"],
                        attention_executed=route["attention_executed"],
                        latency=data.get("latency"),
                        cost=cost,
                        modules=trace.get("states", trace.get("modules")),
                        answer=data["response"]["content"][:1200],
                    )
                    if trace["calls"][-1]["model_id"] != route["model_id"]:
                        entry["issues"].append("trace_model_mismatch")
                    if name == "short_easy":
                        replay = await client.post("/chat", json=body)
                        entry["duplicate_same_request"] = (
                            replay.status_code == 200
                            and replay.json().get("request_id") == data["request_id"]
                        )
                        if not entry["duplicate_same_request"]:
                            entry["issues"].append("idempotency_mismatch")
                else:
                    entry["error"] = data.get("error", {})
                    if expected != response.status_code:
                        entry["issues"].append("unexpected_status")
                    if response.status_code >= 500:
                        # Read owned calls before deciding whether another dispatch is safe.
                        rid = data.get("error", {}).get("request_id")
                        if rid:
                            calls = await client.get(f"/traces/{rid}/calls")
                            write(
                                directory / (name + ".failed-calls.json"), calls.json()
                            )
                        results.append(entry)
                        break
                results.append(entry)
                write(
                    directory / "results.json",
                    {"cases": results, "known_usd": str(spent), "finished": False},
                )
                print(
                    json.dumps(
                        {
                            k: entry.get(k)
                            for k in ("case", "status", "http_ms", "stage_ms", "issues")
                        }
                    ),
                    flush=True,
                )
            write(
                directory / "results.json",
                {
                    "cases": results,
                    "known_usd": str(spent),
                    "finished": len(results) == len(planned_cases),
                    "serving_artifact_changed": False,
                },
            )
    finally:
        async with db.write() as session:
            await session.execute(
                delete(AuthSession).where(AuthSession.token_hash == hashed)
            )
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--url", default="http://host.docker.internal:3000/api/v1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compression-cases", action="store_true",
                        help="Add four paired original/compressed VI/EN manual live probes")
    asyncio.run(run(parser.parse_args()))
