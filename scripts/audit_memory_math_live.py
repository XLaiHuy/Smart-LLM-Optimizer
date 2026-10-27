"""Explicit manual live audit: isolated users, arithmetic and long conversation.

No tests/CI entry point. Ceiling .13 USD total, .01 per request, no unknown retry.
Persists each request before dispatch and revokes temporary authentication at exit.
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
from app.auth.service import AuthService
from app.config import ROOT, Settings
from app.storage.database import Database
from app.storage.models import AuthSession
from sqlalchemy import delete


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalized(text):
    return " ".join(text.casefold().split())


async def run(args):
    settings = Settings()
    if (
        not args.live
        or settings.app_env != "development"
        or settings.provider_mode != "live"
    ):
        raise ValueError("Explicit development --live required")
    output = ROOT / args.output
    output.mkdir(parents=True, exist_ok=False)
    db = Database(settings)
    auth = AuthService(db, settings)
    cap, spent, reservation = Decimal(".13"), Decimal(0), Decimal(".01")
    tokens, rows = [], []
    users = []
    report = {
        "campaign_cap_usd": str(cap),
        "request_cap_usd": str(reservation),
        "fresh_accounts": True,
        "turns_planned": args.turns,
        "unknown_paid_retry": False,
        "cases": rows,
        "finished": False,
    }
    write(output / "protocol.json", report)
    try:
        for suffix, quota in (("a", cap), ("b", reservation)):
            user = await auth.create_user(
                "audit-" + suffix + "-" + uuid4().hex[:12],
                secrets.token_urlsafe(32),
                quota=quota,
                account_purpose="internal_audit",
            )
            users.append(user)
            token = secrets.token_urlsafe(32)
            hashed = hashlib.sha256(token.encode()).hexdigest()
            tokens.append((token, hashed))
            async with db.write() as session:
                session.add(
                    AuthSession(
                        token_hash=hashed,
                        user_id=user.id,
                        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    )
                )
        report["users"] = [{"id": user.id, "username": user.username} for user in users]
        clients = [
            httpx.AsyncClient(
                base_url=args.url, timeout=130, cookies={"smartllm_session": token}
            )
            for token, _ in tokens
        ]

        async def session(client, title):
            result = await client.post("/sessions", json={"title": title})
            result.raise_for_status()
            return result.json()["id"]

        async def send(
            name,
            message,
            *,
            client=None,
            sid=None,
            expected=None,
            required=(),
            forbidden=(),
            flags=None,
        ):
            nonlocal spent
            client = client or clients[0]
            if spent + reservation > cap:
                raise ValueError("Campaign cap reached; no more calls")
            sid = sid or await session(client, name)
            body = {
                "session_id": sid,
                "client_request_id": "audit-quality-" + str(uuid4()),
                "message": message,
                "mode": "optimized",
                "flags": flags
                or {"router": True, "rewrite": True, "context": True, "memory": True},
                "constraints": {
                    "max_total_usd": str(reservation),
                    "deadline_ms": 60000,
                },
            }
            write(output / (name + ".request.json"), body)
            start = perf_counter()
            try:
                response = await client.post("/chat", json=body)
            except httpx.HTTPError as exc:
                write(
                    output / (name + ".unknown.json"),
                    {"error": type(exc).__name__, "stop_paid_calls": True},
                )
                raise
            elapsed = (perf_counter() - start) * 1000
            data = response.json()
            write(output / (name + ".response.json"), data)
            if response.status_code != 200:
                write(
                    output / (name + ".error.json"),
                    {
                        "status": response.status_code,
                        "body": data,
                        "no_automatic_retry": True,
                    },
                )
                raise ValueError(
                    f"{name}: HTTP {response.status_code}; inspect dispatch before any retry"
                )
            cost = data["cost"]["serving_usd"]
            if cost is None:
                raise ValueError("Unknown request cost; stop")
            spent += Decimal(cost)
            trace = await client.get("/traces/" + data["request_id"])
            trace.raise_for_status()
            trace = trace.json()
            write(output / (name + ".trace.json"), trace)
            answer = data["response"]["content"]
            grade = (
                None
                if expected is None
                else answer.strip().replace(",", "") == expected
            )
            checks = {
                literal: normalized(literal) in normalized(answer)
                for literal in required
            }
            checks.update(
                {
                    f"absent:{literal}": literal.casefold() not in answer.casefold()
                    for literal in forbidden
                }
            )
            row = {
                "case": name,
                "session_id": sid,
                "request_id": data["request_id"],
                "http_ms": elapsed,
                "answer": answer,
                "expected": expected,
                "exact_answer_pass": grade,
                "required_checks": checks,
                "checks_pass": all(checks.values()),
                "model": data["route"]["model_id"],
                "ml_executed": data["route"]["ml_executed"],
                "attention_executed": data["route"]["attention_executed"],
                "usage": data["usage"],
                "cost_usd": cost,
                "optimizations": trace["optimizations"],
            }
            rows.append(row)
            report["known_usd"] = str(spent)
            write(output / "results.json", report)
            print(
                json.dumps(
                    {
                        k: row[k]
                        for k in (
                            "case",
                            "model",
                            "http_ms",
                            "exact_answer_pass",
                            "checks_pass",
                        )
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            return row

        try:
            await send(
                "fresh_unknown",
                "Bạn có biết tên tôi, ngành học, trường và đề tài nghiên cứu của tôi không? Nếu chưa có dữ kiện, nói rõ chưa biết, không đoán.",
                forbidden=("SmartLLM Router", "Huy", "An Khang"),
            )
            for i in range(3):
                await send(
                    f"math_percentage_repeat_{i + 1}",
                    "Một giá trị giảm 2% còn 8722. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số.",
                    expected="8900",
                )
            for name, text, expected in (
                (
                    "math_reverse",
                    "Một giá trị giảm 20% còn 96. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số.",
                    "120",
                ),
                (
                    "math_forward",
                    "Giảm 15% của 200, giá trị còn lại là bao nhiêu? Chỉ trả lời số.",
                    "170",
                ),
                ("activate_20b", "Tính (−313) + (−211). Chỉ trả lời kết quả.", "-524"),
                (
                    "activate_luna",
                    "Số nào trong các số sau đây là bội của cả 2, 3, 5 và 9?\n\nA. 4 536\n\nB. 3 240\n\nC. 9 805\n\nD. 12 065\nChỉ trả lời một chữ cái trong các lựa chọn.",
                    "B",
                ),
            ):
                await send(name, text, expected=expected)
            sid = await session(clients[0], "Fresh long conversation")
            await send(
                "long_01_seed",
                "Tôi tên là An Khang.\nTôi học ngành Toán ứng dụng.\nTôi học tại Đại học Mở TP.HCM.\nĐề tài nghiên cứu của tôi là Cổng Kiểm thử Sao Bắc.\nHạn chót là 18/11/2026.\nChỉ xác nhận ngắn.",
                sid=sid,
            )
            for turn in range(2, args.turns + 1):
                if turn == 12:
                    text = "Tôi cập nhật hạn chót: hạn chót là 25/11/2026, thay cho 18/11/2026. Chỉ xác nhận ngắn."
                    required = ()
                elif turn in (6, 18, args.turns):
                    text = "Nhắc lại tên tôi, ngành học, trường, đề tài nghiên cứu và hạn chót mới nhất. Dùng đúng dữ kiện tôi đã cung cấp."
                    required = (
                        "An Khang",
                        "Toán ứng dụng",
                        "Đại học Mở",
                        "Cổng Kiểm thử Sao Bắc",
                        "25/11/2026" if turn > 12 else "18/11/2026",
                    )
                else:
                    text = (
                        "Đây là phần thảo luận nền về tổ chức công việc nhóm, thư viện, lịch trao đổi và quy trình kiểm thử. Các thành viên trao đổi ý tưởng về cách chuẩn bị tài liệu và ghi chép kết quả.\n\n"
                        * 10
                    ) + "Chỉ trả lời OK."
                    required = ()
                await send(f"long_{turn:02}", text, sid=sid, required=required)
            await send(
                "cross_session_recall",
                "Tên tôi, ngành học, trường, đề tài và hạn chót mới nhất là gì?",
                required=(
                    "An Khang",
                    "Toán ứng dụng",
                    "Đại học Mở",
                    "Cổng Kiểm thử Sao Bắc",
                    "25/11/2026",
                ),
            )
            await send(
                "other_user_isolation",
                "Bạn có biết tên tôi và đề tài nghiên cứu của tôi không? Nếu chưa có dữ kiện, nói rõ chưa biết.",
                client=clients[1],
                forbidden=("An Khang", "Sao Bắc", "SmartLLM Router", "Huy"),
            )
            ownership = await clients[1].get("/sessions/" + sid)
            report["other_user_session_status"] = ownership.status_code
            if ownership.status_code != 404:
                raise ValueError("Ownership regression")
            detail = await clients[0].get("/sessions/" + sid)
            detail.raise_for_status()
            report["long_conversation_committed_messages"] = len(
                detail.json()["messages"]
            )
            report["finished"] = True
            write(output / "results.json", report)
        finally:
            for client in clients:
                await client.aclose()
    finally:
        async with db.write() as session:
            for _, hashed in tokens:
                await session.execute(
                    delete(AuthSession).where(AuthSession.token_hash == hashed)
                )
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--url", default="http://host.docker.internal:3000/api/v1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--turns", type=int, default=24, choices=range(18, 41))
    asyncio.run(run(parser.parse_args()))
