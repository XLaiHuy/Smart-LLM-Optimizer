import pytest

from app.memory.extractor import extract_explicit_facts


def test_extracts_only_explicit_facts() -> None:
    facts = extract_explicit_facts(
        "My name is An. The deadline is Friday. I prefer concise answers.", "m1"
    )

    assert [(fact.key, fact.value) for fact in facts] == [
        ("name", "An"),
        ("preference", "concise answers"),
        ("deadline", "Friday"),
    ]


def test_ambiguous_text_is_not_saved() -> None:
    assert extract_explicit_facts("We discussed the deadline.", "m1") == ()


@pytest.mark.parametrize(
    "question",
    [
        "Nhắc lại tên tôi, ngành học, trường, đề tài nghiên cứu và hạn chót mới nhất.",
        "Tên tôi, ngành học, trường, đề tài và hạn chót mới nhất là gì?",
        "Tên tôi là gì?",
        "Hạn chót là gì?",
        "What is my deadline?",
        "Bạn nhớ tôi học tại đâu?",
    ],
)
def test_recall_queries_do_not_become_explicit_facts(question):
    assert extract_explicit_facts(question, "q") == ()


def test_nested_deadline_correction_keeps_only_new_value():
    facts = extract_explicit_facts(
        "Tôi cập nhật hạn chót: hạn chót là 25/11/2026, thay cho 18/11/2026. Chỉ xác nhận ngắn.",
        "m2",
    )
    assert len(facts) == 1 and facts[0].key == "deadline"
    assert facts[0].value.startswith("25/11/2026")


def test_extracts_explicit_vietnamese_facts() -> None:
    facts = extract_explicit_facts(
        "Tên tôi là Tân. Tôi ưu tiên câu trả lời ngắn. Hạn chót là thứ Sáu.", "m1"
    )

    assert [(fact.key, fact.value) for fact in facts] == [
        ("name", "Tân"),
        ("preference", "câu trả lời ngắn"),
        ("deadline", "thứ Sáu"),
    ]


def test_extracts_profile_facts_in_vietnamese_with_or_without_accents() -> None:
    facts = extract_explicit_facts(
        "Tôi tên Tân. Tôi học ngành Kỹ thuật phần mềm. "
        "Tôi học tại Đại học Mở TP.HCM. "
        "Đề tài nghiên cứu của tôi là tối ưu prompt cho LLM. "
        "Han chot nop bao cao la ngay 30/10.",
        "m1",
    )

    assert [(fact.key, fact.value) for fact in facts] == [
        ("name", "Tân"),
        ("deadline", "ngay 30/10"),
        ("major", "Kỹ thuật phần mềm"),
        ("school", "Đại học Mở TP.HCM"),
        ("research_topic", "tối ưu prompt cho LLM"),
    ]
