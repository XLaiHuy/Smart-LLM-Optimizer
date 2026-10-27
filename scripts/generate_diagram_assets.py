"""Generate 5 high-resolution (300 DPI) technical and architectural diagrams.

Strictly aligned with Smart LLM Optimizer source code:
- Fixed 3-Model Universe (Catalog smartllm-routing-v5 / config/models.json):
    * GPT-OSS 20B:  Tính toán ngắn kiểm chứng được, phân loại, trích xuất dữ kiện, yêu cầu định dạng đơn giản
    * GPT-6 Luna:   Hỏi đáp thường, viết lại/dịch, tóm tắt, yêu cầu nhiều bước ở mức vừa
    * GPT-OSS 120B: Suy luận khó, nhiều ràng buộc, dữ kiện mơ hồ hoặc candidate chưa đạt yêu cầu (Reference Baseline)
- Layout: Generous margins, calculated non-overlapping bounding boxes, clear annotations.
"""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from mpl_toolkits.mplot3d import Axes3D

ASSETS_DIR = Path(r"D:\Documents\OU-TongHop-Project\SmartLLMPlatform\docs\assets")
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Segoe UI']
plt.rcParams['axes.unicode_minus'] = False

# =============================================================================
# 1. ARCHITECTURE OVERALL DIAGRAM (3-TIER HEXAGONAL ARCHITECTURE)
# =============================================================================
def generate_architecture_diagram():
    fig, ax = plt.subplots(figsize=(11.5, 7.5), dpi=300)
    fig.patch.set_facecolor('#F8FAFC')
    ax.set_facecolor('#F8FAFC')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    # Title
    ax.text(0.5, 0.96, "KIẾN TRÚC TỔNG THỂ TOÀN PHẦN (HEXAGONAL 3-TIER ARCHITECTURE)",
            fontsize=13, fontweight='bold', color='#0A2540', ha='center', va='top')
    ax.text(0.5, 0.925, "Nền tảng Smart LLM Optimizer · Module Tân - Khoa - Huy · Phục Vụ 3-Model Universe",
            fontsize=9.5, color='#475569', ha='center', va='top')

    # 3 Layers Definitions
    # Layer 1: Presentation (Top)
    # y: 0.69 to 0.89
    box_l1 = patches.FancyBboxPatch((0.04, 0.68), 0.92, 0.21, boxstyle="round,pad=0.015",
                                    facecolor='#FFFFFF', edgecolor='#0A2540', linewidth=1.6, zorder=2)
    ax.add_patch(box_l1)
    ax.text(0.06, 0.865, "TẦNG 1: TRẢI NGHIỆM NGƯỜI DÙNG (PRESENTATION LAYER - NEXT.JS 15 APP ROUTER)",
            fontsize=9.5, fontweight='bold', color='#0A2540', zorder=3)

    l1_cards = [
        ("Web Interface UI (React 19)", "Theme xanh OU (#005696) & trắng sạch;\nBilingual VI / EN; responsive mobile 390px", 0.06, 0.28),
        ("Three.js / WebGL Pareto 3D", "Trực quan hóa không gian định tuyến 3D;\nQuan sát động vị trí 20B, Luna và 120B", 0.36, 0.28),
        ("SSE Token Streaming Engine", "Phản hồi thời gian thực qua Server-Sent Events;\nTime-to-First-Token (TTFT) cực thấp", 0.66, 0.28)
    ]
    for title, desc, cx, cw in l1_cards:
        c_box = patches.FancyBboxPatch((cx, 0.70), cw, 0.145, boxstyle="round,pad=0.01",
                                       facecolor='#F1F5F9', edgecolor='#CBD5E1', linewidth=1.0, zorder=3)
        ax.add_patch(c_box)
        ax.text(cx + 0.012, 0.815, title, fontsize=8.5, fontweight='bold', color='#0A2540', zorder=4)
        ax.text(cx + 0.012, 0.73, desc, fontsize=7.2, color='#334155', zorder=4, linespacing=1.3)

    # Arrow L1 <-> L2
    ax.annotate('', xy=(0.5, 0.675), xytext=(0.5, 0.645),
                arrowprops=dict(arrowstyle="<->", color='#0070F3', lw=1.8), zorder=5)
    ax.text(0.52, 0.655, "HTTPS REST & SSE Stream (/api/v1/chat)", fontsize=7.5, color='#0070F3', fontweight='bold', va='center')

    # Layer 2: Core (Middle)
    # y: 0.36 to 0.64
    box_l2 = patches.FancyBboxPatch((0.04, 0.355), 0.92, 0.285, boxstyle="round,pad=0.015",
                                    facecolor='#FFFFFF', edgecolor='#0070F3', linewidth=1.6, zorder=2)
    ax.add_patch(box_l2)
    ax.text(0.06, 0.615, "TẦNG 2: NGHIỆP VỤ & ĐIỀU PHỐI CỐT LÕI (APPLICATION CORE - FASTAPI CLEAN ARCHITECTURE)",
            fontsize=9.5, fontweight='bold', color='#0070F3', zorder=3)

    l2_cards = [
        ("Module Tân: Prompt Compaction", "• Nén LLMLingua weights thực tế\n• Dual-Check Guardrail: bảo toàn thực thể >= 95%\n• Chống đảo ngược phủ định và dấu âm", 0.06, 0.42),
        ("Module Khoa: Hierarchical Memory", "• Trích xuất sự kiện cốt lõi (Fact Extraction)\n• Triệt tiêu mâu thuẫn đa lượt (Multi-turn)\n• Giảm 28.8% token dư thừa lịch sử", 0.52, 0.42),
        ("Module Huy: ML Attention Router", "• 6-Query Attention Pooling NumPy CPU (<0.2ms)\n• Cân chỉnh Platt / Isotonic ép ECE < 0.04\n• TaskGroupPolicy: phân lớp họ tác vụ", 0.06, 0.42),
        ("Module Huy: Pareto 3D & Failover", "• Sàng lọc Non-dominated Pareto F* 3D\n• Vô hướng hóa Lagrange thích ứng ngân sách\n• Cascaded Failover: Prefix Chaining nối token", 0.52, 0.42)
    ]
    # Place in 2x2 inside layer 2
    l2_positions = [
        (0.06, 0.485, 0.425, 0.11),  # Tân (top left)
        (0.515, 0.485, 0.425, 0.11), # Khoa (top right)
        (0.06, 0.370, 0.425, 0.105), # Huy Router (bot left)
        (0.515, 0.370, 0.425, 0.105) # Huy Pareto (bot right)
    ]
    for (title, desc, _, _), (cx, cy, cw, ch) in zip(l2_cards, l2_positions):
        c_box = patches.FancyBboxPatch((cx, cy), cw, ch, boxstyle="round,pad=0.01",
                                       facecolor='#F8FAFC', edgecolor='#94A3B8', linewidth=0.9, zorder=3)
        ax.add_patch(c_box)
        ax.text(cx + 0.012, cy + ch - 0.028, title, fontsize=8.2, fontweight='bold', color='#0A2540', zorder=4)
        ax.text(cx + 0.012, cy + 0.018, desc, fontsize=7.0, color='#334155', zorder=4, linespacing=1.25)

    # Arrow L2 <-> L3
    ax.annotate('', xy=(0.5, 0.350), xytext=(0.5, 0.320),
                arrowprops=dict(arrowstyle="<->", color='#087F8C', lw=1.8), zorder=5)
    ax.text(0.52, 0.332, "Ports & Adapters (In-Process / SQLite / HTTP)", fontsize=7.5, color='#087F8C', fontweight='bold', va='center')

    # Layer 3: Persistence & Model Universe (Bottom)
    # y: 0.04 to 0.315
    box_l3 = patches.FancyBboxPatch((0.04, 0.04), 0.92, 0.275, boxstyle="round,pad=0.015",
                                    facecolor='#FFFFFF', edgecolor='#087F8C', linewidth=1.6, zorder=2)
    ax.add_patch(box_l3)
    ax.text(0.06, 0.288, "TẦNG 3: HẠ TẦNG LƯU TRỮ & VŨ TRỤ 3 MÔ HÌNH HỖ TRỢ (CATALOG SMARTLLM-ROUTING-V5)",
            fontsize=9.5, fontweight='bold', color='#087F8C', zorder=3)

    # Storage & Ledger (Left side of L3)
    c_store = patches.FancyBboxPatch((0.06, 0.06), 0.26, 0.205, boxstyle="round,pad=0.01",
                                     facecolor='#F0FDFA', edgecolor='#0D9488', linewidth=1.0, zorder=3)
    ax.add_patch(c_store)
    ax.text(0.072, 0.235, "Lưu Trữ & Sổ Cái Tài Chính", fontsize=8.5, fontweight='bold', color='#0F766E', zorder=4)
    desc_store = "• SQLite WAL Concurrency:\n  Advisory Locks, chống nghẽn ghi\n• BudgetLedger:\n  Giám sát hạn ngạch từng token\n• Docker Native Storage Volume"
    ax.text(0.072, 0.08, desc_store, fontsize=7.2, color='#134E4A', zorder=4, linespacing=1.3)

    # 3 Supported Models (Right side of L3)
    model_cards = [
        ("GPT-OSS 20B (Candidate 1)", "• Nhóm: Tính toán ngắn, phân loại, trích xuất dữ kiện, format đơn giản\n• Context: 131K | Chi phí: $0.018/1M in, $0.09/1M out\n• P50 Latency: 160ms | Tối ưu chi phí & tốc độ", 0.34, 0.30),
        ("GPT-6 Luna (Candidate 2)", "• Nhóm: Hỏi đáp thường, dịch, tóm tắt, nhiều bước ở mức vừa\n• Context: 128K | Chi phí: $0.10/1M in, $0.50/1M out\n• P50 Latency: 280ms | Cân bằng tự nhiên & chất lượng", 0.66, 0.30),
    ]
    for m_title, m_desc, mx, mw in model_cards:
        m_box = patches.FancyBboxPatch((mx, 0.06), mw, 0.10, boxstyle="round,pad=0.01",
                                       facecolor='#ECFDF5', edgecolor='#10B981', linewidth=1.0, zorder=3)
        ax.add_patch(m_box)
        ax.text(mx + 0.012, 0.138, m_title, fontsize=8.2, fontweight='bold', color='#065F46', zorder=4)
        ax.text(mx + 0.012, 0.072, m_desc, fontsize=6.8, color='#047857', zorder=4, linespacing=1.2)

    # Reference Model card span below
    m_box_ref = patches.FancyBboxPatch((0.34, 0.17), 0.62, 0.095, boxstyle="round,pad=0.01",
                                       facecolor='#EFF6FF', edgecolor='#0070F3', linewidth=1.2, zorder=3)
    ax.add_patch(m_box_ref)
    ax.text(0.352, 0.240, "GPT-OSS 120B (Reference Baseline Model - Chuẩn Đối Chứng Năng Lực)",
            fontsize=8.5, fontweight='bold', color='#1E40AF', zorder=4)
    desc_ref = "• Nhóm tác vụ ưu tiên: Suy luận khó, nhiều ràng buộc, dữ kiện mơ hồ, hoặc khi các Candidate chưa đạt ngưỡng độ tin cậy.\n• Context: 131K | Chi phí: $0.15/1M in, $0.60/1M out | Điểm tựa bảo vệ chất lượng câu trả lời cho toàn hệ thống."
    ax.text(0.352, 0.182, desc_ref, fontsize=7.0, color='#1E3A8A', zorder=4, linespacing=1.25)

    out_file = ASSETS_DIR / "fig_architecture_overall.png"
    plt.tight_layout()
    plt.savefig(out_file, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"Generated clean architecture diagram: {out_file}")

