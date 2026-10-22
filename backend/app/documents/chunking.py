import hashlib
import os
from functools import lru_cache
from pathlib import Path

import tiktoken

# Tokenizer data must be populated at setup, never fetched implicitly by a request.
CACHE = Path(__file__).resolve().parents[3] / "data/tokenizer"
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(CACHE))


@lru_cache(maxsize=1)
def cached_encoding() -> tiktoken.Encoding | None:
    key = hashlib.sha1(
        b"https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
    ).hexdigest()
    asset = CACHE / key
    if (
        not asset.is_file()
        or hashlib.sha256(asset.read_bytes()).hexdigest()
        != "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
    ):
        return None
    return tiktoken.get_encoding("cl100k_base")


def splitter_version() -> str:
    return "cl100k-600-80-v1" if cached_encoding() else "utf8-byte-bound-600-80-v1"


def split_sections(sections: list[list[str]]) -> list[tuple[str, str]]:
    # Offline fallback is an explicit conservative byte-bound splitter, not usage.
    encoding = cached_encoding()
    result: list[tuple[str, str]] = []
    for location, content in sections:
        if not content.strip():
            continue
        if encoding:
            tokens = encoding.encode(content, disallowed_special=())
            for start in range(0, len(tokens), 520):
                # Boundary fragments are excluded; overlap retains the complete Unicode character in its adjacent chunk.
                raw = encoding.decode_bytes(tokens[start : start + 600])
                result.append((location, raw.decode("utf-8", errors="ignore")))
                if start + 600 >= len(tokens):
                    break
        else:
            # <=600 UTF-8 bytes/chunk for standard byte-level tokenizers.
            start = 0
            while start < len(content):
                end = start
                size = 0
                while end < len(content) and size + len(content[end].encode("utf-8")) <= 600:
                    size += len(content[end].encode("utf-8"))
                    end += 1
                result.append((location, content[start:end]))
                if end == len(content):
                    break
                overlap = end
                size = 0
                while overlap > start and size < 80:
                    overlap -= 1
                    size += len(content[overlap].encode("utf-8"))
                start = max(start + 1, overlap)
    return result
