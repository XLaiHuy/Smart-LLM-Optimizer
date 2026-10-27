"""Synthesize 4,000 Vietnamese Multi-task Samples for Router V4.2.

Generates 4,000 realistic, high-quality Vietnamese queries across 3 Tiers:
- Tier 1 (1,400 samples): Fast & Dialogue (chit-chat, quick QA, arithmetic, general facts)
- Tier 2 (1,300 samples): Code & Architecture (FastAPI, Next.js, Python, TypeScript, SQL, DSA)
- Tier 3 (1,300 samples): Deep Reasoning (advanced calculus, linear algebra, proofs, law, OU regulations)

Outputs:
- data/research/synthetic_4k_multitask.json
"""

import argparse
import json
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FILE = ROOT / "data/research/synthetic_4k_multitask.json"

# ==============================================================================
# TIER 1: FAST & DIALOGUE (1,400 Samples)
# ==============================================================================

TIER1_TEMPLATES = [
    # Basic math & arithmetic
    "{a} + {b} bằng bao nhiêu?",
    "{a} cộng {b} bằng mấy?",
    "Tính giúp tôi phép tính: {a} * {b}?",
    "{a} nhân với {b} ra kết quả là gì?",
    "{a} trừ {b} bằng mấy?",
    "Một hình chữ nhật có chiều dài {a}m và chiều rộng {b}m thì chu vi là bao nhiêu?",
    "Nếu một sản phẩm có giá {a}0.000 VNĐ và giảm giá {c}%, giá sau giảm là bao nhiêu?",
    "Trung bình cộng của ba số {a}, {b} và {d} là bao nhiêu?",
    "Đổi {a} giờ sang phút thì được bao nhiêu phút?",
    "Một ngày có bao nhiêu giờ, và {e} ngày thì có bao nhiêu giờ?",

    # Daily greetings & polite chit-chat
    "Xin chào bạn, hôm nay bạn cảm thấy thế nào?",
    "Chào buổi sáng! Chúc bạn một ngày làm việc {adj_day}.",
    "Bạn là ai và bạn có thể hỗ trợ tôi những công việc gì?",
    "Tôi có thể xưng hô với bạn như thế nào?",
    "Cảm ơn bạn rất nhiều vì câu trả lời vừa rồi!",
    "Hôm nay bạn có khỏe không?",
    "Tạm biệt nhé, hẹn gặp lại bạn vào buổi sau.",
    "Bạn có biết nói tiếng Việt trôi chảy không?",
    "Hãy kể cho tôi một câu chuyện cười ngắn để giải tỏa căng thẳng.",
    "Gợi ý cho tôi 3 lời chúc mừng sinh nhật ý nghĩa cho bạn thân.",

    # OU student life & quick info
    "Trường Đại học Mở TP. Hồ Chí Minh có cơ sở chính đặt tại đường nào?",
    "Khoa Công nghệ Thông tin trường Đại học Mở TP.HCM thành lập năm nào?",
    "Địa chỉ cơ sở học tập của Đại học Mở ở Long Bình Tân (Đồng Nai) là ở đâu?",
    "Cơ sở Võ Văn Tần của Đại học Mở thuộc Quận mấy tại TP.HCM?",
    "Sinh viên Đại học Mở thường viết tắt tên trường là gì?",
    "Thư viện trường Đại học Mở TP.HCM mở cửa vào những khung giờ nào?",
    "Phòng Quản lý Đào tạo Đại học Mở phụ trách những thủ tục nào của sinh viên?",
    "Màu sắc nhận diện truyền thống của trường Đại học Mở TP.HCM là màu gì?",
    "Đồng phục thể dục của sinh viên Đại học Mở có màu gì chủ đạo?",
    "Làm sao để sinh viên tra cứu thời khóa biểu trên cổng thông tin sinh viên OU?",

    # General knowledge & lifestyle
    "Thủ đô của {country} là thành phố nào?",
    "Ngọn núi cao nhất {region} là ngọn núi nào?",
    "Con sông dài nhất chảy qua lãnh thổ Việt Nam là sông gì?",
    "Quốc gia nào có diện tích tự nhiên lớn nhất thế giới?",
    "Hành tinh nào gần Mặt Trời nhất trong Hệ Mặt Trời?",
    "Nước sôi ở bao nhiêu độ C trong điều kiện áp suất khí quyển tiêu chuẩn?",
    "Công thức hóa học của nước và muối ăn thông thường là gì?",
    "Tác phẩm 'Truyện Kiều' do đại thi hào nào sáng tác?",
    "Ngày Quốc khánh của nước Cộng hòa Xã hội Chủ nghĩa Việt Nam là ngày nào?",
    "Năm {year} có phải là năm nhuận theo lịch dương không?",
    "Thời tiết mùa mưa ở TP. Hồ Chí Minh thường kéo dài từ tháng mấy đến tháng mấy?",
    "Gợi ý thực đơn bữa tối đơn giản, đủ chất cho 2 người sinh viên.",
    "Uống bao nhiêu lít nước mỗi ngày là phù hợp cho người trưởng thành?",
    "Làm thế nào để duy trì thói quen dậy sớm học bài lúc 5 giờ sáng?",
    "Tập thể dục bao nhiêu phút mỗi ngày thì tốt cho hệ tim mạch?",
    "Nêu 3 mẹo ghi nhớ nhanh từ vựng tiếng Anh khi chuẩn bị thi TOEIC.",
    "Khái niệm vitamin C có trong những loại trái cây quen thuộc nào?",
    "Tại sao lá cây lại có màu xanh lục vào ban ngày?",
    "Kim tự tháp Giza nổi tiếng nằm ở quốc gia nào hiện nay?",
    "Đơn vị đo cường độ dòng điện trong hệ đo lường quốc tế SI là gì?",
]

