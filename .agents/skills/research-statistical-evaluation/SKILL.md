---
name: research-statistical-evaluation
description: Phương pháp luận NCKH thực nghiệm định lượng chuẩn quốc tế: kiểm định ý nghĩa thống kê (Paired t-test, Wilcoxon), Bootstrap 95% Confidence Intervals, ma trận Ablation Study và xuất bảng LaTeX chuyên nghiệp.
---

# Research Statistical Evaluation & Scientific Benchmarking

Kỹ năng chuyên sâu về phương pháp luận nghiên cứu khoa học thực nghiệm, phân tích thống kê định lượng và thẩm định mô hình AI/LLM chuẩn mực cho bài báo khoa học (A*/Scopus) và Luận văn tốt nghiệp.

## 1. Nguyên tắc cốt lõi & Phương pháp luận (Methodology)

### 1.1. Luôn sử dụng Kiểm định Thống kê Có Cặp (Paired Statistical Tests)
Trong các thí nghiệm so sánh Router hoặc Prompt Optimizer trên cùng một tập benchmark (paired queries):
- **Không bao giờ dùng Independent Two-sample t-test** (vì các mẫu prompt có độ khó và phân bố token không đồng nhất giữa các câu).
- **Phân phối chuẩn (Parametric)**: Dùng **Paired Student's t-test** cho các đại lượng liên tục như độ trễ (latency ms) và chi phí thực tế (serving cost USD).
- **Phân phối phi chuẩn / Điểm số thứ bậc (Non-parametric)**: Dùng **Wilcoxon Signed-Rank Test** cho điểm chất lượng (Pass/Fail rate, Exact Match, Human Judge Likert 1-5).
- **Mức ý nghĩa thống kê chuẩn**:
  - $p < 0.05$ ($^*$ Có ý nghĩa thống kê)
  - $p < 0.01$ ($^{**}$ Rất có ý nghĩa)
  - $p < 0.001$ ($^{***}$ Cực kỳ có ý nghĩa)

### 1.2. Khoảng Tin cậy Bootstrap 95% (Bootstrap 95% Confidence Intervals)
Để khẳng định tỷ lệ tiết kiệm chi phí (Cost Savings %) hoặc P90 Latency không phải do ngẫu nhiên:
- Thực hiện **Non-parametric Bootstrap Resampling** với tối thiểu $B = 1,000$ lần lặp lại (có hoàn lại).
- Báo cáo kết quả dưới dạng:
  $$\text{Savings} = 6.1\% \quad [95\%\text{ CI: } 4.8\% - 7.5\%]$$
- Tránh kết luận quá mức (over-claiming) khi khoảng tin cậy bao gồm giá trị $0\%$ (không có sự khác biệt).

### 1.3. Thiết kế Ma trận Nghiên cứu Bóc tách (Ablation Study Matrix)
Một bài báo/luận văn thuyết phục bắt buộc phải có bảng Ablation chứng minh công lao của từng module độc lập:
1. **Full Hybrid Router**: MiniLM INT8 + 6 Attention Queries + GBDT 100 trees + Calibrated Threshold.
2. **Ablation 1 (No Attention)**: Chỉ dùng GBDT với numeric features (đối chứng xem Attention đóng góp bao nhiêu %).
3. **Ablation 2 (No Calibration)**: Dùng ngưỡng cố định $0.5$ thay vì Isotonic/Platt calibration.
4. **Ablation 3 (No Fallback)**: Tắt cơ chế fallback lên reference model khi gặp failure.

---

## 2. Mã nguồn Mẫu Tái sử dụng (Reusable Python Implementations)

### 2.1. Kiểm định Ý nghĩa Thống kê & Bootstrap Resampling

