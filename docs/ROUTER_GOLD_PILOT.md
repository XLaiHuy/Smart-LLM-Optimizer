# Pilot huấn luyện router bằng nhãn thực tế

Ngày kiểm tra: 22/10/2026. Giữ encoder ONNX INT8 cố định; học sáu query Attention và đầu ML. Artifact mới chỉ được đưa vào Router Lab khi đạt điều kiện đánh giá; không thay router chat production.

## Kết quả chạy thực tế

Campaign `gemini-gold-pilot-v1`, job `60a8f9b9-0490-4134-8258-dfe9e9bac6b8`:

- Đã tải và kiểm tra hash nguồn public; pool pilot có 480 prompt gốc, còn tối đa 20 prompt sinh thêm.
- Metadata API liệt kê cả Flash-Lite, Flash, Pro. Lượt generation đầu tiên (Pro, bước bổ sung toán tiếng Việt) bị từ chối: `MODEL_ACCESS_REQUIRED`. Metadata không chứng minh có quyền generation.
- Hoàn thành **0 prompt**, **chưa train**, **chưa import**. Kết luận: `INSUFFICIENT_EVIDENCE`.
- Có 1 dispatch chưa nhận usage. Chi phí đã biết là 0 USD; **chi phí thực tế chưa xác định**. Ledger giữ nguyên reservation **0.04178125 USD**, còn **4.95821875 USD** trong trần 5 USD. Đây là dự phòng, không phải hóa đơn xác nhận.
- Không retry, không thay model, không thay key hoặc tự tăng ngân sách. Báo cáo local: `output/router-pilot/latest.json`; checkpoint nằm trong `data/router-training/<job-id>/`.
- Đã sửa prompt MBPP để cung cấp tên hàm cần triển khai, không đưa hidden tests/expected answers vào prompt. Pool của job được sửa trước khi có bất kỳ observation nào, giữ nguyên group/split và ngân sách. Bản trước sửa và receipt nằm trong `corpus.before-callable-hints.json`, `corpus-repair.json`.

Cần kiểm tra quyền generation của ba model trong dự án Google dùng key hiện tại và đối soát reservation trước khi chạy tiếp. Không coi lỗi này là bằng chứng key hết tiền, sai key hay model đã ngừng hoạt động: log hiện tại chưa phân biệt được các khả năng đó. Không xóa ledger/cache/dispatch marker để vượt lỗi.

## Nguồn và quyền sử dụng

