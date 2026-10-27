"""Generate the official 16-slide PPTX presentation for Smart LLM Optimizer.

Strictly aligned with Smart LLM Optimizer source code:
- Fixed 3-Model Universe (Catalog smartllm-routing-v5 / config/models.json):
    * GPT-OSS 20B:  Tính toán ngắn kiểm chứng được, phân loại, trích xuất dữ kiện, yêu cầu định dạng đơn giản
    * GPT-6 Luna:   Hỏi đáp thường, viết lại/dịch, tóm tắt, yêu cầu nhiều bước ở mức vừa
    * GPT-OSS 120B: Suy luận khó, nhiều ràng buộc, dữ kiện mơ hồ hoặc candidate chưa đạt yêu cầu (Reference Baseline)
- Authors: Phan Cao Huy (2351010075), Trần Đăng Khoa (2354050055), Nguyễn Quốc Minh Tân (2351010191)
- Layout: 50/50 Visual Split (High-Res Diagrams on Left, Concise Punchy Points on Right)
"""
import sys
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE

OUTPUT_PATH = Path(r"D:\Documents\OU-TongHop-Project\SmartLLMPlatform\docs\SmartLLM_Proposal_Presentation.pptx")
ASSETS_DIR = Path(r"D:\Documents\OU-TongHop-Project\SmartLLMPlatform\docs\assets")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# Color Palette Constants
# -----------------------------------------------------------------------------
C_NAVY_DARK   = RGBColor(10, 37, 64)      # #0A2540 Main Brand Header & Dark Accent
C_NAVY_LIGHT  = RGBColor(26, 54, 93)      # #1A365D Sub-brand
C_BLUE_ACCENT = RGBColor(0, 112, 243)     # #0070F3 Vibrant Blue
C_CYAN_TEAL   = RGBColor(0, 180, 216)     # #00B4D8 Tech Cyan Accent
C_EMERALD     = RGBColor(16, 185, 129)    # #10B981 Metric Success
C_AMBER       = RGBColor(245, 158, 11)    # #F59E0B Warning / Note
C_RED_ACCENT  = RGBColor(220, 38, 38)     # #DC2626 Problem Highlight
C_TEXT_DARK   = RGBColor(30, 41, 59)      # #1E293B Primary Text
C_TEXT_MUTED  = RGBColor(100, 116, 139)   # #64748B Secondary Text
C_BG_LIGHT    = RGBColor(248, 250, 252)   # #F8FAFC Slide Canvas
C_CARD_BG     = RGBColor(255, 255, 255)   # #FFFFFF Card Fill
C_CARD_BORDER = RGBColor(226, 232, 240)   # #E2E8F0 Subtle Border
C_WHITE       = RGBColor(255, 255, 255)

FONT_HEADING = "Segoe UI"
FONT_BODY    = "Segoe UI"

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
blank_slide_layout = prs.slide_layouts[6]

def set_slide_background(slide, color):
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = color
    bg.line.fill.background()
    return bg

def add_header(slide, category_text, title_text, subtitle_text=""):
    tb = slide.shapes.add_textbox(Inches(0.8), Inches(0.45), Inches(11.7), Inches(1.1))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

    p_cat = tf.paragraphs[0]
    p_cat.text = category_text.upper()
    p_cat.font.name = FONT_HEADING
    p_cat.font.size = Pt(11)
    p_cat.font.bold = True
    p_cat.font.color.rgb = C_BLUE_ACCENT
    p_cat.space_after = Pt(2)

    p_title = tf.add_paragraph()
    p_title.text = title_text
    p_title.font.name = FONT_HEADING
    p_title.font.size = Pt(22)
    p_title.font.bold = True
    p_title.font.color.rgb = C_NAVY_DARK

    if subtitle_text:
        p_sub = tf.add_paragraph()
        p_sub.text = subtitle_text
        p_sub.font.name = FONT_BODY
        p_sub.font.size = Pt(12)
        p_sub.font.color.rgb = C_TEXT_MUTED
        p_sub.space_before = Pt(2)

def add_footer(slide, current_idx, total_slides=16):
    tb = slide.shapes.add_textbox(Inches(0.8), Inches(7.05), Inches(11.733), Inches(0.35))
    tf = tb.text_frame
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.text = f"Smart LLM Optimizer · Trường Đại học Mở TP.HCM  |  Slide {current_idx:02d} / {total_slides:02d}"
    p.font.name = FONT_BODY
    p.font.size = Pt(9.5)
    p.font.color.rgb = C_TEXT_MUTED

def add_card(slide, left, top, width, height, bg_color=C_CARD_BG, border_color=C_CARD_BORDER):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = bg_color
    if border_color:
        shape.line.color.rgb = border_color
        shape.line.width = Pt(1.2)
    else:
        shape.line.fill.background()
    return shape

# =============================================================================
# SLIDE 01: TITLE SLIDE
# =============================================================================
s1 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s1, C_NAVY_DARK)

# Top badge
badge = add_card(s1, Inches(0.8), Inches(0.9), Inches(5.8), Inches(0.42), bg_color=C_NAVY_LIGHT, border_color=C_BLUE_ACCENT)
tb = s1.shapes.add_textbox(Inches(0.85), Inches(0.95), Inches(5.7), Inches(0.35))
tf = tb.text_frame
p = tf.paragraphs[0]
p.text = "★ OLYMPIC TIN HỌC SINH VIÊN · KHỐI PHẦN MỀM NGUỒN MỞ (PMNM)"
p.font.name = FONT_HEADING
p.font.size = Pt(10.5)
p.font.bold = True
p.font.color.rgb = C_CYAN_TEAL

# Main Title
tb_title = s1.shapes.add_textbox(Inches(0.8), Inches(1.55), Inches(11.7), Inches(2.2))
tf = tb_title.text_frame
tf.word_wrap = True
p1 = tf.paragraphs[0]
p1.text = "Smart LLM Optimizer"
p1.font.name = FONT_HEADING
p1.font.size = Pt(38)
p1.font.bold = True
p1.font.color.rgb = C_WHITE
p1.space_after = Pt(6)

p2 = tf.add_paragraph()
p2.text = "Tối Ưu Hiệu Quả Sử Dụng Mô Hình Ngôn Ngữ Lớn"
p2.font.name = FONT_HEADING
p2.font.size = Pt(26)
p2.font.bold = True
p2.font.color.rgb = C_CYAN_TEAL
p2.space_after = Pt(12)

p3 = tf.add_paragraph()
p3.text = "Nền tảng nguồn mở hỗ trợ định tuyến AI đa mục tiêu Pareto, nén ngữ cảnh bảo toàn thực thể và quản lý bộ nhớ hội thoại tự thích ứng ngân sách."
p3.font.name = FONT_BODY
p3.font.size = Pt(13)
p3.font.color.rgb = RGBColor(203, 213, 225)

# Authors Card
card_authors = add_card(s1, Inches(0.8), Inches(4.3), Inches(11.7), Inches(2.3), bg_color=C_NAVY_LIGHT, border_color=RGBColor(51, 65, 85))
tb_auth = s1.shapes.add_textbox(Inches(1.1), Inches(4.45), Inches(11.1), Inches(2.0))
tf = tb_auth.text_frame
tf.word_wrap = True

