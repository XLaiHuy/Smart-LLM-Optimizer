# Phân tích lỗi và bổ sung dữ liệu ML + Attention

## Kết quả cũ có những loại lỗi nào?

Giữ nguyên kết quả đã công bố **177/200**, không sửa đáp án hoặc loại câu sau khi
xem kết quả để tăng điểm. Khi đối chiếu cùng phản hồi đã cache của ba model:

| Kết quả | Số câu | Ý nghĩa |
|---|---:|---|
| Router và reference cùng đạt | 176 | Phần đã phục vụ đúng theo grader hiện tại |
| Router đạt, reference không đạt | 1 | Lợi ích lựa chọn model quan sát được |
| Reference đạt, router không đạt | 4 | Regression do lựa chọn model |
| Router/reference không đạt, có model khác đạt | 12 | Cơ hội chọn model tốt hơn, chưa chắc router nhận diện được từ câu hỏi |
| Không model nào đạt | 7 | Cần kiểm tra model, định dạng hoặc dữ liệu; không thể chỉ đổi lựa chọn trong ba phản hồi đã có |

23 câu bị chấm sai gồm **4 + 12 + 7**; không phải 23 lỗi của cùng một nguyên nhân.
Reference 180/200 cũng có 20 câu không đạt. So với reference, router mất bốn câu và
cải thiện một câu, nên chênh lệch ròng là ba câu.

## Bốn regression cụ thể

| Nhóm | Ví dụ và phản hồi | Điểm/ngưỡng của model được chọn |
|---|---|---|
| Tính ngược phần trăm | Chỉ số giảm 2%, còn 8.722: giá trị trước đó là `8722 / 0.98 = 8900`; model 20B trả `8902.04` | 0,93280 / 0,92290 |
| Số âm | `−313 + −211 = −524`, gold C; Luna chọn D | 0,91602 / 0,9 |
| Chia hết cho 9 | Gold D; Luna chọn B, hai GPT OSS chọn D | 0,92955 / 0,9 |
| Số nguyên tố sau tính biểu thức | Gold A; Luna chọn B, hai GPT OSS chọn A | 0,94373 / 0,9 |

Đây là ví dụ router tin rằng ứng viên đủ tốt nhưng phản hồi thực không đạt. Không
nâng threshold theo bốn câu test này để làm đẹp điểm. Cần bổ sung dữ liệu liên quan,
fit/calibrate trên DEV và kiểm tra bằng nhóm câu mới.

## Dữ liệu và cách chấm cũng cần kiểm tra

- Bài tuổi: James kém John 12 tuổi; Tim bằng hai lần tuổi John trừ 5. Nếu Tim 79
  thì John 42, James **30**, trong khi gold nguồn ghi **25**. Đây là sai lệch có
  thể kiểm chứng bằng phép tính; phản hồi `30` bị grader hiện tại chấm không đạt.
- Câu chọn phát biểu đúng chứa cả `6 ∈ N` và `−19 ∈ Z`: có ít nhất hai lựa chọn
  đúng, trong khi gold nguồn chỉ chấp nhận D.
- Một câu chia hết bị chèn tiêu đề trang web vào chỗ biểu thức cần tính. Không
  đủ đề bài thì thêm model hoặc train nhiều epoch không sửa được câu hỏi đó.
- Một phản hồi ghi `3 plum, 3 pear, 3 apricot` có nội dung phù hợp nhưng vi phạm
  yêu cầu chỉ trả một số. Vẫn giữ FAIL theo protocol định dạng đã khóa; không
  nới grader sau khi thấy phản hồi.

Các phát hiện này được lưu riêng cho rà soát nguồn. Không sửa lại tập test cũ hoặc
sử dụng các câu của tập đó trong tập học bổ sung.

## Attention đã cho thấy gì?

Trên 300 mẫu DEV, bốn trong sáu đầu ra gần 0 hoặc 1 ở ít nhất 99% mẫu. Đây là dấu
hiệu biểu diễn cần kiểm tra thêm, **chưa chứng minh** nó gây ra bốn regression.
Sáu đầu ra là đặc trưng học được để dự đoán khả năng đạt của model, chưa được chứng
nhận là sáu năng lực Toán/Code/Sáng tạo riêng biệt.

Đợt này giữ cùng encoder, 5 epoch, 100 cây, cùng công thức huấn luyện và thông số
generation. So sánh ML không Attention, ML có Attention và artifact cũ trên cùng
test mới; không mở nhiều công thức rồi chọn theo điểm test.

## Dữ liệu được bổ sung theo vấn đề

