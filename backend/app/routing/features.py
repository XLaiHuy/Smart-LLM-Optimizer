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
    profile = extract_features(text)
    code_bytes = sum(len(m.group().encode("utf-8")) for m in re.finditer(r"```.*?```", text, re.S))
    return profile.model_copy(
        update={
            "total_input_bytes": len(text.encode("utf-8")),
            "has_rag_context": has_rag,
            "code_ratio": code_bytes / max(1, len(text.encode("utf-8"))),
            # Keyword detection is a heuristic, not a request for enforced JSON Schema.
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