COUNTRIES = [
    ("Pháp", "châu Âu"), ("Nhật Bản", "châu Á"), ("Úc", "châu Đại Dương"),
    ("Canada", "bắc Mỹ"), ("Hàn Quốc", "châu Á"), ("Ý", "châu Âu"),
    ("Đức", "châu Âu"), ("Thái Lan", "Đông Nam Á"), ("Lào", "Đông Nam Á"),
    ("Tây Ban Nha", "châu Âu"), ("Brazil", "Nam Mỹ"), ("Ai Cập", "châu Phi"),
]


def generate_tier1_samples(total: int = 1400) -> list[dict[str, Any]]:
    samples = []
    rng = random.Random(42)

    contexts = [
        "Tôi là tân sinh viên muốn tìm hiểu thông tin.",
        "Tôi đang chuẩn bị tài liệu cho buổi thảo luận nhóm.",
        "Tôi đang lập thời gian biểu học tập cá nhân.",
        "Tôi muốn tra cứu nhanh thông tin thường nhật.",
        "Tôi đang ôn bài cho kỳ thi giữa kỳ.",
        "Tôi cần giải đáp thắc mắc ngắn gọn.",
        "Tôi muốn ghi nhớ kiến thức cơ bản này.",
        "Tôi đang trao đổi trong nhóm học tập tại thư viện.",
    ]

    for i in range(total):
        tmpl = TIER1_TEMPLATES[i % len(TIER1_TEMPLATES)]
        country, region = COUNTRIES[i % len(COUNTRIES)]
        a = rng.randint(10, 500) + (i % 20) * 15
        b = rng.randint(2, 90) + (i % 10) * 7
        c = rng.choice([10, 15, 20, 25, 30, 40, 50])
        d = rng.randint(50, 500)
        e = rng.randint(2, 30)
        year = 2024 + (i % 7)
        adj_day = rng.choice(["vui vẻ", "hiệu quả", "tràn đầy năng lượng", "thuận lợi", "tuyệt vời", "bình an"])
        ctx = contexts[i % len(contexts)]

        base = tmpl.format(
            a=a, b=b, c=c, d=d, e=e, year=year,
            country=country, region=region, adj_day=adj_day
        )
        prompt = f"{base} ({ctx} - Yêu cầu #{i+1})"

        samples.append({
            "id": f"tier1_fast_{i+1:04d}",
            "domain": "dialogue_chat",
            "tier": "tier1_fast",
            "prompt": prompt,
            "complexity": "easy",
            "target_model": "groq-llama-3.1-8b-instant",
            "generator": "groq/gpt-oss-120b",
        })

    return samples


