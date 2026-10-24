"""Observable features only. These heuristics do not predict task difficulty."""

import re

from app.contracts.dtos import ContextResult, ExecutionRequest, Message, TaskProfile


class ObservableTaskAnalyzer:
    def analyze(self, req: ExecutionRequest, prepared: ContextResult | None = None) -> TaskProfile:
        if prepared is None:
            return extract_features(req.request.message)
        return extract_context_features(prepared.messages, bool(req.request.document_ids))


def serving_text(messages: tuple[Message, ...]) -> str:
    """Versioned, role-preserving representation shared by training and serving."""
    return "\n".join(f"{m.role}: {m.content}" for m in messages)


def extract_context_features(messages: tuple[Message, ...], has_rag: bool = False) -> TaskProfile:
    text = serving_text(messages)
    # The active intent is driven by the user's current turn
    current_user_text = next((m.content for m in reversed(messages) if m.role == "user"), "")
    current_profile = extract_features(current_user_text if current_user_text else text)

    total_code_bytes = sum(len(m.group().encode("utf-8")) for m in re.finditer(r"```.*?```", text, re.S))
    total_bytes = len(text.encode("utf-8"))
    code_ratio = total_code_bytes / max(1, total_bytes)

    # If the user's current turn is a simple short inquiry (e.g. "1+1= mấy?", "xin chào"),
    # we must NOT let historical assistant responses falsely tag this turn as domain='code' or 'structured'
    lower_user = current_user_text.casefold()
    code_keywords = ("code", "lập trình", "hàm", "thuật toán", "viết hàm", "debug", "sửa lỗi", "class", "def ", "function")
    is_simple_turn = (
        len(current_user_text.split()) < 20
        and "```" not in current_user_text
        and not any(k in lower_user for k in code_keywords)
    )

    if is_simple_turn:
        domain = "general"
    else:
        if "```" in current_user_text or any(k in lower_user for k in code_keywords):
            domain = "code"
        else:
            domain = current_profile.domain

    return current_profile.model_copy(
        update={
            "domain": domain,
            "total_input_bytes": total_bytes,
            "has_rag_context": has_rag,
            "code_ratio": code_ratio,
            "json_schema_required": False,
        }
    )


def extract_features(text: str) -> TaskProfile:
    lower = text.casefold()
    structured = any(marker in lower for marker in ("json", "schema"))
    code = "```" in text
    size = len(text.encode("utf-8"))
    rules = tuple(
        name for flag, name in ((structured, "structured_keyword"), (code, "code_fence")) if flag
    )
    language = "vi" if any(c in lower for c in "ăâđêôơưáàảãạếệốộứự") else "unknown"
    return TaskProfile(
        domain="structured" if structured else "code" if code else "general",
        reason="observable_rules_v1",
        language=language,
        requires_structured=structured,
        rules_matched=rules,
        input_utf8_bytes=size,
        length_tier="long" if size > 4096 else "short",
    )
