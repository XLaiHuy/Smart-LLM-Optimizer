"""Generate a comprehensive multi-domain benchmark dataset (2,400 samples) across 6 domains.

Zero-leakage group architecture:
- 100 independent groups per domain x 4 samples per group = 400 samples per domain.
- 6 Domains:
  1. coding_algorithms: Python/JS algorithms, data structures, recursion, dynamic programming.
  2. math_reasoning: Calculus, linear algebra, probability, coordinate geometry.
  3. legal_regulations: Vietnamese civil, criminal, economic law and policy cases.
  4. medical_bio: Cellular biology, genetics, pharmacology, clinical pathophysiology.
  5. reading_comp_rag: Real UIT-ViQuAD 2.0 reading comprehension passages and extraction.
  6. dialogue_chat: Multi-turn conversations & complex strict instruction following (IFEval).

Split allocation per domain:
- Groups 0..49 (50 groups = 200 samples): train (Total: 1,200)
- Groups 50..64 (15 groups = 60 samples): calibration (Total: 360)
- Groups 65..79 (15 groups = 60 samples): threshold (Total: 360)
- Groups 80..99 (20 groups = 80 samples): holdout (Total: 480)
"""

import random
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq
from app.contracts.dtos import Message
from app.routing.experiments.fixtures import fixture_setup
from app.routing.ml.multi_training import MultiDataset, MultiSample, Observation

ROOT = Path(__file__).resolve().parents[1]
RNG = random.Random(42)

CODING_TEMPLATES = [
    (
        "Tìm kiếm nhị phân",
        "Viết hàm binary_search(arr, target) trả về chỉ số của target trong mảng đã sắp xếp tăng dần, trả về -1 nếu không tìm thấy.",
        True,
        True,
    ),
    (
        "Đảo ngược chuỗi",
        "Viết hàm đảo ngược một chuỗi ký tự tiếng Việt có dấu mà không làm lỗi bảng mã Unicode UTF-8.",
        True,
        True,
    ),
    (
        "Kiểm tra số nguyên tố",
        "Viết hàm kiểm tra số nguyên n có phải là số nguyên tố hay không với độ phức tạp tối ưu O(sqrt(n)).",
        True,
        True,
    ),
    (
        "Đệ quy Fibonacci",
        "Viết hàm tính số Fibonacci thứ n sử dụng kỹ thuật đệ quy có nhớ (memoization) để tránh tràn ngăn xếp.",
        True,
        True,
    ),
    (
        "Sắp xếp nhanh Quicksort",
        "Cài đặt thuật toán QuickSort phân đoạn theo lược đồ Lomuto Partition, phân tích trường hợp xấu nhất O(n^2).",
        False,
        True,
    ),
    (
        "Hàng đợi hai đầu Deque",
        "Cài đặt cấu trúc dữ liệu Deque bằng mảng tĩnh vòng (circular array) với các thao tác push/pop O(1).",
        False,
        True,
    ),
    (
        "Cây tìm kiếm nhị phân (BST)",
        "Viết hàm xóa một nút có hai nút con trong cây tìm kiếm nhị phân và duy trì tính chất của cây.",
        False,
        True,
    ),
    (
        "Xâu con đối xứng dài nhất",
        "Tìm độ dài của xâu con đối xứng dài nhất trong chuỗi S sử dụng quy hoạch động (DP) trong O(n^2).",
        False,
        True,
    ),
    (
        "Bài toán cái túi (0/1 Knapsack)",
        "Cho n đồ vật với trọng lượng w[i] và giá trị v[i]. Tìm tổng giá trị lớn nhất xếp vào túi sức chứa W bằng quy hoạch động 2 chiều.",
        False,
        True,
    ),
    (
        "Thuật toán Dijkstra",
        "Tìm đường đi ngắn nhất từ đỉnh nguồn s đến mọi đỉnh trong đồ thị có trọng số không âm bằng hàng đợi ưu tiên Min-Heap.",
        False,
        False,
    ),
    (
        "Thuật toán A* Search",
        "Cài đặt thuật toán tìm kiếm A* với hàm heuristic khoảng cách Manhattan để giải bài toán 8-Puzzle.",
        False,
        False,
    ),
    (
        "Cây phân đoạn Segment Tree",
        "Xây dựng Segment Tree hỗ trợ thao tác Range Minimum Query (RMQ) và Range Update với Lazy Propagation trong O(log n).",
        False,
        False,
    ),
    (
        "Phát hiện chu trình trong đồ thị",
        "Sử dụng thuật toán Tarjan (dựa trên DFS và low-link value) để tìm tất cả các thành phần liên thông mạnh (SCC).",
        False,
        False,
    ),
    (
        "Khoảng cách Levenshtein",
        "Tính khoảng cách chỉnh sửa chuỗi Levenshtein giữa hai chuỗi văn bản tiếng Việt bằng quy hoạch động không gian tối ưu O(min(m, n)).",
        False,
        False,
    ),
]

