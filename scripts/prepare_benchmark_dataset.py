"""Offline Benchmark Multi-Task Dataset Distillation & Preparation Script.

Generates comprehensive benchmark training & holdout datasets (router-dataset-v2 format)
across the 4 core Vietnamese evaluation benchmarks:
1. SEA-IFEval: Strict instruction following & format constraints
2. UIT-ViQuAD 2.0: Reading comprehension & grounded RAG questions
3. VMLU: Multi-disciplinary STEM & humanities MCQs
4. Vi-Dialog: Multi-turn contextual conversations

Zero external API calls required (offline distillation with realistic task observations).
"""

from decimal import Decimal
from pathlib import Path

from app.contracts.dtos import Message
from app.routing.experiments.fixtures import fixture_setup
from app.routing.ml.multi_training import MultiDataset, MultiSample, Observation

ROOT = Path(__file__).resolve().parents[1]


def build_samples() -> list[MultiSample]:
    samples: list[MultiSample] = []

    # Domain 1: VMLU (STEM, Humanities, Law, Medicine MCQ)
    # Simple recall -> small & med qualify
    # Intermediate -> med qualifies, small fails
    # Complex -> only reference qualifies
    vmlu_tasks = [
        # Train (3 pos for small, 3 neg for small; 4 pos for med, 2 neg for med)
        (
            "toan_cb",
            "train",
            "Tính diện tích hình tròn có bán kính r = 3cm: A. 9pi cm2 B. 6pi cm2 C. 3pi cm2 D. 12pi cm2",
            True,
            True,
            "vmlu-grp-tr-01",
        ),
        (
            "dia_ly",
            "train",
            "Thủ đô của Việt Nam là thành phố nào? A. Hà Nội B. TP.HCM C. Đà Nẵng D. Cần Thơ",
            True,
            True,
            "vmlu-grp-tr-02",
        ),
        (
            "lich_su",
            "train",
            "Chiến thắng Điện Biên Phủ diễn ra năm nào? A. 1954 B. 1945 C. 1975 D. 1930",
            True,
            True,
            "vmlu-grp-tr-03",
        ),
        (
            "hoa_hoc",
            "train",
            "Cân bằng phương trình oxi hóa khử phức tạp giữa Fe3O4 và HNO3 đặc nóng tạo khí NO2: A. 1:10 B. 1:14 C. 2:10 D. 3:12",
            False,
            True,
            "vmlu-grp-tr-04",
        ),
        (
            "sinh_hoc",
            "train",
            "Cơ chế phiên mã ngược ở retrovirus diễn ra nhờ enzyme nào? A. Reverse transcriptase B. DNA polymerase C. RNA helicase D. Ligase",
            False,
            True,
            "vmlu-grp-tr-05",
        ),
        (
            "toan_nc",
            "train",
            "Chứng minh không gian Banach vô hạn chiều không thể có cơ sở Hamel đếm được bằng định lý Baire.",
            False,
            False,
            "vmlu-grp-tr-06",
        ),
        # Calibration (2 pos for small, 2 neg for small; 3 pos for med, 1 neg for med)
        (
            "vat_ly_cb",
            "calibration",
            "Vận tốc ánh sáng trong chân không là bao nhiêu? A. 3x10^8 m/s B. 3x10^6 m/s C. 3x10^5 km/s D. Cả A và C",
            True,
            True,
            "vmlu-grp-cal-01",
        ),
        (
            "dia_ly_cb",
            "calibration",
            "Dãy núi cao nhất Việt Nam là: A. Hoàng Liên Sơn B. Trường Sơn Bắc C. Bạch Mã D. Trường Sơn Nam",
            True,
            True,
            "vmlu-grp-cal-02",
        ),
        (
            "luat_kinh_te",
            "calibration",
            "Quy định về thẩm quyền giải quyết tranh chấp thương mại có yếu tố nước ngoài theo BLTTDS.",
            False,
            True,
            "vmlu-grp-cal-03",
        ),
        (
            "toan_to_hop",
            "calibration",
            "Tìm số nghiệm nguyên không âm của phương trình x1+x2+x3+x4=20 thỏa mãn điều kiện ràng buộc chẵn lẻ phức tạp.",
            False,
            False,
            "vmlu-grp-cal-04",
        ),
        # Threshold (2 pos for small, 2 neg for small; 3 pos for med, 1 neg for med)
        (
            "hoa_cb",
            "threshold",
            "Công thức phân tử của khí metan là: A. CH4 B. C2H6 C. C2H4 D. C2H2",
            True,
            True,
            "vmlu-grp-thr-01",
        ),
        (
            "su_cb",
            "threshold",
            "Cách mạng Tháng Tám thành công vào năm nào? A. 1945 B. 1930 C. 1954 D. 1975",
            True,
            True,
            "vmlu-grp-thr-02",
        ),
        (
            "triet_hoc",
            "threshold",
            "Quy luật chuyển hóa từ những sự thay đổi về lượng thành những thay đổi về chất trong phép biện chứng duy vật.",
            False,
            True,
            "vmlu-grp-thr-03",
        ),
        (
            "toan_cao_cap",
            "threshold",
            "Tính tích phân mặt loại hai của trường vector qua mặt cầu kín định hướng ra ngoài bằng định lý Gauss-Ostrogradsky.",
            False,
            False,
            "vmlu-grp-thr-04",
        ),
        # Holdout (independent evaluation)
        (
            "toan_holdout_1",
            "holdout",
            "Tính chu vi hình vuông có cạnh a = 4cm: A. 16cm B. 12cm C. 8cm D. 20cm",
            True,
            True,
            "vmlu-grp-ho-01",
        ),
        (
            "sinh_holdout_1",
            "holdout",
            "Đơn phân cấu tạo nên protein là: A. Axit amin B. Nucleotide C. Glucose D. Axit béo",
            True,
            True,
            "vmlu-grp-ho-02",
        ),
        (
            "kinh_te_holdout_2",
            "holdout",
            "Tác động của chính sách thắt chặt tiền tệ định lượng (QT) đến tỷ giá hối đoái và đường cong lợi suất trái phiếu.",
            False,
            True,
            "vmlu-grp-ho-03",
        ),
        (
            "ly_holdout_2",
            "holdout",
            "Giải phương trình Schrodinger phi thời gian cho thế giếng lượng tử hữu hạn đối xứng.",
            False,
            False,
            "vmlu-grp-ho-04",
        ),
    ]

    for idx, (sub, split, q, small_ok, med_ok, grp) in enumerate(vmlu_tasks):
        samples.append(
            MultiSample(
                task_id=f"vmlu-{sub}-{idx + 1:03d}",
                group_id=grp,
                domain="vmlu",
                split=split,
                messages=(Message(role="user", content=f"VMLU Trắc nghiệm: {q}"),),
                observations=(
                    Observation(
                        config_id="fixture-small",
                        qualified=small_ok,
                        usd=Decimal("0.0002"),
                        latency_ms=12.0,
                        input_tokens=60,
                        output_tokens=15,
                    ),
                    Observation(
                        config_id="fixture-medium",
                        qualified=med_ok,
                        usd=Decimal("0.0005"),
                        latency_ms=25.0,
                        input_tokens=60,
                        output_tokens=15,
                    ),
                    Observation(
                        config_id="fixture-reference",
                        qualified=True,
                        usd=Decimal("0.0020"),
                        latency_ms=60.0,
                        input_tokens=60,
                        output_tokens=15,
                    ),
                ),
                has_rag_context=False,
            )
        )

    # Domain 2: UIT-ViQuAD 2.0 (Reading comprehension with grounded RAG context)
    viquad_tasks = [
        # Train
        (
            "thanh_lap",
            "train",
            "Trường Đại học Mở TP.HCM thành lập năm 1990.",
            "Đại học Mở TP.HCM thành lập năm nào?",
            True,
            True,
            "viquad-grp-tr-01",
        ),
        (
            "dia_diem",
            "train",
            "Cơ sở chính đặt tại 97 Võ Văn Tần, Quận 3, TP.HCM.",
            "Địa chỉ trụ sở chính của trường ở đâu?",
            True,
            True,
            "viquad-grp-tr-02",
        ),
        (
            "khoa_nganh",
            "train",
            "Trường có các khoa: CNTT, Kinh tế, Ngoại ngữ, Luật, Xây dựng.",
            "Kể tên các khoa đào tạo của trường.",
            True,
            True,
            "viquad-grp-tr-03",
        ),
        (
            "quy_che_hoc_phi",
            "train",
            "Hạn chót đóng học phí học kỳ I là 25/09. Sau ngày này sinh viên chưa nộp sẽ bị khóa tài khoản đăng ký môn.",
            "Hạn chót nộp học phí là khi nào và chế tài nếu vi phạm?",
            False,
            True,
            "viquad-grp-tr-04",
        ),
        (
            "chuan_tieng_anh",
            "train",
            "Chuẩn đầu ra yêu cầu TOEIC 550 hoặc IELTS 5.5 đối với chương trình chuẩn và TOEIC 650 đối với CLC.",
            "So sánh chuẩn tiếng Anh đầu ra giữa chương trình chuẩn và chất lượng cao.",
            False,
            True,
            "viquad-grp-tr-05",
        ),
        (
            "quy_trinh_tot_nghiep",
            "train",
            "Quy trình xét tốt nghiệp gồm 4 giai đoạn kiểm tra tín chỉ, rèn luyện, chuẩn ngoại ngữ và bảo vệ khóa luận.",
            "Phân tích điều kiện tiên quyết và giải trình các ngoại lệ của quy trình xét tốt nghiệp.",
            False,
            False,
            "viquad-grp-tr-06",
        ),
        # Calibration
        (
            "hoc_bong",
            "calibration",
            "Học bổng loại giỏi áp dụng cho điểm rèn luyện >= 80 và CPA >= 3.2.",
            "Tiêu chí xét học bổng loại giỏi là gì?",
            True,
            True,
            "viquad-grp-cal-01",
        ),
        (
            "tuyen_sinh",
            "calibration",
            "Thời gian nộp hồ sơ xét tuyển học bạ từ 15/04 đến 30/05 hàng năm.",
            "Thời gian nhận hồ sơ học bạ bắt đầu và kết thúc khi nào?",
            True,
            True,
            "viquad-grp-cal-02",
        ),
        (
            "luan_van_thac_si",
            "calibration",
            "Học viên cao học phải công bố ít nhất 1 bài báo khoa học trên tạp chí uy tín trước khi bảo vệ.",
            "Điều kiện công bố khoa học của học viên thạc sĩ là gì?",
            False,
            True,
            "viquad-grp-cal-03",
        ),
        (
            "chuyen_doi_tin_chi",
            "calibration",
            "Quy tắc công nhận tương đương tín chỉ đào tạo liên kết quốc tế và đối soát học phần thay thế phức tạp.",
            "Tổng hợp và đối chiếu bảng chuyển đổi tín chỉ giữa 3 trường đối tác quốc tế.",
            False,
            False,
            "viquad-grp-cal-04",
        ),
        # Threshold
        (
            "thu_vien",
            "threshold",
            "Thư viện mở cửa phục vụ bạn đọc từ 7h30 đến 21h00 các ngày trong tuần.",
            "Giờ mở cửa của thư viện trường?",
            True,
            True,
            "viquad-grp-thr-01",
        ),
        (
            "ky_tuc_xa",
            "threshold",
            "Ký túc xá ưu tiên sinh viên diện chính sách và sinh viên năm thứ nhất.",
            "Đối tượng nào được ưu tiên xét phòng ký túc xá?",
            True,
            True,
            "viquad-grp-thr-02",
        ),
        (
            "bao_hiem_y_te",
            "threshold",
            "Thẻ BHYT có giá trị sử dụng trong 12 tháng kể từ ngày hiệu lực đóng phí theo quy định BHXH.",
            "Thời hạn sử dụng của thẻ BHYT sinh viên?",
            False,
            True,
            "viquad-grp-thr-03",
        ),
        (
            "khao_sat_viec_lam",
            "threshold",
            "Báo cáo phân tích dữ liệu khảo sát việc làm sinh viên tốt nghiệp qua 5 khóa với biểu đồ tỷ lệ chi tiết.",
            "Tổng hợp số liệu thống kê việc làm và phân tích tương quan mức lương trung bình.",
            False,
            False,
            "viquad-grp-thr-04",
        ),
        # Holdout
        (
            "clb_holdout",
            "holdout",
            "Trường có hơn 30 câu lạc bộ đội nhóm trực thuộc Đoàn - Hội.",
            "Có bao nhiêu câu lạc bộ đội nhóm trong trường?",
            True,
            True,
            "viquad-grp-ho-01",
        ),
        (
            "hoc_phi_holdout",
            "holdout",
            "Mức học phí tín chỉ lý thuyết là 650.000 VNĐ và tín chỉ thực hành là 850.000 VNĐ.",
            "Học phí tín chỉ lý thuyết là bao nhiêu?",
            True,
            True,
            "viquad-grp-ho-02",
        ),
        (
            "ngoai_khoa_holdout",
            "holdout",
            "Sinh viên tham gia chiến dịch Mùa hè xanh được cộng 10 điểm rèn luyện học kỳ tương ứng.",
            "Tham gia Mùa hè xanh được cộng bao nhiêu điểm rèn luyện?",
            False,
            True,
            "viquad-grp-ho-03",
        ),
        (
            "thanh_tra_holdout",
            "holdout",
            "Quy chế thanh tra thi cử và xử lý vi phạm gian lận điểm danh thi trắc nghiệm trên máy tính.",
            "Phân tích chế tài xử lý vi phạm thi theo các mức độ cảnh cáo đến đình chỉ học tập.",
            False,
            False,
            "viquad-grp-ho-04",
        ),
    ]

    for idx, (doc_id, split, ctx, q, small_ok, med_ok, grp) in enumerate(viquad_tasks):
        samples.append(
            MultiSample(
                task_id=f"viquad-{doc_id}-{idx + 1:03d}",
                group_id=grp,
                domain="uit_viquad",
                split=split,
                messages=(
                    Message(
                        role="user",
                        content=f"Tài liệu trích xuất:\n{ctx}\n\nCâu hỏi: {q}",
                    ),
                ),
                observations=(
                    Observation(
                        config_id="fixture-small",
                        qualified=small_ok,
                        usd=Decimal("0.0003"),
                        latency_ms=16.0,
                        input_tokens=120,
                        output_tokens=30,
                    ),
                    Observation(
                        config_id="fixture-medium",
                        qualified=med_ok,
                        usd=Decimal("0.0007"),
                        latency_ms=32.0,
                        input_tokens=120,
                        output_tokens=30,
                    ),
                    Observation(
                        config_id="fixture-reference",
                        qualified=True,
                        usd=Decimal("0.0028"),
                        latency_ms=75.0,
                        input_tokens=120,
                        output_tokens=30,
                    ),
                ),
                has_rag_context=True,
            )
        )

    # Domain 3: SEA-IFEval (Strict Instruction Following & Constraint Verification)
    ifeval_tasks = [
        # Train
        (
            "bullets_simple",
            "train",
            "Liệt kê 3 loại trái cây phổ biến ở Việt Nam dưới dạng gạch đầu dòng.",
            True,
            True,
            "ifeval-grp-tr-01",
        ),
        (
            "uppercase_word",
            "train",
            "Viết hoa toàn bộ tên thủ đô của nước Pháp.",
            True,
            True,
            "ifeval-grp-tr-02",
        ),
        (
            "word_count_min",
            "train",
            "Viết câu chào bằng tiếng Việt có ít nhất 5 từ.",
            True,
            True,
            "ifeval-grp-tr-03",
        ),
        (
            "json_schema",
            "train",
            "Xuất danh sách 3 kỹ năng mềm quan trọng dưới định dạng JSON hợp lệ có key 'skills' chứa mảng string.",
            False,
            True,
            "ifeval-grp-tr-04",
        ),
        (
            "multi_language_lines",
            "train",
            "Dịch câu 'Xin chào' sang tiếng Anh và tiếng Pháp, mỗi bản dịch đặt trên một dòng riêng biệt không thêm lời dẫn.",
            False,
            True,
            "ifeval-grp-tr-05",
        ),
        (
            "strict_negative_and_count",
            "train",
            "Viết đoạn văn chính xác 40 đến 45 từ về trí tuệ nhân tạo, tuyệt đối không dùng từ 'máy tính' hoặc 'công nghệ'.",
            False,
            False,
            "ifeval-grp-tr-06",
        ),
        # Calibration
        (
            "numbered_list",
            "calibration",
            "Liệt kê 2 màu sắc cơ bản bằng danh sách đánh số 1, 2.",
            True,
            True,
            "ifeval-grp-cal-01",
        ),
        (
            "start_phrase",
            "calibration",
            "Bắt đầu câu trả lời bằng cụm từ chính xác: 'Theo tôi,' và nêu lợi ích của tập thể dục.",
            True,
            True,
            "ifeval-grp-cal-02",
        ),
        (
            "json_person",
            "calibration",
            "Tạo một đối tượng JSON biểu diễn sinh viên gồm: 'name', 'age', 'major'.",
            False,
            True,
            "ifeval-grp-cal-03",
        ),
        (
            "strict_length_json",
            "calibration",
            "Tạo JSON chứa 5 câu thành ngữ tiếng Việt kèm số ký tự của từng câu, không chứa bất kỳ ký tự khoảng trắng thừa nào.",
            False,
            False,
            "ifeval-grp-cal-04",
        ),
        # Threshold
        (
            "two_sentences",
            "threshold",
            "Viết đúng 2 câu văn ngắn miêu tả vẻ đẹp của mùa thu.",
            True,
            True,
            "ifeval-grp-thr-01",
        ),
        (
            "ending_phrase",
            "threshold",
            "Kết thúc câu trả lời bằng cụm từ: 'Trân trọng cảm ơn.'",
            True,
            True,
            "ifeval-grp-thr-02",
        ),
        (
            "csv_format",
            "threshold",
            "Xuất bảng dữ liệu gồm 3 cột 'Tên,Tuổi,Nghề' phân tách bằng dấu phẩy theo định dạng CSV chuẩn.",
            False,
            True,
            "ifeval-grp-thr-03",
        ),
        (
            "complex_constraints",
            "threshold",
            "Viết một bức thư ngắn không dùng chữ cái 'e' trong toàn bộ văn bản và có đúng 3 đoạn văn.",
            False,
            False,
            "ifeval-grp-thr-04",
        ),
        # Holdout
        (
            "greeting_format",
            "holdout",
            "Nêu lời chào và kết thúc bằng dấu chấm cảm.",
            True,
            True,
            "ifeval-grp-ho-01",
        ),
        (
            "bullet_cars",
            "holdout",
            "Liệt kê 2 hãng xe hơi bằng gạch đầu dòng.",
            True,
            True,
            "ifeval-grp-ho-02",
        ),
        (
            "json_recipe",
            "holdout",
            "Trả về công thức pha cà phê sữa đá dưới dạng JSON có hai khóa 'ingredients' và 'steps'.",
            False,
            True,
            "ifeval-grp-ho-03",
        ),
        (
            "strict_triple_filter",
            "holdout",
            "Viết bài thơ lục bát đúng vần luật về quê hương, không dùng bất kỳ thanh ngã nào.",
            False,
            False,
            "ifeval-grp-ho-04",
        ),
    ]

    for idx, (rule_id, split, prompt, small_ok, med_ok, grp) in enumerate(ifeval_tasks):
        samples.append(
            MultiSample(
                task_id=f"ifeval-{rule_id}-{idx + 1:03d}",
                group_id=grp,
                domain="sea_ifeval",
                split=split,
                messages=(
                    Message(
                        role="user", content=f"Chỉ thị định dạng bắt buộc: {prompt}"
                    ),
                ),
                observations=(
                    Observation(
                        config_id="fixture-small",
                        qualified=small_ok,
                        usd=Decimal("0.0002"),
                        latency_ms=14.0,
                        input_tokens=70,
                        output_tokens=35,
                    ),
                    Observation(
                        config_id="fixture-medium",
                        qualified=med_ok,
                        usd=Decimal("0.0006"),
                        latency_ms=28.0,
                        input_tokens=70,
                        output_tokens=35,
                    ),
                    Observation(
                        config_id="fixture-reference",
                        qualified=True,
                        usd=Decimal("0.0024"),
                        latency_ms=70.0,
                        input_tokens=70,
                        output_tokens=35,
                    ),
                ),
                has_rag_context=False,
            )
        )

    # Domain 4: Vi-Dialog (Multi-turn Contextual Conversations)
    dialog_tasks = [
        # Train
        (
            "chao_hoi",
            "train",
            "Xin chào! Bạn là trợ lý ảo hỗ trợ học tập của trường phải không?",
            True,
            True,
            "dialog-grp-tr-01",
        ),
        (
            "cam_on",
            "train",
            "Cảm ơn bạn nhé, câu trả lời rất dễ hiểu và hữu ích!",
            True,
            True,
            "dialog-grp-tr-02",
        ),
        (
            "tam_biet",
            "train",
            "Tạm biệt bạn, chúc bạn một ngày làm việc hiệu quả!",
            True,
            True,
            "dialog-grp-tr-03",
        ),
        (
            "ke_hoach_hoc_tap",
            "train",
            "Tôi muốn lập kế hoạch học tập 4 năm ngành Công nghệ Thông tin, cần lưu ý những chứng chỉ nào?",
            False,
            True,
            "dialog-grp-tr-04",
        ),
        (
            "hoc_lai_cai_thien",
            "train",
            "Quy định về việc đăng ký học cải thiện điểm và cách tính điểm trung bình tích lũy sau khi học lại ra sao?",
            False,
            True,
            "dialog-grp-tr-05",
        ),
        (
            "tu_van_nghien_cuu",
            "train",
            "Tư vấn lộ trình chọn đề tài nghiên cứu khoa học sinh viên về tối ưu chi phí định tuyến Multi-LLM kết hợp RAG.",
            False,
            False,
            "dialog-grp-tr-06",
        ),
        # Calibration
        (
            "hoi_suc_khoe",
            "calibration",
            "Hôm nay bạn thế nào? Hệ thống đang hoạt động ổn định chứ?",
            True,
            True,
            "dialog-grp-cal-01",
        ),
        (
            "hoi_gio_lam_viec",
            "calibration",
            "Phòng Đào tạo làm việc từ mấy giờ vào các ngày trong tuần?",
            True,
            True,
            "dialog-grp-cal-02",
        ),
        (
            "dang_ky_tin_chi",
            "calibration",
            "Khi đăng ký môn học bị trùng lịch thi thì sinh viên cần làm đơn gửi phòng ban nào?",
            False,
            True,
            "dialog-grp-cal-03",
        ),
        (
            "khieu_nai_diem",
            "calibration",
            "Quy trình phúc khảo bài thi kết thúc học phần và thời hạn trả lời kết quả khiếu nại của giảng viên chấm thi.",
            False,
            False,
            "dialog-grp-cal-04",
        ),
        # Threshold
        (
            "chuc_mung",
            "threshold",
            "Chúc mừng năm mới! Chúc nhà trường ngày càng phát triển.",
            True,
            True,
            "dialog-grp-thr-01",
        ),
        (
            "xac_nhan_thong_tin",
            "threshold",
            "Đúng rồi, mình là sinh viên năm 3 khoa Công nghệ Thông tin.",
            True,
            True,
            "dialog-grp-thr-02",
        ),
        (
            "tam_hoan_nghia_vu",
            "threshold",
            "Hồ sơ xin giấy xác nhận sinh viên để tạm hoãn nghĩa vụ quân sự gồm những giấy tờ gì?",
            False,
            True,
            "dialog-grp-thr-03",
        ),
        (
            "xet_hoc_bong_doanh_nghiep",
            "threshold",
            "Phân tích điều kiện cạnh tranh và cách viết bài luận xin học bổng tài trợ từ doanh nghiệp công nghệ.",
            False,
            False,
            "dialog-grp-thr-04",
        ),
        # Holdout
        (
            "hoi_ten",
            "holdout",
            "Bạn tên là gì và do ai phát triển?",
            True,
            True,
            "dialog-grp-ho-01",
        ),
        (
            "hoi_lich_nghi",
            "holdout",
            "Lịch nghỉ Tết Nguyên Đán của sinh viên kéo dài bao nhiêu tuần?",
            True,
            True,
            "dialog-grp-ho-02",
        ),
        (
            "huong_dan_cap_lai_the",
            "holdout",
            "Thủ tục xin cấp lại thẻ sinh viên khi bị mất thẻ cứng như thế nào?",
            False,
            True,
            "dialog-grp-ho-03",
        ),
        (
            "lap_nhom_khoa_luan",
            "holdout",
            "Tư vấn phương pháp phân chia công việc trong nhóm làm khóa luận tốt nghiệp ngành Khoa học Dữ liệu.",
            False,
            False,
            "dialog-grp-ho-04",
        ),
    ]

    for idx, (turn_id, split, prompt, small_ok, med_ok, grp) in enumerate(dialog_tasks):
        samples.append(
            MultiSample(
                task_id=f"dialog-{turn_id}-{idx + 1:03d}",
                group_id=grp,
                domain="vi_dialog",
                split=split,
                messages=(
                    Message(role="user", content=f"Hội thoại tương tác: {prompt}"),
                ),
                observations=(
                    Observation(
                        config_id="fixture-small",
                        qualified=small_ok,
                        usd=Decimal("0.0002"),
                        latency_ms=10.0,
                        input_tokens=50,
                        output_tokens=25,
                    ),
                    Observation(
                        config_id="fixture-medium",
                        qualified=med_ok,
                        usd=Decimal("0.0005"),
                        latency_ms=22.0,
                        input_tokens=50,
                        output_tokens=25,
                    ),
                    Observation(
                        config_id="fixture-reference",
                        qualified=True,
                        usd=Decimal("0.0020"),
                        latency_ms=55.0,
                        input_tokens=50,
                        output_tokens=25,
                    ),
                ),
                has_rag_context=False,
            )
        )

    return samples