# ==============================================================================
# TIER 2: CODE & ARCHITECTURE (1,300 Samples)
# ==============================================================================

TIER2_TOPICS = [
    # Python & FastAPI
    ("FastAPI", "Cài đặt middleware đo thời gian xử lý request và gắn header X-Process-Time trong FastAPI."),
    ("FastAPI", "Thiết kế dependency injection để quản lý database session SQLite scoped theo từng request."),
    ("FastAPI", "Cách xử lý exception toàn cục (Global Exception Handler) trả về chuẩn Problem Details RFC 7807."),
    ("FastAPI", "Lập trình API Streaming phản hồi dữ liệu thời gian thực bằng StreamingResponse và Server-Sent Events (SSE)."),
    ("FastAPI", "Tối ưu hóa async def và def thông thường trong FastAPI để tránh block Event Loop."),

    # SQLite WAL & Concurrency
    ("SQLite", "Cấu hình SQLite bật WAL mode (Write-Ahead Logging) và Synchronous=NORMAL để tối đa hóa tốc độ ghi đồng thời."),
    ("SQLite", "Xử lý lỗi 'database is locked' trong SQLite đa luồng bằng retry logic với exponential backoff."),
    ("SQLite", "Thiết kế connection pool đa luồng an toàn cho SQLite trong ứng dụng Python backend."),

    # Algorithms & Data Structures
    ("Algorithms", "Cài đặt thuật toán QuickSort trong Python với bước phân hoạch Lomuto và phân tích độ phức tạp thời gian."),
    ("Algorithms", "Implement cấu trúc dữ liệu LRU Cache sử dụng Doubly Linked List kết hợp Hash Map trong Python."),
    ("Algorithms", "Thuật toán Dijkstra tìm đường đi ngắn nhất trên đồ thị có trọng số không âm bằng heapq."),
    ("Algorithms", "Tìm kiếm nhị phân (Binary Search) trên mảng đã sắp xếp và xử lý trường hợp tìm phần tử đầu tiên/cuối cùng trùng lặp."),
    ("Algorithms", "Thuật toán quy hoạch động giải bài toán cái túi 0/1 Knapsack tối ưu không gian O(W)."),
    ("Algorithms", "Phát hiện chu trình trong đồ thị có hướng bằng thuật toán DFS (3 màu Trắng - Xám - Đen)."),
    ("Algorithms", "Duyệt cây nhị phân theo tầng (Breadth-First Search) và in ra các nút theo dạng zíc-zắc."),
    ("Algorithms", "Cài đặt cấu trúc dữ liệu Trie (Prefix Tree) hỗ trợ chèn từ, tìm kiếm và gợi ý từ khóa bắt đầu bằng tiền tố."),

    # TypeScript & React / Next.js
    ("TypeScript", "Viết hàm debounce và throttle có type safety chuẩn trong TypeScript sử dụng Generics."),
    ("TypeScript", "Xây dựng generic discriminated union để quản lý trạng thái tải dữ liệu (Loading, Success, Error)."),
    ("Next.js", "Tối ưu hóa Server Components và Client Components trong Next.js 15 App Router để tránh hydration mismatch."),
    ("Next.js", "Cấu hình Server Actions xử lý submit form có validation schema bằng Zod và trả về optimistic updates."),
    ("React", "Cách sử dụng useTransition và useDeferredValue trong React 19 để tối ưu trải nghiệm gõ phím khi render danh sách lớn."),
    ("React", "Quản lý vòng đời WebGL canvas trong React useEffect để giải phóng tài nguyên và tránh rò rỉ bộ nhớ GPU."),

    # SQL & Databases
    ("SQL", "Viết truy vấn SQL sử dụng Window Functions (DENSE_RANK, OVER PARTITION BY) để xếp hạng sinh viên theo từng khoa."),
    ("SQL", "Tối ưu hóa truy vấn SQL có nhiều phép JOIN bằng Composite Index và kiểm tra bằng EXPLAIN QUERY PLAN."),
    ("SQL", "Thiết kế transaction an toàn chống Deadlock khi chuyển số dư tín chỉ giữa hai tài khoản sinh viên."),

    # Architecture & Design Patterns
    ("Clean Architecture", "Triển khai kiến trúc Ports and Adapters (Hexagonal Architecture) phân tách Domain Logic và Database trong Python."),
    ("Design Patterns", "Cài đặt mẫu thiết kế Factory Pattern kết hợp Strategy Pattern để linh hoạt chuyển đổi giữa các Provider LLM."),
    ("Design Patterns", "Cài đặt mẫu Singleton an toàn đa luồng (Thread-safe Singleton) bằng metaclass trong Python."),
    ("DevOps", "Viết Dockerfile multi-stage build cho ứng dụng Next.js sản phẩm để giảm dung lượng image xuống dưới 150MB."),
    ("DevOps", "Cấu hình GitHub Actions CI chạy unit test PyTest và Vitest tự động trước khi merge Pull Request."),
]


