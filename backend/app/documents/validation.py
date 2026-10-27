import re

from app.contracts.dtos import Citation
from app.contracts.errors import AppError


def validate_citations(answer: str, citations: tuple[Citation, ...], mode: str) -> None:
    ids = {c.chunk_id for c in citations}
    referenced = set(re.findall(r"[\[【]([0-9a-f-]{36})[\]】]", answer))
    if not referenced.issubset(ids):
        raise AppError("OUTPUT_INVALID", 502, "Answer references an unknown source")
    has_filename_ref = any(
        bool(c.filename and c.filename.casefold() in answer.casefold()) for c in citations
    )
    if (
        mode == "live"
        and ids
        and not referenced
        and not has_filename_ref
        and not any(
            marker in answer.casefold()
            for marker in (
                "không đủ",
                "không tìm thấy",
                "chưa đủ",
                "không có",
                "chưa có",
                "insufficient",
                "not enough",
                "not found",
            )
        )
    ):
        raise AppError("OUTPUT_INVALID", 502, "Document answer lacks valid source references")
