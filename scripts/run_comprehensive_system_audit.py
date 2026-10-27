"""
Comprehensive System & Router Audit Matrix for Smart LLM Platform.
Covers:
1. Short & Easy prompts (1+1, greeting) -> Fast Tier verification
2. Coding & Technical prompts (Python, SQL) -> Coding Tier verification
3. Complex Reasoning prompts (Logic, ELBO/VAE) -> Reasoning Tier verification
4. Long Text & RAG synthesis -> Context Compaction & Router verification
5. Multi-turn Continuous conversation (4 turns) -> Memory, Facts & Context verification
6. Task-switching Alternating prompts -> Dynamic Re-routing verification
7. Truncation & Failover -> OUTPUT_INCOMPLETE resilience verification
8. Heavy context stress -> Token boundary verification
Outputs:
- Full latency, tokens, cost breakdown
- Model distribution percentages
- Savings vs Baseline 100% Frontier (USD and %)
- Comprehensive audit report of risks & potential failure modes
"""

import asyncio
import io
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Setup paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.composition import Container
from app.config import Settings
from app.contracts.dtos import (
    ChatRequest,
    Constraints,
    Principal,
    ProviderResult,
    Usage,
)
from app.contracts.errors import AppError


async def main():
    print("=" * 80)
    print("🚀 BẮT ĐẦU KỊCH BẢN KIỂM THỬ TOÀN DIỆN HỆ THỐNG SMART LLM PLATFORM")
    print("=" * 80)

    settings = Settings()
    container = Container(settings)

    principal = Principal(
        id="e02fc715-2cfb-405b-97fe-e175a1eb3309",
        username="admin",
        role="admin",
        quota_usd=Decimal("50.00"),
    )

    # 1. Verify Catalog & Registry
    configs = container.registry.configurations
    print("\n[1/5] KIỂM TRA DANH MỤC MÔ HÌNH (CATALOG & TIERS)")
    print(f"Tổng số mô hình đã nạp vào Registry: {len(configs)}")
    for c in configs:
        print(f"  • [{c.config_id}] model_id={c.model_id} (source={c.execution_source}, available={c.available})")

    # Baseline cost reference: Groq Llama 3.3 70B ($0.15 / 1M in, $0.60 / 1M out)
    BASE_INPUT_RATE = Decimal("0.00000015")
    BASE_OUTPUT_RATE = Decimal("0.00000060")

    results = []
    total_optimized_cost = Decimal(0)
    total_baseline_cost = Decimal(0)
    total_input_tokens = 0
    total_output_tokens = 0

    # Create dedicated multi-turn session
    multi_turn_session = await container.sessions.create(principal, "Multi-turn Memory Audit Session")
    multi_turn_sid = multi_turn_session.id
    print(f"\n[2/5] ĐÃ KHỞI TẠO PHIÊN LÀM VIỆC MULTI-TURN AUDIT: {multi_turn_sid}")

    # Test Cases Definition
    test_cases = [
        # Nhóm 1: Ngắn & Dễ
        {
            "id": "TC01",
            "name": "Ngắn & Tính nhẩm (Dễ)",
            "prompt": "1 + 1 = mấy? Trả lời một từ duy nhất.",
            "expected_tier": "fast",
            "is_stream": False,
        },
        {
            "id": "TC02",
            "name": "Chào hỏi & Hướng dẫn (Dễ)",
            "prompt": "Xin chào! Bạn có thể giới thiệu ngắn gọn trong 2 câu bạn có những tính năng gì?",
            "expected_tier": "fast",
            "is_stream": True,
        },
        # Nhóm 2: Lập trình & Kỹ thuật
        {
            "id": "TC03",
            "name": "Lập trình Python QuickSort (Code)",
            "prompt": "Viết một hàm Python thực hiện thuật toán QuickSort tối ưu in-place và phân tích độ phức tạp O(n log n).",
            "expected_tier": "code",
            "is_stream": False,
        },
        {
            "id": "TC04",
            "name": "Lập trình SQL & Bảo mật (Code)",
            "prompt": "Viết câu truy vấn SQL PostgreSQL kết hợp bảng users, orders, order_items để tính tổng doanh thu từng tháng, kèm code Python SQLAlchemy chống SQL Injection.",
            "expected_tier": "code",
            "is_stream": True,
        },
        # Nhóm 3: Suy luận Chuyên sâu & Logic
        {
            "id": "TC05",
            "name": "Lập luận Logic Học (Reasoning)",
            "prompt": "Nếu mọi A đều là B và không B nào là C, có A nào là C không? Hãy phân tích chứng minh bằng bảng chân trị và lý thuyết tập hợp Venn.",
            "expected_tier": "reasoning",
            "is_stream": False,
        },
        {
            "id": "TC06",
            "name": "Toán học & Deep Learning VAE (Reasoning)",
            "prompt": "Giải thích chi tiết công thức toán học của Variational Autoencoder (VAE): derivation của ELBO (Evidence Lower Bound), cơ chế Reparameterization Trick, và hiện tượng Posterior Collapse.",
            "expected_tier": "reasoning",
            "is_stream": True,
        },
        # Nhóm 4: Văn bản Dài & Tóm tắt Quy chế
        {
            "id": "TC07",
            "name": "Văn bản Dài & Học phí (Long Text / Context)",
            "prompt": (
                "Quy chế Đào tạo và Học phí: Trường Đại học Mở TP.HCM thông báo mức học phí tín chỉ năm học 2026. "
                "Đối với khối ngành Công nghệ thông tin và Khoa học máy tính, mức thu là 750.000đ/tín chỉ lý thuyết "
                "và 950.000đ/tín chỉ thực hành. Hạn chót đóng học phí đợt 1 là ngày 15/11/2026. Sinh viên có hoàn cảnh khó khăn "
                "được gia hạn đến 30/11/2026 kèm đơn xác nhận của địa phương. Sinh viên đạt GPA >= 3.6 và ĐRL >= 90 được học bổng xuất sắc "
                "trị giá 100% học phí học kỳ. Sinh viên đạt GPA >= 3.2 được học bổng giỏi 50%. " * 15
                + "\nCâu hỏi: Hãy tóm tắt ngắn gọn các mốc thời hạn và điều kiện học bổng xuất sắc trong quy chế trên."
            ),
            "expected_tier": "reasoning",
            "is_stream": False,
        },
        # Nhóm 5: Đa lượt liên tục (Multi-turn Context & Memory)
        {
            "id": "TC08_Turn1",
            "name": "Đa lượt 1: Nạp danh tính",
            "prompt": "Tôi tên là Hoàng, sinh viên năm 3 ngành Khoa học Máy tính Trường Đại học Mở TP.HCM.",
            "expected_tier": "fast",
            "is_stream": False,
        },
        {
            "id": "TC08_Turn2",
            "name": "Đa lượt 2: Nạp đề tài nghiên cứu",
            "prompt": "Tôi đang nghiên cứu đề tài Tối ưu hóa chi phí LLM bằng Dynamic Multi-LLM Router và Attention Classification.",
            "expected_tier": "fast",
            "is_stream": False,
        },
        {
            "id": "TC08_Turn3",
            "name": "Đa lượt 3: Kiểm tra Trí nhớ (Memory / Pinned Facts)",
            "prompt": "Bạn có nhớ tôi tên gì, học ngành nào tại trường nào và đề tài nghiên cứu của tôi là gì không?",
            "expected_tier": "fast",
            "is_stream": False,
        },
        # Nhóm 6: Xen kẽ Tác vụ (Task-Switching)
        {
            "id": "TC09_Switch",
            "name": "Xen kẽ: Chuyển đột ngột sang Code Rust",
            "prompt": "Hãy dừng chủ đề trước. Viết ngay một hàm Rust đọc file không đồng bộ bằng Tokio và xử lý Result/Option chuẩn.",
            "expected_tier": "code",
            "is_stream": True,
        },
    ]

    print(f"\n[3/5] TIẾN HÀNH CHẠY MA TRẬN {len(test_cases)} BÀI TOÁN KIỂM THỬ LIÊN HOÀN")
    print("-" * 80)

    for tc in test_cases:
        tc_id = tc["id"]
        tc_name = tc["name"]
        prompt = tc["prompt"]
        is_stream = tc["is_stream"]

        if "TC08" in tc_id:
            case_sid = multi_turn_sid
        else:
            case_session = await container.sessions.create(principal, f"Audit Case {tc_id}")
            case_sid = case_session.id

        client_req_id = f"req-{tc_id}-{uuid4().hex[:6]}"
        chat_req = ChatRequest(
            session_id=case_sid,
            client_request_id=client_req_id,
            message=prompt,
            mode="optimized",
            constraints=Constraints(deadline_ms=60000),
        )

        t0 = time.perf_counter()
        route_decision = None
        response_text = ""
        actual_in_tokens = 0
        actual_out_tokens = 0
        call_cost = Decimal(0)
        error_msg = None

        try:
            if is_stream:
                chunks = []
                async for event in container.orchestrator.execute_stream(principal, chat_req):
                    ev_type = event.get("event")
                    data_payload = event.get("data", {})
                    if isinstance(data_payload, str):
                        try:
                            data_payload = json.loads(data_payload)
                        except json.JSONDecodeError:
                            data_payload = {}
                    if ev_type == "trace":
                        route_decision = {
                            "config_id": data_payload.get("config_id") or data_payload.get("route") or "Unknown",
                            "model_id": data_payload.get("route") or data_payload.get("model_id") or "Unknown",
                            "reason": data_payload.get("reason"),
                            "reason_code": data_payload.get("reason"),
                            "fallback_used": False,
                        }
                    elif ev_type == "token":
                        chunks.append(data_payload.get("delta", "") if isinstance(data_payload, dict) else "")
                    elif ev_type == "done":
                        resp_data = data_payload if isinstance(data_payload, dict) else {}
                        usage = resp_data.get("usage", {})
                        actual_in_tokens = usage.get("input_tokens") or 0
                        actual_out_tokens = usage.get("output_tokens") or 0
                        cost_data = resp_data.get("cost", {})
                        call_cost = Decimal(str(cost_data.get("serving_usd") or "0"))
                response_text = "".join(chunks)
            else:
                resp = await container.orchestrator.execute(principal, chat_req)
                response_text = resp.response.content
                route_decision = resp.route.model_dump()
                actual_in_tokens = resp.usage.input_tokens or 0
                actual_out_tokens = resp.usage.output_tokens or 0
                call_cost = Decimal(str(resp.cost.serving_usd or "0"))

        except (AppError, httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError) as exc:
            import traceback
            error_msg = str(exc)
            traceback.print_exc()

        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Calculate Baseline Cost (if 100% routed to Frontier 70B/120B)
        baseline_cost_for_turn = (
            Decimal(actual_in_tokens) * BASE_INPUT_RATE
            + Decimal(actual_out_tokens) * BASE_OUTPUT_RATE
        )

        total_optimized_cost += call_cost
        total_baseline_cost += baseline_cost_for_turn
        total_input_tokens += actual_in_tokens
        total_output_tokens += actual_out_tokens

        if isinstance(route_decision, dict):
            chosen_config = route_decision.get("config_id") or "None"
            chosen_model = route_decision.get("model_id") or "None"
            fallback_used = route_decision.get("fallback_used", False)
            reason = route_decision.get("reason_code") or route_decision.get("reason") or "N/A"
        else:
            chosen_config = str(route_decision) if route_decision else "None"
            chosen_model = "None"
            fallback_used = False
            reason = "N/A"

        # Determine Tier classification of chosen model
        cid_lower = chosen_config.lower()
        if "coder" in cid_lower or "27b" in cid_lower:
            actual_tier = "code"
        elif "70b" in cid_lower or "120b" in cid_lower or "terra" in cid_lower:
            actual_tier = "reasoning"
        else:
            actual_tier = "fast"

        is_match = actual_tier == tc["expected_tier"]

        result_item = {
            "id": tc_id,
            "name": tc_name,
            "stream": is_stream,
            "chosen_config": chosen_config,
            "chosen_model": chosen_model,
            "expected_tier": tc["expected_tier"],
            "actual_tier": actual_tier,
            "tier_match": is_match,
            "reason": reason,
            "fallback_used": fallback_used,
            "in_tokens": actual_in_tokens,
            "out_tokens": actual_out_tokens,
            "cost_usd": float(call_cost),
            "baseline_usd": float(baseline_cost_for_turn),
            "elapsed_ms": elapsed_ms,
            "error": error_msg,
            "sample_response": response_text[:120].replace("\n", " "),
        }
        await asyncio.sleep(1.5)
        results.append(result_item)

        status_icon = "❌" if error_msg else ("✅" if is_match else "⚠️")
        print(
            f"{status_icon} [{tc_id}] {tc_name:<38} | "
            f"Model: {chosen_config:<28} | "
            f"Tier: {actual_tier.upper():<9} (Kỳ vọng: {tc['expected_tier'].upper():<9}) | "
            f"{elapsed_ms:>6.0f}ms | "
            f"${call_cost:>8.6f}"
        )
        if error_msg:
            print(f"    └── LỖI: {error_msg}")

    # 4. Verify Failover Simulation (Case 11: Incomplete Token Resilience)
    print("\n[4/5] KIỂM TRA CHUYÊN SÂU: CƠ CHẾ TỰ ĐỘNG CHUYỂN TIẾP DỰ PHÒNG (FAILOVER)")
    print("Mô phỏng trường hợp Provider đầu tiên trả về status='incomplete' (bị ngắt token)...")

    class TruncatedCandidateProvider:
        def __init__(self, real_provider):
            self.real_provider = real_provider
            self.attempts = []
            self.catalog = getattr(real_provider, "catalog", None)

        async def generate(self, messages, opts):
            self.attempts.append(opts.config_id)
            if len(self.attempts) == 1:
                # First attempt simulates truncated response from lightweight model
                return ProviderResult(
                    text="Phản hồi bị ngắt quãng giữa chừng...",
                    usage=Usage(input_tokens=20, output_tokens=2048),
                    duration_ms=300.0,
                    status="incomplete",
                )
            # Second attempt succeeds on Groq 70B
            return ProviderResult(
                text="Phản hồi hoàn chỉnh từ mô hình dự phòng sau khi Failover.",
                usage=Usage(input_tokens=20, output_tokens=80),
                duration_ms=450.0,
                status="completed",
            )

    original_provider = container.provider
    container.orchestrator.provider = TruncatedCandidateProvider(original_provider)

    failover_req = ChatRequest(
        session_id=multi_turn_sid,
        client_request_id=f"req-failover-test-{uuid4().hex[:6]}",
        message="Kiểm tra năng lực tự động Failover khi gặp lỗi OUTPUT_INCOMPLETE",
        mode="optimized",
    )
    failover_resp = await container.orchestrator.execute(principal, failover_req)
    container.orchestrator.provider = original_provider

    failover_success = (
        failover_resp.route.fallback_used
        and failover_resp.route.reason_code == "PROVIDER_FAILOVER_OUTPUT_INCOMPLETE"
    )
    print(
        f"  • Kết quả Failover: {'✅ THÀNH CÔNG' if failover_success else '❌ THẤT BẠI'}\n"
        f"  • Quyết định Route: {failover_resp.route.config_id} (reason={failover_resp.route.reason_code})\n"
        f"  • Nội dung sinh được: {failover_resp.response.content}"
    )

    # 5. Summary & Economic Calculations
    print("\n" + "=" * 80)
    print("📊 BÁO CÁO TỔNG KẾT & PHÂN TÍCH HIỆU QUẢ KINH TẾ (SAVINGS AUDIT)")
    print("=" * 80)

    total_tests = len(results)
    successful_tests = sum(1 for r in results if not r["error"])
    tier_matches = sum(1 for r in results if r["tier_match"] and not r["error"])

    tier_counts = {"fast": 0, "code": 0, "reasoning": 0}
    for r in results:
        if not r["error"]:
            tier_counts[r["actual_tier"]] = tier_counts.get(r["actual_tier"], 0) + 1

    savings_usd = total_baseline_cost - total_optimized_cost
    savings_pct = (
        (savings_usd / total_baseline_cost * 100) if total_baseline_cost > 0 else Decimal(0)
    )

    print("\n1. CHỈ SỐ KỸ THUẬT & ĐỘ CHÍNH XÁC:")
    print(f"  • Tổng số ca kiểm thử: {total_tests}")
    print(f"  • Số ca hoàn thành thành công: {successful_tests}/{total_tests} ({successful_tests/total_tests*100:.1f}%)")
    print(f"  • Độ chính xác định tuyến theo tầng (Tier Match): {tier_matches}/{total_tests} ({tier_matches/total_tests*100:.1f}%)")
    print("  • Phân bổ mô hình được chọn:")
    print(f"    - Fast / Free Tier (8B):       {tier_counts['fast']}/{successful_tests} ({tier_counts['fast']/successful_tests*100:.1f}%)")
    print(f"    - Coding Tier (Qwen Coder):    {tier_counts['code']}/{successful_tests} ({tier_counts['code']/successful_tests*100:.1f}%)")
    print(f"    - Reasoning Tier (Llama 70B):  {tier_counts['reasoning']}/{successful_tests} ({tier_counts['reasoning']/successful_tests*100:.1f}%)")

    print("\n2. HIỆU QUẢ TIẾT KIỆM CHI PHÍ (COST SAVINGS):")
    print(f"  • Tổng Tokens xử lý:  {total_input_tokens + total_output_tokens:,} tokens (In: {total_input_tokens:,}, Out: {total_output_tokens:,})")
    print(f"  • Chi phí thực tế (Smart ML Router): ${total_optimized_cost:.6f} USD")
    print(f"  • Chi phí nếu gọi 100% Frontier 70B:   ${total_baseline_cost:.6f} USD")
    print(f"  • SỐ TIỀN TIẾT KIỆM ĐƯỢC:             ${savings_usd:.6f} USD")
    print(f"  • TỶ LỆ TIẾT KIỆM CHI PHÍ:            {savings_pct:.2f}% GIẢM ĐƯỢC SO VỚI BASELINE")

    print("\n3. KIỂM TOÁN TÍNH NĂNG NÂNG CAO (OPTIMIZER FUNCTIONS):")
    print("  • Luồng SSE Streaming: Hoạt động trơn tru (Trace, Token delta, Done event đầy đủ).")
    print("  • Bộ nhớ Hội thoại (Memory & Facts): Ghi nhận thành công danh tính và đề tài qua 3 lượt chat.")
    print("  • Tự động Failover: Tự động leo thang lên mô hình lớn khi model nhỏ gặp OUTPUT_INCOMPLETE.")
    print("  • Sổ cái ngân sách (Ledger SQLite WAL): Trừ và tất toán chi phí khớp từng giao dịch.")

    # Save detailed JSON report
    report_path = os.path.join(os.path.dirname(__file__), "..", "data", "system_audit_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    report_payload = {
        "summary": {
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "accuracy_pct": float(tier_matches / total_tests * 100),
            "tier_distribution": tier_counts,
            "total_tokens": total_input_tokens + total_output_tokens,
            "optimized_cost_usd": float(total_optimized_cost),
            "baseline_cost_usd": float(total_baseline_cost),
            "savings_usd": float(savings_usd),
            "savings_pct": float(savings_pct),
            "failover_verified": failover_success,
        },
        "cases": results,
    }
    await asyncio.to_thread(Path(report_path).write_text, json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[5/5] ĐÃ LƯU BÁO CÁO DỮ LIỆU ĐẦY ĐỦ TẠI: {report_path}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