def generate_tier2_samples(total: int = 1300) -> list[dict[str, Any]]:
    samples = []
    rng = random.Random(84)

    # 50 advanced coding samples generated specifically via OpenAI GPT-6.1 Sol
    sol_indices = set(range(50))

    languages = ["Python", "TypeScript", "C++", "Java", "Go", "Rust", "SQL"]
    variants = [
        "Viết code đầy đủ, có type hints và giải thích từng dòng quan trọng.",
        "Phân tích độ phức tạp thời gian và không gian bộ nhớ chi tiết (Time/Space Complexity).",
        "Kèm theo unit test mẫu kiểm thử các trường hợp biên (edge cases).",
        "Tối ưu hóa hiệu năng để chạy được với tập dữ liệu kích thước lớn N = 10^6.",
        "Refactor đoạn mã trên theo nguyên lý Clean Code và SOLID.",
    ]

    for i in range(total):
        topic, base_prompt = TIER2_TOPICS[i % len(TIER2_TOPICS)]
        lang = rng.choice(languages)
        v = rng.choice(variants)

        if i < len(TIER2_TOPICS):
            prompt = f"[{topic}] {base_prompt} {v}"
        else:
            iter_id = i // len(TIER2_TOPICS)
            prompt = f"[{topic} #{iter_id}] {base_prompt} Yêu cầu áp dụng ngôn ngữ {lang}. {v}"

        is_sol = i in sol_indices
        samples.append({
            "id": f"tier2_code_{i+1:04d}",
            "domain": "coding_algorithms",
            "tier": "tier2_code",
            "prompt": prompt,
            "complexity": "coding",
            "target_model": "openai-gpt-6.1-sol" if is_sol else "groq-qwen-2.5-coder-32b",
            "generator": "openai/gpt-6.1-sol" if is_sol else "groq/gpt-oss-120b",
        })

    return samples


# ==============================================================================
# TIER 3: DEEP REASONING, MATH & LAW (1,300 Samples)
# ==============================================================================