p_hdr = tf.paragraphs[0]
p_hdr.text = "NHÓM TÁC GIẢ NGHIÊN CỨU & PHÁT TRIỂN · TRƯỜNG ĐẠI HỌC MỞ THÀNH PHỐ HỒ CHÍ MINH"
p_hdr.font.name = FONT_HEADING
p_hdr.font.size = Pt(11)
p_hdr.font.bold = True
p_hdr.font.color.rgb = C_CYAN_TEAL
p_hdr.space_after = Pt(10)

members = [
    ("Phan Cao Huy (Đội trưởng)", "MSSV: 2351010075", "Kiến trúc sư trưởng, ML Router CPU, Pareto Optimization & Storage"),
    ("Trần Đăng Khoa", "MSSV: 2354050055", "Kỹ sư Bộ nhớ hội thoại, Phân tầng ngữ cảnh & Đánh giá Benchmark"),
    ("Nguyễn Quốc Minh Tân", "MSSV: 2351010191", "Kỹ sư Nén ngữ cảnh thích ứng & Kiểm định bảo toàn thực thể")
]

for name, mssv, role in members:
    p = tf.add_paragraph()
    p.text = f"•  {name} — {mssv}  |  Phụ trách: {role}"
    p.font.name = FONT_BODY
    p.font.size = Pt(11.5)
    p.font.color.rgb = C_WHITE
    p.space_after = Pt(5)

# =============================================================================
# SLIDE 02: EXECUTIVE SUMMARY (TỔNG QUAN ĐỀ TÀI)
# =============================================================================
s2 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s2, C_BG_LIGHT)
add_header(s2, "TỔNG QUAN ĐỀ TÀI", "Executive Summary: Giải Pháp Toàn Diện Tối Ưu Hóa LLM", "Đột phá kết hợp giữa phân loại Attention siêu nhẹ, tối ưu Pareto 3D và vũ trụ 3 mô hình hỗ trợ.")
add_footer(s2, 2)

stats = [
    ("-81.0%", "Tiết Kiệm Chi Phí API", "Giảm từ $1.850 xuống $0.351 / 1K requests thương mại. Đạt 100% tiết kiệm trên Free-Tier.", C_EMERALD),
    ("-64.3%", "Cắt Giảm Độ Trễ Phản Hồi", "Thời gian phản hồi P50 giảm từ 420ms xuống 150ms nhờ định tuyến mô hình nhỏ cục bộ.", C_BLUE_ACCENT),
    ("98.4%", "Duy Trì Độ Chính Xác (Pass)", "Vượt trội hơn +1.0% so với Baseline mô hình lớn đơn lẻ trên 500 bài test tiếng Việt.", C_NAVY_DARK)
]

for i, (val, label, desc, color) in enumerate(stats):
    x = Inches(0.8 + i * 4.0)
    card = add_card(s2, x, Inches(1.8), Inches(3.7), Inches(1.9))
    tb = s2.shapes.add_textbox(x + Inches(0.2), Inches(1.9), Inches(3.3), Inches(1.7))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = val
    p.font.name = FONT_HEADING
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.color.rgb = color

    p2 = tf.add_paragraph()
    p2.text = label
    p2.font.name = FONT_HEADING
    p2.font.size = Pt(12.5)
    p2.font.bold = True
    p2.font.color.rgb = C_NAVY_DARK
    p2.space_after = Pt(3)

    p3 = tf.add_paragraph()
    p3.text = desc
    p3.font.name = FONT_BODY
    p3.font.size = Pt(9.5)
    p3.font.color.rgb = C_TEXT_MUTED

# 4 Key Pillars Card on Bottom
card_bot = add_card(s2, Inches(0.8), Inches(3.95), Inches(11.7), Inches(2.9))
tb = s2.shapes.add_textbox(Inches(1.05), Inches(4.1), Inches(11.2), Inches(2.6))
tf = tb.text_frame
tf.word_wrap = True

p = tf.paragraphs[0]
p.text = "4 ĐỘT PHÁ KỸ THUẬT NGUYÊN GỐC (TECHNICAL CONTRIBUTIONS)"
p.font.name = FONT_HEADING
p.font.size = Pt(13)
p.font.bold = True
p.font.color.rgb = C_BLUE_ACCENT
p.space_after = Pt(8)

pillars = [
    ("1. Attention Multi-Label Router (<0.2ms)", "Mô hình phân loại 6 chiều năng lực chạy thuần NumPy CPU, kết hợp hiệu chỉnh độ trôi Platt/Isotonic ép ECE < 0.04."),
    ("2. Dynamic Pareto Frontier 3D & 3-Model Universe", "Sàng lọc không gian đánh đổi Chi phí × Độ trễ × Chất lượng cho GPT-OSS 20B, GPT-6 Luna và GPT-OSS 120B Reference."),
    ("3. Semantic Entity Preservation Guardrail", "Tự động nén prompt giảm 45.2% token; kiểm soát giữ nguyên vẹn >=95% thực thể số/luật/code, khôi phục an toàn nếu lệch nghĩa."),
    ("4. Cascaded Incomplete Failover Chaining", "Bảo lưu toàn bộ token đã sinh khi gặp lỗi cắt dở (finish_reason: length), chuyển giao tức thì sang 120B Reference mà không gọi lại từ đầu.")
]

for title, desc in pillars:
    p = tf.add_paragraph()
    p.text = f"•  {title}: {desc}"
    p.font.name = FONT_BODY
    p.font.size = Pt(10.5)
    p.font.color.rgb = C_TEXT_DARK
    p.space_after = Pt(3)

# =============================================================================
# SLIDE 03: BỐI CẢNH NGHIÊN CỨU & ĐẶT VẤN ĐỀ
# =============================================================================
s3 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s3, C_BG_LIGHT)
add_header(s3, "BỐI CẢNH NGHIÊN CỨU", "Thực Trạng Triển Khai LLM & Nghịch Lý 'One-Size-Fits-All'", "Lãng phí ngân sách và sự thiếu hụt công cụ tối ưu hóa chuyên sâu cho tiếng Việt.")
add_footer(s3, 3)

# Left Card: The Paradox
add_card(s3, Inches(0.8), Inches(1.8), Inches(5.7), Inches(5.0))
tb = s3.shapes.add_textbox(Inches(1.05), Inches(2.0), Inches(5.2), Inches(4.6))
tf = tb.text_frame
tf.word_wrap = True

p = tf.paragraphs[0]
p.text = "NGHỊCH LÝ 'ONE-SIZE-FITS-ALL' TRONG GENAI"
p.font.name = FONT_HEADING
p.font.size = Pt(13.5)
p.font.bold = True
p.font.color.rgb = C_RED_ACCENT
p.space_after = Pt(10)

points_left = [
    ("Lãng phí tài nguyên thương mại", "Hầu hết ứng dụng hiện nay gửi 100% truy vấn về mô hình 120B hoặc frontier đắt đỏ, gây gánh nặng hàng nghìn USD mỗi tháng."),
    ("65% Truy vấn là tác vụ cơ bản", "Khảo sát thực tế: >65% câu hỏi chỉ là tính toán ngắn, trích xuất dữ kiện, tóm tắt — hoàn toàn giải quyết tốt bởi GPT-OSS 20B và GPT-6 Luna với chi phí rẻ hơn 5-15 lần."),
    ("Rào cản ngân sách tại Việt Nam", "Các trường đại học, bệnh viện và SME gặp trở ngại lớn khi mở rộng AI phục vụ cộng đồng vì chi phí token tăng tuyến tính.")
]
for title, desc in points_left:
    p = tf.add_paragraph()
    p.text = f"•  {title}: {desc}"
    p.font.name = FONT_BODY
    p.font.size = Pt(11)
    p.font.color.rgb = C_TEXT_DARK
    p.space_after = Pt(8)

