# Asset provenance

- `oulogo/OUlogo.jfif`: logo OU do người dùng cung cấp. `frontend/public/brand/ou-logo.jpg` là bản copy nguyên byte, không đổi màu/tỷ lệ hoặc vẽ lại. Logo không được cấp lại MIT theo code của dự án.
- Xanh OU `#034EA2`, xanh phụ `#387EC1`, họ Roboto tham khảo [cẩm nang OU công khai, bản 28/12/2018](https://ou.edu.vn/wp-content/uploads/2018/08/HCMCOU-BrandBook.pdf). Trọng lượng 900/300 cho tên trường trong cẩm nang; body UI dùng 400/500/700 theo nhu cầu đọc trên màn hình. Không trình bày app như một dịch vụ chính thức của trường.
- Roboto phục vụ local qua `@fontsource/roboto`, gồm subset tiếng Việt. [License đi kèm fonts](../frontend/public/brand/ROBOTO_LICENSE.txt) được copy nguyên bản từ package; không cần runtime font network request. [Fontsource Roboto](https://fontsource.org/fonts/roboto/use).
- Icons từ Lucide, Radix primitives cho dialogs/switches; giữ licenses trong installed packages/lockfile. Không có ảnh hoặc logo AI-generated.