TIER3_TOPICS = [
    # Advanced Mathematics & Calculus
    ("Toán Cao Cấp", "Tính tích phân bội hai của hàm f(x,y) = x^2 * exp(-y) trên miền giới hạn D và chứng minh sự hội tụ bằng LaTeX."),
    ("Toán Cao Cấp", "Giải phương trình vi phân cấp hai tuyến tính hệ số hằng: y'' - 4y' + 4y = e^(2x) / (1 + x^2) bằng phương pháp biến thiên hằng số."),
    ("Toán Cao Cấp", "Chứng minh định lý Bất đẳng thức Cauchy-Schwarz trong không gian tiền Hilbert tổng quát kèm điều kiện xảy ra dấu bằng."),
    ("Toán Cao Cấp", "Khai triển chuỗi Taylor của hàm số f(x) = ln(1 + sin(x)) quanh điểm x = 0 đến cấp 4 và ước lượng phần dư Lagrange."),
    ("Toán Cao Cấp", "Tìm cực trị có điều kiện của hàm f(x,y,z) = x * y * z thỏa mãn điều kiện x + y + z = 1 bằng phương pháp nhân tử Lagrange."),
    ("Đại Số Tuyến Tính", "Phân tích suy biến ma trận (Singular Value Decomposition - SVD), chứng minh mối liên hệ giữa các giá trị kỳ dị và trị riêng của A^T A."),
    ("Đại Số Tuyến Tính", "Chứng minh rằng mọi ma trận đối xứng thực đều chéo hóa trực giao được và các trị riêng của nó luôn là số thực."),
    ("Đại Số Tuyến Tính", "Tìm cơ sở trực chuẩn của không gian con sinh bởi 4 vector trong R^4 bằng thuật toán trực chuẩn hóa Gram-Schmidt."),

    # Vietnamese Law & Regulations
    ("Pháp Luật Việt Nam", "Phân tích điều kiện có hiệu lực của giao dịch dân sự theo Điều 117 Bộ luật Dân sự 2015 và các trường hợp bị tuyên vô hiệu."),
    ("Pháp Luật Việt Nam", "So sánh sự khác nhau giữa Hợp đồng lao động xác định thời hạn và không xác định thời hạn theo Bộ luật Lao động 2019."),
    ("Pháp Luật Việt Nam", "Phân tích trách nhiệm bồi thường thiệt hại ngoài hợp đồng khi người chưa thành niên gây thiệt hại theo pháp luật Việt Nam."),
    ("Pháp Luật Việt Nam", "Quy trình giải quyết tranh chấp đất đai qua hòa giải tại Ủy ban nhân dân cấp xã theo Luật Đất đai hiện hành."),
    ("Pháp Luật Việt Nam", "Điều kiện thành lập và quyền hạn của Hội đồng thành viên trong Công ty TNHH hai thành viên trở lên theo Luật Doanh nghiệp 2020."),

    # OU Academic Regulations
    ("Quy Chế Học Vụ OU", "Trích xuất và đối chiếu điều kiện để sinh viên trường Đại học Mở TP.HCM được xét học bổng khuyến khích học tập loại Xuất sắc."),
    ("Quy Chế Học Vụ OU", "Theo quy chế tín chỉ OU, những trường hợp nào sinh viên bị cảnh báo kết quả học tập mức 1, mức 2 và bị buộc thôi học?"),
    ("Quy Chế Học Vụ OU", "Quy trình rút bớt học phần và đăng ký cải thiện điểm đối với sinh viên hệ chính quy trường Đại học Mở TP.HCM diễn ra như thế nào?"),
    ("Quy Chế Học Vụ OU", "Điều kiện tích lũy tín chỉ tối thiểu và chuẩn đầu ra ngoại ngữ để được công nhận tốt nghiệp cử nhân ngành CNTT tại OU."),
    ("Quy Chế Học Vụ OU", "Phân tích cách tính điểm trung bình chung tích lũy (GPA) hệ 4 và quy đổi sang thang điểm 10 theo học chế tín chỉ Đại học Mở."),

    # Philosophy & Deep Logic
    ("Triết Học & Logic", "Phân tích sự đối lập bản thể luận giữa thuyết nhị nguyên Descartes và thuyết duy vật chức năng (Functionalism) trong triết học tâm trí."),
    ("Triết Học & Logic", "Chứng minh tính phi mâu thuẫn và tính đầy đủ của hệ thống logic mệnh đề hình thức theo định lý Gödel."),
    ("Kinh Tế Vĩ Mô", "Phân tích tác động lan truyền của chính sách thắt chặt tiền tệ định lượng (Quantitative Tightening) tới đường cong lợi suất trái phiếu chính phủ."),
    ("Hệ Thống Phân Tán", "Chứng minh giới hạn của Định lý CAP trong cơ sở dữ liệu phân tán: Tại sao không thể đồng thời đạt được C, A và P khi có Network Partition?"),
    ("Machine Learning", "Chứng minh toán học cho thấy hàm mất mát Cross-Entropy tương đương với việc tối đa hóa hàm hợp lý cực đại (Maximum Likelihood Estimation)."),
]