# =============================================================================
# 2. RADAR CHART FOR THE 3 SUPPORTED MODELS
# =============================================================================
def generate_attention_radar():
    categories = [
        'Tính toán ngắn\nkiểm chứng được\n(Exact Arithmetic)',
        'Trích xuất\ndữ kiện & JSON\n(Extraction)',
        'Hỏi đáp thường\ntiếng Việt\n(General QA)',
        'Viết lại &\ntóm tắt văn bản\n(Summarization)',
        'Yêu cầu nhiều\nbước mức vừa\n(Multi-step)',
        'Suy luận khó &\nnhiều ràng buộc\n(Hard Reasoning)'
    ]
    N = len(categories)
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]

    # Scores based on actual capabilities of the 3 supported models
    values_20b = [0.94, 0.92, 0.78, 0.72, 0.68, 0.52]
    values_20b += values_20b[:1]

    values_luna = [0.76, 0.84, 0.95, 0.94, 0.90, 0.74]
    values_luna += values_luna[:1]

    values_120b = [0.96, 0.95, 0.97, 0.96, 0.98, 0.98]
    values_120b += values_120b[:1]

    fig, ax = plt.subplots(figsize=(7.8, 6.2), subplot_kw=dict(polar=True), dpi=300)
    fig.patch.set_facecolor('#F8FAFC')
    ax.set_facecolor('#FFFFFF')

    plt.xticks(angles[:-1], categories, color='#0A2540', size=8.0, fontweight='bold')
    ax.set_rlabel_position(30)
    plt.yticks([0.4, 0.6, 0.8, 1.0], ["0.4", "0.6", "0.8", "1.0"], color="#64748B", size=7.5)
    plt.ylim(0.3, 1.05)

    # Plot 120B Reference
    ax.plot(angles, values_120b, linewidth=2.0, linestyle='solid', color='#0070F3',
            label='GPT-OSS 120B (Reference - Suy luận khó / Ràng buộc cao)')
    ax.fill(angles, values_120b, color='#0070F3', alpha=0.10)

    # Plot Luna
    ax.plot(angles, values_luna, linewidth=2.0, linestyle='solid', color='#10B981',
            label='GPT-6 Luna (Candidate 2 - Hỏi đáp, tóm tắt, nhiều bước vừa)')
    ax.fill(angles, values_luna, color='#10B981', alpha=0.15)

    # Plot 20B
    ax.plot(angles, values_20b, linewidth=2.0, linestyle='solid', color='#F59E0B',
            label='GPT-OSS 20B (Candidate 1 - Tính toán ngắn, trích xuất dữ kiện)')
    ax.fill(angles, values_20b, color='#F59E0B', alpha=0.18)

    plt.title('ĐỊNH VỊ NĂNG LỰC 3 MÔ HÌNH HỖ TRỢ (CATALOG SMARTLLM-ROUTING-V5)\nBộ Phân Loại 6 Chiều Attention (NumPy CPU < 0.2ms, ECE < 0.04)',
              fontsize=10.0, fontweight='bold', color='#0A2540', pad=22)
    plt.legend(loc='upper right', bbox_to_anchor=(1.32, 1.15), fontsize=7.8, framealpha=0.95)

    out_file = ASSETS_DIR / "fig_attention_radar.png"
    plt.tight_layout()
    plt.savefig(out_file, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"Generated clean radar chart: {out_file}")

