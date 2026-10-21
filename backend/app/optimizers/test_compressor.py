from app.optimizers.compressor import (
    compress_rule_based,
    normalize_whitespace,
)


def test_normalize_whitespace_removes_extra_blank_lines() -> None:
    prompt = "A\n\n\n\nB"

    result = normalize_whitespace(prompt)

    assert result == "A\n\nB"


def test_compressor_skips_short_prompt() -> None:
    prompt = "Prompt ngắn."

    result = compress_rule_based(
        prompt,
        compression_threshold=100,
    )

    assert result.status == "skipped"
    assert result.compressed == prompt
    assert result.savings == 0


def test_compressor_preserves_number_and_url() -> None:
    prompt = (
        "Không được xóa số 10% và URL "
        "https://example.com.   \n\n\nDòng tiếp theo."
    )

    result = compress_rule_based(
        prompt,
        compression_threshold=1,
    )

    assert "10%" in result.compressed
    assert "https://example.com" in result.compressed
    assert "\n\nDòng tiếp theo." in result.compressed
    assert result.status == "applied"

def test_remove_trailing_whitespace() -> None:
    prompt = "Hello world   \nNext line   "

    result = normalize_whitespace(prompt)

    assert result == "Hello world\nNext line"


def test_preserve_code_block() -> None:
    prompt = (
        "Explain:\n"
        "```python\n"
        "x = 10    \n"
        "\n\n\n"
        "print(x)\n"
        "```\n\n\n"
        "Thank you"
    )

    result = normalize_whitespace(prompt)

    assert "x = 10    \n" in result
    assert "\n\n\nprint(x)" in result
    assert result.endswith("\n\nThank you")


def test_no_token_savings() -> None:
    prompt = "Explain machine learning."

    result = compress_rule_based(
        prompt,
        compression_threshold=1,
    )

    assert result.status == "skipped"
    assert result.reason == "no_token_savings"
    assert result.savings == 0
    assert result.compressed_tokens < result.original_tokens
    assert result.compressed == prompt


def test_compression_metrics() -> None:
    prompt = "Explain AI.    \n\n\n\nExplain ML."

    result = compress_rule_based(
        prompt,
        compression_threshold=1,
    )

    assert result.savings == (
        result.original_tokens - result.compressed_tokens
    )

    assert result.ratio == (
        result.compressed_tokens / result.original_tokens
    )

    assert result.compressed_tokens <= result.original_tokens