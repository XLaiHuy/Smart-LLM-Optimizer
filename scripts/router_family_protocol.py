"""Text-only source-family audit and original explicit MCQ answer extraction.

No model outputs or quality scores enter grouping. Similarity is a conservative
heuristic, not proof of semantic independence; every connected family stays together.
"""

import hashlib
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]


def explicit_gold(prompt: str, target: str) -> tuple[str, tuple[str, ...]] | None:
    options = tuple(
        c.upper()
        for c in re.findall(r"(?:^|\n)[ \t]*([A-E])[.)][ \t]+", prompt, re.IGNORECASE)
    )
    if not 3 <= len(options) <= 5 or options != tuple("ABCDE"[: len(options)]):
        return None
    # Handle a publisher's explicit answer statement on any complete line.
    # Reject multipart solutions and conflicting final answers.
    if (
        len(
            {
                c.upper()
                for c in re.findall(
                    r"(?:^|\n)[ \t]*([A-E])[.)][ \t]+", target, re.IGNORECASE
                )
            }
        )
        > 1
    ):
        return None
    answers = re.findall(
        r"(?:^|\n)[ \t]*(?:(?:Chọn|Hãy chọn)[ \t]+)?(?:Đáp án|Câu trả lời|Lựa chọn)(?:[ \t]+(?:đúng|cần chọn))?(?:[ \t]+là)?[ \t]*:?[ \t]*([A-E])(?:[.) \t:]|$)",
        target,
        re.IGNORECASE,
    )
    first = target.strip().splitlines()[0] if target.strip() else ""
    match = re.match(r"^([A-E])[.)][ \t]+", first, re.IGNORECASE)
    if match:
        answers.append(match[1])
    letters = {a.upper() for a in answers}
    return (
        (next(iter(letters)), options)
        if len(letters) == 1 and letters <= set(options)
        else None
    )


def family_map(texts: dict[str, str], similarity: float = 0.90) -> dict[str, str]:
    keys = sorted(texts)
    if not keys:
        return {}
    vectorizer = TfidfVectorizer(
        analyzer="char_wb", ngram_range=(3, 5), min_df=1, max_features=40000
    )
    matrix = vectorizer.fit_transform([texts[key] for key in keys])
    parents = list(range(len(keys)))

    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    # Batch the similarity matrix so the audit does not grow quadratically in RAM.
    for start in range(0, len(keys), 128):
        scores = (matrix[start : start + 128] @ matrix.T).toarray()
        for i, j in zip(*np.where(scores >= similarity), strict=True):
            i = int(i) + start
            j = int(j)
            if i < j:
                parents[find(j)] = find(i)
    groups: dict[int, list[str]] = {}
    for i, key in enumerate(keys):
        groups.setdefault(find(i), []).append(key)
    result = {}
    for members in groups.values():
        identity = (
            "text-family-v1:" + hashlib.sha256("\n".join(members).encode()).hexdigest()
        )
        result.update({key: identity for key in members})
    return result
