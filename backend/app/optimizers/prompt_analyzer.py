import re
from dataclasses import dataclass

import tiktoken


@dataclass(frozen=True)
class ProtectedSpan:
    kind: str
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class PromptAnalyzer:
    token_count: int
    protected_spans: tuple[ProtectedSpan, ...]
    has_code: bool
    has_json: bool
    has_url: bool
    has_negation: bool
    should_compress: bool


_ENCODING = tiktoken.get_encoding("cl100k_base")

_CODE_PATTERN = re.compile(r"```.*?```", re.DOTALL)

_URL_PATTERN = re.compile(r"(?:\[[^\]]+\]\(https?://[^)\s]+\)|https?://[^\s<>()]+)")

_VIETNAMESE_NEGATION_PATTERN = re.compile(
    r"\b(?:không|chưa|chẳng|khong|chua|chang)\b",
    re.IGNORECASE,
)

_JSON_KEY_PATTERN = re.compile(r'"[^"]+"\s*:')

_UTF8_VIETNAMESE_NEGATION_PATTERN = re.compile(
    r"\b(?:kh\u00f4ng|ch\u01b0a|ch\u1eb3ng|khong|chua|chang)\b",
    re.IGNORECASE,
)

_NEGATION_PATTERN = re.compile(
    r"\b(?:không|chưa|chẳng|not|never|cannot|"
    r"must\s+not|do\s+not|don't|isn't|can't|won't)\b",
    re.IGNORECASE,
)

_NUMBER_PATTERN = re.compile(
    r"(?<!\w)\d+(?:[.,]\d+)*(?:\s*(?:%|kg|km|USD|VND))?(?!\w)",
    re.IGNORECASE,
)


def extract_spans(
    prompt: str,
    pattern: re.Pattern[str],
    kind: str,
) -> list[ProtectedSpan]:

    return [
        ProtectedSpan(
            kind=kind,
            text=match.group(),
            start=match.start(),
            end=match.end(),
        )
        for match in pattern.finditer(prompt)
    ]


def analyze_prompt(
    prompt: str,
    compression_threshold: int = 1000,
) -> PromptAnalyzer:

    token_count = len(_ENCODING.encode(prompt))

    code_matches = extract_spans(prompt, _CODE_PATTERN, "code")
    url_matches = extract_spans(prompt, _URL_PATTERN, "url")
    json_matches = extract_spans(prompt, _JSON_KEY_PATTERN, "json_key")
    negation_matches = extract_spans(
        prompt,
        _NEGATION_PATTERN,
        "negation",
    ) + extract_spans(prompt, _UTF8_VIETNAMESE_NEGATION_PATTERN, "negation")
    number_matches = extract_spans(prompt, _NUMBER_PATTERN, "number")

    all_spans = code_matches + url_matches + json_matches + negation_matches + number_matches
    unique_spans = {(span.kind, span.text, span.start, span.end): span for span in all_spans}
    protected_spans = tuple(
        sorted(unique_spans.values(), key=lambda span: (span.start, span.end, span.kind))
    )

    return PromptAnalyzer(
        token_count=token_count,
        protected_spans=protected_spans,
        has_code=bool(code_matches),
        has_json=bool(json_matches),
        has_url=bool(url_matches),
        has_negation=bool(negation_matches),
        should_compress=token_count >= compression_threshold,
    )
