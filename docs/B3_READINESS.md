# B3 — hồ sơ bằng chứng nguồn mở

Đối chiếu ảnh tiêu chí do nhóm cung cấp, không tự nhận đạt 5/5 hoặc PoF ≤60. Các nhận xét dưới đây là trạng thái kiểm tra, không thay kết luận của giám khảo.

| Tiêu chí | Bằng chứng trong repo | Còn phải xác minh |
|---|---|---|
| Mã nguồn/phần mềm trên Internet | Remote [GitHub](https://github.com/XLaiHuy/Smart-LLM-Optimizer), README cài từ nguồn | Repo thực sự public, commit bàn giao đã push và clone sạch chạy được |
| Giấy phép mở và đúng đề | MIT ở LICENSE; spec mô tả tối ưu LLM | Giấy phép code không cấp lại quyền đối với logo, dữ liệu hay model API |
| PoF ≤60 | Bảng kiểm dưới đây | Chấm từng mục theo hướng dẫn giám khảo; chưa đủ bằng chứng tính tổng |
| Công cụ phát triển mở | Git, Python/FastAPI, Next.js, SQLite; lockfiles | Kiểm tra các công cụ bắt buộc trong bản phát hành |
| Tương thích giấy phép | [Kiểm kê dependency](THIRD_PARTY_INVENTORY.json), [assets](ASSETS.md) | Metadata không phải xác nhận tương thích; review obligations của từng thành phần khi phân phối |
| Hướng dẫn cài/build | README Windows/POSIX, .env.example, scripts | Clean install trên môi trường bàn giao; không dựa vào DB/key của người phát triển |
| Kênh giao tiếp công khai | Footer liên kết GitHub Issues, CONTRIBUTING | Kiểm tra Issues đang bật và khách chưa đăng nhập đọc được |

## PoF là gì?

[Hướng dẫn VFOSSA](https://vfossa.vn/thu-vien-sach/danh-gia-kha-nang-phat-trien-cua-mot-du-an-phan-mem-tu-do-nguon-mo-69.html) gọi PoF là Points of FAIL: điểm phạt cộng dồn cho các điểm yếu của một dự án nguồn mở. Điểm thấp hơn tốt hơn; không phải phần trăm bug, coverage hay chỉ số tốc độ của router.

[Bảng chấm VFOSSA năm 2023](https://vfossa.vn/hoat-dong-cong-dong/the-le-khoi-thi-phan-mem-nguon-mo-olympic-tin-hoc-sinh-vien-viet-nam-2023-678.html) có mốc ≤60 tương ứng ảnh. Chưa xác nhận đây là thể lệ hiện hành của trường. Bảng PoF gốc có những tiêu chí thiên về phần mềm biên dịch/Linux; giữ nguyên nguồn, ghi rõ cách áp dụng hoặc mục chờ giám khảo xác nhận, không tự loại để giảm điểm.

| Nhóm PoF | Bằng chứng / việc cần làm | Trạng thái điểm |
|---|---|---|
| Kích thước nguồn | Đo gói nguồn của release, loại dependency cài đặt/build output theo phạm vi công bố | Chờ đo |
| Quản lý mã nguồn | Git, web viewer, CONTRIBUTING, lịch sử đóng góp | Cần xác minh public và commit release |
| Build/cấu hình/cài đặt | npm, pip/venv, env mẫu, README; không cần sửa source để chạy mock | Cần chạy clean setup; cách áp dụng tiêu chí make/header chờ xác nhận |
| Bundling/thư viện | Dependency locks, không đóng gói node_modules/venv/DB/key | Review gói phát hành và metadata |
| Đặc điểm mã nguồn | .gitattributes LF; không yêu cầu Visual Studio để chạy | Kiểm tra gói thực tế; không suy từ editor đang dùng |
| Giao tiếp | GitHub repo/Issues và tài liệu; chưa xác minh mailing list/website riêng | Chờ xác minh cách công nhận kênh GitHub |
| Phát hành | Changelog/checklist; chưa tạo release trong đợt này | Chờ release có phiên bản |
| Lịch sử | Ghi nhận mã được tham khảo/tái sử dụng và đóng góp nhóm | Cần nhóm review |
| Giấy phép | LICENSE MIT, assets và inventory | Chưa review đầy đủ thông báo từng file/giấy phép phụ thuộc |
| Tài liệu | README, docs, changelog, nghiên cứu công khai trong ứng dụng | Cần xác minh tài liệu truy cập công khai |

## Kiểm kê và phát hành

Từ repo root, sau cài dependencies: `.\.venv\Scripts\python.exe scripts/license_inventory.py` (POSIX: `.venv/bin/python scripts/license_inventory.py`). Script đọc metadata dependency đã khóa phiên bản, không tải mạng và không tự kết luận pháp lý. Thiếu/khác metadata phải review riêng. Logo OU do người dùng cung cấp: nguồn đã biết, quyền phân phối ngoài phạm vi học tập chưa được xác minh. Font giữ license riêng. Dữ liệu benchmark giữ provenance/giấy phép theo từng nguồn; không mặc định thuộc MIT. API model là dịch vụ ngoài, không gọi model/weights là mã nguồn mở của dự án.

Checklist trước phát hành:

- [ ] Chọn commit được chấp nhận theo feature → develop → main; không chứa secrets, history, DB hay dữ liệu không được phép phân phối.
- [ ] Kiểm tra public repo/Issues không đăng nhập, quyền assets/datasets và notices dependency.
- [ ] Clone sạch, cài dependencies theo locks, migrate DB mới, tạo account và chạy mock/build theo README.
- [ ] Chốt số phiên bản, changelog và tạo gói nguồn có thư mục tên dự án–phiên bản; chuẩn bị ZIP và tar.gz.
- [ ] Ghi ma trận PoF từng mục với bằng chứng và xác nhận cách chấm; chưa rõ thì để unknown.
- [ ] Chỉ publish release sau khi nhóm duyệt; đợt sửa UI không tự push/publish.
