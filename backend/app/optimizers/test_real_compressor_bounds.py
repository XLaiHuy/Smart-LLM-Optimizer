"""No downloads/inference in unit tests: cover the failures observed with real weights."""

from types import SimpleNamespace

import pytest

from app.optimizers.llmlingua_compressor import LLMLinguaCompressor


def compressor(score=0.96):
    calls = []

    def compress(text, **kwargs):
        calls.append(text)
        return {"compressed_prompt": text.replace("general background", "background")}

    instance = LLMLinguaCompressor(lambda original, candidate: score)
    instance.compressor = SimpleNamespace(
        tokenizer=SimpleNamespace(encode=lambda text, **kwargs: text.split()),
        compress_prompt=compress,
    )
    return instance, calls


def test_repeated_paragraphs_reuse_inference_but_keep_order_and_count():
    instance, calls = compressor()
    text = "University general background information.\n\n" * 20 + "Reply only BLUE-851."
    result = instance.compress(text)
    assert len(calls) == 1
    assert result["compressed"].count("University background information.") == 20
    assert result["compressed"].endswith("Reply only BLUE-851.")
    assert result["preservation"] == "preserved"
    assert result["compressed_tokens"] < result["original_tokens"]


@pytest.mark.parametrize("score", [None, 0.2, float("nan")])
def test_unproven_paragraph_keeps_original(score):
    instance, _ = compressor(score)
    text = "University general background information.\n\nReply only BLUE-851."
    assert instance.compress(text)["compressed"] == text


def test_protected_paragraph_and_nonfinal_instructions_are_verbatim():
    instance, calls = compressor()
    protected = "An có 20 USD, Bình có 10 USD. Chọn người có không ít hơn 15 USD."
    instruction = "Chỉ trả lời bằng tiếng Việt."
    text = protected + "\n\n" + instruction + "\n\nUniversity general background.\n\nFinal task."
    result = instance.compress(text)
    assert protected in result["compressed"]
    assert instruction in result["compressed"]
    assert calls == ["University general background."]


def test_unique_work_limit_stops_before_inference():
    instance, calls = compressor()
    # Each paragraph fits the model window; aggregate unique work does not.
    text = "\n\n".join((word + " general background") * 100 for word in ("Alpha", "Beta", "Gamma"))
    text += "\n\nFinal task."
    result = instance.compress(text)
    assert result["reason"] == "compression_work_budget"
    assert result["compressed"] == text and not calls