- **58 câu nguồn mới**: 48 toán, 10 trắc nghiệm tiếng Việt. Ưu tiên phần trăm,
  quan hệ nhiều bước và các câu có phủ định khi nguồn còn mẫu phù hợp.
- Sau màn lọc đầu vào, hai câu mới cần cách ly: một câu phụ thuộc thời điểm nhưng
  không ghi mốc thời gian, một câu hỏi nước “giàu nhất” nhưng không nêu thước đo.
  Một câu DEV cũ bị hỏng nội dung scrape cũng được cách ly khỏi bản huấn luyện mới.
- **18 biến thể chỉ dùng TRAIN**, từ sáu câu TRAIN gốc về số âm/thứ tự phép tính:
  xoay vị trí các lựa chọn và đổi lại chữ cái gold tương ứng. Đáp án số được kiểm
  chứng bằng phép tính độc lập. Giữ nguyên nhóm của câu cha; không coi 18 câu là
  18 nhóm độc lập. Nhãn model đạt/không đạt vẫn phải lấy từ phản hồi thật.
- Bản DEV chuẩn bị có **373 dòng, 355 nhóm**, gồm dữ liệu cũ còn phù hợp, nguồn mới
  và các biến thể. Chưa có đủ phản hồi thật thì không train trên nhãn suy đoán.
- **110 câu kiểm tra mới được niêm phong trước collection**, gồm 100 toán và 10
  trắc nghiệm tiếng Việt. Không đưa vào optimizer, calibration hoặc chọn threshold.

Sau khi loại nhóm đã đo và các câu gần trùng bằng quy tắc TF-IDF đã ghi, nguồn Aya
còn 20 nhóm MCQ mới phù hợp màn lọc: 10 DEV và 10 test. Không nhân bản để lấp đủ
100 câu VI. Với 10 nhóm test VI, không thể chứng minh cổng regression 3% cũ.
Nhóm gần trùng là quy tắc bảo thủ theo văn bản, không phải chứng minh độc lập ngữ nghĩa.

