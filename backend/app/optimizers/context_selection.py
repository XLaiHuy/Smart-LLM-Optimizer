import re

import tiktoken

from app.contracts.dtos import Message


def lexical_relevance(query: str, context: str) -> float:
    query_words = set(re.findall(r"\w+", query.lower()))
    context_words = set(re.findall(r"\w+", context.lower()))
    if not query_words:
        return 0.0
    return len(query_words & context_words) / len(query_words)


def recency_score(index: int, total_turns: int) -> float:
    if total_turns < 1:
        raise ValueError("total_turns must be positive")

    if not 0 <= index < total_turns:
        raise ValueError("index out of range")

    if total_turns == 1:
        return 1.0

    return index / (total_turns - 1)


def hybrid_score(
    query: str,
    content: str,
    index: int,
    total: int,
    alpha: float = 0.7,
) -> float:
    if not 0 <= alpha <= 1:
        raise ValueError("alpha must be between 0 and 1")

    relevance = lexical_relevance(query, content)
    recency = recency_score(index, total)

    return alpha * relevance + (1 - alpha) * recency


def group_conversation_turns(
    messages: tuple[Message, ...],
) -> tuple[tuple[Message, ...], ...]:
    turns: list[tuple[Message, ...]] = []
    current: list[Message] = []

    for message in messages:
        if message.role == "user" and current:
            turns.append(tuple(current))
            current = []
        current.append(message)
    if current:
        turns.append(tuple(current))
    return tuple(turns)


_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_messages_tokens(
    messages: tuple[Message, ...],
) -> int:
    content = "\n".join(f"{message.role}: {message.content}" for message in messages)

    return len(_ENCODING.encode(content))


def count_turn_tokens(
    turn: tuple[Message, ...],
) -> int:
    return count_messages_tokens(turn)


def select_hybrid_turns(
    query: str,
    turns: tuple[tuple[Message, ...], ...],
    token_budget: int,
    recent_turn_count: int = 2,
) -> tuple[tuple[Message, ...], ...]:
    if token_budget < 0:
        raise ValueError("token_budget must be non-negative")

    if not turns:
        return ()

    selected_indices: set[int] = set()
    used_tokens = 0

    recent_start = max(0, len(turns) - recent_turn_count)
    recent_indices = range(recent_start, len(turns))

    # Ưu tiên giữ các turn gần nhất
    for index in reversed(tuple(recent_indices)):
        turn_tokens = count_turn_tokens(turns[index])

        if used_tokens + turn_tokens <= token_budget:
            selected_indices.add(index)
            used_tokens += turn_tokens

    # Chọn các turn cũ theo hybrid score
    old_indices = range(0, recent_start)

    ranked_indices = sorted(
        old_indices,
        key=lambda index: hybrid_score(
            query,
            " ".join(message.content for message in turns[index]),
            index,
            len(turns),
        ),
        reverse=True,
    )

    for index in ranked_indices:
        turn_tokens = count_turn_tokens(turns[index])

        if used_tokens + turn_tokens <= token_budget:
            selected_indices.add(index)
            used_tokens += turn_tokens

    # Trả lại thứ tự hội thoại ban đầu
    return tuple(turn for index, turn in enumerate(turns) if index in selected_indices)
