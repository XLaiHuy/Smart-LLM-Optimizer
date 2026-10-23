from app.optimizers.prompt_analyzer import analyze_prompt


def test_vietnamese_negation_is_protected() -> None:
    prompt = "Kh" + chr(0xF4) + "ng duoc xoa thong tin."
    analysis = analyze_prompt(
        prompt,
        compression_threshold=0,
    )

    assert analysis.has_negation is True
    assert any(
        span.kind == "negation" and span.text == "Kh" + chr(0xF4) + "ng"
        for span in analysis.protected_spans
    )


def test_markdown_url_does_not_include_trailing_punctuation() -> None:
    analysis = analyze_prompt(
        "Xem [tai lieu](https://example.com/docs).",
        compression_threshold=0,
    )

    urls = [span for span in analysis.protected_spans if span.kind == "url"]
    assert len(urls) == 1
    assert urls[0].text == "[tai lieu](https://example.com/docs)"


def test_ascii_vietnamese_negation_is_protected() -> None:
    analysis = analyze_prompt("Khong duoc xoa gia tri.", compression_threshold=0)

    assert analysis.has_negation is True