```python
import numpy as np
from scipy import stats
from typing import Dict, Tuple, Any


class StatisticalEvaluator:
    """Công cụ tính toán kiểm định thống kê và khoảng tin cậy khoa học."""

    @staticmethod
    def paired_significance_test(
        baseline_scores: np.ndarray,
        variant_scores: np.ndarray
    ) -> Dict[str, Any]:
        """Thực hiện Paired t-test và Wilcoxon signed-rank test."""
        diff = variant_scores - baseline_scores

        # 1. Paired t-test
        t_stat, t_pvalue = stats.ttest_rel(variant_scores, baseline_scores)

        # 2. Wilcoxon signed-rank test (cho non-parametric)
        try:
            w_stat, w_pvalue = stats.wilcoxon(variant_scores, baseline_scores)
        except ValueError:
            # Xảy ra khi tất cả diff = 0
            w_stat, w_pvalue = 0.0, 1.0

        # 3. Cohen's d effect size
        std_diff = np.std(diff, ddof=1)
        cohens_d = (np.mean(diff) / std_diff) if std_diff > 0 else 0.0

        return {
            "mean_difference": float(np.mean(diff)),
            "paired_t_statistic": float(t_stat),
            "paired_t_pvalue": float(t_pvalue),
            "wilcoxon_pvalue": float(w_pvalue),
            "cohens_d": float(cohens_d),
            "is_significant_p05": bool(t_pvalue < 0.05 or w_pvalue < 0.05),
        }

    @staticmethod
    def bootstrap_confidence_interval(
        data: np.ndarray,
        statistic_func=np.mean,
        n_resamples: int = 1000,
        alpha: float = 0.05
    ) -> Tuple[float, float, float]:
        """Tính toán 95% Bootstrap CI: (point_estimate, ci_lower, ci_upper)."""
        n = len(data)
        resample_stats = np.empty(n_resamples)

        rng = np.random.default_rng(seed=42)
        for i in range(n_resamples):
            sample = rng.choice(data, size=n, replace=True)
            resample_stats[i] = statistic_func(sample)

        ci_lower = float(np.percentile(resample_stats, 100 * (alpha / 2)))
        ci_upper = float(np.percentile(resample_stats, 100 * (1 - alpha / 2)))
        point_est = float(statistic_func(data))

        return point_est, ci_lower, ci_upper
```

### 2.2. Trình Xuất Bảng LaTeX Chuẩn Bài Báo (LaTeX Booktabs Generator)

```python
from typing import List, Dict


def export_ablation_to_latex(rows: List[Dict[str, Any]], caption: str, label: str) -> str:
    """Sinh mã bảng LaTeX chuyên nghiệp với booktabs và định dạng số chính xác."""
    latex = []
    latex.append("\\begin{table}[t]")
    latex.append("\\centering")
    latex.append(f"\\caption{{{caption}}}")
    latex.append(f"\\label{{{label}}}")
    latex.append("\\begin{tabular}{lcccc}")
    latex.append("\\toprule")
    latex.append("\\textbf{Configuration} & \\textbf{Pass Rate (\\%)} & \\textbf{Cost (USD)} & \\textbf{Savings (\\%)} & \\textbf{P50 Lat. (ms)} \\\\")
    latex.append("\\midrule")

    for r in rows:
        name = r["name"]
        pass_rate = f"{r['pass_rate']:.2f}"
        cost = f"\\${r['cost']:.4f}"
        savings = f"{r['savings']:.1f}\\%" if r["savings"] > 0 else "--"
        latency = f"{r['p50_latency']:.1f}"

        # Đánh dấu in đậm dòng tốt nhất
        if r.get("is_best", False):
            row_str = f"\\textbf{{{name}}} & \\textbf{{{pass_rate}}} & \\textbf{{{cost}}} & \\textbf{{{savings}}} & \\textbf{{{latency}}} \\\\"
        else:
            row_str = f"{name} & {pass_rate} & {cost} & {savings} & {latency} \\\\"
        latex.append(row_str)

    latex.append("\\bottomrule")
    latex.append("\\end{tabular}")
    latex.append("\\end{table}")

    return "\n".join(latex)
```

---

## 3. Checklist Thực hiện Đánh giá Nghiên cứu Khoa học

- [ ] Tập HOLDOUT tuyệt đối không bị rò rỉ vào quá trình huấn luyện hay tinh chỉnh siêu tham số.
- [ ] Mọi tuyên bố về hiệu năng tiết kiệm đều đi kèm giá trị p-value và khoảng tin cậy 95% CI.
- [ ] Bảng Ablation Study chỉ ra rõ vai trò của từng thành phần kỹ thuật.
- [ ] Không giả mạo nhãn (synthetic fake labels) để làm đẹp biểu đồ khi thiếu dữ liệu thực nghiệm.