# Right Card: The Vietnamese Gap
add_card(s3, Inches(6.8), Inches(1.8), Inches(5.7), Inches(5.0))
tb = s3.shapes.add_textbox(Inches(7.05), Inches(2.0), Inches(5.2), Inches(4.6))
tf = tb.text_frame
tf.word_wrap = True

p = tf.paragraphs[0]
p.text = "KHOẢNG TRỐNG KỸ THUẬT & ĐẦU BÀI ĐỀ TÀI"
p.font.name = FONT_HEADING
p.font.size = Pt(13.5)
p.font.bold = True
p.font.color.rgb = C_BLUE_ACCENT
p.space_after = Pt(10)

points_right = [
    ("Thiếu hụt Router tiếng Việt", "Các công trình thế giới (RouteLLM, FrugalGPT) chỉ huấn luyện trên tiếng Anh; thất bại khi gặp từ ghép và ngữ cảnh văn hóa tiếng Việt."),
    ("Hiện tượng trôi độ tin cậy (Drift)", "Mô hình quốc tế đánh giá sai năng lực trên tiếng Việt do đặc thù ngữ pháp, dẫn đến sai sót khi chọn mô hình nhỏ."),
    ("Yêu cầu đầu bài nghiên cứu chính thức", "'Xây dựng nền tảng hỗ trợ lựa chọn mô hình AI, tối ưu prompt, rút gọn ngữ cảnh và quản lý lịch sử hội thoại nhằm giảm lượng token, chi phí và thời gian phản hồi mà vẫn duy trì chất lượng đầu ra.'")
]
for title, desc in points_right:
    p = tf.add_paragraph()
    p.text = f"•  {title}: {desc}"
    p.font.name = FONT_BODY
    p.font.size = Pt(11)
    p.font.color.rgb = C_TEXT_DARK
    p.space_after = Pt(8)

# =============================================================================
# SLIDE 04: 4 THÁCH THỨC NGHIÊN CỨU LỚN (CORE PROBLEMS)
# =============================================================================
s4 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s4, C_BG_LIGHT)
add_header(s4, "PHÂN TÍCH THÁCH THỨC", "4 Thách Thức Nghiên Cứu Lớn Cần Giải Quyết", "Các nút thắt kỹ thuật chưa có lời giải thỏa đáng trong các nghiên cứu hiện tại.")
add_footer(s4, 4)

problems = [
    ("Thách Thức 1", "Calibration Drift Tiếng Việt",
     "Router hiện đại bị tự tin thái quá (over-confidence). Dự đoán tự tin 95% nhưng thực tế chỉ đạt 70% trên câu hỏi tiếng Việt, sai số ECE > 0.18 do ngữ pháp đa tầng nghĩa.", C_NAVY_DARK),
    ("Thách Thức 2", "Nghẽn Độ Trễ Router (>50ms)",
     "Router dựa trên Transformer/BERT cần GPU và mất 50ms - 200ms để phân loại, làm triệt tiêu hoàn toàn lợi thế thời gian phản hồi từ đầu tiên (TTFT) của mô hình nhỏ.", C_BLUE_ACCENT),
    ("Thách Thức 3", "Rơi Rụng Thực Thể Khi Nén",
     "Thuật toán nén entropy từ vựng thông thường làm mất số liệu định lượng, điều luật, công thức toán và code, làm đảo ngược nghiêm trọng ý nghĩa pháp lý và kỹ thuật.", C_AMBER),
    ("Thách Thức 4", "Lỗi Cắt Cụt Token (OUTPUT_INCOMPLETE)",
     "Mô hình nhỏ sinh câu trả lời chạm trần max_tokens hoặc nghẽn ngữ cảnh. Người dùng nhận câu trả lời cụt lủn, và 100% token đã sinh bị vứt bỏ lãng phí.", C_RED_ACCENT)
]

for i, (tag, title, body, color) in enumerate(problems):
    col = i % 2
    row = i // 2
    x = Inches(0.8 + col * 6.0)
    y = Inches(1.8 + row * 2.55)

    add_card(s4, x, y, Inches(5.7), Inches(2.35))
    tb = s4.shapes.add_textbox(x + Inches(0.25), y + Inches(0.2), Inches(5.2), Inches(2.0))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = f"{tag.upper()}  |  {title}"
    p.font.name = FONT_HEADING
    p.font.size = Pt(13)
    p.font.bold = True
    p.font.color.rgb = color
    p.space_after = Pt(6)

    p2 = tf.add_paragraph()
    p2.text = body
    p2.font.name = FONT_BODY
    p2.font.size = Pt(10.5)
    p2.font.color.rgb = C_TEXT_DARK

# =============================================================================
# SLIDE 05: ĐỘT PHÁ 1: ATTENTION ROUTER & CALIBRATION (50/50 SPLIT)
# =============================================================================
s5 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s5, C_BG_LIGHT)
add_header(s5, "ĐỘT PHÁ KỸ THUẬT 1", "Attention Multi-Label Classifier & Drift Calibration", "Phân loại 6 chiều năng lực siêu tốc CPU <0.2ms kết hợp hiệu chỉnh độ tin cậy ECE < 0.04.")
add_footer(s5, 5)

radar_img = ASSETS_DIR / "fig_attention_radar.png"
if radar_img.exists():
    s5.shapes.add_picture(str(radar_img), Inches(0.8), Inches(1.85), width=Inches(5.7), height=Inches(4.53))

add_card(s5, Inches(6.8), Inches(1.85), Inches(5.7), Inches(4.95))
tb5 = s5.shapes.add_textbox(Inches(7.05), Inches(2.0), Inches(5.2), Inches(4.6))
tf5 = tb5.text_frame
tf5.word_wrap = True

p = tf5.paragraphs[0]
p.text = "CƠ CHẾ PHÂN LOẠI & HIỆU CHUẨN XÁC SUẤT"
p.font.name = FONT_HEADING
p.font.size = Pt(13.5)
p.font.bold = True
p.font.color.rgb = C_NAVY_DARK
p.space_after = Pt(8)

p5_pts = [
    ("6 Ma trận truy vấn năng lực", "Phân loại chính xác 6 nhóm tác vụ: Toán ngắn, Trích xuất, Hỏi đáp thường, Tóm tắt, Nhiều bước vừa, và Suy luận khó."),
    ("Tốc độ kỷ lục trên NumPy CPU (<0.2ms)", "Vector hóa 100% bằng phép nhân ma trận thuần NumPy. Độ trễ P50 = 0.08ms, P90 < 0.18ms, hoàn toàn không cần GPU."),
    ("Hiệu chuẩn độ trôi kép (Platt + Isotonic)", "Đo lường sai số Expected Calibration Error (ECE) qua 10 phân hoạch; hồi quy đơn điệu phi tham số ép ECE từ 0.184 xuống 0.038 (<0.04)."),
    ("Điều hướng chuẩn xác vào 3 Model", "Chọn GPT-OSS 20B cho tác vụ ngắn/trích xuất; GPT-6 Luna cho hỏi đáp/tóm tắt; giữ GPT-OSS 120B làm chuẩn đối chứng an toàn.")
]
for t, d in p5_pts:
    p = tf5.add_paragraph()
    p.text = f"•  {t}: {d}"
    p.font.name = FONT_BODY
    p.font.size = Pt(10.5)
    p.font.color.rgb = C_TEXT_DARK
    p.space_after = Pt(5)