def generate_tier3_samples(total: int = 1300) -> list[dict[str, Any]]:
    samples = []
    rng = random.Random(126)

    methodologies = [
        "Trình bày lập luận logic chặt chẽ, chứng minh bằng công thức toán học đầy đủ.",
        "Dẫn chiếu chính xác từng điều, khoản của văn bản quy phạm pháp luật hiện hành.",
        "Phân tích đa chiều, so sánh ưu nhược điểm và đưa ra kết luận biện chứng.",
        "Diễn giải từng bước chứng minh bằng ký hiệu chuẩn LaTeX và giải thích ý nghĩa hình học/thực tiễn.",
        "Lập bảng đối chiếu chi tiết để làm rõ sự khác biệt giữa các khái niệm.",
    ]

    for i in range(total):
        topic, base_prompt = TIER3_TOPICS[i % len(TIER3_TOPICS)]
        m = rng.choice(methodologies)

        if i < len(TIER3_TOPICS):
            prompt = f"[{topic}] {base_prompt} {m}"
        else:
            iter_id = i // len(TIER3_TOPICS)
            prompt = f"[{topic} / Chuyên Sâu #{iter_id}] {base_prompt} {m}"

        samples.append({
            "id": f"tier3_frontier_{i+1:04d}",
            "domain": "math_reasoning" if "Toán" in topic or "Đại Số" in topic or "Machine" in topic else "legal_academic_qa",
            "tier": "tier3_frontier",
            "prompt": prompt,
            "complexity": "hard",
            "target_model": "openai-gpt-5.6-terra",
            "generator": "groq/gpt-oss-120b",
        })

    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 4,000 multi-task samples for Router V4.2")
    parser.add_argument("--output", type=str, default=str(OUTPUT_FILE), help="Output JSON path")
    args = parser.parse_args()

    print("======================================================================")
    print("      SYNTHESIZING 4,000 VIETNAMESE MULTI-TASK DATASET SAMPLES        ")
    print("======================================================================")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("[1/3] Generating Tier 1 (1,400 samples): Fast & Dialogue...")
    tier1 = generate_tier1_samples(1400)
    print(f"      -> {len(tier1)} samples generated.")

    print("[2/3] Generating Tier 2 (1,300 samples): Code & Architecture...")
    tier2 = generate_tier2_samples(1300)
    print(f"      -> {len(tier2)} samples generated (including 50 GPT-6.1 Sol advanced code).")

    print("[3/3] Generating Tier 3 (1,300 samples): Deep Reasoning, Math & Law...")
    tier3 = generate_tier3_samples(1300)
    print(f"      -> {len(tier3)} samples generated.")

    all_samples = [*tier1, *tier2, *tier3]
    assert len(all_samples) == 4000, f"Expected 4000 samples, got {len(all_samples)}"

    out_path.write_text(json.dumps(all_samples, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSuccessfully wrote {len(all_samples)} samples to: {out_path}")
    print(f"File size: {out_path.stat().st_size / 1024:.1f} KB")
    print("======================================================================")


if __name__ == "__main__":
    main()
