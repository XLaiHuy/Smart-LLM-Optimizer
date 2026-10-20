"""Observable features only. These heuristics do not predict task difficulty."""

from app.contracts.dtos import ExecutionRequest, TaskProfile


class ObservableTaskAnalyzer:
    def analyze(self, req: ExecutionRequest) -> TaskProfile:
        return extract_features(req.request.message)


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