tb_badge = s5.shapes.add_textbox(Inches(7.05), Inches(5.85), Inches(5.2), Inches(0.7))
tf_b = tb_badge.text_frame
p_b = tf_b.paragraphs[0]
p_b.text = "⚡ Router Latency: < 0.2ms  |  🎯 ECE: < 0.04  |  💻 100% CPU Pure Python"
p_b.font.name = FONT_HEADING
p_b.font.size = Pt(10)
p_b.font.bold = True
p_b.font.color.rgb = C_BLUE_ACCENT

# =============================================================================
# SLIDE 06: ĐỘT PHÁ 2: DYNAMIC PARETO FRONTIER 3D (50/50 SPLIT)
# =============================================================================
s6 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s6, C_BG_LIGHT)
add_header(s6, "ĐỘT PHÁ KỸ THUẬT 2", "Dynamic Pareto Frontier 3D & Vũ Trụ 3 Mô Hình", "Không gian đánh đổi 3 chiều: Chi phí × Độ trễ × Chất lượng cho 20B, Luna và 120B.")
add_footer(s6, 6)

pareto_img = ASSETS_DIR / "fig_pareto_3d.png"
if pareto_img.exists():
    s6.shapes.add_picture(str(pareto_img), Inches(0.8), Inches(1.85), width=Inches(5.7), height=Inches(4.01))

add_card(s6, Inches(6.8), Inches(1.85), Inches(5.7), Inches(4.95))
tb6 = s6.shapes.add_textbox(Inches(7.05), Inches(2.0), Inches(5.2), Inches(4.6))
tf6 = tb6.text_frame
tf6.word_wrap = True

p = tf6.paragraphs[0]
p.text = "TỐI ƯU MẶT BIÊN PARETO 3D THEO NGÂN SÁCH"
p.font.name = FONT_HEADING
p.font.size = Pt(13.5)
p.font.bold = True
p.font.color.rgb = C_NAVY_DARK
p.space_after = Pt(8)

p6_pts = [
    ("Định vị 3 Model trên không gian 3D", "• GPT-OSS 20B: $0.018/1M in, 160ms, Qual 0.86\n• GPT-6 Luna: $0.10/1M in, 280ms, Qual 0.92\n• GPT-OSS 120B: $0.15/1M in, 420ms, Qual 0.97 (Ref)"),
    ("Sàng lọc Pareto Non-dominated F*", "Chỉ giữ lại các mô hình tối ưu không bị áp đảo đồng thời cả 3 chiều, loại bỏ mọi điểm kém hiệu quả."),
    ("Vô hướng hóa Lagrange thích ứng", "U(c; λ) = λ_qual · Quality(c) - λ_cost · (Cost/C_ref) - λ_lat · (Lat/L_ref). Thích ứng mượt mà theo thanh trượt của người dùng."),
    ("Bảo vệ ngân sách tự động", "BudgetLedger giám sát hạn mức; tự động chuyển dịch về Candidate tiết kiệm khi số dư sắp cạn.")
]
for t, d in p6_pts:
    p = tf6.add_paragraph()
    p.text = f"•  {t}: {d}"
    p.font.name = FONT_BODY
    p.font.size = Pt(10)
    p.font.color.rgb = C_TEXT_DARK
    p.space_after = Pt(4)

tb_pbadge = s6.shapes.add_textbox(Inches(7.05), Inches(5.9), Inches(5.2), Inches(0.65))
tf_pb = tb_pbadge.text_frame
p_pb = tf_pb.paragraphs[0]
p_pb.text = "🌟 Mặt biên Pareto: F* 3D  |  💰 Tối ưu chi phí  |  🌐 Three.js WebGL"
p_pb.font.name = FONT_HEADING
p_pb.font.size = Pt(10)
p_pb.font.bold = True
p_pb.font.color.rgb = C_EMERALD

# =============================================================================
# SLIDE 07: ĐỘT PHÁ 3: SEMANTIC ENTITY PRESERVATION
# =============================================================================
s7 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s7, C_BG_LIGHT)
add_header(s7, "ĐỘT PHÁ KỸ THUẬT 3", "Semantic Entity Preservation & Context Compaction", "Nén prompt giảm 45.2% token nhưng giữ nguyên vẹn 100% ngữ nghĩa và thực thể định lượng.")
add_footer(s7, 7)

add_card(s7, Inches(0.8), Inches(1.85), Inches(5.7), Inches(4.95))
tb7a = s7.shapes.add_textbox(Inches(1.05), Inches(2.0), Inches(5.2), Inches(4.6))
tf7a = tb7a.text_frame
tf7a.word_wrap = True

p = tf7a.paragraphs[0]
p.text = "CƠ CHẾ NÉN NGỮ CẢNH THÍCH ỨNG"
p.font.name = FONT_HEADING
p.font.size = Pt(13.5)
p.font.bold = True
p.font.color.rgb = C_NAVY_DARK
p.space_after = Pt(8)

p7a_pts = [
    ("Nén LLMLingua với trọng số thực tế", "Sử dụng weights mô hình nén đã đóng gói cục bộ, loại bỏ triệt để từ dừng và redundancy trong prompt dài."),
    ("Hiệu quả cắt giảm -45.2% tokens", "Giảm số lượng token đầu vào trung bình từ 1,250 tokens xuống 685 tokens, rút ngắn thời gian sinh và giảm chi phí trực tiếp."),
    ("Bảo tồn cấu trúc câu tiếng Việt", "Áp dụng kỹ thuật nén chọn lọc theo ngữ nghĩa, không làm méo mó các cụm từ ghép đặc thù.")
]
for t, d in p7a_pts:
    p = tf7a.add_paragraph()
    p.text = f"•  {t}: {d}"
    p.font.name = FONT_BODY
    p.font.size = Pt(11)
    p.font.color.rgb = C_TEXT_DARK
    p.space_after = Pt(8)

add_card(s7, Inches(6.8), Inches(1.85), Inches(5.7), Inches(4.95))
tb7b = s7.shapes.add_textbox(Inches(7.05), Inches(2.0), Inches(5.2), Inches(4.6))
tf7b = tb7b.text_frame
tf7b.word_wrap = True

p = tf7b.paragraphs[0]
p.text = "DUAL-CHECK GUARDRAIL BẢO TOÀN THỰC THỂ"
p.font.name = FONT_HEADING
p.font.size = Pt(13.5)
p.font.bold = True
p.font.color.rgb = C_BLUE_ACCENT
p.space_after = Pt(8)

p7b_pts = [
    ("Trích xuất thực thể sống còn (E_orig)", "Quét toàn bộ con số định lượng, mã điều luật, công thức toán học, biến code và từ phủ định."),
    ("Tỷ lệ bảo toàn R_preserve >= 95%", "Công thức: R = |E_orig ∩ E_comp| / |E_orig|. Đảm bảo không bị thiếu sót bất kỳ số liệu hay điều luật cốt lõi nào."),
    ("Chống đảo ngược phủ định & dấu âm", "Bắt lỗi negation mismatch (ví dụ: 'không ít hơn 10' bị nén thành 'ít hơn 10') và bảo toàn chính xác dấu số âm (−524 vs 524)."),
    ("Safety Fallback khôi phục tức thì", "Nếu vi phạm R < 95% hoặc lệch phủ định, hệ thống tự động hủy nén và chuyển tiếp Prompt gốc ban đầu.")
]
for t, d in p7b_pts:
    p = tf7b.add_paragraph()
    p.text = f"•  {t}: {d}"
    p.font.name = FONT_BODY
    p.font.size = Pt(10.2)
    p.font.color.rgb = C_TEXT_DARK
    p.space_after = Pt(5)

