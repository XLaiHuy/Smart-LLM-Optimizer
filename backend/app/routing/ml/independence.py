"""Conservative duplicate key; source/document grouping is still required separately."""

import hashlib
import json
import re

from app.contracts.dtos import Message


def content_key(messages: tuple[Message, ...]) -> str:
    values = []
    for message in messages:
        text = re.sub(r"^\[[\w-]+-grp-\d+\.\d+\]\s*", "", message.content)
        text = re.sub(
            r"- (?:Phân nhánh|Biến thể|Hồ sơ vụ việc|Ca nghiên cứu|Phiên đối thoại) \d+:", ":", text
        )
        values.append((message.role, " ".join(text.split())))
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()
