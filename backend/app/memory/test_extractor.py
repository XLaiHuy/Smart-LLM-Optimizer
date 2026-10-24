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
