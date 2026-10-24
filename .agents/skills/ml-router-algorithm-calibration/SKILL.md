---
name: ml-router-algorithm-calibration
description: Thuật toán định tuyến ML Router: huấn luyện Attention Multi-label BCE, đo lường & cân chỉnh độ tin cậy ECE (Isotonic/Platt), biên dịch cây quyết định GBDT sang pure Python (<0.5ms), và sàng lọc mặt biên Pareto đa mục tiêu.
---

# ML Router Algorithm & Calibration Engineering

Kỹ năng chuyên sâu về kỹ thuật thuật toán Định tuyến Mô hình Đa nhiệm (Dynamic Multi-LLM Routing): kiến trúc Attention Multi-label BCE, đo lường và cân chỉnh độ tin cậy xác suất (Expected Calibration Error - ECE, Isotonic Regression, Platt Scaling), kỹ thuật biên dịch cây quyết định GBDT sang pure Python tối ưu thời gian thực (<0.5ms CPU), và thuật toán chọn lọc mặt biên Pareto đa mục tiêu.

## 1. Nguyên tắc cốt lõi & Thuật toán (Algorithms)

### 1.1. Attention Multi-Label BCE Formulation
Thay vì phân loại multi-class một nhãn duy nhất (vốn không thể hiện được việc câu hỏi có thể giải được bởi nhiều model khác nhau), router giải bài toán **Multi-label Binary Classification**:
- Với mỗi model ứng viên $c \in \{\text{small}, \text{medium}, \text{reference}\}$, mô hình dự đoán xác suất trả lời đạt yêu cầu:
  $$\hat{p}_c = \sigma(\mathbf{w}_c^T \mathbf{h}_{\text{query}} + b_c) \in [0, 1]$$
- Hàm mất mát tối ưu hóa:
  $$\mathcal{L}_{\text{BCE}} = -\frac{1}{C} \sum_{c=1}^C \left[ y_c \log \hat{p}_c + (1 - y_c) \log (1 - \hat{p}_c) \right]$$
- **6 Attention Queries**: Tương ứng 6 chiều năng lực: Math, Code, Creative/Open, Reasoning, Extraction, Multilingual.

### 1.2. Đo lường & Cân chỉnh Xác suất (Post-hoc Probability Calibration)
Đầu ra từ GBDT hay neural network thường bị tự tin thái quá (over-confident) hoặc kém tự tin. Để làm căn cứ định tuyến an toàn:
1. **Expected Calibration Error (ECE)**:
   Chia dải xác suất $[0, 1]$ thành $M = 10$ bins:
   $$\text{ECE} = \sum_{m=1}^M \frac{|B_m|}{N} \left| \text{acc}(B_m) - \text{conf}(B_m) \right|$$
2. **Phương pháp cân chỉnh**:
   - **Platt Scaling**: Huấn luyện một hàm Logistic Sigmoid $P(y=1|f) = \frac{1}{1 + \exp(A \cdot f + B)}$ trên tập Calibration tách biệt.
   - **Isotonic Regression**: Hàm đơn điệu phi tham số (non-parametric monotonic step function) phù hợp khi dữ liệu calibration đủ lớn ($N > 500$).

### 1.3. Biên dịch Cây Quyết định sang Pure Python (Tree Compiler)
Để router có độ trễ cực thấp (P90 CPU latency $< 0.5\text{ ms}$) và không cần phụ thuộc thư viện scikit-learn/LightGBM nặng nề khi phục vụ production:
- Duyệt cây quyết định và sinh mã Python dạng mảng phẳng (flat array) hoặc các nhánh `if-else` lồng nhau.
- Bỏ qua toàn bộ overhead tạo Python objects hay matrix multiplication khi inference 1 mẫu.

### 1.4. Lọc Mặt biên Pareto Đa mục tiêu (Pareto Non-dominated Sorting)
Chọn model tối ưu dựa trên 3 tiêu chí:
- Tối đa hóa: Calibrated Pass Probability $P(c)$
- Tối thiểu hóa: Cost USD $C(c)$
- Tối thiểu hóa: Latency ms $L(c)$
Một model $A$ được coi là **áp đảo (dominates)** model $B$ nếu $A$ không tệ hơn $B$ ở cả 3 tiêu chí và tốt hơn $B$ ở ít nhất 1 tiêu chí. Tập các model không bị model nào khác áp đảo tạo thành **Pareto Frontier**.