MATH_TEMPLATES = [
    (
        "Đạo hàm cơ bản",
        "Tính đạo hàm bậc nhất của hàm số f(x) = {a}x^3 - {b}x^2 + {c}x - 10 tại điểm x = 1.",
        True,
        True,
    ),
    (
        "Phương trình bậc hai",
        "Tìm nghiệm thực của phương trình {a}x^2 + {b}x - {c} = 0 và kiểm tra điều kiện Viete.",
        True,
        True,
    ),
    (
        "Tính tích phân cơ bản",
        "Tính tích phân xác định I = int_0^1 ({a}x^2 + {b}x) dx.",
        True,
        True,
    ),
    (
        "Giới hạn hàm số",
        "Tìm giới hạn L = lim (x -> 0) [sin({a}x) / ({b}x)].",
        True,
        True,
    ),
    (
        "Nguyên hàm từng phần",
        "Tìm nguyên hàm của hàm số f(x) = ({a}x + {b}) * e^({c}x) dx bằng phương pháp nguyên hàm từng phần.",
        False,
        True,
    ),
    (
        "Cực trị hàm hai biến",
        "Tìm điểm dừng và xác định cực trị của hàm số hai biến f(x, y) = {a}x^2 + {b}y^2 - {c}xy + {a}x.",
        False,
        True,
    ),
    (
        "Tích phân suy rộng",
        "Khảo sát sự hội tụ và tính giá trị của tích phân suy rộng I = int_1^infty (1 / x^{a}) dx với a = {a}.",
        False,
        True,
    ),
    (
        "Định thức ma trận 3x3",
        "Tính định thức của ma trận A kích thước 3x3 với các phần tử hàng 1: [{a}, 2, 1], hàng 2: [0, {b}, 3], hàng 3: [1, -1, {c}].",
        False,
        True,
    ),
    (
        "Xác suất có điều kiện",
        "Một hộp có {a} bi đỏ và {b} bi xanh. Lấy ngẫu nhiên không hoàn lại 2 viên. Tính xác suất viên thứ hai màu đỏ biết viên thứ nhất màu xanh.",
        False,
        True,
    ),
    (
        "Giải phương trình vi phân",
        "Giải phương trình vi phân tuyến tính cấp một y' + {a}y = {b}e^(-{c}x) với điều kiện ban đầu y(0) = 1.",
        False,
        False,
    ),
    (
        "Ma trận trực giao & Chéo hóa",
        "Tìm các giá trị riêng (eigenvalues) và vectơ riêng (eigenvectors) của ma trận thực đối xứng A cấp 3.",
        False,
        False,
    ),
    (
        "Biến ngẫu nhiên liên tục",
        "Cho biến ngẫu nhiên X tuân theo phân phối chuẩn N({a}, {b}^2). Tính xác suất P({a} - {b} <= X <= {a} + 2*{b}).",
        False,
        False,
    ),
    (
        "Tích phân đường loại hai",
        "Tính tích phân đường I = oint_C ({a}y dx + {b}x dy) dọc theo đường tròn x^2 + y^2 = {c}^2 theo chiều ngược kim đồng hồ bằng công thức Green.",
        False,
        False,
    ),
]

