"""Validate documentation fences/examples and local links without executing snippets."""

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
paths = [
    ROOT / "README.md",
    ROOT / "SMART_LLM_OPTIMIZER_SPEC_V2_COMPLETE.md",
    *ROOT.glob("docs/*.md"),
    *ROOT.glob(".agents/skills/*/SKILL.md"),
]
errors: list[str] = []
blocks = 0
for path in paths:
    text = path.read_text(encoding="utf-8")
    active: str | None = None
    buffer: list[str] = []
    width: int | None = None
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("```"):
            if active is None:
                active = line[3:].strip()
                buffer = []
            elif line.strip() == "```":
                try:
                    if active == "json":
                        json.loads("\n".join(buffer))
                    if active == "python":
                        ast.parse("\n".join(buffer))
                except (ValueError, SyntaxError) as exc:
                    errors.append(f"{path.name}:{n}: {exc}")
                active = None
                blocks += 1
            continue
        if active is not None:
            buffer.append(line)
            continue
        if line.startswith("|"):
            cells = len(re.findall(r"(?<!\\)\|", line))
            if width is not None and cells != width:
                errors.append(f"{path.name}:{n}: table width")
            width = cells
        else:
            width = None
        for target in re.findall(r"\]\(([^)]+)\)", line):
            if re.match(r"^(?:[a-z]+:|#)", target):
                continue
            local = target.split("#")[0]
            if local and not (path.parent / local).exists():
                errors.append(f"{path.name}:{n}: missing {local}")
    if active is not None:
        errors.append(f"{path.name}: unclosed fence")
if errors:
    raise SystemExit("\n".join(errors))
print(f"{len(paths)} Markdown documents valid; {blocks} fenced examples checked.")