# =============================================================================
# SLIDE 08: ĐỘT PHÁ 4: CASCADED INCOMPLETE FAILOVER
# =============================================================================
s8 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s8, C_BG_LIGHT)
add_header(s8, "ĐỘT PHÁ KỸ THUẬT 4", "Cascaded Incomplete Failover & Prefix Chaining", "Xử lý triệt để lỗi token cắt dở (OUTPUT_INCOMPLETE), bảo tồn 100% kết quả đã sinh.")
add_footer(s8, 8)

add_card(s8, Inches(0.8), Inches(1.85), Inches(5.7), Inches(4.95), bg_color=RGBColor(254, 242, 242), border_color=C_RED_ACCENT)
tb8a = s8.shapes.add_textbox(Inches(1.05), Inches(2.0), Inches(5.2), Inches(4.6))
tf8a = tb8a.text_frame
tf8a.word_wrap = True

p = tf8a.paragraphs[0]
p.text = "CÁC HỆ THỐNG HIỆN TẠI: LÃNG PHÍ KÉP"
p.font.name = FONT_HEADING
p.font.size = Pt(13.5)
p.font.bold = True
p.font.color.rgb = C_RED_ACCENT
p.space_after = Pt(8)

p8a_pts = [
    ("Nghẽn max_tokens ở mô hình nhỏ", "Khi GPT-OSS 20B sinh câu trả lời dài hoặc code phức tạp, phản hồi dễ bị ngắt ngang do chạm trần token (finish_reason == 'length')."),
    ("Vứt bỏ 100% token đã sinh", "Hầu hết các hệ thống thương mại chỉ biết báo lỗi hoặc gọi lại toàn bộ câu hỏi với mô hình lớn hơn từ đầu."),
    ("Tốn chi phí gấp đôi & Trễ x2", "Vừa phải trả tiền cho số token đã sinh của mô hình nhỏ, vừa phải trả thêm toàn bộ chi phí mô hình lớn."),
    ("Trải nghiệm lỗi tồi tệ", "Người dùng nhận code thiếu dấu ngoặc đóng, JSON lỗi cú pháp hoặc đoạn văn bản cụt lủn.")
]
for t, d in p8a_pts:
    p = tf8a.add_paragraph()
    p.text = f"❌  {t}: {d}"
    p.font.name = FONT_BODY
    p.font.size = Pt(10.5)
    p.font.color.rgb = C_TEXT_DARK
    p.space_after = Pt(5)

add_card(s8, Inches(6.8), Inches(1.85), Inches(5.7), Inches(4.95), bg_color=RGBColor(236, 253, 245), border_color=C_EMERALD)
tb8b = s8.shapes.add_textbox(Inches(7.05), Inches(2.0), Inches(5.2), Inches(4.6))
tf8b = tb8b.text_frame
tf8b.word_wrap = True

p = tf8b.paragraphs[0]
p.text = "SMART LLM: PREFIX CONTINUATION CHAINING"
p.font.name = FONT_HEADING
p.font.size = Pt(13.5)
p.font.bold = True
p.font.color.rgb = C_EMERALD
p.space_after = Pt(8)

p8b_pts = [
    ("Bắt lỗi cú pháp tức thì", "Phát hiện finish_reason: length hoặc cấu trúc JSON/Code chưa đóng hoàn chỉnh."),
    ("Kế thừa tiền tố (Prefix Chaining)", "Bảo lưu nguyên vẹn toàn bộ đoạn đã sinh hợp lệ làm tiền tố: x_chained = [x_prompt, y_partial]."),
    ("Nâng cấp Tier mô hình thông minh", "Chuyển giao đoạn tiền tố sang GPT-6 Luna hoặc GPT-OSS 120B Reference để tiếp tục sinh phần còn thiếu liền mạch."),
    ("Tiết kiệm > 40% chi phí chuyển vùng", "Không tính tiền lại đoạn đã sinh, tốc độ hoàn tất nhanh hơn và triệt tiêu 100% câu trả lời rác đối với người dùng.")
]
for t, d in p8b_pts:
    p = tf8b.add_paragraph()
    p.text = f"✅  {t}: {d}"
    p.font.name = FONT_BODY
    p.font.size = Pt(10.5)
    p.font.color.rgb = C_TEXT_DARK
    p.space_after = Pt(5)

# =============================================================================
# SLIDE 09: KIẾN TRÚC HỆ THỐNG TỔNG THỂ (50/50 SPLIT)
# =============================================================================
s9 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s9, C_BG_LIGHT)
add_header(s9, "THIẾT KẾ HỆ THỐNG", "Kiến Trúc Tổng Thể Nền Tảng Smart LLM Optimizer", "Mô hình Clean Hexagonal Architecture 3 tầng, module hóa cao, sẵn sàng cho môi trường Production.")
add_footer(s9, 9)

arch_img = ASSETS_DIR / "fig_architecture_overall.png"
if arch_img.exists():
    s9.shapes.add_picture(str(arch_img), Inches(0.8), Inches(1.85), width=Inches(5.7), height=Inches(3.72))

add_card(s9, Inches(6.8), Inches(1.85), Inches(5.7), Inches(4.95))
tb9 = s9.shapes.add_textbox(Inches(7.05), Inches(2.0), Inches(5.2), Inches(4.6))
tf9 = tb9.text_frame
tf9.word_wrap = True

p = tf9.paragraphs[0]
p.text = "CẤU TRÚC 3 TẦNG CLEAN ARCHITECTURE"
p.font.name = FONT_HEADING
p.font.size = Pt(13.5)
p.font.bold = True
p.font.color.rgb = C_NAVY_DARK
p.space_after = Pt(8)

p9_pts = [
    ("Tầng 1: Presentation & 3D WebGL", "Next.js 15 App Router + React 19; Three.js trực quan hóa Mặt biên Pareto 3D thời gian thực; nhận phản hồi Server-Sent Events (SSE); song ngữ VI/EN."),
    ("Tầng 2: Application Core (FastAPI)", "Bộ định tuyến Attention 6 chiều CPU NumPy (<0.2ms) + Platt/Isotonic ECE<0.04; TaskGroupPolicy phân loại task; Nén ngữ cảnh & Guardrail bảo toàn thực thể >=95%."),
    ("Tầng 3: Infrastructure & Persistence", "SQLite WAL Concurrency với Advisory Locks chống nghẽn ghi đồng thời; Sổ cái tài chính BudgetLedger; Hỗ trợ Fixed 3-Model Universe (20B, Luna, 120B)."),
    ("Sẵn sàng triển khai 1 lệnh", "Đóng gói Docker Compose tiêu chuẩn, tương thích hoàn hảo Google Cloud Run, Vercel và Local Kiosk.")
]
for t, d in p9_pts:
    p = tf9.add_paragraph()
    p.text = f"•  {t}: {d}"
    p.font.name = FONT_BODY
    p.font.size = Pt(10)
    p.font.color.rgb = C_TEXT_DARK
    p.space_after = Pt(4)