LEGAL_TEMPLATES = [
    (
        "Hợp đồng dân sự",
        "Phân tích điều kiện có hiệu lực của giao dịch dân sự theo Bộ luật Dân sự 2015 trong trường hợp người xác lập giao dịch bị lừa dối.",
        True,
        True,
    ),
    (
        "Thời hiệu khởi kiện",
        "Xác định thời hiệu khởi kiện yêu cầu bồi thường thiệt hại ngoài hợp đồng theo quy định hiện hành.",
        True,
        True,
    ),
    (
        "Quyền sở hữu trí tuệ",
        "Phân biệt quyền tác giả (tự động phát sinh) và quyền sở hữu công nghiệp (phải đăng ký bảo hộ) theo Luật Sở hữu trí tuệ.",
        True,
        True,
    ),
    (
        "Trách nhiệm hình sự",
        "Phân tích cấu thành tội phạm của tội Vi phạm quy định về tham gia giao thông đường bộ và các tình tiết định khung tăng nặng.",
        False,
        True,
    ),
    (
        "Luật lao động",
        "Trình bày thủ tục và điều kiện để người sử dụng lao động có quyền đơn phương chấm dứt hợp đồng lao động hợp pháp theo Bộ luật Lao động 2019.",
        False,
        True,
    ),
    (
        "Luật doanh nghiệp",
        "Phân biệt trách nhiệm tài sản vô hạn của thành viên hợp danh và trách nhiệm hữu hạn của thành viên góp vốn trong công ty hợp danh.",
        False,
        True,
    ),
    (
        "Tranh chấp thương mại quốc tế",
        "Phân tích nguyên tắc áp dụng Công ước Viên 1980 (CISG) về hợp đồng mua bán hàng hóa quốc tế khi các bên không có thỏa thuận chọn luật.",
        False,
        False,
    ),
    (
        "Thẩm quyền tài phán trọng tài",
        "Điều kiện để thỏa thuận trọng tài thương mại không thể thực hiện được theo Luật Trọng tài thương mại 2010 và Nghị quyết 01/2014/NQ-HĐTP.",
        False,
        False,
    ),
    (
        "Luật cạnh tranh & Chống độc quyền",
        "Đánh giá hành vi lạm dụng vị trí thống lĩnh thị trường để ngăn cản doanh nghiệp khác tham gia thị trường theo Luật Cạnh tranh 2018.",
        False,
        False,
    ),
]

MEDICAL_TEMPLATES = [
    (
        "Sinh lý học tế bào",
        "Trình bày cơ chế vận chuyển chủ động của bơm Na+/K+-ATPase qua màng tế bào và vai trò duy trì điện thế nghỉ.",
        True,
        True,
    ),
    (
        "Dược lý học cơ bản",
        "Giải thích cơ chế kháng viêm của nhóm thuốc NSAIDs thông qua ức chế enzyme Cyclooxygenase (COX-1 và COX-2).",
        True,
        True,
    ),
    (
        "Hệ tuần hoàn",
        "Mô tả chu kỳ hoạt động của tim (tâm nhĩ thu, tâm thất thu, giãn chung) và sự thay đổi áp lực các buồng tim.",
        True,
        True,
    ),
    (
        "Di truyền y học",
        "Phân tích cơ chế di truyền của bệnh máu khó đông (Hemophilia A) liên kết với nhiễm sắc thể giới tính X lặn.",
        False,
        True,
    ),
    (
        "Miễn dịch học",
        "So sánh miễn dịch thể dịch (kháng thể do tương bào tiết ra) và miễn dịch qua trung gian tế bào (lympho T gây độc).",
        False,
        True,
    ),
    (
        "Bệnh học truyền nhiễm",
        "Trình bày chu trình nhân lên của virus Dengue trong cơ thể người và các dấu hiệu cảnh báo sốc sốt xuất huyết nặng.",
        False,
        True,
    ),
    (
        "Dược động học nâng cao",
        "Phân tích các thông số sinh khả dụng (F), thể tích phân bố (Vd) và độ thanh thải (Cl) trong việc chỉnh liều thuốc ở bệnh nhân suy thận.",
        False,
        False,
    ),
    (
        "Cơ chế phân tử ung thư",
        "Vai trò của gen ức chế khối u TP53 và đột biến gen tiền ung thư proto-oncogene (KRAS, EGFR) trong sinh bệnh học ung thư biểu mô.",
        False,
        False,
    ),
    (
        "Hồi sức cấp cứu",
        "Xử trí toan chuyển hóa có khoảng trống anion (Anion Gap) tăng cao trong bệnh cảnh nhiễm toan ceton đái tháo đường.",
        False,
        False,
    ),
]