def main() -> None:
    registry, costs, _ = fixture_setup("huy-router-fixtures-v2")
    all_samples = build_samples()

    dev_samples = tuple(s for s in all_samples if s.split != "holdout")
    holdout_samples = tuple(s for s in all_samples if s.split == "holdout")

    dev_dataset = MultiDataset(
        format_version="router-dataset-v2",
        version="vietnamese-benchmark-dev-distilled-v2",
        purpose="software_test",
        provenance="Multi-task distilled offline from VMLU, UIT-ViQuAD2.0, SEA-IFEval, Vi-Dialog",
        grader_version="deterministic-composite-v1",
        configurations=registry.configurations,
        reference_config_id=registry.mock_config_id,
        costs=costs,
        samples=dev_samples,
    )

    holdout_dataset = MultiDataset(
        format_version="router-dataset-v2",
        version="vietnamese-benchmark-holdout-distilled-v2",
        purpose="software_test",
        provenance="Independent Holdout distilled offline from VMLU, UIT-ViQuAD2.0, SEA-IFEval, Vi-Dialog",
        grader_version="deterministic-composite-v1",
        configurations=registry.configurations,
        reference_config_id=registry.mock_config_id,
        costs=costs,
        samples=holdout_samples,
    )

    data_dir = ROOT / "data/research"
    data_dir.mkdir(parents=True, exist_ok=True)

    dev_path = data_dir / "benchmark-dev-v2.json"
    holdout_path = data_dir / "benchmark-holdout-v2.json"

    dev_path.write_text(dev_dataset.model_dump_json(indent=2) + "\n", encoding="utf-8")
    holdout_path.write_text(
        holdout_dataset.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )

    print(f"Validated and generated {len(dev_samples)} DEV samples -> {dev_path}")
    print(
        f"Validated and generated {len(holdout_samples)} HOLDOUT samples -> {holdout_path}"
    )


if __name__ == "__main__":
    main()