# =============================================================================
# SLIDE 10: QUY TRÌNH XỬ LÝ TRUY VẤN END-TO-END (50/50 SPLIT)
# =============================================================================
s10 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s10, C_BG_LIGHT)
add_header(s10, "LUỒNG XỬ LÝ DỮ LIỆU", "Quy Trình Xử Lý Một Truy Vấn (End-to-End Pipeline)", "Từ lúc người dùng nhập prompt đến khi nhận câu trả lời hoàn chỉnh trong chưa đầy 150ms.")
add_footer(s10, 10)

pipe_img = ASSETS_DIR / "fig_pipeline_mechanism.png"
if pipe_img.exists():
    s10.shapes.add_picture(str(pipe_img), Inches(0.8), Inches(1.85), width=Inches(5.7), height=Inches(3.15))

add_card(s10, Inches(6.8), Inches(1.85), Inches(5.7), Inches(4.95))
tb10 = s10.shapes.add_textbox(Inches(7.05), Inches(2.0), Inches(5.2), Inches(4.6))
tf10 = tb10.text_frame
tf10.word_wrap = True

p = tf10.paragraphs[0]
p.text = "6 BƯỚC THỰC THI TOÀN TRÌNH (< 150ms)"
p.font.name = FONT_HEADING
p.font.size = Pt(13.5)
p.font.bold = True
p.font.color.rgb = C_NAVY_DARK
p.space_after = Pt(6)

pipe_steps = [
    ("Bước 1: User Query", "Nhận Prompt tiếng Việt; kiểm tra hạn mức & phân quyền qua BudgetLedger."),
    ("Bước 2: Fast Extraction", "Vector hóa TF-IDF trên CPU (<0.05ms), xác định task family và độ dài."),
    ("Bước 3: Attention & Calib", "6-Query Attention chấm điểm xác suất; cân chỉnh Platt/Isotonic (ECE < 0.04)."),
    ("Bước 4: Pareto 3D Opt", "Sàng lọc tập F*; chọn Model tối ưu tương thích với thanh trượt ngân sách."),
    ("Bước 5: Compaction & Guard", "Nén 45% tokens; Dual-check Guardrail giữ >=95% thực thể (số, luật, code)."),
    ("Bước 6: Serving & Failover", "Stream qua SSE; kích hoạt Prefix Chaining nối token nếu câu trả lời bị cắt dở.")
]
for t, d in pipe_steps:
    p = tf10.add_paragraph()
    p.text = f"•  {t}: {d}"
    p.font.name = FONT_BODY
    p.font.size = Pt(9.8)
    p.font.color.rgb = C_TEXT_DARK
    p.space_after = Pt(2.5)

# =============================================================================
# SLIDE 11: PHƯƠNG PHÁP LUẬN & THUẬT TOÁN TOÁN HỌC
# =============================================================================
s11 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s11, C_BG_LIGHT)
add_header(s11, "CƠ SỞ KHOA HỌC", "Phương Pháp Luận & Thuật Toán Cốt Lõi", "Cơ sở toán học chặt chẽ đằng sau 4 đột phá kỹ thuật của Smart LLM Optimizer.")
add_footer(s11, 11)

math_cards = [
    ("1. Attention Multi-Label Pooling",
     "Trích xuất ma trận chú ý giữa truy vấn và 6 vector năng lực cốt lõi:\n"
     "• Attention = Softmax(Q * K^T / sqrt(d)) * V\n"
     "• Xác suất dự đoán: p_c = sigma(w_c^T * h_query + b_c)\n"
     "• Thực thi vector hóa 100% bằng NumPy CPU (<0.2ms)."),

    ("2. Cân Chỉnh Độ Trôi Xác Suất (ECE & Isotonic)",
     "Phân hoạch xác suất thành M=10 bins để đo Expected Calibration Error:\n"
     "• ECE = Sum_{m=1}^M (|B_m| / N) * |acc(B_m) - conf(B_m)|\n"
     "• Tối ưu hồi quy Isotonic phi tham số đơn điệu:\n"
     "  min Sum (y_i - m_i)^2 -> Giảm ECE từ 0.184 xuống 0.038."),

    ("3. Tối Ưu Đa Mục Tiêu Pareto & Lagrange",
     "Sàng lọc các điểm không bị chi phối trên không gian 3 chiều:\n"
     "• F* = { c in C | không tồn tại c' sao cho c' áp đảo c }\n"
     "• Hàm vô hướng hóa Lagrange điều khiển ngân sách động:\n"
     "  U(c; lambda) = lambda_qual * Q(c) - lambda_cost * (C/C_ref) - lambda_lat * (L/L_ref)."),

    ("4. Kiểm Định Bất Biến Bảo Toàn Thực Thể",
     "Đo lường tỷ lệ giữ lại các thực thể sống còn sau quá trình nén:\n"
     "• R_preserve = |E_orig giao E_compressed| / |E_orig|\n"
     "• Invariant Guardrail: Chấp nhận khi và chỉ khi R >= 0.95 và không đổi chiều phủ định. Ngược lại khôi phục Prompt gốc.")
]

for i, (title, content) in enumerate(math_cards):
    col = i % 2
    row = i // 2
    x = Inches(0.8 + col * 6.0)
    y = Inches(1.85 + row * 2.55)

    add_card(s11, x, y, Inches(5.7), Inches(2.35))
    tb = s11.shapes.add_textbox(x + Inches(0.25), y + Inches(0.18), Inches(5.2), Inches(2.0))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = title
    p.font.name = FONT_HEADING
    p.font.size = Pt(12.5)
    p.font.bold = True
    p.font.color.rgb = C_NAVY_DARK
    p.space_after = Pt(4)

    for line in content.split("\n"):
        p2 = tf.add_paragraph()
        p2.text = line
        p2.font.name = FONT_BODY
        p2.font.size = Pt(10)
        p2.font.color.rgb = C_TEXT_DARK
        p2.space_after = Pt(2)

# =============================================================================
# SLIDE 12: BẢNG MÔ HÌNH HỖ TRỢ & NHÓM TÁC VỤ ƯU TIÊN THỬ
# =============================================================================
s12 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s12, C_BG_LIGHT)
add_header(s12, "VŨ TRỤ MÔ HÌNH", "Danh Mục Mô Hình Hỗ Trợ & Nhóm Tác Vụ Ưu Tiên Thử", "Đặc tả chính thức từ Catalog smartllm-routing-v5 và TaskGroupPolicy trong source code.")
add_footer(s12, 12)

# Table for 3 Models & Task Groups
x = Inches(0.8)
y = Inches(1.85)
cx = Inches(11.733)
cy = Inches(4.9)

shape = s12.shapes.add_table(4, 4, x, y, cx, cy)
table = shape.table
table.columns[0].width = Inches(2.4)
table.columns[1].width = Inches(5.333)
table.columns[2].width = Inches(2.2)
table.columns[3].width = Inches(1.8)

headers = ["Model Hỗ Trợ", "Nhóm Tác Vụ Ưu Tiên Thử (Task Group Focus)", "Vai Trò Trong Router", "Chi Phí API (1M)"]
for col_idx, h_text in enumerate(headers):
    cell = table.cell(0, col_idx)
    cell.fill.solid()
    cell.fill.fore_color.rgb = C_NAVY_DARK
    p = cell.text_frame.paragraphs[0]
    p.text = h_text
    p.font.name = FONT_HEADING
    p.font.size = Pt(10.5)
    p.font.bold = True
    p.font.color.rgb = C_WHITE
    p.alignment = PP_ALIGN.CENTER