VMLU đã có bản mirror local nhưng chưa đủ bằng chứng điều khoản dữ liệu để nhập vào
đợt thu này. Trang nguồn cũng còn để mục giấy phép dữ liệu là TBU; không coi giấy
phép code là sự xác nhận tự động cho bản mirror. Nguồn đối chiếu:
[repository VMLU chính thức](https://github.com/ZaloAI-Jaist/VMLU#licenses).

## Collection, ngân sách và quyết định thử lại

Job chính: `a2c21243-ebc6-47f0-a0e6-e50a14eba2cc`, 168 câu gồm 58 DEV và 110 test.
Trần request **0,15 USD**, tiếp tục chịu ngân sách user/project và quota provider.
Không trả phí trong tests/CI.

Lần thu đầu dừng ở 11 câu vì lỗi kết nối `DEPENDENCY_UNAVAILABLE`. Mã HTTP 503 là
mã ứng dụng quy đổi; `upstream_status=null`, không đủ bằng chứng OpenRouter trả 503.
Khoản **0,000190710 USD** của lần gọi chưa rõ vẫn giữ nguyên, cùng khoản OpenAI cũ
**0,0034292 USD**. Huy đã yêu cầu thử lại; receipt riêng ghi đúng call và việc giữ
dự phòng. Resume cùng job, cache và ngân sách; không mở quyền tự retry mọi lỗi unknown.

Collection biến thể chỉ bắt đầu sau job chính hoàn tất, dùng ngân sách tối đa
0,025 USD, và phải xác nhận tổng cam kết của cả hai đợt vẫn dưới 0,15 USD. Nếu phát
sinh lần gọi unknown mới, dừng để xử lý. Bản artifact đang phục vụ chưa bị thay thế.

## Bằng chứng và cách chạy

- `data/router-targeted-v1-20261027/error-analysis.json`: từng câu sai và phản hồi cache.
- `regression-confidence-diagnostics.json`: điểm và threshold của bốn regression.
- `fixed-training-recipe-v2.json`: công thức khóa trước khi xem điểm test mới.
- `train-variants/parent-arithmetic-proofs.json`: phép tính kiểm chứng sáu câu cha.
- `collection/explicit-retry-authorization.json`: phạm vi thử lại theo yêu cầu Huy.
- `scripts/train_router_targeted.py`: chỉ train sau khi thu đủ, dùng DEV và nhãn thật.
- `scripts/evaluate_router_targeted.py`: xác minh hash, tách nhóm rồi replay trên test mới.

## Kết quả hoàn tất sau khi thử lại

Đã thu đủ **168/168 câu nguồn** và **18/18 biến thể TRAIN**, tổng cộng 558 lượt
provider hoàn tất và một lượt cũ chưa đối soát được. Chi phí catalog đã biết
**0,015069 USD**, khoản dự phòng của đợt này **0,000190710 USD**; tổng cam kết
**0,015259710 USD**, dưới trần 0,15 USD. Khoản OpenAI cũ 0,0034292 USD vẫn giữ riêng.
Không có lỗi unknown mới sau lần thử lại được Huy cho phép.

18 biến thể: GPT OSS 120B đạt 18/18, GPT OSS 20B đạt 18/18, Luna đạt 16/18.
Hai lỗi Luna xuất hiện ở biến thể của câu cha từng đạt. Đổi thứ tự đáp án và
dao động ngẫu nhiên của provider đều có thể góp phần; không kết luận quan hệ nhân quả.

Đã train hai artifact mới offline, mạng bị chặn, **373 dòng / 355 nhóm DEV**:
229 TRAIN (gồm 18 biến thể cùng nhóm cha), 71 calibration, 73 threshold. Ba câu
đầu vào có vấn đề được cách ly. Dùng 5 epoch Attention, 100 cây và encoder cũ;
không dùng test để đổi công thức. Hash hai artifact đã khóa trước khi mở điểm test.

Kết quả trên **cùng 110 câu test mới**, không so trực tiếp với điểm 177/200 cũ:

| Bản | Toán | MCQ tiếng Việt | Tổng | Regression so reference |
|---|---:|---:|---:|---:|
| Reference cố định | 93/100 | 5/10 | 98/110 | — |
| ML + Attention đang chạy | 93/100 | 6/10 | **99/110** | 1 |
| ML mới không Attention | 94/100 | 5/10 | **99/110** | 1 |
| ML + Attention mới | 90/100 | 5/10 | **95/110** | 3 |

Attention mới giảm khoảng **25,5% chi phí provider quan sát** so với Attention cũ
nhưng mất bốn câu đúng trong tổng số 110. Khoảng tin cậy bootstrap 95% của chênh
lệch chất lượng là khoảng −8,18 đến +0,91 điểm phần trăm; không khẳng định ý nghĩa
thống kê. Không đánh đổi chất lượng bằng cách coi tiết kiệm này là đã đạt yêu cầu.

**Quyết định: không thay artifact đang phục vụ.** Bản mới giữ riêng để nghiên cứu,
không promote hoặc cấp receipt dùng thử tự động. Tập VI mới chỉ có 10 nhóm nên
chưa đủ bằng chứng chứng nhận cổng 3%; kết quả năm câu sai cần audit nguồn riêng,
không sửa test rồi báo lại điểm của cùng bản như kiểm định độc lập.

Đã sửa và kiểm thử lỗi xác minh hash trên Windows: training khóa hash của JSON text
chuẩn LF, file text có thể ghi CRLF. Evaluation nay dùng cùng protocol text hash,
vẫn từ chối artifact bị sửa nội dung trước khi đọc test. Không thay artifact hoặc
hash đã khóa để bỏ qua kiểm tra. Bộ kiểm thử liên quan: **51 kiểm thử phân biệt đạt**;
Ruff và `git diff --check` đạt. Không có API trả phí trong kiểm thử.

Bằng chứng cuối:

- `output/project-audit/router-targeted-fresh-evaluation-20261027.json`.
- `data/router-targeted-v1-20261027/cost-and-completion-audit.json`.
- `data/router-targeted-v1-20261027/trained/frozen.json`, `dev-comparison.json`.
- `data/router-targeted-v1-20261027/train-variants/measured-option-rotation-diagnostics.json`.

## Hướng sửa tiếp theo dựa trên bằng chứng

Không tiếp tục tăng epoch hoặc nới threshold theo 110 câu đã xem. Bản thử nghiệm
kế tiếp cần đo trên DEV: độ bão hòa và biến thiên của sáu đầu ra, chênh phân phối
đặc trưng giữa các fold OOF và head final, calibration riêng cho ứng viên theo
nhóm toán. Các head OOF huấn luyện độc lập có thể không cùng ý nghĩa sáu trục;
đây là giả thuyết kiến trúc cần đo, chưa phải nguyên nhân đã chứng minh.

Cần nguồn VI mới có đề đầy đủ, đáp án duy nhất và provenance/điều khoản rõ ràng
để có thêm nhóm độc lập. Biến thể lựa chọn chỉ giúp TRAIN và kiểm tra độ ổn định,
không thể thay thế các nhóm test độc lập. Sau khi thay công thức phải dùng test mới
khác 110 câu của báo cáo này. Phạm vi chat mở, code, memory và RAG vẫn chưa được
chứng nhận bằng đợt bổ sung toán/MCQ này.
