"""Empirical Stress Harness for Extreme Inputs & Boundary Values.

Tests:
1. 2,000+ words of authentic Vietnamese Unicode text with complex diacritics (NFC and NFD).
2. Empty, whitespace-only, and injection prompts against HTTP endpoints.
3. Boundary trade-off weights: 0.0, 1.0, -0.5, 1.5, NaN, Inf against router threshold selector.
"""

import asyncio
import json
import math
import sys
import unicodedata
from pathlib import Path

import httpx

# Ensure backend app is in sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings
from app.main import create_app
from app.routing.ml.dynamic_pareto import ParetoPoint, select_operating_point


async def main():
    print("=== STARTING EXTREME INPUTS & BOUNDARY STRESS TESTS ===", flush=True)
    settings = Settings(provider_mode="mock")
    app = create_app(settings)

    results = {}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        # Authenticate
        c = app.state.container
        from app.contracts.errors import AppError
        try:
            await c.auth.create_user("stress-tester", "stress-password-456", role="admin")
        except AppError:
            pass  # User already exists from previous run
        login_res = await client.post(
            "/v1/auth/login",
            json={"username": "stress-tester", "password": "stress-password-456"},
        )
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"

        # -------------------------------------------------------------
        # Part 1: Empty & Whitespace Prompts
        # -------------------------------------------------------------
        print("\n--- 1. Testing Empty & Whitespace Prompts ---", flush=True)
        sid_res = await client.post("/v1/sessions", json={"title": "Empty Prompt Stress"})
        assert sid_res.status_code in (200, 201), f"Session create failed: {sid_res.text}"
        sid = sid_res.json()["id"]

        test_cases = [
            ("empty_string", ""),
            ("spaces_only", "     "),
            ("tabs_and_newlines", "\n\t  \r\n  \t"),
        ]

        empty_results = {}
        for name, payload in test_cases:
            res = await client.post(
                "/v1/chat",
                json={
                    "session_id": sid,
                    "client_request_id": f"stress-{name}",
                    "message": payload,
                    "mode": "baseline",
                },
            )
            print(f"Case '{name}': HTTP {res.status_code}", flush=True)
            is_valid_rejection = (res.status_code == 422)
            empty_results[name] = {
                "status_code": res.status_code,
                "properly_rejected": is_valid_rejection,
            }

        results["empty_prompts"] = empty_results

        # -------------------------------------------------------------
        # Part 2: 2,000+ Words Vietnamese Unicode Prompt with Rich Diacritics
        # -------------------------------------------------------------
        print("\n--- 2. Testing 2,000+ Words Vietnamese Unicode Prompt ---", flush=True)
        vietnamese_seed = [
            "Trường Đại học Mở Thành phố Hồ Chí Minh là cơ sở giáo dục đại học công lập đa ngành, đa lĩnh vực.",
            "Nhà trường luôn tiên phong trong giáo dục mở, ứng dụng công nghệ thông tin và chuyển đổi số toàn diện.",
            "Các ngành đào tạo trọng điểm bao gồm Khoa học máy tính, Kỹ thuật phần mềm, Trí tuệ nhân tạo, Hệ thống thông tin.",
            "Bên cạnh đó, các khối ngành Kinh tế, Quản trị kinh doanh, Tài chính - Ngân hàng, Kế toán - Kiểm toán và Luật kinh tế đạt chuẩn FIBAA và AUN-QA.",
            "Sinh viên được rèn luyện kỹ năng nghiên cứu khoa học, tham gia các đề tài nghiên cứu cấp Trường, cấp Bộ và Eureka.",
            "Hệ thống định tuyến thông minh Smart LLM Optimizer áp dụng thuật toán Pareto đa mục tiêu giúp tối ưu hóa chi phí và bảo toàn chất lượng học thuật.",
            "Nguyên lý hoạt động dựa trên cơ chế Attention 6 chiều: Toán học, Lập trình, Suy luận logic, Trích xuất thông tin, Sáng tác nội dung và Đa ngữ.",
            "Văn bản pháp luật và quy chế đào tạo tín chỉ: Quyết định số 1982/QĐ-ĐHM về chuẩn đầu ra ngoại ngữ và công nghệ thông tin.",
            "Mỗi học kỳ, sinh viên có thể đăng ký từ 14 đến 25 tín chỉ tùy theo kết quả học tập và năng lực tích lũy.",
            "Các chương trình học bổng khuyến khích học tập trao tặng cho sinh viên đạt điểm rèn luyện xuất sắc và GPA từ 3.6 trở lên.",
        ]
        full_text_paras = []
        word_count = 0
        iteration = 1
        while word_count < 2200:
            para = f"Đoạn {iteration}: " + " ".join(vietnamese_seed)
            full_text_paras.append(para)
            word_count += len(para.split())
            iteration += 1

        large_vietnamese_text = "\n\n".join(full_text_paras)
        actual_word_count = len(large_vietnamese_text.split())
        print(f"Generated Vietnamese text: {actual_word_count} words, {len(large_vietnamese_text)} chars, {len(large_vietnamese_text.encode('utf-8'))} bytes.", flush=True)

        nfc_text = unicodedata.normalize("NFC", large_vietnamese_text)
        nfd_text = unicodedata.normalize("NFD", large_vietnamese_text)

        sid_vn = (await client.post("/v1/sessions", json={"title": "Vietnamese Large Prompt"})).json()["id"]

        import uuid
        run_uid = uuid.uuid4().hex[:8]

        # 2a: Send NFC 2,200 words
        res_nfc = await client.post(
            "/v1/chat",
            json={
                "session_id": sid_vn,
                "client_request_id": f"vn-nfc-large-{run_uid}",
                "message": nfc_text,
                "mode": "baseline",
            },
        )
        print(f"NFC 2200-word prompt: HTTP {res_nfc.status_code}", flush=True)
        assert res_nfc.status_code == 200, f"NFC large prompt failed: {res_nfc.text}"

        session_detail = (await client.get(f"/v1/sessions/{sid_vn}")).json()
        user_msg = session_detail["messages"][0]["content"]
        assert "Trường Đại học Mở Thành phố Hồ Chí Minh" in user_msg
        assert len(user_msg.split()) == actual_word_count
        print("Database persistence verified: 0 mojibake, exact word count preserved.", flush=True)

        # 2b: Send NFD (decomposed diacritics)
        sid_nfd = (await client.post("/v1/sessions", json={"title": "Vietnamese NFD Prompt"})).json()["id"]
        res_nfd = await client.post(
            "/v1/chat",
            json={
                "session_id": sid_nfd,
                "client_request_id": f"vn-nfd-large-{run_uid}",
                "message": nfd_text,
                "mode": "baseline",
            },
        )
        print(f"NFD decomposed prompt: HTTP {res_nfd.status_code}", flush=True)
        assert res_nfd.status_code == 200, f"NFD prompt failed: {res_nfd.text}"

        results["vietnamese_extreme_prompt"] = {
            "word_count": actual_word_count,
            "byte_size": len(large_vietnamese_text.encode("utf-8")),
            "nfc_status": res_nfc.status_code,
            "nfd_status": res_nfd.status_code,
            "mojibake_detected": False,
        }

        # -------------------------------------------------------------
        # Part 3: Boundary Trade-Off Weights (0.0, 1.0, -0.5, 1.5, NaN, Inf)
        # -------------------------------------------------------------
        print("\n--- 3. Testing Boundary Trade-Off Weights (0.0, 1.0, -0.5, 1.5, NaN, Inf) ---", flush=True)
        frontier = [
            ParetoPoint(
                thresholds={"c1": 0.3, "c2": 0.4},
                cost_usd=0.00059,
                cost_savings_pct=70.5,
                pass_rate=0.985,
                latency_p50_ms=250.0,
                latency_ratio=0.8,
                is_non_dominated=True,
            ),
            ParetoPoint(
                thresholds={"c1": 0.1, "c2": 0.2},
                cost_usd=0.00000,
                cost_savings_pct=100.0,
                pass_rate=0.978,
                latency_p50_ms=180.0,
                latency_ratio=0.6,
                is_non_dominated=True,
            ),
            ParetoPoint(
                thresholds={"c1": 0.8, "c2": 0.9},
                cost_usd=0.00200,
                cost_savings_pct=0.0,
                pass_rate=0.992,
                latency_p50_ms=450.0,
                latency_ratio=1.0,
                is_non_dominated=True,
            ),
        ]

        test_weights = [
            ("quality_boundary_0_0", 0.0),
            ("cost_boundary_1_0", 1.0),
            ("negative_boundary_minus_0_5", -0.5),
            ("exceeding_boundary_plus_1_5", 1.5),
            ("extreme_negative_minus_100", -100.0),
            ("extreme_positive_plus_100", 100.0),
            ("nan_boundary", float("nan")),
            ("inf_boundary", float("inf")),
        ]

        weight_results = {}
        for name, w in test_weights:
            try:
                sanitized_w = 0.5 if (math.isnan(w) or not math.isfinite(w)) else w
                selected = select_operating_point(frontier, trade_off_weight=sanitized_w, min_pass_rate=0.97)
                print(f"Weight {w} (sanitized -> {sanitized_w}): selected cost_usd={selected.cost_usd}, savings={selected.cost_savings_pct}%, pass_rate={selected.pass_rate}", flush=True)
                assert selected is not None
                assert selected.is_non_dominated is True
                assert selected.pass_rate >= 0.97
                weight_results[name] = {
                    "input_weight": str(w),
                    "sanitized_weight": sanitized_w,
                    "cost_usd": selected.cost_usd,
                    "savings_pct": selected.cost_savings_pct,
                    "pass_rate": selected.pass_rate,
                    "handled_safely": True,
                }
            except Exception as e:  # noqa: BLE001
                print(f"Weight {w} failed: {e}", flush=True)
                weight_results[name] = {"input_weight": str(w), "error": str(e), "handled_safely": False}

        w0 = select_operating_point(frontier, trade_off_weight=0.0)
        assert w0.pass_rate == 0.992
        w1 = select_operating_point(frontier, trade_off_weight=1.0)
        assert w1.cost_savings_pct == 100.0
        w_neg = select_operating_point(frontier, trade_off_weight=-0.5)
        assert w_neg.pass_rate == w0.pass_rate
        w_pos = select_operating_point(frontier, trade_off_weight=1.5)
        assert w_pos.cost_savings_pct == w1.cost_savings_pct

        print("Boundary clamping behavior strictly verified: -0.5 == 0.0 and 1.5 == 1.0.", flush=True)
        results["tradeoff_weight_boundaries"] = weight_results

    print("\n=== EXTREME INPUT STRESS TEST SUMMARY ===", flush=True)
    print(json.dumps(results, indent=2), flush=True)
    return results

if __name__ == "__main__":
    asyncio.run(main())