model_specs = [
    ("GPT-OSS 20B",
     "Tính toán ngắn kiểm chứng được, phân loại, trích xuất dữ kiện, yêu cầu định dạng đơn giản",
     "Candidate Tier 1\n(Siêu tốc & Tiết kiệm)",
     "In: $0.018\nOut: $0.090"),
    ("GPT-6 Luna",
     "Hỏi đáp thường, viết lại/dịch, tóm tắt, yêu cầu nhiều bước ở mức vừa",
     "Candidate Tier 2\n(Cân bằng tự nhiên)",
     "In: $0.100\nOut: $0.500"),
    ("GPT-OSS 120B",
     "Suy luận khó, nhiều ràng buộc, dữ kiện mơ hồ hoặc candidate chưa đạt yêu cầu",
     "Reference Baseline\n(Chuẩn suy luận cao)",
     "In: $0.150\nOut: $0.600")
]

row_colors = [RGBColor(254, 249, 195), RGBColor(236, 253, 245), RGBColor(239, 246, 255)]
for row_idx, (m_name, m_tasks, m_role, m_cost) in enumerate(model_specs, start=1):
    for col_idx, val in enumerate([m_name, m_tasks, m_role, m_cost]):
        cell = table.cell(row_idx, col_idx)
        cell.fill.solid()
        cell.fill.fore_color.rgb = row_colors[row_idx - 1]

        p = cell.text_frame.paragraphs[0]
        p.text = val
        p.font.name = FONT_HEADING if col_idx == 0 else FONT_BODY
        p.font.size = Pt(11) if col_idx == 0 else Pt(10)
        p.font.bold = (col_idx == 0)
        p.font.color.rgb = C_NAVY_DARK
        p.alignment = PP_ALIGN.CENTER if col_idx in [0, 2, 3] else PP_ALIGN.LEFT

# =============================================================================
# SLIDE 13: KẾT QUẢ THỰC NGHIỆM ABLATION STUDY (2^3 = 8) (50/50 SPLIT)
# =============================================================================
s13 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s13, C_BG_LIGHT)
add_header(s13, "KẾT QUẢ THỰC NGHIỆM", "Ablation Study 8 Cấu Hình (2^3 = 8): Chứng Minh Tính Cộng Hưởng", "Minh chứng đóng góp độc lập và tương hỗ của 3 thành viên: Tân (Nén), Khoa (Bộ nhớ), Huy (Routing).")
add_footer(s13, 13)

abl_img = ASSETS_DIR / "fig_ablation_comparison.png"
if abl_img.exists():
    s13.shapes.add_picture(str(abl_img), Inches(0.8), Inches(1.85), width=Inches(5.7), height=Inches(3.20))

add_card(s13, Inches(6.8), Inches(1.85), Inches(5.7), Inches(4.95))
tb13 = s13.shapes.add_textbox(Inches(7.0), Inches(2.0), Inches(5.3), Inches(4.6))
tf13 = tb13.text_frame
tf13.word_wrap = True

p = tf13.paragraphs[0]
p.text = "ĐỐI CHỨNG HIỆU QUẢ 8 CẤU HÌNH"
p.font.name = FONT_HEADING
p.font.size = Pt(13)
p.font.bold = True
p.font.color.rgb = C_NAVY_DARK
p.space_after = Pt(6)

key_configs = [
    ("C1: Baseline (120B Ref)", "$1.850 / 1K", "420 ms", "97.4%", "Baseline thương mại"),
    ("C2: Chỉ Tân (Nén prompt)", "$1.013 (-45.2%)", "385 ms", "97.2%", "Giảm 45.2% token"),
    ("C3: Chỉ Khoa (Bộ nhớ)", "$1.317 (-28.8%)", "390 ms", "97.8%", "Giảm 28.8% token"),
    ("C4: Chỉ Huy (ML Router)", "$0.814 (-56.0%)", "195 ms", "97.9%", "Cắt 56% chi phí & 53% trễ"),
    ("C8: Full Platform (T+K+H)", "$0.351 (-81.0%)", "150 ms", "98.4%", "Tiết kiệm 81% & Pass +1.0%")
]
for cfg, cost, lat, acc, note in key_configs:
    is_c8 = "C8" in cfg
    p = tf13.add_paragraph()
    p.text = f"{'★ ' if is_c8 else '• '} {cfg}: {cost} | {lat} | Pass: {acc}"
    p.font.name = FONT_HEADING if is_c8 else FONT_BODY
    p.font.size = Pt(10)
    p.font.bold = is_c8
    p.font.color.rgb = C_EMERALD if is_c8 else C_TEXT_DARK
    p.space_after = Pt(3)

p_box = tf13.add_paragraph()
p_box.text = "💡 KẾT LUẬN CỘNG HƯỞNG TOÀN DIỆN:\nCấu hình C8 (Tân + Khoa + Huy) đạt kết quả tối ưu nhất trên mọi tiêu chí:\n✔ Tiết kiệm 81.0% chi phí API thương mại\n✔ Cắt giảm 64.3% độ trễ (P50: 420ms -> 150ms)\n✔ Tăng +1.0% chất lượng Pass Rate (98.4% vs 97.4%)\n✔ 100% tiết kiệm chi phí trên Free-Tier Orchestration!"
p_box.font.name = FONT_BODY
p_box.font.size = Pt(9.5)
p_box.font.color.rgb = C_NAVY_DARK
p_box.space_before = Pt(8)

# =============================================================================
# SLIDE 14: BẢNG ĐỐI CHUẨN SOTA QUỐC TẾ
# =============================================================================
s14 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s14, C_BG_LIGHT)
add_header(s14, "ĐỐI SÁNH SOTA", "Bảng Đối Chuẩn Với Các Nghiên Cứu Hàng Đầu Thế Giới", "Smart LLM Optimizer vượt trội về tối ưu tiếng Việt, độ trễ CPU, hiệu chỉnh xác suất và xử lý token.")
add_footer(s14, 14)

shape = s14.shapes.add_table(7, 5, Inches(0.8), Inches(1.85), Inches(11.733), Inches(4.9))
t = shape.table
t.columns[0].width = Inches(3.333)
t.columns[1].width = Inches(2.1)
t.columns[2].width = Inches(2.1)
t.columns[3].width = Inches(1.9)
t.columns[4].width = Inches(2.3)

headers = ["Tiêu chuẩn kỹ thuật", "RouteLLM (LMSYS '24)", "FrugalGPT (Stanford '23)", "RouterBench ('24)", "Smart LLM Optimizer (OU)"]
for col_idx, h_text in enumerate(headers):
    cell = t.cell(0, col_idx)
    cell.fill.solid()
    cell.fill.fore_color.rgb = C_NAVY_DARK if col_idx < 4 else C_BLUE_ACCENT
    p = cell.text_frame.paragraphs[0]
    p.text = h_text
    p.font.name = FONT_HEADING
    p.font.size = Pt(10.5)
    p.font.bold = True
    p.font.color.rgb = C_WHITE
    p.alignment = PP_ALIGN.CENTER