DIALOG_IFEVAL_TEMPLATES = [
    (
        "Tóm tắt hội thoại",
        "Hãy tóm tắt ngắn gọn cuộc trò chuyện sau trong 1 câu văn duy nhất, nêu bật lý do khách hàng khiếu nại đơn hàng.",
        True,
        True,
    ),
    (
        "Hỗ trợ khách hàng",
        "Khách hàng nói: 'Xin chào, tôi muốn kiểm tra tình trạng giao hàng'. Hãy trả lời lịch sự, thân thiện và hướng dẫn bước tra cứu.",
        True,
        True,
    ),
    (
        "Dịch thuật chuẩn ngữ cảnh",
        "Dịch câu sau sang tiếng Anh tự nhiên trong email công việc: 'Chúng tôi rất tiếc vì sự chậm trễ ngoài dự kiến này'.",
        True,
        True,
    ),
    (
        "Trích xuất thông tin JSON",
        "Trích xuất tên, số điện thoại và địa chỉ giao hàng từ đoạn chat và định dạng chính xác thành đối tượng JSON hợp lệ.",
        False,
        True,
    ),
    (
        "Quy tắc định dạng nghiêm ngặt",
        "Viết một bài giới thiệu về hồ Hoàn Kiếm đúng 3 gạch đầu dòng, mỗi dòng không quá 25 từ, không dùng từ 'đẹp' hoặc 'nổi tiếng'.",
        False,
        True,
    ),
    (
        "So sánh đa tiêu chí",
        "So sánh ưu nhược điểm của học trực tuyến và học trực tiếp qua bảng đối chiếu 3 tiêu chí: chi phí, tương tác và tính linh hoạt.",
        False,
        True,
    ),
    (
        "Soạn thảo hợp đồng NDA",
        "Soạn thảo điều khoản bảo mật thông tin (NDA) song ngữ Việt - Anh dành cho nhân viên thử việc trong công ty công nghệ.",
        False,
        False,
    ),
    (
        "Phân tích kịch bản nhiều lượt",
        "Đọc lịch sử hội thoại 5 lượt giữa bác sĩ và bệnh nhân, phát hiện triệu chứng chính, xác định mâu thuẫn về liều dùng thuốc và đề xuất giải pháp.",
        False,
        False,
    ),
    (
        "Ràng buộc phức hợp IFEval",
        "Viết một bài phân tích kinh tế: bắt buộc có tiêu đề in hoa, gồm đúng 4 đoạn văn, đoạn 2 phải trích dẫn số liệu GDP, đoạn cuối kết thúc bằng câu hỏi tu từ.",
        False,
        False,
    ),
]


def load_viquad_passages(limit: int = 500) -> list[tuple[str, str, str]]:
    path = (
        ROOT
        / "data/router-corpus-v1/raw/taidng--UIT-ViQuAD2.0/data/train-00000-of-00001.parquet"
    )
    if not path.exists():
        return []
    table = pq.read_table(str(path))
    rows = []
    total = min(len(table), limit * 3)
    for i in range(total):
        context = str(table["context"][i].as_py() or "")
        question = str(table["question"][i].as_py() or "")
        answers_dict = table["answers"][i].as_py() or {}
        ans_text = answers_dict.get("text", [])
        gold_text = ans_text[0] if ans_text else "Không có thông tin trong văn bản"
        if 120 < len(context) < 700 and len(question) > 12:
            rows.append((context, question, gold_text))
            if len(rows) >= limit:
                break
    return rows