| Nguồn | Pool đã tải | Điều khoản trong dataset card của nhà phát hành | Sử dụng |
|---|---:|---|---|
| [GSM8K](https://huggingface.co/datasets/openai/gsm8k) | 7.473 bài TRAIN | MIT | Toán, gold sau `####` |
| [MBPP](https://huggingface.co/datasets/google-research-datasets/mbpp) | 374 bài TRAIN | CC BY 4.0 | Code, hidden tests + setup |
| [Aya](https://huggingface.co/datasets/CohereLabs/aya_dataset) | 8.676 dòng tiếng Việt TRAIN | Apache 2.0 | Instruction mở; target tham chiếu, qualification do teacher/human chấm |

`data/router-pilot-v1/sources.json` ghi revision 40 ký tự, SHA256 raw, số dòng, license. `manifest.json` ghi hash JSON chuyển đổi, link card ghim revision, eligibility đã review, cấu hình và giá. Giữ attribution và điều khoản khi phân phối lại dữ liệu/artifact.

VMLU có adapter MCQ; ViQuAD có adapter đọc hiểu/no-answer. **Chưa đưa hai nguồn vào campaign này**: license của repository code không tự chứng minh điều khoản của dataset; cần xác nhận quyền dữ liệu gốc. Pool hiện tại cũng chưa đủ để kết luận về luật, y khoa hoặc toàn bộ tác vụ tiếng Việt.

Nhóm tài liệu/bài gốc được chia trước mọi biến thể. Hash group hướng tới tỷ lệ **50/20/15/15**; số thực tế của 480 bài là train 239, calibration 94, threshold 84, HOLDOUT 63. Tỷ lệ là xấp xỉ theo group, không ép cắt nhóm. Mẫu bổ sung chỉ vào TRAIN, giữ group của bài cha, tối đa 20% TRAIN cả khi dừng ở một prefix; tối đa 500 prompt tổng cộng. HOLDOUT dùng original public targets/human-verified targets. Public TRAIN được chia thành DEV/HOLDOUT riêng cho pilot; đây không phải claim benchmark chính thức hoặc bảo đảm không xuất hiện trong pretraining của provider.

Gold, hidden tests và grading spec không đi vào encoder/router hoặc candidate prompt. MBPP chỉ cung cấp tên callable như một interface. Reference Pro cũng được chấm đúng/sai; không hardcode qualified=True.

## Quy trình

1. Đọc nguồn local đã ghim hash, kiểm tra điều khoản, encoder/Torch, Docker/image ID bất biến và catalog/access metadata trước dispatch. Không tự đổi model.
2. Nếu bật bổ sung: Gemini chỉ đề xuất biểu thức; AST allowlist và phép tính độc lập xác nhận đáp án. JSON đúng cấu trúc chưa đủ để có nhãn. Các mẫu toán tiếng Việt này bổ sung phần ngôn ngữ còn thiếu; không tạo gold luật/y khoa bằng teacher.
3. Mỗi prompt chạy đủ ba cấu hình. Cache output/usage/cost/latency sau từng call. Sau khi đủ output và nhãn, checkpoint một observation row; mỗi đợt 25 prompt. Output đã hoàn thành được tái sử dụng khi resume, kể cả khi prompt trước đó mới chạy được một phần ba model.
4. Tác vụ mở dùng Pro judge ba output ẩn danh, đảo thứ tự có seed rồi ánh xạ lại đúng model; ngưỡng rubric 80. Queue kiểm tra thủ công khoảng 10%, ít nhất một tác vụ mở mỗi split và các critical cases. Chưa review DEV thì chưa fit; chưa review HOLDOUT thì khóa artifact rồi dừng trước evaluation.
5. Train ML không Attention và ML + Attention trên cùng DEV. TRAIN dùng grouped OOF; calibration và threshold có vai trò riêng. Không đọc HOLDOUT để chọn hyperparameter/ngưỡng.
6. Attention: BCE qualification của hai model thay thế reference, domain loss mặc định 0, seed 42, batch 64, 15 epochs. Sáu query không phải sáu nhãn domain bắt buộc. GBDT 100 cây, depth 3. Thiếu cả hai loại nhãn/nhóm độc lập ở TRAIN/calibration thì trả `INSUFFICIENT_EVIDENCE`; không chế nhãn để trainer chạy.
7. Ngưỡng chọn trên threshold split: chất lượng trước, rồi USD và latency. Routing dùng feasibility hiện tại, chọn cấu hình rẻ nhất vượt ngưỡng; nếu không có thì về reference khả thi. Reference vẫn có thể trả lời sai.
8. Lưu và hash cả hai artifact cùng DEV trước HOLDOUT. Sau freeze không thu thêm DEV; sau evaluation không đổi nhãn hoặc chạy lại HOLDOUT để tìm kết quả tốt hơn. Báo cáo point estimates, từng domain, regression, model selection, cost, latency cộng cold-cache routing overhead và paired group bootstrap. Không coi `PASS_OBSERVED` là chứng minh non-inferiority hoặc Attention tốt hơn; so với baseline thực tế và đọc uncertainty.

Nếu chạm budget trong collection, chỉ các row hoàn tất đủ ba output mới được train. Những output chưa đủ vẫn có cache/accounting. Đủ dữ liệu và review thì pha `full` dùng phần hoàn tất để train; thiếu thì báo phần thiếu. Pha `collect` luôn dừng trước fit. Mỗi lượt chạy chỉ thu số đợt đã yêu cầu (UI: 1, CLI mặc định: 2); chạy tiếp dùng cùng operation và ngân sách gốc. Muốn thu thêm DEV phải làm trước freeze.

## Bộ chấm phiên bản v1

- MCQ: chữ cái cuối cùng, thuộc options; không chấp nhận JSON/prose mơ hồ thay đáp án.
- Toán: số/fraction cuối cùng, tolerance tuyệt đối/tương đối cấu hình; từ chối đơn vị, thiếu đáp án, NaN/Inf và số ngoài giới hạn xử lý.
- ViQuAD: JSON `{"answer":"span"}` hoặc `{"answer":null}`; EM quyết định qualified, F1 báo cáo thêm, no-answer kiểm tra riêng. Chuẩn hóa giữ dấu tiếng Việt và chữ `a`; đây là protocol thích nghi được ghi phiên bản, không tự nhận tương đương scorer chính thức.
- Code: chỉ chạy trong Docker image ID ghim, không mạng, filesystem chỉ đọc, bỏ capability, user không root, giới hạn PID/RAM/CPU/output/timeout. Không thực thi code candidate trên host. Tests cùng interpreter chưa phải bảo đảm chống mọi hành vi gian lận; không dùng pilot này làm sandbox công cộng đa tenant.
- Open: `teacher_judged`, không tự đổi thành `dataset_gold`. Human review gắn response hash, actor, lý do và thời điểm. Các nguồn nhãn hỗ trợ: `dataset_gold`, `human_verified`, `teacher_judged`, `synthetic_verified`; observation ghi grader version và metrics.

## Ngân sách và chạy tiếp

Trần operation tối đa **5 USD**, gồm bổ sung, candidate và judge. Mỗi call reserve upper bound trước dispatch; unknown vẫn giữ dự phòng. Giá Standard text <=200k được ghi trong manifest: Lite 0.10/0.40, Flash 0.30/2.50, Pro 1.25/10.00 USD mỗi triệu input/output tokens. Output tính phí lấy từ `total_tokens - prompt_tokens`, không chỉ số token câu trả lời nhìn thấy; thiếu/không nhất quán usage thì giữ unresolved. Nếu provider báo vượt reservation, settle số thực tế rồi dừng. Nguồn: [Google pricing](https://ai.google.dev/gemini-api/docs/pricing), [thinking và usage](https://ai.google.dev/gemini-api/docs/thinking). Đây là catalog estimate; cần đối soát usage/billing thực tế.

Campaign version dùng một operation ID xuyên admin/client request/batch/resume. Gửi client ID mới không đặt lại ngân sách. Không sửa version chỉ để né cap. Không có auto retry với dispatch thiếu cache hoàn tất; kể cả khi đã settle usage nhưng output bị cắt, cần review thủ công. Các reservation unresolved được đối soát bằng API admin billing hiện có, dựa trên bằng chứng thực tế, không tự ghi 0.

Chuẩn bị trên máy có Docker và dependency optional `router_ml`, `router_data`:

```powershell
docker pull python:3.11-slim
.venv\Scripts\python.exe scripts/prepare_public_router_pilot.py --synthesize
# Chỉ chọn manifest sau khi review nguồn/catalog; giữ mock production.
# ROUTER_TRAINING_MANIFEST_PATH=data/router-pilot-v1/manifest.json
# Dùng tài khoản admin đã tồn tại, không tạo account tự động.
.venv\Scripts\python.exe scripts/run_router_pilot.py --owner admin --live --batches 2
# Resume campaign hiện có, vẫn dùng cap/count batch ban đầu:
.venv\Scripts\python.exe scripts/run_router_pilot.py --owner admin --resume JOB_ID --phase collect
.venv\Scripts\python.exe scripts/run_router_pilot.py --owner admin --resume JOB_ID --phase train
```

Các lệnh resume ở trên **không giải quyết quyền truy cập hoặc dispatch unknown**. Campaign hiện tại vẫn cần xử lý hai việc đó trước. Bỏ `--live` chỉ đọc cache; không chuyển một campaign live sang cache bằng cách tạo ID mới.

Trong Router Lab, chọn **Chỉ thu thập và chấm** hoặc **Thu thập rồi huấn luyện**; mỗi lần UI thu tối đa 25 prompt. Xem budget/report, hoàn tất các thẻ review, dùng **Train từ các mẫu đã hoàn thành** hoặc **Tiếp tục cùng pilot** trước freeze. Cache là mặc định cho campaign mới. Job có dispatch chưa rõ kết quả không tự chạy lại.

API admin theo owner:

- `POST /v1/research/training/jobs`: phase, collection_batches, budget_usd; pilot chặn >5 USD.
- `POST /v1/research/training/jobs/{id}/resume`: cùng ID, body `{"phase":"collect"}` hoặc `{"phase":"train"}`.
- `GET /v1/research/training/jobs/{id}/reviews`: task, reference, anonymous answers và response hashes.
- `POST /v1/research/training/jobs/{id}/reviews`: `items` gồm task_id, config_id, response_sha256, qualified và reason. Không auto xác nhận các lựa chọn do teacher gợi ý.

Gates production không đổi. Chỉ import vào Lab khi HOLDOUT đủ review, quality/latency guardrails quan sát đạt và Attention không bị baseline thống trị. Baseline tương đương không chứng minh Attention có ích. Độ trễ báo cáo chưa gồm HTTP/DB của serving; không quảng cáo end-to-end production savings.

## Kiểm chứng phần mềm

Test không gọi paid API. Có test grader đúng/sai/thiếu/sai định dạng/biên; arithmetic allowlist; Docker flags/timeout/output limit; chống rò rỉ; cache/resume/cap qua nhiều batch; unknown không retry; owner/hash review; cùng DEV cho hai variant; freeze trước HOLDOUT và khóa sau evaluation. Docker smoke thực tế đã xác nhận code đúng/sai, ghi file bị chặn, network bị chặn. Phần mềm chạy đúng không phải bằng chứng chất lượng router; cần hoàn tất pilot bằng output thật sau khi sửa quyền truy cập.
