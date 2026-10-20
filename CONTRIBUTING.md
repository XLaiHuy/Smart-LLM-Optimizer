# Contributing

Mọi người dùng feature branch và database/run directory riêng. Chỉ tách nhánh thuật toán sau foundation G0 handoff; Huy tích hợp contracts, migrations, wiring, locks và generated TypeScript. Tân/Khoa review các consumers bị ảnh hưởng.

Luồng nhánh: `feature/* → develop → main`. Tạo feature branch từ develop, cập nhật develop trước review và mở PR vào develop. Main giữ bản chốt để nộp; chỉ promote develop sang main khi nhóm xác nhận acceptance. Mỗi PR nêu problem/behavior, module/files, contract/schema changes, commands đã chạy và limitations. Không reformat hoặc reorganize module người khác. Đổi contract phải cập nhật producer, consumer, tests và generated artifacts trong cùng PR. Không merge signature mới làm develop hỏng rồi chờ consumer sau.

Python: typed functions, frozen DTOs với nested immutable values, Ruff format/import order, mypy strict trong app. TypeScript strict, ESLint/Prettier, generated API types. Tên code tiếng Anh; UI strings qua VI/EN translations. Comments giải thích invariants, không kể lại code. Chỉ thêm abstraction/dependency khi có consumer/use case thực.

Test hành vi có rủi ro: isolation, history, dedupe, ledger, flags/provenance và UI flows; không test getter hoặc cấu trúc JSX tĩnh. Mọi CI/unit test mặc định offline/mock, không yêu cầu API key. Không tune trên holdout. Dữ liệu nghiên cứu phải qualification theo spec trước live runs.

Huy sở hữu `routing/experiments` và Router Lab UI/API. Fixtures của Huy chỉ là kiểm tra chức năng; Khoa vẫn sở hữu scientific loaders/graders/reports trong evaluation/benchmark. DatasetSource, PredictionGrader và RoutingEvidenceSource là điểm ghép; gold/reference không đi vào router/provider. Không merge fixture profiles vào production evidence hoặc nhập mock thành live research.

Không commit `.env`, key/token, DB, private histories, node_modules hoặc generated runtime reports. Không dùng GitHub handles giả trong CODEOWNERS; bổ sung khi nhóm đã xác nhận identifiers. Revert/policy-disable để rollback; explicit purge/retention áp dụng cho raw data, không dùng Git để backup private DB.