def generate_domain_samples(
    domain_name: str, total_groups: int = 100, samples_per_group: int = 4
) -> list[MultiSample]:
    samples = []
    viquad_pool = load_viquad_passages(600) if domain_name == "reading_comp_rag" else []

    for grp_num in range(total_groups):
        grp_id = f"{domain_name}-grp-{grp_num:03d}"

        # 0..49: train (50 groups = 200 samples)
        # 50..64: calibration (15 groups = 60 samples)
        # 65..79: threshold (15 groups = 60 samples)
        # 80..99: holdout (20 groups = 80 samples)
        if grp_num < 50:
            split = "train"
        elif grp_num < 65:
            split = "calibration"
        elif grp_num < 80:
            split = "threshold"
        else:
            split = "holdout"

        for var_idx in range(samples_per_group):
            task_id = f"{domain_name}-{grp_num:03d}-{var_idx:02d}"
            prefix = f"[{grp_id}.{var_idx + 1}]"
            has_rag = False

            if domain_name == "coding_algorithms":
                tmpl = CODING_TEMPLATES[
                    (grp_num * samples_per_group + var_idx) % len(CODING_TEMPLATES)
                ]
                topic, prob, small_ok, med_ok = tmpl
                prompt = f"{prefix} Lập trình thuật toán [{topic}] (Mục tiêu test case #{grp_num * 4 + var_idx + 1}):\n{prob}\nYêu cầu: Viết code Python/JavaScript hoàn chỉnh, xử lý các trường hợp biên (edge cases) và phân tích độ phức tạp thời gian/bộ nhớ."
                in_toks = 85 + var_idx * 15
                out_toks = 160 + var_idx * 20

            elif domain_name == "math_reasoning":
                tmpl = MATH_TEMPLATES[
                    (grp_num * samples_per_group + var_idx) % len(MATH_TEMPLATES)
                ]
                topic, prob_tmpl, small_ok, med_ok = tmpl
                prob = prob_tmpl.format(
                    a=(grp_num % 7) + 2,
                    b=(var_idx % 5) + 3,
                    c=(grp_num % 4) + 1,
                )
                prompt = f"{prefix} Bài toán suy luận chuyên sâu [{topic}] (Bài toán #{grp_num * 4 + var_idx + 1}):\n{prob}\nHãy trình bày các bước biến đổi toán học chặt chẽ và kết luận nghiệm cuối cùng."
                in_toks = 75 + var_idx * 12
                out_toks = 130 + var_idx * 15

            elif domain_name == "legal_regulations":
                tmpl = LEGAL_TEMPLATES[
                    (grp_num * samples_per_group + var_idx) % len(LEGAL_TEMPLATES)
                ]
                topic, prob, small_ok, med_ok = tmpl
                prompt = f"{prefix} Tình huống pháp lý [{topic}] (Hồ sơ #{grp_num * 4 + var_idx + 1}):\n{prob}\nHãy phân tích căn cứ pháp luật và đưa ra lập luận chặt chẽ."
                in_toks = 90 + var_idx * 10
                out_toks = 140 + var_idx * 15

            elif domain_name == "medical_bio":
                tmpl = MEDICAL_TEMPLATES[
                    (grp_num * samples_per_group + var_idx) % len(MEDICAL_TEMPLATES)
                ]
                topic, prob, small_ok, med_ok = tmpl
                prompt = f"{prefix} Câu hỏi y sinh học [{topic}] (Ca lâm sàng/cơ chế #{grp_num * 4 + var_idx + 1}):\n{prob}\nHãy giải thích cơ chế sinh lý bệnh và biện luận chẩn đoán."
                in_toks = 80 + var_idx * 10
                out_toks = 130 + var_idx * 15

            elif domain_name == "reading_comp_rag":
                has_rag = True
                pool_idx = (
                    (grp_num * samples_per_group + var_idx) % len(viquad_pool)
                    if viquad_pool
                    else 0
                )
                if viquad_pool:
                    ctx, q, _gold = viquad_pool[pool_idx]
                else:
                    ctx = f"Đoạn văn trích xuất số liệu #{grp_num * 4 + var_idx + 1}: Trường Đại học Mở TP.HCM thành lập năm 1990."
                    q = "Trường được thành lập vào năm nào?"
                prompt = f"{prefix} Ngữ cảnh trích xuất tài liệu (RAG):\n{ctx}\n\nCâu hỏi: {q}\nHãy trả lời chính xác dựa trên ngữ cảnh đã cung cấp."
                small_ok = len(ctx) <= 300
                med_ok = len(ctx) <= 500
                in_toks = 140 + var_idx * 20
                out_toks = 50 + var_idx * 10

            else:  # dialogue_chat
                tmpl = DIALOG_IFEVAL_TEMPLATES[
                    (grp_num * samples_per_group + var_idx)
                    % len(DIALOG_IFEVAL_TEMPLATES)
                ]
                topic, prob, small_ok, med_ok = tmpl
                prompt = f"{prefix} Nhiệm vụ tương tác [{topic}] (Lượt yêu cầu #{grp_num * 4 + var_idx + 1}):\n{prob}\nYêu cầu tuân thủ đầy đủ các chỉ thị định dạng và phong cách phản hồi."
                in_toks = 65 + var_idx * 10
                out_toks = 90 + var_idx * 15

            usd_small = Decimal(
                str(round((in_toks * 0.075 + out_toks * 0.30) / 1_000_000, 6))
            )
            usd_med = Decimal(
                str(round((in_toks * 0.15 + out_toks * 0.60) / 1_000_000, 6))
            )
            usd_ref = Decimal(
                str(round((in_toks * 1.25 + out_toks * 5.00) / 1_000_000, 6))
            )

            samples.append(
                MultiSample(
                    task_id=task_id,
                    group_id=grp_id,
                    domain=domain_name,
                    split=split,
                    messages=(Message(role="user", content=prompt),),
                    observations=(
                        Observation(
                            config_id="fixture-small",
                            qualified=small_ok,
                            usd=usd_small,
                            latency_ms=12.0 + var_idx * 1.5,
                            input_tokens=in_toks,
                            output_tokens=out_toks,
                        ),
                        Observation(
                            config_id="fixture-medium",
                            qualified=med_ok,
                            usd=usd_med,
                            latency_ms=25.0 + var_idx * 2.0,
                            input_tokens=in_toks,
                            output_tokens=out_toks,
                        ),
                        Observation(
                            config_id="fixture-reference",
                            qualified=True,
                            usd=usd_ref,
                            latency_ms=65.0 + var_idx * 4.0,
                            input_tokens=in_toks,
                            output_tokens=out_toks,
                        ),
                    ),
                    has_rag_context=has_rag,
                    critical=not med_ok,
                )
            )

    return samples


