from typing import Literal


def check_preservation(original: str, proposed: str) -> Literal["preserved", "unknown"]:
    """Only byte-identical content is verified in G0. Tân extends this after handoff."""
    return "preserved" if original == proposed else "unknown"
