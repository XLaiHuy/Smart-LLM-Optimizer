"""Shared fixtures and test helpers for E2E testing track."""

import json
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.providers.catalog import Catalog, ModelEntry


@pytest.fixture
async def admin_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Client authenticated with 'admin' role for research and lab routes."""
    c = app.state.container
    await c.auth.create_user("e2e-admin", "password-e2e-admin", role="admin")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        res = await client.post(
            "/v1/auth/login",
            json={"username": "e2e-admin", "password": "password-e2e-admin"},
        )
        assert res.status_code == 200
        yield client


@pytest.fixture
async def unauth_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Client with no authentication cookie for boundary tests."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
def free_tier_catalog() -> Catalog:
    """Catalog containing Groq, Hugging Face, OpenRouter :free, and baseline models."""
    return Catalog(
        version="e2e-free-tier-v1",
        baseline_config="terra56-none-1024-v1",
        embedding_config="embedding-small-v1",
        models=(
            ModelEntry(
                config_id="groq-llama-3.3-70b-v1",
                model_id="llama-3.3-70b-versatile",
                kind="generation",
                endpoint="responses",
                context_window=128000,
                max_output_tokens=4096,
                input_per_million=Decimal("0.59"),
                output_per_million=Decimal("0.79"),
                source_url="https://groq.com/pricing",
                effective_at="2026-10-22",
                verified_access=True,
                pricing_verified=True,
                structured_output=True,
                function_calling=True,
            ),
            ModelEntry(
                config_id="groq-qwen-2.5-coder-32b-v1",
                model_id="qwen-2.5-coder-32b",
                kind="generation",
                endpoint="responses",
                context_window=32768,
                max_output_tokens=4096,
                input_per_million=Decimal("0.00"),
                output_per_million=Decimal("0.00"),
                source_url="https://groq.com/pricing",
                effective_at="2026-10-22",
                verified_access=True,
                pricing_verified=True,
                structured_output=True,
                function_calling=True,
            ),
            ModelEntry(
                config_id="hf-serverless-llama3-v1",
                model_id="meta-llama/Llama-3.2-3B-Instruct",
                kind="generation",
                endpoint="responses",
                context_window=8192,
                max_output_tokens=1024,
                input_per_million=Decimal("0.00"),
                output_per_million=Decimal("0.00"),
                source_url="https://huggingface.co/docs/api-inference",
                effective_at="2026-10-22",
                verified_access=True,
                pricing_verified=True,
            ),
            ModelEntry(
                config_id="openrouter-free-mistral-v1",
                model_id="mistralai/mistral-7b-instruct:free",
                kind="generation",
                endpoint="responses",
                context_window=32768,
                max_output_tokens=2048,
                input_per_million=Decimal("0.00"),
                output_per_million=Decimal("0.00"),
                source_url="https://openrouter.ai/models",
                effective_at="2026-10-22",
                verified_access=True,
                pricing_verified=True,
            ),
            ModelEntry(
                config_id="terra56-none-1024-v1",
                model_id="gpt-5.6-terra",
                kind="generation",
                endpoint="responses",
                context_window=64000,
                max_output_tokens=1024,
                input_per_million=Decimal("2.00"),
                output_per_million=Decimal("12.00"),
                source_url="https://developers.openai.com/api/docs/models/gpt-5.6-terra",
                effective_at="2026-10-21",
                verified_access=True,
                pricing_verified=True,
            ),
            ModelEntry(
                config_id="embedding-small-v1",
                model_id="text-embedding-3-small",
                kind="embedding",
                endpoint="embeddings",
                context_window=8191,
                max_output_tokens=1,
                input_per_million=Decimal("0.02"),
                output_per_million=Decimal("0.00"),
                source_url="https://developers.openai.com/api/docs/models/text-embedding-3-small",
                effective_at="2026-10-21",
                verified_access=True,
                pricing_verified=True,
            ),
        ),
    )


@pytest.fixture
def sample_vietnamese_tasks() -> dict[str, list[dict[str, Any]]]:
    """Authentic Vietnamese multi-task samples across 4 domains."""
    return {
        "vmlu": [
            {
                "id": "vmlu-stem-001",
                "question": "Trong không gian Oxyz, mặt cầu (S): (x-1)^2 + (y+2)^2 + (z-3)^2 = 16 có bán kính bằng bao nhiêu?",
                "choices": ["A. 4", "B. 16", "C. 8", "D. 2"],
                "gold_answer": "A",
                "domain": "STEM",
            },
            {
                "id": "vmlu-med-002",
                "question": "Thành phần cấu trúc nào của tế bào vi khuẩn có chức năng duy trì hình dạng và chống lại áp suất thẩm thấu?",
                "choices": ["A. Màng sinh chất", "B. Thành tế bào", "C. Vỏ nhầy", "D. Ribosome"],
                "gold_answer": "B",
                "domain": "Medical",
            },
            {
                "id": "vmlu-hum-003",
                "question": "Tác phẩm 'Tuyên ngôn Độc lập' của Chủ tịch Hồ Chí Minh được đọc tại Quảng trường Ba Đình vào năm nào?",
                "choices": ["A. 1930", "B. 1945", "C. 1954", "D. 1975"],
                "gold_answer": "B",
                "domain": "Humanities",
            },
            {
                "id": "vmlu-soc-004",
                "question": "Khái niệm 'Tổng sản phẩm quốc nội' trong kinh tế học vĩ mô thường được viết tắt là gì?",
                "choices": ["A. GNP", "B. CPI", "C. GDP", "D. FDI"],
                "gold_answer": "C",
                "domain": "Social",
            },
            {
                "id": "vmlu-cs-005",
                "question": "Độ phức tạp thời gian trung bình của thuật toán QuickSort là bao nhiêu?",
                "choices": ["A. O(n)", "B. O(n log n)", "C. O(n^2)", "D. O(log n)"],
                "gold_answer": "B",
                "domain": "ComputerScience",
            },
        ],
        "viquad": [
            {
                "id": "viquad-001",
                "context": "Trường Đại học Mở Thành phố Hồ Chí Minh (OU) là một trường đại học công lập đa ngành, được thành lập vào năm 1990.",
                "question": "Trường Đại học Mở TP.HCM được thành lập năm nào?",
                "answers": ["1990"],
                "answer_start": "Trường Đại học Mở Thành phố Hồ Chí Minh (OU) là một trường đại học công lập đa ngành, được thành lập vào năm 1990.".find(
                    "1990"
                ),
                "is_impossible": False,
            },
            {
                "id": "viquad-002",
                "context": "Hồ Ba Bể là hồ nước ngọt tự nhiên lớn nhất Việt Nam, nằm ở xã Nam Mẫu, huyện Ba Bể, tỉnh Bắc Kạn.",
                "question": "Hồ Ba Bể nằm ở tỉnh nào của Việt Nam?",
                "answers": ["Bắc Kạn"],
                "answer_start": "Hồ Ba Bể là hồ nước ngọt tự nhiên lớn nhất Việt Nam, nằm ở xã Nam Mẫu, huyện Ba Bể, tỉnh Bắc Kạn.".find(
                    "Bắc Kạn"
                ),
                "is_impossible": False,
            },
            {
                "id": "viquad-003",
                "context": "Nguyễn Du sinh năm 1765 tại Thăng Long, quê gốc ở làng Tiên Điền, huyện Nghi Xuân, tỉnh Hà Tĩnh. Ông là tác giả Truyện Kiều.",
                "question": "Ai là tác giả của kiệt tác Truyện Kiều?",
                "answers": ["Nguyễn Du"],
                "answer_start": "Nguyễn Du sinh năm 1765 tại Thăng Long, quê gốc ở làng Tiên Điền, huyện Nghi Xuân, tỉnh Hà Tĩnh. Ông là tác giả Truyện Kiều.".find(
                    "Nguyễn Du"
                ),
                "is_impossible": False,
            },
            {
                "id": "viquad-004",
                "context": "Phố cổ Hội An là một đô thị cổ nằm ở hạ lưu sông Thu Bồn, thuộc vùng đồng bằng ven biển tỉnh Quảng Nam.",
                "question": "Phố cổ Hội An thuộc tỉnh nào?",
                "answers": ["Quảng Nam"],
                "answer_start": "Phố cổ Hội An là một đô thị cổ nằm ở hạ lưu sông Thu Bồn, thuộc vùng đồng bằng ven biển tỉnh Quảng Nam.".find(
                    "Quảng Nam"
                ),
                "is_impossible": False,
            },
            {
                "id": "viquad-005",
                "context": "Hệ tuần hoàn kín có máu lưu thông liên tục trong mạch kín, từ tim qua động mạch, mao mạch, tĩnh mạch rồi về tim.",
                "question": "Trong hệ tuần hoàn kín, máu từ mao mạch sẽ đi vào đâu tiếp theo?",
                "answers": ["tĩnh mạch"],
                "answer_start": "Hệ tuần hoàn kín có máu lưu thông liên tục trong mạch kín, từ tim qua động mạch, mao mạch, tĩnh mạch rồi về tim.".find(
                    "tĩnh mạch"
                ),
                "is_impossible": False,
            },
        ],
        "legal": [
            {
                "id": "legal-001",
                "provision": "Điều 104 Bộ luật Lao động 2019 quy định về Thưởng: Người sử dụng lao động thưởng cho người lao động căn cứ vào kết quả sản xuất kinh doanh và mức độ hoàn thành công việc.",
                "question": "Căn cứ thưởng cho người lao động theo Điều 104 Bộ luật Lao động 2019 là gì?",
                "gold_citation": "Điều 104 Bộ luật Lao động 2019",
                "gold_answer": "kết quả sản xuất kinh doanh và mức độ hoàn thành công việc",
            },
            {
                "id": "legal-002",
                "provision": "Điều 30 Luật Doanh nghiệp 2020: Doanh nghiệp phải thông báo với Cơ quan đăng ký kinh doanh khi thay đổi ngành, nghề kinh doanh trong thời hạn 10 ngày kể từ ngày có thay đổi.",
                "question": "Thời hạn thông báo thay đổi ngành nghề kinh doanh theo Luật Doanh nghiệp 2020 là bao nhiêu ngày?",
                "gold_citation": "Điều 30 Luật Doanh nghiệp 2020",
                "gold_answer": "10 ngày",
            },
            {
                "id": "legal-003",
                "provision": "Điều 13 Luật Căn cước 2023: Người từ đủ 14 tuổi trở lên là công dân Việt Nam phải thực hiện thủ tục cấp thẻ căn cước.",
                "question": "Độ tuổi bắt buộc thực hiện thủ tục cấp thẻ căn cước theo Luật Căn cước 2023 là bao nhiêu?",
                "gold_citation": "Điều 13 Luật Căn cước 2023",
                "gold_answer": "từ đủ 14 tuổi trở lên",
            },
            {
                "id": "legal-004",
                "provision": "Điều 112 Bộ luật Lao động 2019: Người lao động được nghỉ làm việc, hưởng nguyên lương trong ngày Quốc khánh 02 ngày (ngày 02 tháng 9 dương lịch và 01 ngày liền kề).",
                "question": "Dịp Quốc khánh người lao động được nghỉ hưởng nguyên lương bao nhiêu ngày?",
                "gold_citation": "Điều 112 Bộ luật Lao động 2019",
                "gold_answer": "02 ngày",
            },
            {
                "id": "legal-005",
                "provision": "Điều 116 Bộ luật Dân sự 2015: Giao dịch dân sự là hợp đồng hoặc hành vi pháp lý đơn phương làm phát sinh, thay đổi hoặc chấm dứt quyền, nghĩa vụ dân sự.",
                "question": "Giao dịch dân sự theo Điều 116 Bộ luật Dân sự 2015 bao gồm những hình thức nào?",
                "gold_citation": "Điều 116 Bộ luật Dân sự 2015",
                "gold_answer": "hợp đồng hoặc hành vi pháp lý đơn phương",
            },
        ],
        "phoqa": [
            {
                "id": "phoqa-001",
                "context": "Văn Miếu - Quốc Tử Giám là quần thể di tích đa dạng và phong phú hàng đầu của thành phố Hà Nội, nằm ở phía Nam kinh thành Thăng Long xưa.",
                "question": "Văn Miếu - Quốc Tử Giám nằm ở thành phố nào?",
                "answers": ["Hà Nội"],
            },
            {
                "id": "phoqa-002",
                "context": "Đờn ca tài tử Nam Bộ là một dòng nhạc dân tộc của Việt Nam đã được UNESCO ghi danh là di sản văn hóa phi vật thể vào năm 2013.",
                "question": "Đờn ca tài tử Nam Bộ được UNESCO công nhận vào năm nào?",
                "answers": ["2013"],
            },
            {
                "id": "phoqa-003",
                "context": "Vườn quốc gia Cúc Phương nằm trên địa phận ba tỉnh Ninh Bình, Hòa Bình và Thanh Hóa, là vườn quốc gia đầu tiên tại Việt Nam.",
                "question": "Vườn quốc gia Cúc Phương là vườn quốc gia thứ mấy tại Việt Nam?",
                "answers": ["đầu tiên"],
            },
            {
                "id": "phoqa-004",
                "context": "Cầu Vàng tại Bà Nà Hills, Đà Nẵng có thiết kế độc đáo với hai bàn tay khổng lồ nâng đỡ thân cầu ở độ cao hơn 1400m.",
                "question": "Cầu Vàng nằm ở thành phố nào của Việt Nam?",
                "answers": ["Đà Nẵng"],
            },
            {
                "id": "phoqa-005",
                "context": "Cà phê Robusta chiếm hơn 90% sản lượng cà phê của Việt Nam, được trồng chủ yếu tại vùng Tây Nguyên.",
                "question": "Vùng nào trồng cà phê Robusta chủ yếu tại Việt Nam?",
                "answers": ["Tây Nguyên"],
            },
        ],
    }


def parse_sse_events(raw_stream: str) -> list[dict[str, Any]]:
    """Parse raw SSE text into structured list of events."""
    events = []
    current_event = "message"
    data_lines = []

    for line in raw_stream.splitlines():
        line = line.strip()
        if not line:
            if data_lines:
                combined_data = "\n".join(data_lines)
                try:
                    parsed_json = json.loads(combined_data)
                except json.JSONDecodeError:
                    parsed_json = combined_data
                events.append({"event": current_event, "data": parsed_json})
                data_lines = []
                current_event = "message"
            continue

        if line.startswith("event:"):
            current_event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())

    if data_lines:
        combined_data = "\n".join(data_lines)
        try:
            parsed_json = json.loads(combined_data)
        except json.JSONDecodeError:
            parsed_json = combined_data
        events.append({"event": current_event, "data": parsed_json})

    return events


def cubic_bezier_point(
    p0: tuple[float, float, float],
    p1: tuple[float, float, float],
    p2: tuple[float, float, float],
    p3: tuple[float, float, float],
    t: float,
) -> tuple[float, float, float]:
    """Calculate point on 3D cubic Bezier curve for energy particle beam animation."""
    u = 1.0 - t
    tt = t * t
    uu = u * u
    uuu = uu * u
    ttt = tt * t

    x = uuu * p0[0] + 3 * uu * t * p1[0] + 3 * u * tt * p2[0] + ttt * p3[0]
    y = uuu * p0[1] + 3 * uu * t * p1[1] + 3 * u * tt * p2[1] + ttt * p3[1]
    z = uuu * p0[2] + 3 * uu * t * p2[2] + 3 * u * tt * p2[2] + ttt * p3[2]
    return (round(x, 4), round(y, 4), round(z, 4))
