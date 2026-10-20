# Contributing

Mọi người dùng feature branch và database/run directory riêng. Chỉ tách nhánh thuật toán sau foundation G0 handoff; Huy tích hợp contracts, migrations, wiring, locks và generated TypeScript. Tân/Khoa review các consumers bị ảnh hưởng.

Mỗi PR nêu problem/behavior, module/files, contract/schema changes, commands đã chạy và limitations. Giữ PR nhỏ, cập nhật main trước review; không reformat hoặc reorganize module người khác. Đổi contract phải cập nhật producer, consumer, tests và generated artifacts trong cùng PR. Không merge signature mới làm main hỏng rồi chờ consumer sau.

Python: typed functions, frozen DTOs với nested immutable values, Ruff format/import order, mypy strict trong app. TypeScript strict, ESLint/Prettier, generated API types. Tên code tiếng Anh; UI strings qua VI/EN translations. Comments giải thích invariants, không kể lại code. Chỉ thêm abstraction/dependency khi có consumer/use case thực.

Test hành vi có rủi ro: isolation, history, dedupe, ledger, flags/provenance và UI flows; không test getter hoặc cấu trúc JSX tĩnh. Mọi CI/unit test mặc định offline/mock, không yêu cầu API key. Không tune trên holdout. Dữ liệu nghiên cứu phải qualification theo spec trước live runs.

Không commit `.env`, key/token, DB, private histories, node_modules hoặc generated runtime reports. Không dùng GitHub handles giả trong CODEOWNERS; bổ sung khi nhóm đã xác nhận identifiers. Revert/policy-disable để rollback; explicit purge/retention áp dụng cho raw data, không dùng Git để backup private DB.
