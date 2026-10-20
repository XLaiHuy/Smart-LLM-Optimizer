import re

from app.contracts.dtos import Citation
from app.contracts.errors import AppError


def validate_citations(answer: str, citations: tuple[Citation, ...], mode: str) -> None:
    ids = {c.chunk_id for c in citations}
    referenced = set(re.findall(r"\[([0-9a-f-]{36})\]", answer))
    if not referenced.issubset(ids):
        raise AppError("OUTPUT_INVALID", 502, "Answer references an unknown source")
    if (
        mode == "live"
        and ids
        and not referenced
        and not any(
            marker in answer.casefold()
            for marker in ("kh?ng ??", "kh?ng t?m th?y", "insufficient", "not enough", "not found")
        )
    ):
        raise AppError("OUTPUT_INVALID", 502, "Document answer lacks valid source references")