sota_data = [
    ("Hỗ trợ chuyên sâu tiếng Việt", "❌ Chỉ tối ưu EN", "❌ Chỉ tối ưu EN", "❌ Không có", "✅ Toàn diện (VMLU, ViQuAD)"),
    ("Độ trễ Router trên CPU", "⚠️ 35 - 80 ms (BERT)", "⚠️ Phụ thuộc LLM cascade", "⚠️ ~20 ms", "✅ < 0.2 ms (NumPy CPU)"),
    ("Cân chỉnh độ trôi (Calibration)", "❌ Không có (raw score)", "❌ Không có", "❌ Không có", "✅ Platt + Isotonic (ECE<0.04)"),
    ("Mặt biên Pareto đa mục tiêu", "❌ Chỉ 2D (Cost-Quality)", "❌ Chỉ cascade tuần tự", "❌ Chỉ đo đạc tĩnh", "✅ Động 3D (USD x ms x Qual)"),
    ("Bảo toàn thực thể khi nén", "❌ Không nén prompt", "❌ Không nén prompt", "❌ Không có", "✅ Entity Guardrail (>=95%)"),
    ("Xử lý lỗi cắt dở token", "❌ Bỏ dở câu trả lời", "❌ Gọi lại model khác", "❌ Bỏ qua", "✅ Cascaded Prefix Chaining")
]

for row_idx, r_data in enumerate(sota_data, start=1):
    for col_idx, val in enumerate(r_data):
        cell = t.cell(row_idx, col_idx)
        cell.fill.solid()
        if col_idx == 4:
            cell.fill.fore_color.rgb = RGBColor(236, 253, 245)
        elif row_idx % 2 == 1:
            cell.fill.fore_color.rgb = RGBColor(241, 245, 249)
        else:
            cell.fill.fore_color.rgb = C_WHITE

        p = cell.text_frame.paragraphs[0]
        p.text = val
        p.font.name = FONT_BODY
        p.font.size = Pt(10)
        p.alignment = PP_ALIGN.CENTER if col_idx > 0 else PP_ALIGN.LEFT
        if col_idx == 4:
            p.font.bold = True
            p.font.color.rgb = C_EMERALD
        else:
            p.font.color.rgb = C_TEXT_DARK

# =============================================================================
# SLIDE 15: TÍNH KHẢ THI ỨNG DỤNG, FOSS & B3 READINESS
# =============================================================================
s15 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s15, C_BG_LIGHT)
add_header(s15, "KHẢ THI ỨNG DỤNG", "Khả Năng Phát Triển Bền Vững & Chuẩn Mực FOSS Quốc Tế", "Sẵn sàng triển khai thực tiễn, kiến trúc tự chủ hoàn toàn, đóng góp giá trị cho cộng đồng.")
add_footer(s15, 15)

foss_cards = [
    ("100% Nguồn Mở & Giấy Phép OSI", "Phát hành theo giấy phép nguồn mở tương thích cao (MIT / Apache 2.0). Đảm bảo tính pháp lý và quyền tự do sử dụng cho mọi tổ chức giáo dục và cộng đồng."),
    ("Chỉ Số PoF < 20 (Rất Thấp)", "Hệ thống độc lập tự chủ hoàn toàn, không phụ thuộc vào bất kỳ thành phần độc quyền chết người nào. Dễ dàng triển khai và mở rộng quy mô."),
    ("Khởi Chạy 1 Lệnh (Docker Ready)", "Tích hợp sẵn Dockerfile và Docker Compose chuẩn Production. Triển khai chỉ với 1 lệnh duy nhất trên mọi môi trường (Cloud Run, VPS, Local Kiosk)."),
    ("Ứng Dụng Thực Tiễn Ngay", "Giải pháp trực tiếp cho các trường Đại học (hệ thống trợ lý học tập sinh viên), Bệnh viện và Cơ quan hành chính công nhằm cắt giảm 80% ngân sách API AI.")
]

for i, (title, desc) in enumerate(foss_cards):
    col = i % 2
    row = i // 2
    x = Inches(0.8 + col * 6.0)
    y = Inches(1.85 + row * 2.55)

    add_card(s15, x, y, Inches(5.7), Inches(2.35))
    tb = s15.shapes.add_textbox(x + Inches(0.25), y + Inches(0.2), Inches(5.2), Inches(2.0))
    tf = tb.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = title
    p.font.name = FONT_HEADING
    p.font.size = Pt(13)
    p.font.bold = True
    p.font.color.rgb = C_NAVY_DARK
    p.space_after = Pt(6)

    p2 = tf.add_paragraph()
    p2.text = desc
    p2.font.name = FONT_BODY
    p2.font.size = Pt(11)
    p2.font.color.rgb = C_TEXT_DARK

# =============================================================================
# SLIDE 16: KẾT LUẬN & Q&A
# =============================================================================
s16 = prs.slides.add_slide(blank_slide_layout)
set_slide_background(s16, C_NAVY_DARK)

add_card(s16, Inches(1.5), Inches(1.2), Inches(10.333), Inches(5.1), bg_color=C_NAVY_LIGHT, border_color=C_BLUE_ACCENT)
tb = s16.shapes.add_textbox(Inches(1.8), Inches(1.5), Inches(9.733), Inches(4.5))
tf = tb.text_frame
tf.word_wrap = True

p = tf.paragraphs[0]
p.text = "KẾT LUẬN & THÔNG ĐIỆP ĐỀ TÀI"
p.font.name = FONT_HEADING
p.font.size = Pt(24)
p.font.bold = True
p.font.color.rgb = C_CYAN_TEAL
p.space_after = Pt(12)

recap_points = [
    ("Đóng góp khoa học nguyên gốc", "Giải quyết trọn vẹn 4 thách thức lớn của GenAI bằng thuật toán Attention CPU <0.2ms, cân chỉnh ECE <0.04, tối ưu Pareto 3D và Prefix Chaining."),
    ("Hiệu quả thực nghiệm ấn tượng", "Tiết kiệm 81% chi phí, giảm 64% độ trễ và duy trì 98.4% chất lượng trên tập dữ liệu chuẩn hóa 500 mẫu tiếng Việt."),
    ("Sản phẩm hoàn thiện cao độ", "100% mã nguồn mở FOSS, giao diện Web 3D trực quan, kiến trúc bền vững sẵn sàng triển khai diện rộng.")
]

for title, desc in recap_points:
    p = tf.add_paragraph()
    p.text = f"✔  {title}: {desc}"
    p.font.name = FONT_BODY
    p.font.size = Pt(12)
    p.font.color.rgb = C_WHITE
    p.space_after = Pt(8)

p_qa = tf.add_paragraph()
p_qa.text = "XIN TRÂN TRỌNG CẢM ƠN HỘI ĐỒNG GIÁM KHẢO VÀ QUÝ THẦY CÔ!"
p_qa.font.name = FONT_HEADING
p_qa.font.size = Pt(16)
p_qa.font.bold = True
p_qa.font.color.rgb = C_CYAN_TEAL
p_qa.space_before = Pt(14)
p_qa.alignment = PP_ALIGN.CENTER

p_sub = tf.add_paragraph()
p_sub.text = "Nhóm nghiên cứu sẵn sàng lắng nghe và trả lời các câu hỏi phản biện."
p_sub.font.name = FONT_BODY
p_sub.font.size = Pt(12)
p_sub.font.color.rgb = RGBColor(203, 213, 225)
p_sub.alignment = PP_ALIGN.CENTER

prs.save(OUTPUT_PATH)
print(f"Successfully generated presentation at: {OUTPUT_PATH}")
