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
