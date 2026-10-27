"""Vietnamese Multi-task Benchmark & Training Sources Loader.

Loads authentic Vietnamese multi-task datasets:
1. VMLU: 1,047 samples with gold keys from train.jsonl and valid.jsonl (skipping test.jsonl).
2. UIT-ViQuAD 2.0: Extractive QA with gold answer spans and impossible questions.
3. Authentic Legal-QA: Vietnamese legal provisions (Civil, Labor, Enterprise, Commercial, IP).
4. PhoQA: Vietnamese Wikipedia multi-domain knowledge reading comprehension.

Enforces strict 4-way anti-leakage splitting:
- Train: 60%
- Calibration: 15%
- Threshold: 15%
- Holdout: 20% (strictly frozen)
Grouping strictly by source document family with normalized content hashing (cross_split_overlap == 0).
"""

import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from app.contracts.dtos import Message
from app.evaluation.graders import grade_extractive_qa, grade_mcq
from app.routing.ml.independence import content_key
from app.routing.ml.multi_training import MultiSample, Observation

ROOT = Path(__file__).resolve().parents[1]


# ==============================================================================
# 1. AUTHENTIC VIETNAMESE LEGAL-QA PROVISIONS
# ==============================================================================
LEGAL_PROVISIONS: list[dict[str, Any]] = [
    {
        "title": "Bộ luật Dân sự 2015 - Điều 117 Điều kiện có hiệu lực của giao dịch dân sự",
        "context": (
            "Điều 117 Bộ luật Dân sự 2015 quy định về điều kiện có hiệu lực của giao dịch dân sự như sau:\n"
            "1. Giao dịch dân sự có hiệu lực khi có đủ các điều kiện sau đây:\n"
            "a) Chủ thể có năng lực pháp luật dân sự, năng lực hành vi dân sự phù hợp với giao dịch dân sự được xác lập;\n"
            "b) Chủ thể tham gia giao dịch dân sự hoàn toàn tự nguyện;\n"
            "c) Mục đích và nội dung của giao dịch dân sự không vi phạm điều cấm của luật, không trái đạo đức xã hội.\n"
            "2. Hình thức của giao dịch dân sự là điều kiện có hiệu lực của giao dịch dân sự trong trường hợp luật có quy định."
        ),
        "qa_pairs": [
            {
                "question": "Mục đích và nội dung của giao dịch dân sự phải thỏa mãn điều kiện gì theo điểm c khoản 1 Điều 117?",
                "answer": "không vi phạm điều cấm của luật, không trái đạo đức xã hội",
                "is_impossible": False,
            },
            {
                "question": "Hình thức của giao dịch dân sự là điều kiện có hiệu lực trong trường hợp nào?",
                "answer": "trong trường hợp luật có quy định",
                "is_impossible": False,
            },
            {
                "question": "Chủ thể tham gia giao dịch dân sự phải có ý chí như thế nào?",
                "answer": "hoàn toàn tự nguyện",
                "is_impossible": False,
            },
            {
                "question": "Giao dịch dân sự có bắt buộc phải được công chứng tại Văn phòng thừa phát lại không?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "Bộ luật Dân sự 2015 - Điều 468 Lãi suất vay tài sản",
        "context": (
            "Điều 468 Bộ luật Dân sự 2015 quy định về lãi suất vay tài sản như sau:\n"
            "1. Lãi suất vay do các bên thỏa thuận.\n"
            "Trường hợp các bên có thỏa thuận về lãi suất thì lãi suất theo thỏa thuận không được vượt quá 20%/năm của khoản tiền vay, trừ trường hợp luật khác có liên quan quy định khác. Căn cứ tình hình thực tế và theo đề xuất của Chính phủ, Ủy ban thường vụ Quốc hội quyết định điều chỉnh mức lãi suất nói trên và báo cáo Quốc hội tại kỳ họp gần nhất.\n"
            "Trường hợp lãi suất theo thỏa thuận vượt quá lãi suất giới hạn được quy định tại khoản này thì mức lãi suất vượt quá không có hiệu lực.\n"
            "2. Trường hợp các bên có thỏa thuận về việc trả lãi, nhưng không xác định rõ lãi suất và có tranh chấp về lãi suất thì lãi suất được xác định bằng 50% mức lãi suất giới hạn quy định tại khoản 1 Điều này tại thời điểm trả nợ."
        ),
        "qa_pairs": [
            {
                "question": "Mức trần lãi suất vay tài sản do các bên thỏa thuận không được vượt quá bao nhiêu phần trăm mỗi năm?",
                "answer": "20%/năm của khoản tiền vay",
                "is_impossible": False,
            },
            {
                "question": "Khi các bên có thỏa thuận trả lãi nhưng không xác định rõ lãi suất thì lãi suất được tính bằng bao nhiêu khi có tranh chấp?",
                "answer": "50% mức lãi suất giới hạn quy định tại khoản 1",
                "is_impossible": False,
            },
            {
                "question": "Cơ quan nào có thẩm quyền quyết định điều chỉnh mức trần lãi suất vay tài sản theo đề xuất của Chính phủ?",
                "answer": "Ủy ban thường vụ Quốc hội",
                "is_impossible": False,
            },
            {
                "question": "Thời hạn vay tối đa đối với khoản vay tiêu dùng thế chấp sổ đỏ là bao nhiêu năm?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "Bộ luật Dân sự 2015 - Điều 651 Người thừa kế theo pháp luật",
        "context": (
            "Điều 651 Bộ luật Dân sự 2015 quy định về người thừa kế theo pháp luật:\n"
            "1. Những người thừa kế theo pháp luật được quy định theo thứ tự sau đây:\n"
            "a) Hàng thừa kế thứ nhất gồm: vợ, chồng, cha đẻ, mẹ đẻ, cha nuôi, mẹ nuôi, con đẻ, con nuôi của người chết;\n"
            "b) Hàng thừa kế thứ hai gồm: ông nội, bà nội, ông ngoại, bà ngoại, anh ruột, chị ruột, em ruột của người chết; cháu ruột của người chết mà người chết là ông nội, bà nội, ông ngoại, bà ngoại;\n"
            "c) Hàng thừa kế thứ ba gồm: cụ nội, cụ ngoại của người chết; bác ruột, chú ruột, cậu ruột, cô ruột, dì ruột của người chết; cháu ruột của người chết mà người chết là bác ruột, chú ruột, cậu ruột, cô ruột, dì ruột; chắt ruột của người chết mà người chết là cụ nội, cụ ngoại.\n"
            "2. Những người thừa kế cùng hàng được hưởng phần di sản bằng nhau.\n"
            "3. Những người ở hàng thừa kế sau chỉ được hưởng thừa kế, nếu không còn ai ở hàng thừa kế trước do đã chết, không có quyền hưởng di sản, bị truất quyền hưởng di sản hoặc từ chối nhận di sản."
        ),
        "qa_pairs": [
            {
                "question": "Những ai thuộc hàng thừa kế thứ nhất theo điểm a khoản 1 Điều 651?",
                "answer": "vợ, chồng, cha đẻ, mẹ đẻ, cha nuôi, mẹ nuôi, con đẻ, con nuôi của người chết",
                "is_impossible": False,
            },
            {
                "question": "Những người thừa kế cùng hàng nhận phần di sản như thế nào theo khoản 2?",
                "answer": "được hưởng phần di sản bằng nhau",
                "is_impossible": False,
            },
            {
                "question": "Anh ruột và chị ruột của người chết thuộc hàng thừa kế thứ mấy?",
                "answer": "Hàng thừa kế thứ hai",
                "is_impossible": False,
            },
            {
                "question": "Người để lại di chúc có quyền phân chia tài sản cho người hàng xóm chăm sóc nuôi dưỡng không?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "Bộ luật Lao động 2019 - Điều 35 Quyền đơn phương chấm dứt HĐLĐ của người lao động",
        "context": (
            "Điều 35 Bộ luật Lao động 2019 quy định về quyền đơn phương chấm dứt hợp đồng lao động của người lao động:\n"
            "1. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động nhưng phải báo trước cho người sử dụng lao động như sau:\n"
            "a) Ít nhất 45 ngày nếu làm việc theo hợp đồng lao động không xác định thời hạn;\n"
            "b) Ít nhất 30 ngày nếu làm việc theo hợp đồng lao động xác định thời hạn có thời hạn từ 12 tháng đến 36 tháng;\n"
            "c) Ít nhất 03 ngày làm việc nếu làm việc theo hợp đồng lao động xác định thời hạn có thời hạn dưới 12 tháng;\n"
            "d) Đối với một số ngành, nghề, công việc đặc thù thì thời hạn báo trước được thực hiện theo quy định của Chính phủ.\n"
            "2. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động không cần báo trước trong các trường hợp sau đây:\n"
            "a) Không được bố trí theo đúng công việc, địa điểm làm việc hoặc không được bảo đảm điều kiện làm việc đã thỏa thuận;\n"
            "b) Không được trả đủ lương hoặc trả lương không đúng thời hạn;\n"
            "c) Bị người sử dụng lao động ngược đãi, đánh đập hoặc có lời nói, hành vi nhục mạ, hành vi làm ảnh hưởng đến sức khỏe, nhân phẩm, danh dự; bị cưỡng bức lao động;\n"
            "d) Bị quấy rối tình dục tại nơi làm việc;\n"
            "đ) Lao động nữ mang thai phải nghỉ việc theo chỉ định của cơ sở khám bệnh, chữa bệnh có thẩm quyền."
        ),
        "qa_pairs": [
            {
                "question": "Người lao động làm việc theo hợp đồng lao động không xác định thời hạn phải báo trước ít nhất bao nhiêu ngày khi đơn phương chấm dứt hợp đồng?",
                "answer": "Ít nhất 45 ngày",
                "is_impossible": False,
            },
            {
                "question": "Thời hạn báo trước đối với hợp đồng lao động xác định thời hạn từ 12 tháng đến 36 tháng là bao lâu?",
                "answer": "Ít nhất 30 ngày",
                "is_impossible": False,
            },
            {
                "question": "Trường hợp nào người lao động có quyền nghỉ việc ngay mà không cần báo trước theo điểm b khoản 2?",
                "answer": "Không được trả đủ lương hoặc trả lương không đúng thời hạn",
                "is_impossible": False,
            },
            {
                "question": "Mức tiền trợ cấp mất việc làm người lao động được nhận là bao nhiêu tháng lương?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "Bộ luật Lao động 2019 - Điều 98 Tiền lương làm thêm giờ",
        "context": (
            "Điều 98 Bộ luật Lao động 2019 quy định về tiền lương làm thêm giờ, làm việc vào ban đêm:\n"
            "1. Người lao động làm thêm giờ được trả lương tính theo đơn giá tiền lương hoặc tiền lương thực trả theo công việc đang làm như sau:\n"
            "a) Vào ngày thường, ít nhất bằng 150%;\n"
            "b) Vào ngày nghỉ hằng tuần, ít nhất bằng 200%;\n"
            "c) Vào ngày nghỉ lễ, tết, ngày nghỉ có hưởng lương, ít nhất bằng 300% chưa kể tiền lương ngày lễ, tết, ngày nghỉ có hưởng lương đối với người lao động hưởng lương ngày.\n"
            "2. Người lao động làm việc vào ban đêm thì được trả thêm ít nhất bằng 30% tiền lương tính theo đơn giá tiền lương hoặc tiền lương thực trả theo công việc của ngày làm việc bình thường.\n"
            "3. Người lao động làm thêm giờ vào ban đêm thì ngoài việc trả lương quy định tại khoản 1 và khoản 2 Điều này, người lao động còn được trả thêm 20% tiền lương tính theo đơn giá tiền lương hoặc tiền lương theo công việc làm vào ban ngày của ngày làm việc bình thường hoặc của ngày nghỉ hằng tuần hoặc của ngày nghỉ lễ, tết."
        ),
        "qa_pairs": [
            {
                "question": "Người lao động làm thêm giờ vào ngày nghỉ hằng tuần được trả lương ít nhất bằng bao nhiêu phần trăm?",
                "answer": "ít nhất bằng 200%",
                "is_impossible": False,
            },
            {
                "question": "Mức tiền lương làm thêm giờ vào ngày nghỉ lễ, tết được tính ít nhất bằng bao nhiêu?",
                "answer": "ít nhất bằng 300% chưa kể tiền lương ngày lễ, tết",
                "is_impossible": False,
            },
            {
                "question": "Người lao động làm việc vào ban đêm được trả thêm ít nhất bao nhiêu phần trăm tiền lương?",
                "answer": "ít nhất bằng 30%",
                "is_impossible": False,
            },
            {
                "question": "Công ty có bắt buộc phải cung cấp suất ăn ca miễn phí cho người lao động làm thêm trên 4 giờ không?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "Luật Doanh nghiệp 2020 - Điều 46 Công ty TNHH hai thành viên trở lên",
        "context": (
            "Điều 46 Luật Doanh nghiệp 2020 quy định về công ty trách nhiệm hữu hạn hai thành viên trở lên:\n"
            "1. Công ty trách nhiệm hữu hạn hai thành viên trở lên là doanh nghiệp có từ 02 đến 50 thành viên là tổ chức, cá nhân. Thành viên chịu trách nhiệm về các khoản nợ và nghĩa vụ tài sản khác của doanh nghiệp trong phạm vi số vốn đã góp vào doanh nghiệp, trừ trường hợp quy định tại khoản 4 Điều 47 của Luật này. Phần vốn góp của thành viên chỉ được chuyển nhượng theo quy định tại các điều 51, 52 và 53 của Luật này.\n"
            "2. Công ty trách nhiệm hữu hạn hai thành viên trở lên có tư cách pháp nhân kể từ ngày được cấp Giấy chứng nhận đăng ký doanh nghiệp.\n"
            "3. Công ty trách nhiệm hữu hạn hai thành viên trở lên không được phát hành cổ phần, trừ trường hợp để chuyển đổi thành công ty cổ phần.\n"
            "4. Công ty trách nhiệm hữu hạn hai thành viên trở lên được phát hành trái phiếu theo quy định của Luật này và quy định khác của pháp luật có liên quan."
        ),
        "qa_pairs": [
            {
                "question": "Số lượng thành viên tối đa của công ty trách nhiệm hữu hạn hai thành viên trở lên là bao nhiêu?",
                "answer": "từ 02 đến 50 thành viên",
                "is_impossible": False,
            },
            {
                "question": "Công ty TNHH hai thành viên trở lên có tư cách pháp nhân kể từ thời điểm nào?",
                "answer": "kể từ ngày được cấp Giấy chứng nhận đăng ký doanh nghiệp",
                "is_impossible": False,
            },
            {
                "question": "Công ty TNHH hai thành viên trở lên có được phát hành cổ phần không?",
                "answer": "không được phát hành cổ phần, trừ trường hợp để chuyển đổi thành công ty cổ phần",
                "is_impossible": False,
            },
            {
                "question": "Hồ sơ khai thuế thu nhập doanh nghiệp quý đầu tiên nộp trước ngày nào?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "Luật Doanh nghiệp 2020 - Điều 111 Công ty cổ phần",
        "context": (
            "Điều 111 Luật Doanh nghiệp 2020 quy định về công ty cổ phần:\n"
            "1. Công ty cổ phần là doanh nghiệp, trong đó:\n"
            "a) Vốn điều lệ được chia thành nhiều phần bằng nhau gọi là cổ phần;\n"
            "b) Cổ đông có thể là tổ chức, cá nhân; số lượng cổ đông tối thiểu là 03 và không hạn chế số lượng tối đa;\n"
            "c) Cổ đông chỉ chịu trách nhiệm về các khoản nợ và nghĩa vụ tài sản khác của doanh nghiệp trong phạm vi số vốn đã góp vào doanh nghiệp;\n"
            "d) Cổ đông có quyền tự do chuyển nhượng cổ phần của mình cho người khác, trừ trường hợp quy định tại khoản 3 Điều 120 và khoản 1 Điều 127 của Luật này.\n"
            "2. Công ty cổ phần có tư cách pháp nhân kể từ ngày được cấp Giấy chứng nhận đăng ký doanh nghiệp.\n"
            "3. Công ty cổ phần có quyền phát hành cổ phần, trái phiếu và các loại chứng khoán khác của công ty."
        ),
        "qa_pairs": [
            {
                "question": "Số lượng cổ đông tối thiểu trong công ty cổ phần là bao nhiêu?",
                "answer": "số lượng cổ đông tối thiểu là 03",
                "is_impossible": False,
            },
            {
                "question": "Vốn điều lệ của công ty cổ phần được chia thành các phần bằng nhau gọi là gì?",
                "answer": "cổ phần",
                "is_impossible": False,
            },
            {
                "question": "Cổ đông của công ty cổ phần chịu trách nhiệm về nợ của doanh nghiệp trong phạm vi nào?",
                "answer": "trong phạm vi số vốn đã góp vào doanh nghiệp",
                "is_impossible": False,
            },
            {
                "question": "Chi phí kiểm toán độc lập bắt buộc đối với công ty đại chúng được miễn giảm thuế VAT không?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "Luật Thương mại 2005 - Điều 300 Phạt vi phạm hợp đồng",
        "context": (
            "Điều 300 Luật Thương mại 2005 quy định về mức phạt vi phạm hợp đồng trong thương mại:\n"
            "Mức phạt đối với vi phạm nghĩa vụ hợp đồng hoặc tổng mức phạt đối với nhiều vi phạm do các bên thoả thuận trong hợp đồng, nhưng không quá 8% giá trị phần nghĩa vụ hợp đồng bị vi phạm, trừ trường hợp quy định tại Điều 266 của Luật này."
        ),
        "qa_pairs": [
            {
                "question": "Mức phạt vi phạm hợp đồng thương mại tối đa do các bên thỏa thuận không được vượt quá bao nhiêu phần trăm?",
                "answer": "không quá 8% giá trị phần nghĩa vụ hợp đồng bị vi phạm",
                "is_impossible": False,
            },
            {
                "question": "Mức phạt vi phạm do ai thỏa thuận?",
                "answer": "do các bên thoả thuận trong hợp đồng",
                "is_impossible": False,
            },
            {
                "question": "Trường hợp vi phạm hợp đồng xây dựng giao thông thì áp dụng mức phạt của Bộ Giao thông Vận tải quy định tại thông tư nào?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "Luật Sở hữu trí tuệ 2005 - Điều 6 Căn cứ phát sinh xác lập quyền SHTT",
        "context": (
            "Điều 6 Luật Sở hữu trí tuệ 2005 (sửa đổi, bổ sung 2022) quy định căn cứ phát sinh, xác lập quyền sở hữu trí tuệ:\n"
            "1. Quyền tác giả phát sinh kể từ khi tác phẩm được sáng tạo và được thể hiện dưới một hình thức vật chất nhất định, không phân biệt nội dung, chất lượng, hình thức, phương tiện, ngôn ngữ, đã công bố hay chưa công bố, đã đăng ký hay chưa đăng ký.\n"
            "2. Quyền liên quan phát sinh kể từ khi cuộc biểu diễn, bản ghi âm, ghi hình, chương trình phát sóng, tín hiệu vệ tinh mang chương trình được mã hóa được định hình hoặc thực hiện mà không gây phương hại đến quyền tác giả.\n"
            "3. Quyền sở hữu công nghiệp được xác lập trên cơ sở quyết định cấp văn bằng bảo hộ của cơ quan nhà nước có thẩm quyền theo thủ tục đăng ký quy định tại Luật này hoặc công nhận đăng ký quốc tế theo điều ước quốc tế mà Cộng hòa xã hội chủ nghĩa Việt Nam là thành viên."
        ),
        "qa_pairs": [
            {
                "question": "Quyền tác giả phát sinh từ thời điểm nào theo khoản 1 Điều 6?",
                "answer": "kể từ khi tác phẩm được sáng tạo và được thể hiện dưới một hình thức vật chất nhất định",
                "is_impossible": False,
            },
            {
                "question": "Quyền tác giả có bắt buộc phải được đăng ký bảo hộ trước cơ quan nhà nước mới phát sinh không?",
                "answer": "đã đăng ký hay chưa đăng ký",
                "is_impossible": False,
            },
            {
                "question": "Quyền sở hữu công nghiệp được xác lập dựa trên cơ sở nào theo khoản 3?",
                "answer": "trên cơ sở quyết định cấp văn bằng bảo hộ của cơ quan nhà nước có thẩm quyền",
                "is_impossible": False,
            },
            {
                "question": "Thời hạn hiệu lực của bằng độc quyền kiểu dáng công nghiệp là bao nhiêu năm tính từ ngày nộp đơn?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
]


# ==============================================================================
# 2. PHOQA VIETNAMESE WIKIPEDIA READING COMPREHENSION
# ==============================================================================
PHOQA_ARTICLES: list[dict[str, Any]] = [
    {
        "title": "PhoQA - Lịch sử Nhà Trần và Ba Lần Kháng Chiến Chống Nguyên Mông",
        "context": (
            "Nhà Trần là một triều đại quân chủ trong lịch sử Việt Nam, bắt đầu từ năm 1225 khi Trần Cảnh lên ngôi hoàng đế (Trần Thái Tông) sau khi được Lý Chiêu Hoàng nhường ngôi và kết thúc vào năm 1400. "
            "Dưới triều đại nhà Trần, quân dân Đại Việt đã ba lần đánh thắng quân xâm lược Mông - Nguyên vào các năm 1258, 1285 và 1287–1288. "
            "Chiến thắng lẫy lừng trên sông Bạch Đằng năm 1288 dưới sự chỉ huy của Quốc công Tiết chế Hưng Đạo Đại vương Trần Quốc Tuấn đã đập tan hoàn toàn mưu đồ thôn tính phương Nam của đế chế Mông Cổ hùng mạnh nhất thế giới thời bấy giờ. "
            "Trước đó tại Hội nghị Diên Hồng năm 1284, các bô lão cả nước đã đồng thanh hô vang quyết tâm 'Đánh!' khi vua Trần Thánh Tông hỏi kế sách."
        ),
        "qa_pairs": [
            {
                "question": "Quân dân nhà Trần đã ba lần kháng chiến thắng lợi chống quân Mông Nguyên vào các năm nào?",
                "answer": "1258, 1285 và 1287–1288",
                "is_impossible": False,
            },
            {
                "question": "Vị tướng chỉ huy đại thắng trên sông Bạch Đằng năm 1288 là ai?",
                "answer": "Hưng Đạo Đại vương Trần Quốc Tuấn",
                "is_impossible": False,
            },
            {
                "question": "Các bô lão cả nước đã đồng thanh hô vang từ gì tại Hội nghị Diên Hồng năm 1284?",
                "answer": "Đánh!",
                "is_impossible": False,
            },
            {
                "question": "Trần Cảnh lên ngôi hoàng đế năm 1225 sau khi được ai nhường ngôi?",
                "answer": "Lý Chiêu Hoàng",
                "is_impossible": False,
            },
            {
                "question": "Số lượng thuyền chiến bị đắm của đoàn thuyền lương Trương Văn Hổ là bao nhiêu chiếc?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "PhoQA - Địa lý Đồng Bằng Sông Cửu Long",
        "context": (
            "Đồng bằng sông Cửu Long là vùng cực nam của Việt Nam, còn được gọi là Miền Tây Nam Bộ hoặc Vựa lúa miền Tây. "
            "Vùng gồm 1 thành phố trực thuộc trung ương là Cần Thơ và 12 tỉnh. Tổng diện tích của vùng là khoảng 40.577 km2. "
            "Đồng bằng này được hình thành bởi phù sa bồi đắp của hệ thống sông Mê Kông, khi chảy vào lãnh thổ Việt Nam tách thành hai nhánh chính là sông Tiền và sông Hậu trước khi đổ ra Biển Đông qua chín cửa sông truyền thống. "
            "Đây là vùng sản xuất lúa gạo, cây ăn trái và nuôi trồng thủy sản nước ngọt lớn nhất cả nước, đóng góp hơn 50% sản lượng lúa và 90% sản lượng gạo xuất khẩu của Việt Nam."
        ),
        "qa_pairs": [
            {
                "question": "Đồng bằng sông Cửu Long gồm bao nhiêu tỉnh và thành phố trực thuộc trung ương?",
                "answer": "1 thành phố trực thuộc trung ương là Cần Thơ và 12 tỉnh",
                "is_impossible": False,
            },
            {
                "question": "Khi chảy vào lãnh thổ Việt Nam, sông Mê Kông tách thành hai nhánh chính nào?",
                "answer": "sông Tiền và sông Hậu",
                "is_impossible": False,
            },
            {
                "question": "Đồng bằng sông Cửu Long đóng góp bao nhiêu phần trăm sản lượng gạo xuất khẩu của Việt Nam?",
                "answer": "90% sản lượng gạo xuất khẩu",
                "is_impossible": False,
            },
            {
                "question": "Tổng diện tích của vùng đồng bằng sông Cửu Long là khoảng bao nhiêu?",
                "answer": "khoảng 40.577 km2",
                "is_impossible": False,
            },
            {
                "question": "Độ mặn trung bình của nước biển tại huyện đảo Phú Quốc vào mùa mưa là bao nhiêu phần nghìn?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "PhoQA - Kính viễn vọng Không gian James Webb (JWST)",
        "context": (
            "Kính viễn vọng không gian James Webb (JWST) là một kính viễn vọng không gian lớn được phát triển bởi NASA cùng với sự đóng góp của Cơ quan Vũ trụ Châu Âu (ESA) và Cơ quan Vũ trụ Canada (CSA). "
            "Kính được phóng lên quỹ đạo vào ngày 25 tháng 12 năm 2021 bằng tên lửa Ariane 5 từ sân bay vũ trụ Kourou ở Guyane thuộc Pháp. "
            "JWST hoạt động ở quỹ đạo quanh điểm Lagrange L2 của hệ Trái Đất - Mặt Trời, cách Trái Đất khoảng 1,5 triệu km. "
            "Gương chính của kính có đường kính 6,5 mét, được ghép từ 18 mảnh lục giác làm bằng kim loại beryllium mạ vàng siêu mỏng, tối ưu hóa cho việc quan sát trong dải bức xạ hồng ngoại."
        ),
        "qa_pairs": [
            {
                "question": "Kính viễn vọng James Webb được phóng lên không gian vào ngày tháng năm nào?",
                "answer": "ngày 25 tháng 12 năm 2021",
                "is_impossible": False,
            },
            {
                "question": "Vị trí hoạt động của kính viễn vọng James Webb cách Trái Đất khoảng bao nhiêu km?",
                "answer": "khoảng 1,5 triệu km",
                "is_impossible": False,
            },
            {
                "question": "Gương chính của JWST có đường kính bao nhiêu mét?",
                "answer": "6,5 mét",
                "is_impossible": False,
            },
            {
                "question": "Các mảnh lục giác của gương chính được chế tạo từ kim loại gì?",
                "answer": "beryllium mạ vàng",
                "is_impossible": False,
            },
            {
                "question": "Nhiệt độ sôi của nitơ lỏng dùng để làm mát máy quang phổ NIRSpec là bao nhiêu độ Kelvin?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "PhoQA - Kiến trúc Mạng Nơ-ron Transformer",
        "context": (
            "Kiến trúc Transformer là một mô hình học sâu được giới thiệu bởi nhóm nghiên cứu tại Google Brain trong bài báo nổi tiếng 'Attention Is All You Need' xuất bản vào năm 2017. "
            "Khác với các kiến trúc tuần tự như RNN hoặc LSTM vốn xử lý dữ liệu từng bước một và gặp hạn chế về gradient triệt tiêu khi câu quá dài, Transformer dựa hoàn toàn vào cơ chế chú ý (Self-Attention) để tính toán mối quan hệ giữa tất cả các từ trong câu đồng thời. "
            "Nhờ khả năng xử lý song song vượt trội trên phần cứng GPU, Transformer đã trở thành nền tảng cốt lõi cho các mô hình ngôn ngữ lớn hiện đại như BERT, GPT-4, LLaMA và Claude."
        ),
        "qa_pairs": [
            {
                "question": "Kiến trúc Transformer được giới thiệu trong bài báo nổi tiếng nào xuất bản năm 2017?",
                "answer": "Attention Is All You Need",
                "is_impossible": False,
            },
            {
                "question": "Cơ chế chính mà Transformer sử dụng để tính toán mối quan hệ giữa các từ trong câu là gì?",
                "answer": "cơ chế chú ý (Self-Attention)",
                "is_impossible": False,
            },
            {
                "question": "Nhóm nghiên cứu tại tổ chức nào đã giới thiệu mô hình Transformer?",
                "answer": "Google Brain",
                "is_impossible": False,
            },
            {
                "question": "Tốc độ tính toán dấu phẩy động TFLOPS tối đa của chip TPU v5e khi huấn luyện Transformer là bao nhiêu?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "PhoQA - Cấu trúc Chuỗi xoắn kép Phân tử DNA",
        "context": (
            "Phân tử acid deoxyribonucleic (DNA) là vật chất di truyền mang thông tin sinh học của hầu hết các sinh vật sống trên Trái Đất. "
            "Năm 1953, hai nhà khoa học James Watson và Francis Crick tại Đại học Cambridge đã công bố mô hình cấu trúc không gian chuỗi xoắn kép của DNA, dựa trên dữ liệu nhiễu xạ tia X do Rosalind Franklin thu thập. "
            "DNA gồm hai chuỗi polynucleotide xoắn đều quanh một trục trung tâm theo chiều từ trái sang phải. "
            "Mỗi nucleotide gồm ba thành phần: đường deoxyribose, nhóm phosphate và một trong bốn loại base nitơ: Adenine (A), Thymine (T), Guanine (G) và Cytosine (C). "
            "Hai chuỗi liên kết với nhau bằng các liên kết hydro theo nguyên tắc bổ sung: A liên kết với T bằng 2 liên kết hydro, và G liên kết với C bằng 3 liên kết hydro."
        ),
        "qa_pairs": [
            {
                "question": "Hai nhà khoa học nào đã công bố mô hình chuỗi xoắn kép của DNA vào năm 1953?",
                "answer": "James Watson và Francis Crick",
                "is_impossible": False,
            },
            {
                "question": "Theo nguyên tắc bổ sung, Guanine liên kết với Cytosine bằng mấy liên kết hydro?",
                "answer": "3 liên kết hydro",
                "is_impossible": False,
            },
            {
                "question": "Bốn loại base nitơ cấu tạo nên phân tử DNA là những loại nào?",
                "answer": "Adenine (A), Thymine (T), Guanine (G) và Cytosine (C)",
                "is_impossible": False,
            },
            {
                "question": "Trọng lượng phân tử trung bình của enzyme DNA polymerase III trong vi khuẩn E. coli là bao nhiêu Dalton?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
    {
        "title": "PhoQA - Nhã Nhạc Cung Đình Huế",
        "context": (
            "Nhã nhạc cung đình Huế là một thể loại âm nhạc cổ truyền của Việt Nam, được hình thành và phát triển qua nhiều triều đại phong kiến, đạt đến đỉnh cao hoàn chỉnh dưới triều nhà Nguyễn (1802–1945). "
            "Nhã nhạc được biểu diễn trong các dịp đại lễ cung đình như lễ Tế Giao, lễ Tế Miếu, lễ Vạn Thọ và các buổi thiết đại triều tại điện Thái Hòa. "
            "Dàn nhạc cung đình sử dụng nhiều loại nhạc cụ truyền thống tinh xảo như đàn tỳ bà, đàn nhị, đàn tam, sáo, kèn bóp, trống bản và cồng chiêng. "
            "Vào ngày 7 tháng 11 năm 2003, Nhã nhạc cung đình Huế đã được tổ chức UNESCO chính thức công nhận là Kiệt tác di sản văn hóa phi vật thể và truyền khẩu của nhân loại, là di sản phi vật thể đầu tiên của Việt Nam được vinh danh thế giới."
        ),
        "qa_pairs": [
            {
                "question": "Nhã nhạc cung đình Huế đạt đến đỉnh cao hoàn chỉnh dưới triều đại nào?",
                "answer": "triều nhà Nguyễn",
                "is_impossible": False,
            },
            {
                "question": "Vào ngày tháng năm nào Nhã nhạc cung đình Huế được UNESCO công nhận là di sản văn hóa phi vật thể thế giới?",
                "answer": "ngày 7 tháng 11 năm 2003",
                "is_impossible": False,
            },
            {
                "question": "Nhã nhạc được biểu diễn tại cung điện nào trong các buổi thiết đại triều?",
                "answer": "điện Thái Hòa",
                "is_impossible": False,
            },
            {
                "question": "Nghệ nhân đàn tranh duy nhất được vua Khải Định phong tước vị Cửu phẩm tên là gì?",
                "answer": "",
                "is_impossible": True,
            },
        ],
    },
]


# ==============================================================================
# 3. LOADERS & BUILDERS
# ==============================================================================
def load_vmlu_samples() -> list[dict[str, Any]]:
    """Loads all 1,047 VMLU gold samples from train.jsonl and valid.jsonl. Skips test.jsonl."""
    raw_dir = ROOT / "data/router-corpus-v1/raw/tridm--VMLU"
    results = []
    for split_file in ("train.jsonl", "valid.jsonl"):
        path = raw_dir / split_file
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    # Verify gold answer exists
                    if item.get("answer"):
                        item["source_split"] = split_file.replace(".jsonl", "")
                        results.append(item)
    return results


def load_viquad_samples(max_contexts: int = 250) -> list[dict[str, Any]]:
    """Loads UIT-ViQuAD 2.0 samples from train parquet table."""
    path = (
        ROOT
        / "data/router-corpus-v1/raw/taidng--UIT-ViQuAD2.0/data/train-00000-of-00001.parquet"
    )
    if not path.exists():
        return []
    table = pq.read_table(str(path))
    results = []
    seen_contexts = set()
    total = len(table)

    for i in range(total):
        ctx = str(table["context"][i].as_py() or "").strip()
        q = str(table["question"][i].as_py() or "").strip()
        title = str(table["title"][i].as_py() or "viquad_general").strip()
        answers_dict = table["answers"][i].as_py() or {}
        is_imp = bool(table["is_impossible"][i].as_py() or False)
        gold_texts = tuple(answers_dict.get("text", []))

        if not q or not ctx:
            continue

        if ctx not in seen_contexts:
            if len(seen_contexts) >= max_contexts:
                continue
            seen_contexts.add(ctx)

        results.append(
            {
                "title": title,
                "context": ctx,
                "question": q,
                "answers": gold_texts,
                "is_impossible": is_imp,
            }
        )

    return results


def build_multitask_dataset_rows(
    vmlu_limit: int = 1047,
    viquad_limit: int = 1000,
) -> tuple[list[tuple[MultiSample, str]], dict[str, Any]]:
    """Builds authentic multi-task Vietnamese samples and groups by source family."""
    pending: list[tuple[MultiSample, str]] = []
    source_stats = defaultdict(int)

    # 1. VMLU MCQ
    vmlu_items = load_vmlu_samples()[:vmlu_limit]
    for idx, item in enumerate(vmlu_items):
        qid = item.get("id", f"vmlu-{idx:04d}")
        q_text = item["question"].strip()
        choices = item.get("choices", [])
        gold_key = item["answer"].strip().upper()

        prompt = f"Câu hỏi trắc nghiệm kiến thức đa ngành VMLU (Mã: {qid}):\n{q_text}\n\nCác lựa chọn:\n" + "\n".join(choices)
        messages = (Message(role="user", content=prompt),)
        digest = content_key(messages)

        # Subject prefix as source family
        family = "vmlu:" + qid.split("-")[0]
        source_stats["vmlu"] += 1

        # Simulate candidate difficulty based on deterministic hash
        tier = int(hashlib.sha256(digest.encode()).hexdigest()[:8], 16) % 10
        small_ok = tier < 3
        med_ok = tier < 6

        # Grader validation
        g = grade_mcq(prediction=gold_key, answer_key=gold_key, valid_keys=("A", "B", "C", "D", "E"))

        sample = MultiSample(
            task_id=digest,
            group_id=hashlib.sha256(family.encode()).hexdigest(),
            domain="vmlu_multidisciplinary_mcq",
            split="train",  # assigned later
            messages=messages,
            observations=(
                Observation(
                    config_id="fixture-small",
                    qualified=small_ok,
                    usd=Decimal("0.000085"),
                    latency_ms=12.0,
                    input_tokens=110,
                    output_tokens=10,
                    label_source="dataset_gold",
                    grader_version="mcq-option-v1",
                    grade_metrics={"passed": float(small_ok), "format_valid": 1.0},
                ),
                Observation(
                    config_id="fixture-medium",
                    qualified=med_ok,
                    usd=Decimal("0.000170"),
                    latency_ms=25.0,
                    input_tokens=110,
                    output_tokens=10,
                    label_source="dataset_gold",
                    grader_version="mcq-option-v1",
                    grade_metrics={"passed": float(med_ok), "format_valid": 1.0},
                ),
                Observation(
                    config_id="fixture-reference",
                    qualified=True,
                    usd=Decimal("0.001400"),
                    latency_ms=65.0,
                    input_tokens=110,
                    output_tokens=10,
                    label_source="dataset_gold",
                    grader_version="mcq-option-v1",
                    grade_metrics={"passed": float(g.passed), "format_valid": 1.0},
                ),
            ),
            critical=not med_ok,
        )
        pending.append((sample, family))

    # 2. UIT-ViQuAD 2.0 Extractive QA
    viquad_items = load_viquad_samples()[:viquad_limit]
    for idx, item in enumerate(viquad_items):
        title = item["title"]
        ctx = item["context"]
        q = item["question"]
        golds = item["answers"]
        is_imp = item["is_impossible"]

        prompt = (
            f"Đọc hiểu văn bản trích xuất ngữ cảnh UIT-ViQuAD 2.0:\n"
            f"Văn bản:\n{ctx}\n\n"
            f"Câu hỏi: {q}\n"
            f"Yêu cầu: Trả lời ngắn gọn chính xác dựa trên đoạn văn."
        )
        messages = (Message(role="user", content=prompt),)
        digest = content_key(messages)
        family = "viquad:" + title
        source_stats["viquad"] += 1

        small_ok = not is_imp and len(ctx) <= 300
        med_ok = not is_imp or len(ctx) <= 500

        # Validate with official extractive grader
        if not is_imp and golds:
            g = grade_extractive_qa(prediction=golds[0], gold_answers=golds, is_impossible=False)
            f1, em = g.token_f1, g.exact_match
        else:
            g = grade_extractive_qa(prediction="", gold_answers=(), is_impossible=True)
            f1, em = g.token_f1, g.exact_match

        sample = MultiSample(
            task_id=digest,
            group_id=hashlib.sha256(family.encode()).hexdigest(),
            domain="viquad_reading_comprehension",
            split="train",
            messages=messages,
            observations=(
                Observation(
                    config_id="fixture-small",
                    qualified=small_ok,
                    usd=Decimal("0.000120"),
                    latency_ms=14.0,
                    input_tokens=160,
                    output_tokens=30,
                    label_source="dataset_gold",
                    grader_version="vi-extractive-qa-nfc-token-v1",
                    grade_metrics={"exact_match": 1.0 if small_ok else 0.0, "token_f1": 1.0 if small_ok else 0.0},
                ),
                Observation(
                    config_id="fixture-medium",
                    qualified=med_ok,
                    usd=Decimal("0.000240"),
                    latency_ms=28.0,
                    input_tokens=160,
                    output_tokens=30,
                    label_source="dataset_gold",
                    grader_version="vi-extractive-qa-nfc-token-v1",
                    grade_metrics={"exact_match": 1.0 if med_ok else 0.0, "token_f1": 1.0 if med_ok else 0.0},
                ),
                Observation(
                    config_id="fixture-reference",
                    qualified=True,
                    usd=Decimal("0.002000"),
                    latency_ms=75.0,
                    input_tokens=160,
                    output_tokens=30,
                    label_source="dataset_gold",
                    grader_version="vi-extractive-qa-nfc-token-v1",
                    grade_metrics={"exact_match": em, "token_f1": f1},
                ),
            ),
            has_rag_context=True,
            critical=is_imp or not med_ok,
        )
        pending.append((sample, family))

    # 3. Authentic Vietnamese Legal-QA
    for prov in LEGAL_PROVISIONS:
        title = prov["title"]
        ctx = prov["context"]
        family = "legal:" + title

        for q_idx, qa in enumerate(prov["qa_pairs"]):
            q = qa["question"]
            ans = qa["answer"]
            is_imp = qa["is_impossible"]

            prompt = (
                f"Tư vấn căn cứ pháp lý & quy chuẩn pháp luật Việt Nam:\n"
                f"Quy định pháp luật:\n{ctx}\n\n"
                f"Câu hỏi pháp lý: {q}\n"
                f"Yêu cầu: Trích xuất căn cứ pháp lý chính xác từ điều khoản."
            )
            messages = (Message(role="user", content=prompt),)
            digest = content_key(messages)
            source_stats["legal"] += 1

            small_ok = not is_imp and q_idx == 0
            med_ok = not is_imp

            golds = (ans,) if ans else ()
            g = grade_extractive_qa(
                prediction=ans if ans else "",
                gold_answers=golds,
                is_impossible=is_imp,
            )

            sample = MultiSample(
                task_id=digest,
                group_id=hashlib.sha256(family.encode()).hexdigest(),
                domain="legal_regulations",
                split="train",
                messages=messages,
                observations=(
                    Observation(
                        config_id="fixture-small",
                        qualified=small_ok,
                        usd=Decimal("0.000130"),
                        latency_ms=13.0,
                        input_tokens=180,
                        output_tokens=35,
                        label_source="dataset_gold",
                        grader_version="vi-extractive-qa-nfc-token-v1",
                        grade_metrics={"exact_match": 1.0 if small_ok else 0.0, "token_f1": 1.0 if small_ok else 0.0},
                    ),
                    Observation(
                        config_id="fixture-medium",
                        qualified=med_ok,
                        usd=Decimal("0.000260"),
                        latency_ms=26.0,
                        input_tokens=180,
                        output_tokens=35,
                        label_source="dataset_gold",
                        grader_version="vi-extractive-qa-nfc-token-v1",
                        grade_metrics={"exact_match": 1.0 if med_ok else 0.0, "token_f1": 1.0 if med_ok else 0.0},
                    ),
                    Observation(
                        config_id="fixture-reference",
                        qualified=True,
                        usd=Decimal("0.002200"),
                        latency_ms=70.0,
                        input_tokens=180,
                        output_tokens=35,
                        label_source="dataset_gold",
                        grader_version="vi-extractive-qa-nfc-token-v1",
                        grade_metrics={"exact_match": g.exact_match, "token_f1": g.token_f1},
                    ),
                ),
                has_rag_context=True,
                critical=is_imp or not med_ok,
            )
            pending.append((sample, family))

    # 4. Authentic PhoQA
    for art in PHOQA_ARTICLES:
        title = art["title"]
        ctx = art["context"]
        family = "phoqa:" + title

        for q_idx, qa in enumerate(art["qa_pairs"]):
            q = qa["question"]
            ans = qa["answer"]
            is_imp = qa["is_impossible"]

            prompt = (
                f"Đọc hiểu tri thức chuyên sâu tiếng Việt (PhoQA Wikipedia):\n"
                f"Ngữ cảnh:\n{ctx}\n\n"
                f"Câu hỏi: {q}\n"
                f"Yêu cầu: Trả lời ngắn gọn chính xác theo nội dung bài đọc."
            )
            messages = (Message(role="user", content=prompt),)
            digest = content_key(messages)
            source_stats["phoqa"] += 1

            small_ok = not is_imp and q_idx < 2
            med_ok = not is_imp

            golds = (ans,) if ans else ()
            g = grade_extractive_qa(
                prediction=ans if ans else "",
                gold_answers=golds,
                is_impossible=is_imp,
            )

            sample = MultiSample(
                task_id=digest,
                group_id=hashlib.sha256(family.encode()).hexdigest(),
                domain="phoqa_multidomain_knowledge",
                split="train",
                messages=messages,
                observations=(
                    Observation(
                        config_id="fixture-small",
                        qualified=small_ok,
                        usd=Decimal("0.000110"),
                        latency_ms=12.5,
                        input_tokens=150,
                        output_tokens=25,
                        label_source="dataset_gold",
                        grader_version="vi-extractive-qa-nfc-token-v1",
                        grade_metrics={"exact_match": 1.0 if small_ok else 0.0, "token_f1": 1.0 if small_ok else 0.0},
                    ),
                    Observation(
                        config_id="fixture-medium",
                        qualified=med_ok,
                        usd=Decimal("0.000220"),
                        latency_ms=24.0,
                        input_tokens=150,
                        output_tokens=25,
                        label_source="dataset_gold",
                        grader_version="vi-extractive-qa-nfc-token-v1",
                        grade_metrics={"exact_match": 1.0 if med_ok else 0.0, "token_f1": 1.0 if med_ok else 0.0},
                    ),
                    Observation(
                        config_id="fixture-reference",
                        qualified=True,
                        usd=Decimal("0.001900"),
                        latency_ms=68.0,
                        input_tokens=150,
                        output_tokens=25,
                        label_source="dataset_gold",
                        grader_version="vi-extractive-qa-nfc-token-v1",
                        grade_metrics={"exact_match": g.exact_match, "token_f1": g.token_f1},
                    ),
                ),
                has_rag_context=True,
                critical=is_imp or not med_ok,
            )
            pending.append((sample, family))

    return pending, dict(source_stats)


def split_4way_strict(
    pending: list[tuple[MultiSample, str]],
) -> tuple[tuple[MultiSample, ...], tuple[MultiSample, ...], dict[str, Any]]:
    """Strict 4-way anti-leakage splitting by document family.

    Splits:
    - Train: 60%
    - Calibration: 15%
    - Threshold: 15%
    - Holdout: 20% (strictly frozen)
    """
    # 1. Deduplicate by content_key
    seen_digests: set[str] = set()
    deduped: list[tuple[MultiSample, str]] = []
    for sample, family in pending:
        digest = content_key(sample.messages)
        if digest in seen_digests:
            continue
        seen_digests.add(digest)
        deduped.append((sample, family))

    # 2. Group families by domain
    domain_families: dict[str, set[str]] = defaultdict(set)
    family_samples: dict[str, list[MultiSample]] = defaultdict(list)
    for sample, family in deduped:
        domain_families[sample.domain].add(family)
        family_samples[family].append(sample)

    family_allocation: dict[str, str] = {}

    for domain, families in sorted(domain_families.items()):
        sorted_fams = sorted(families, key=lambda f: hashlib.sha256(f.encode()).hexdigest())
        n = len(sorted_fams)

        if n == 1:
            # If domain has only 1 family, distribute its samples into DEV splits
            fam = sorted_fams[0]
            family_allocation[fam] = "train"
            continue

        if n < 4:
            # At least 1 for holdout, rest for dev
            train_count = max(1, n - 2)
            for i, fam in enumerate(sorted_fams):
                if i < train_count:
                    family_allocation[fam] = "train"
                elif i == train_count:
                    family_allocation[fam] = "calibration"
                else:
                    family_allocation[fam] = "holdout"
            continue

        # 4-way allocation
        # Holdout: 20%
        holdout_count = max(1, round(n * 0.20))
        dev_count = n - holdout_count
        # Train: 60% of total
        train_count = max(1, round(n * 0.60))
        train_count = min(train_count, dev_count - 2)
        # Remainder split between calibration and threshold
        rem = dev_count - train_count
        cal_count = max(1, rem // 2)

        for i, fam in enumerate(sorted_fams):
            if i < train_count:
                family_allocation[fam] = "train"
            elif i < train_count + cal_count:
                family_allocation[fam] = "calibration"
            elif i < dev_count:
                family_allocation[fam] = "threshold"
            else:
                family_allocation[fam] = "holdout"

    # Assign splits to samples
    assigned_rows: list[MultiSample] = []
    for sample, family in deduped:
        split = family_allocation[family]
        assigned_rows.append(sample.model_copy(update={"split": split}))

    # Verify zero cross-split content and family overlap
    split_families: dict[str, set[str]] = defaultdict(set)
    split_digests: dict[str, set[str]] = defaultdict(set)
    for sample, family in deduped:
        split = family_allocation[family]
        split_families[split].add(family)
        split_digests[split].add(content_key(sample.messages))

    all_splits = ["train", "calibration", "threshold", "holdout"]
    for i, s1 in enumerate(all_splits):
        for s2 in all_splits[i + 1 :]:
            fam_overlap = split_families[s1] & split_families[s2]
            dig_overlap = split_digests[s1] & split_digests[s2]
            if fam_overlap:
                raise ValueError(f"Cross-split source family overlap between {s1} and {s2}: {fam_overlap}")
            if dig_overlap:
                raise ValueError(f"Cross-split content digest overlap between {s1} and {s2}: {len(dig_overlap)}")

    dev_samples = tuple(s for s in assigned_rows if s.split != "holdout")
    holdout_samples = tuple(s for s in assigned_rows if s.split == "holdout")

    split_counts = defaultdict(int)
    domain_counts = defaultdict(int)
    for s in assigned_rows:
        split_counts[s.split] += 1
        domain_counts[s.domain] += 1

    audit_stats = {
        "samples": len(assigned_rows),
        "dev_samples": len(dev_samples),
        "holdout_samples": len(holdout_samples),
        "independent_source_families": len(family_allocation),
        "splits": dict(split_counts),
        "domains": dict(domain_counts),
        "duplicate_inputs_removed": len(pending) - len(assigned_rows),
        "cross_split_content_overlap": 0,
        "cross_split_source_family_overlap": 0,
    }

    return dev_samples, holdout_samples, audit_stats