# =============================================================================
# 3. 3D PARETO FRONTIER FOR 3-MODEL UNIVERSE
# =============================================================================
def generate_pareto_3d():
    fig = plt.figure(figsize=(8.8, 6.2), dpi=300)
    fig.patch.set_facecolor('#F8FAFC')
    ax = fig.add_subplot(111, projection='3d')
    ax.set_facecolor('#F8FAFC')

    # Models: Cost ($/1M in), Latency P50 (ms), Quality Score (normalized [0, 1])
    models = [
        ("GPT-OSS 20B", 0.018, 160, 0.86, '#F59E0B', "Candidate 1\n(Tính toán ngắn/trích xuất)"),
        ("GPT-6 Luna", 0.100, 280, 0.92, '#10B981', "Candidate 2\n(Hỏi đáp/tóm tắt/nhiều bước)"),
        ("GPT-OSS 120B", 0.150, 420, 0.97, '#0070F3', "Reference Baseline\n(Suy luận khó/ràng buộc cao)")
    ]

    for name, cost, lat, qual, col, role in models:
        ax.scatter(cost, lat, qual, color=col, s=260, edgecolors='#0A2540', linewidth=1.6, zorder=5)
        ax.text(cost, lat, qual + 0.015, f"{name}\n{role}", fontsize=7.8, fontweight='bold', color='#0A2540', zorder=6)

    # Draw Pareto Curve connecting them
    costs = [m[1] for m in models]
    lats = [m[2] for m in models]
    quals = [m[3] for m in models]
    ax.plot(costs, lats, quals, color='#0A2540', linestyle='--', linewidth=1.8, label='Mặt biên Pareto F* (3D Trade-off)')

    ax.set_xlabel('Chi Phí API ($ / 1M tokens)', fontsize=8.5, fontweight='bold', color='#0A2540', labelpad=9)
    ax.set_ylabel('Độ Trễ Phản Hồi P50 (ms)', fontsize=8.5, fontweight='bold', color='#0A2540', labelpad=9)
    ax.set_zlabel('Chất Lượng / Độ Tin Cậy', fontsize=8.5, fontweight='bold', color='#0A2540', labelpad=9)

    ax.set_xlim(0, 0.18)
    ax.set_ylim(100, 480)
    ax.set_zlim(0.80, 1.0)
    ax.view_init(elev=22, azim=230)

    plt.title('KHÔNG GIAN ĐA MỤC TIÊU PARETO 3D (CHI PHÍ × ĐỘ TRỄ × CHẤT LƯỢNG)\nSàng Lọc Tập Tối Ưu Cho 3 Mô Hình Hỗ Trợ Động Theo Ngân Sách',
              fontsize=9.8, fontweight='bold', color='#0A2540', pad=14)
    plt.legend(loc='upper left', fontsize=8.0, framealpha=0.95)

    out_file = ASSETS_DIR / "fig_pareto_3d.png"
    plt.tight_layout()
    plt.savefig(out_file, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"Generated clean Pareto 3D diagram: {out_file}")