---

## 2. Mã nguồn Mẫu Tái sử dụng (Reusable Python Implementations)

### 2.1. Tính toán ECE và Cân chỉnh Isotonic/Platt

```python
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from typing import Dict, Any, Tuple


class ProbabilityCalibrator:
    """Đo lường sai số ECE và hiệu chỉnh xác suất router."""

    @staticmethod
    def calculate_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> Dict[str, Any]:
        """Tính Expected Calibration Error (ECE) và Maximum Calibration Error (MCE)."""
        bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
        ece = 0.0
        mce = 0.0
        n_samples = len(y_true)

        bin_accuracies = []
        bin_confidences = []

        for i in range(n_bins):
            bin_mask = (y_prob >= bin_edges[i]) & (y_prob < bin_edges[i + 1])
            if i == n_bins - 1:
                bin_mask = bin_mask | (y_prob == 1.0)

            bin_size = np.sum(bin_mask)
            if bin_size > 0:
                acc = float(np.mean(y_true[bin_mask]))
                conf = float(np.mean(y_prob[bin_mask]))
                diff = abs(acc - conf)
                ece += (bin_size / n_samples) * diff
                mce = max(mce, diff)
                bin_accuracies.append(acc)
                bin_confidences.append(conf)
            else:
                bin_accuracies.append(0.0)
                bin_confidences.append((bin_edges[i] + bin_edges[i + 1]) / 2)

        return {
            "ece": float(ece),
            "mce": float(mce),
            "bin_accuracies": bin_accuracies,
            "bin_confidences": bin_confidences,
        }

    @classmethod
    def fit_isotonic(cls, cal_scores: np.ndarray, cal_labels: np.ndarray) -> IsotonicRegression:
        """Cân chỉnh đơn điệu phi tham số."""
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(cal_scores, cal_labels)
        return iso
```

### 2.2. Biên dịch Cây Quyết định sang Flat Array Pure Python

```python
from typing import Dict, Any, List


class TreeCompiler:
    """Biên dịch cây scikit-learn DecisionTree sang mảng phẳng thực thi thuần túy."""

    @staticmethod
    def export_tree_dict(tree) -> Dict[str, Any]:
        tree_ = tree.tree_
        return {
            "children_left": tree_.children_left.tolist(),
            "children_right": tree_.children_right.tolist(),
            "feature": tree_.feature.tolist(),
            "threshold": tree_.threshold.tolist(),
            "value": [v[0].tolist() for v in tree_.value],
        }

    @staticmethod
    def evaluate_compiled_tree(tree_dict: Dict[str, Any], features: List[float]) -> float:
        """Thực thi suy luận 1 cây mà không cần thư viện ngoài (siêu nhẹ < 5 micro-giây)."""
        node = 0
        children_left = tree_dict["children_left"]
        children_right = tree_dict["children_right"]
        feature = tree_dict["feature"]
        threshold = tree_dict["threshold"]
        value = tree_dict["value"]

        while children_left[node] != children_right[node]:  # Không phải leaf node
            feat_idx = feature[node]
            if features[feat_idx] <= threshold[node]:
                node = children_left[node]
            else:
                node = children_right[node]

        # Trả về xác suất class 1
        leaf_vals = value[node]
        total = sum(leaf_vals)
        return leaf_vals[1] / total if total > 0 else 0.0
```

---

## 3. Checklist Thuật toán & Triển khai

- [ ] Cân chỉnh Isotonic/Platt phải được fit hoàn toàn trên tập CALIBRATION độc lập, không dùng tập TRAIN (tránh overfitting) và không dùng HOLDOUT (tránh data leakage).
- [ ] GBDT Tree Compiler phải đạt kết quả dự đoán sai số tuyệt đối $< 10^{-6}$ so với `clf.predict_proba()` của scikit-learn.
- [ ] Thời gian trễ suy luận routing không được vượt quá $1\text{ ms}$ trên CPU cho 1 request.
- [ ] Luật an toàn: Nếu cả 3 candidate đều có xác suất dưới ngưỡng an toàn, router bắt buộc phải chọn model Reference mặc định.