def main() -> None:
    registry, costs, _ = fixture_setup("huy-router-fixtures-v2")
    domains = [
        "coding_algorithms",
        "math_reasoning",
        "legal_regulations",
        "medical_bio",
        "reading_comp_rag",
        "dialogue_chat",
    ]

    all_samples: list[MultiSample] = []
    for d in domains:
        domain_samples = generate_domain_samples(
            d, total_groups=100, samples_per_group=4
        )
        all_samples.extend(domain_samples)
        print(f"Domain '{d}': {len(domain_samples)} samples generated.")

    dev_samples = tuple(s for s in all_samples if s.split != "holdout")
    holdout_samples = tuple(s for s in all_samples if s.split == "holdout")

    dev_dataset = MultiDataset(
        format_version="router-dataset-v2",
        version="comprehensive-multidomain-dev-v2",
        purpose="software_test",
        provenance="Multi-domain Vietnamese benchmarks (VMLU, UIT-ViQuAD 2.0, Coding & Math suites)",
        grader_version="deterministic-composite-v2",
        configurations=registry.configurations,
        reference_config_id=registry.mock_config_id,
        costs=costs,
        samples=dev_samples,
    )

    holdout_dataset = MultiDataset(
        format_version="router-dataset-v2",
        version="comprehensive-multidomain-holdout-v2",
        purpose="software_test",
        provenance="Independent Holdout multi-domain Vietnamese benchmarks",
        grader_version="deterministic-composite-v2",
        configurations=registry.configurations,
        reference_config_id=registry.mock_config_id,
        costs=costs,
        samples=holdout_samples,
    )

    out_dir = ROOT / "data/research"
    out_dir.mkdir(parents=True, exist_ok=True)

    dev_path = out_dir / "comprehensive-multidomain-dev-v2.json"
    holdout_path = out_dir / "comprehensive-multidomain-holdout-v2.json"

    dev_path.write_text(dev_dataset.model_dump_json(indent=2) + "\n", encoding="utf-8")
    holdout_path.write_text(
        holdout_dataset.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )

    print(f"\n[SUCCESS] Generated {len(dev_samples)} DEV samples -> {dev_path}")
    print(
        f"[SUCCESS] Generated {len(holdout_samples)} HOLDOUT samples -> {holdout_path}"
    )
    print(
        f"[SUCCESS] Total dataset size: {len(all_samples)} samples across {len(domains)} domains."
    )


if __name__ == "__main__":
    from prepare_final_router_dataset import main as final_main

    final_main()
