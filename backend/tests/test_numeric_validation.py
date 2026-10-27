import pytest

from app.core.numeric_validation import numeric_answer_verdict


@pytest.mark.parametrize(
    "prompt,answer,expected",
    [
        (
            "Một giá trị giảm 2% còn 8722. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số.",
            "8899",
            False,
        ),
        (
            "Một giá trị giảm 2% còn 8722. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số.",
            "8900",
            True,
        ),
        ("Một giá trị giảm 20% còn 96. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số.", "120", True),
        ("Giảm 15% của 200, giá trị còn lại là bao nhiêu? Chỉ trả lời số.", "170", True),
        ("Tính (−313) + (−211). Chỉ trả lời kết quả, giữ dấu âm.", "-524", True),
        ("Tính (−313) + (−211). Chỉ trả lời kết quả, giữ dấu âm.", "524", False),
        ("Tính 1 / 0. Chỉ trả lời số.", "undefined", None),
        ("Tính 2 ** 100000. Chỉ trả lời số.", "4", None),
        ("Một giá trị giảm 100% còn 0. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số.", "0", None),
        (
            "Một giá trị giảm 2% còn 8722. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số. Sau đó làm tròn.",
            "8899",
            None,
        ),
        ("Tính 1 + 1. Chỉ trả lời số.", "nan", False),
        ("1+1 bằng mấy? Trả lời bằng chữ.", "Hai", None),
        ("Tính 1000000000000000 + 1. Chỉ trả lời số.", "1000000000000000", False),
        ("Tính 1 / 3. Chỉ trả lời số.", "0.333333", None),
    ],
)
def test_numeric_guard_uses_only_unambiguous_supported_requests(prompt, answer, expected):
    assert numeric_answer_verdict(prompt, answer) is expected


async def test_known_wrong_numeric_output_is_not_committed_or_retried(client, app):
    from app.contracts.dtos import ProviderResult

    class WrongProvider:
        calls = 0

        async def generate(self, messages, opts):
            self.calls += 1
            return ProviderResult(text="8899", execution_source="live", duration_ms=1)

    provider = WrongProvider()
    app.state.container.orchestrator.provider = provider
    sid = (await client.post("/v1/sessions", json={})).json()["id"]
    response = await client.post(
        "/v1/chat",
        json={
            "session_id": sid,
            "client_request_id": "wrong-arithmetic",
            "message": "Một giá trị giảm 2% còn 8722. Giá trị ban đầu là bao nhiêu? Chỉ trả lời số.",
            "mode": "optimized",
        },
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "OUTPUT_INVALID"
    assert provider.calls == 1
    assert (await client.get("/v1/sessions/" + sid)).json()["messages"] == []