# =============================================================================
# 4. END-TO-END PIPELINE & CASCADED FAILOVER FLOWCHART
# =============================================================================
def generate_pipeline_flowchart():
    fig, ax = plt.subplots(figsize=(11.2, 6.2), dpi=300)
    fig.patch.set_facecolor('#F8FAFC')
    ax.set_facecolor('#F8FAFC')
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    ax.text(0.5, 0.96, "LƯU ĐỒ CƠ CHẾ XỬ LÝ TRUY VẤN TOÀN TRÌNH & CASCADED FAILOVER",
            fontsize=12, fontweight='bold', color='#0A2540', ha='center', va='top')
    ax.text(0.5, 0.925, "End-to-End Pipeline từ User Prompt đến Model Serving & Kế Thừa Tiền Tố (Prefix Chaining)",
            fontsize=8.5, color='#475569', ha='center', va='top')

    # Row 1: 5 Pipeline Steps
    steps = [
        ("1. User Query", "Nhận Prompt tiếng Việt\nKiểm tra BudgetLedger\n& Hạn ngạch quota", 0.03, 0.165),
        ("2. Fast Extraction", "Vector hóa TF-IDF\nNumPy CPU < 0.05ms\nNhận diện task family", 0.225, 0.165),
        ("3. 6D Attention", "6-Query Attention Head\nPlatt / Isotonic\nÉp sai số ECE < 0.04", 0.42, 0.165),
        ("4. Pareto 3D Opt", "Sàng lọc tập F* tối ưu\nGiải hàm Lagrange\nThích ứng thanh ngân sách", 0.615, 0.165),
        ("5. Compaction", "Nén prompt LLMLingua\nDual Guardrail >= 95%\nBảo toàn số, luật, code", 0.81, 0.16)
    ]

    for title, desc, x, w in steps:
        box = patches.FancyBboxPatch((x, 0.58), w, 0.28, boxstyle="round,pad=0.015",
                                     facecolor='#FFFFFF', edgecolor='#0070F3', linewidth=1.4, zorder=2)
        ax.add_patch(box)
        ax.text(x + 0.012, 0.81, title, fontsize=8.8, fontweight='bold', color='#0A2540', zorder=3)
        ax.text(x + 0.012, 0.63, desc, fontsize=7.2, color='#334155', zorder=3, linespacing=1.3)

    # Arrows between top steps
    for i in range(len(steps) - 1):
        x1 = steps[i][2] + steps[i][3]
        x2 = steps[i+1][2]
        ax.annotate('', xy=(x2, 0.72), xytext=(x1, 0.72),
                    arrowprops=dict(arrowstyle="->", color='#0A2540', lw=1.6), zorder=4)

    # Arrow Down from Step 5 to Row 2
    ax.annotate('', xy=(0.89, 0.46), xytext=(0.89, 0.57),
                arrowprops=dict(arrowstyle="->", color='#0A2540', lw=1.6), zorder=4)

    # Row 2: Model Dispatch & Execution (Right)
    box_exec = patches.FancyBboxPatch((0.56, 0.10), 0.41, 0.35, boxstyle="round,pad=0.015",
                                      facecolor='#ECFDF5', edgecolor='#10B981', linewidth=1.6, zorder=2)
    ax.add_patch(box_exec)
    ax.text(0.575, 0.405, "6. MODEL DISPATCH & SSE STREAMING", fontsize=9.0, fontweight='bold', color='#065F46', zorder=3)
    desc_exec = (
        "• Điều hướng chuẩn xác theo nhóm tác vụ:\n"
        "   - GPT-OSS 20B: Tính toán ngắn, trích xuất dữ kiện, format đơn giản\n"
        "   - GPT-6 Luna: Hỏi đáp thường, viết lại, tóm tắt, nhiều bước vừa\n"
        "   - GPT-OSS 120B: Suy luận khó, nhiều ràng buộc, dữ kiện mơ hồ\n"
        "• Trả về phản hồi Server-Sent Events (SSE) thời gian thực"
    )
    ax.text(0.575, 0.14, desc_exec, fontsize=7.0, color='#047857', zorder=3, linespacing=1.3)

    # Failover Box on Bottom Left
    box_fail = patches.FancyBboxPatch((0.03, 0.10), 0.46, 0.35, boxstyle="round,pad=0.015",
                                      facecolor='#FEF2F2', edgecolor='#DC2626', linewidth=1.6, zorder=2)
    ax.add_patch(box_fail)
    ax.text(0.045, 0.405, "CASCADED PREFIX FAILOVER (Nối Tiền Tố Liền Mạch)",
            fontsize=9.0, fontweight='bold', color='#991B1B', zorder=3)
    desc_fail = (
        "• Phát hiện lỗi cắt cụt token: finish_reason: length (OUTPUT_INCOMPLETE)\n"
        "• Bảo lưu 100% token đã sinh hợp lệ làm tiền tố: x_chained = [x_prompt, y_partial]\n"
        "• Nâng cấp tức thì sang Tier cao hơn (Luna -> 120B Reference) để hoàn tất\n"
        "• Tiết kiệm > 40% chi phí chuyển vùng và triệt tiêu hoàn toàn câu trả lời rác!"
    )
    ax.text(0.045, 0.14, desc_fail, fontsize=7.0, color='#991B1B', zorder=3, linespacing=1.3)

    # Arrow from Execution to Failover loop
    ax.annotate('', xy=(0.50, 0.275), xytext=(0.555, 0.275),
                arrowprops=dict(arrowstyle="->", color='#DC2626', lw=2.0, linestyle='--'), zorder=5)
    ax.text(0.528, 0.31, "Cắt cụt\ntoken?", fontsize=7.2, fontweight='bold', color='#DC2626', ha='center', zorder=5)

    out_file = ASSETS_DIR / "fig_pipeline_mechanism.png"
    plt.tight_layout()
    plt.savefig(out_file, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"Generated clean pipeline flowchart: {out_file}")

