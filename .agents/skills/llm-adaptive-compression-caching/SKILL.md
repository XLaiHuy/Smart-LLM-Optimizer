---
name: llm-adaptive-compression-caching
description: Chiến lược tối ưu hóa prompt qua nén ngữ nghĩa thích ứng (LLMLingua entropy), kiểm định bảo toàn thực thể cốt lõi (numbers, formulas, code), và cấu trúc prompt tối đa hóa Prefix Caching.
---

# LLM Adaptive Prompt Compression & Prefix Caching

Kỹ năng chuyên sâu về tối ưu hóa độ dài prompt ngữ cảnh cho LLM: nén ngữ nghĩa thích ứng (LLMLingua entropy/perplexity token filtering), thuật toán kiểm định bảo toàn thông tin sống còn (Semantic Preservation Validation), và kỹ thuật kiến trúc prompt tương thích tối đa với bộ đệm KV-Cache / Prompt Caching của các nhà cung cấp mô hình.

## 1. Nguyên tắc cốt lõi (Core Principles)

### 1.1. Quy tắc Bảo toàn Thực thể Sống còn (Entity Shielding Rule)
Trước khi đưa qua bất kỳ mô hình nén token nào (LLMLingua, Perplexity dropping):
- **Phải nhận diện và bảo vệ tuyệt đối (100% Non-negotiable)**:
  - Tất cả các con số, số tiền, tỷ lệ phần trăm (ví dụ: `5 USD`, `15%`, `2026-10-22`).
  - Các công thức toán học, biểu thức logic, toán tử (`A + B = C`, `x >= 10`).
  - Tên bảng, tên trường dữ liệu trong CSDL, URL, email.
  - Các khối code blocks (Markdown code blocks ```...```) và chuỗi JSON schema.
- **Vùng được phép nén**: Các từ nối, thán từ, cấu trúc câu rườm rà, các đoạn lặp lại trong tài liệu RAG dài.

### 1.2. Kiểm định Bảo toàn Ngữ nghĩa (Semantic Preservation Validation)
Sau khi nén, đoạn văn bản đã nén phải vượt qua 2 chốt chặn:
1. **Kiểm tra mất mát thực thể (Entity Loss Gate)**: Tất cả thực thể số và mã định danh trong câu hỏi gốc phải có mặt đầy đủ trong câu đã nén.
2. **Ngưỡng tương đồng ngữ nghĩa (Embedding Cosine Similarity Gate)**:
   $$\text{CosineSim}(\mathbf{e}_{\text{original}}, \mathbf{e}_{\text{compressed}}) \ge 0.85$$
   Nếu không vượt qua ngưỡng, lập tức hủy bỏ bản nén và chuyển về nguyên bản (`PassThroughContext`).

### 1.3. Cấu trúc Prompt tối đa hóa Prefix Caching (KV-Cache Optimization)
Nhà cung cấp (Google Gemini, OpenAI, Claude) tính phí rẻ hơn tới 50% – 80% nếu phần đầu của Prompt (Prefix) trùng khớp hoàn toàn giữa các lượt gọi:
- **Thứ tự sắp xếp bắt buộc**:
  1. `[Tầng 1 - Cực kỳ tĩnh]`: System Prompt & Role definition (Không bao giờ thay đổi).
  2. `[Tầng 2 - Tĩnh theo phiên]`: Few-shot examples, Tool definitions, Tài liệu văn bản tham chiếu cố định.
  3. `[Tầng 3 - Tăng dần]`: Lịch sử các lượt chat trước (Turns 1..N-1).
  4. `[Tầng 4 - Biến động liên tục]`: Câu hỏi mới nhất của người dùng (Turn N) kèm thời gian thực (`current_timestamp`).
- **Tuyệt đối không chèn `current_time` vào đầu System Prompt**, vì điều này sẽ làm hỏng (invalidate) toàn bộ KV-Cache của nhà cung cấp.

---

## 2. Mã nguồn Mẫu Tái sử dụng (Reusable Python Implementations)

### 2.1. Bộ lọc bảo vệ thực thể và nén prompt Heuristic

```python
import re
from typing import Tuple, Set


class EntityPreservingCompressor:
    """Nén prompt an toàn với lá chắn bảo vệ thực thể số liệu và code."""

    # Regex trích xuất thực thể cần bảo vệ
    NUMBER_PATTERN = re.compile(r'\b\d+(?:[\.,]\d+)?%?\b')
    CODE_BLOCK_PATTERN = re.compile(r'```[\s\S]*?```')
    FORMULA_PATTERN = re.compile(r'[\$].*?[\$]|[\w]+\s*[=><+\-*/]\s*[\w]+')

    def __init__(self, target_ratio: float = 0.6):
        self.target_ratio = target_ratio

    def extract_critical_entities(self, text: str) -> Set[str]:
        """Thu thập danh sách tất cả các thực thể không được phép rơi rụng."""
        entities = set()
        for match in self.NUMBER_PATTERN.finditer(text):
            entities.add(match.group().strip())
        for match in self.FORMULA_PATTERN.finditer(text):
            entities.add(match.group().strip())
        return entities

    def compress_safe(self, text: str) -> Tuple[str, bool]:
        """Nén an toàn: loại bỏ từ đệm nhưng giữ nguyên thực thể."""
        critical_entities = self.extract_critical_entities(text)

        # Loại bỏ các đoạn đệm tiếng Việt phổ biến không mang ngữ nghĩa
        fillers = [
            r'\bthì là mà rằng\b',
            r'\bhãy cho tôi biết\b',
            r'\bvui lòng cho biết\b',
            r'\btôi muốn hỏi là\b',
            r'\bcó thể giúp tôi\b',
            r'\blàm ơn\b',
        ]

        compressed = text
        for pattern in fillers:
            compressed = re.sub(pattern, '', compressed, flags=re.IGNORECASE)

        # Chuẩn hóa khoảng trắng
        compressed = re.sub(r'\s+', ' ', compressed).strip()

        # Kiểm định: Đảm bảo không mất thực thể cốt lõi
        preserved_entities = self.extract_critical_entities(compressed)
        is_safe = critical_entities.issubset(preserved_entities)

        if not is_safe:
            # Fallback về văn bản gốc nếu rơi rụng thực thể
            return text, False

        return compressed, True
```

### 2.2. Kiểm định Tương đồng Ngữ nghĩa (Cosine Preservation Grader)

```python
import numpy as np


class SemanticPreservationValidator:
    """Đánh giá mức độ bảo toàn ngữ nghĩa sau nén."""

    @staticmethod
    def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))

    def validate(
        self,
        original_embedding: np.ndarray,
        compressed_embedding: np.ndarray,
        threshold: float = 0.85
    ) -> bool:
        score = self.cosine_similarity(original_embedding, compressed_embedding)
        return score >= threshold
```

---

## 3. Checklist Thực chiến cho LLM Optimizers

- [ ] Các con số tài chính, ngày tháng, phép tính toán học không bị thay đổi hoặc cắt cụt.
- [ ] Các đoạn mã nguồn (`def ...:`, JSON) không bị làm hỏng cú pháp bởi thuật toán nén.
- [ ] Phần System Prompt cố định được giữ nguyên vẹn ở đầu để tận dụng Prompt Caching.
- [ ] Có cơ chế fallback tự động về prompt gốc (`is_safe=False`) khi điểm tương đồng ngữ nghĩa rơi xuống dưới 0.85.