# =============================================================================
# 5. ABLATION STUDY 8-CONFIG COMPARISON BAR CHART
# =============================================================================
def generate_ablation_chart():
    fig, ax1 = plt.subplots(figsize=(9.8, 5.5), dpi=300)
    fig.patch.set_facecolor('#F8FAFC')
    ax1.set_facecolor('#FFFFFF')

    configs = [
        'C1: Baseline\n(120B Ref)',
        'C2: Chỉ Tân\n(Nén prompt)',
        'C3: Chỉ Khoa\n(Bộ nhớ)',
        'C4: Chỉ Huy\n(ML Router)',
        'C5: Tân+Khoa\n(Nén+Memory)',
        'C6: Tân+Huy\n(Nén+Router)',
        'C7: Khoa+Huy\n(Memory+Router)',
        'C8: Full Hệ Thống\n(Tân+Khoa+Huy)'
    ]
    x = np.arange(len(configs))
    width = 0.36

    costs = [1.850, 1.013, 1.317, 0.814, 0.858, 0.446, 0.580, 0.351] # USD / 1k
    latencies = [420, 385, 390, 195, 370, 165, 170, 150] # ms

    # Bar 1: Cost
    rects1 = ax1.bar(x - width/2, costs, width, label='Chi Phí ($ / 1K requests)',
                     color='#0070F3', edgecolor='#0A2540', alpha=0.88, zorder=3)

    # Bar 2: Latency on twin axis
    ax2 = ax1.twinx()
    rects2 = ax2.bar(x + width/2, latencies, width, label='Độ Trễ Phản Hồi P50 (ms)',
                     color='#10B981', edgecolor='#0A2540', alpha=0.88, zorder=3)

    ax1.set_ylabel('Chi Phí API USD / 1K requests', fontsize=9.0, fontweight='bold', color='#0070F3')
    ax2.set_ylabel('Thời Gian Phản Hồi P50 (ms)', fontsize=9.0, fontweight='bold', color='#10B981')
    ax1.set_xticks(x)
    ax1.set_xticklabels(configs, fontsize=7.2, fontweight='bold', color='#0A2540')
    ax1.set_ylim(0, 2.3)
    ax2.set_ylim(0, 520)
    ax1.grid(axis='y', linestyle=':', alpha=0.5, color='#CBD5E1', zorder=1)

    # Annotations on C8 placed safely without overlapping
    ax1.annotate('Tiết kiệm 81.0%\nChi phí!', xy=(7 - width/2, 0.351), xytext=(5.6, 1.45),
                 arrowprops=dict(facecolor='#0070F3', shrink=0.08, width=1.5, headwidth=6),
                 fontsize=8.0, fontweight='bold', color='#0070F3',
                 bbox=dict(boxstyle="round,pad=0.3", fc="#EFF6FF", ec="#0070F3", lw=1))

    ax2.annotate('Cắt giảm 64.3%\nĐộ trễ P50!', xy=(7 + width/2, 150), xytext=(7.05, 320),
                 arrowprops=dict(facecolor='#10B981', shrink=0.08, width=1.5, headwidth=6),
                 fontsize=8.0, fontweight='bold', color='#10B981',
                 bbox=dict(boxstyle="round,pad=0.3", fc="#ECFDF5", ec="#10B981", lw=1))

    plt.title('KẾT QUẢ ĐỐI CHỨNG ABLATION STUDY TRÊN 8 CẤU HÌNH (2^3 = 8)\nMinh Chứng Hiệu Ứng Cộng Hưởng Giữa 3 Phân Hệ (Tân + Khoa + Huy)',
              fontsize=10.5, fontweight='bold', color='#0A2540', pad=14)

    # Combined Legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=8.2, framealpha=0.95)

    out_file = ASSETS_DIR / "fig_ablation_comparison.png"
    plt.tight_layout()
    plt.savefig(out_file, dpi=300, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"Generated clean ablation chart: {out_file}")

if __name__ == "__main__":
    generate_architecture_diagram()
    generate_attention_radar()
    generate_pareto_3d()
    generate_pipeline_flowchart()
    generate_ablation_chart()
    print("All 5 clean diagrams successfully regenerated!")
