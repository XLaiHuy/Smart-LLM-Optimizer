import json
from pathlib import Path

from app.routing.ml.prepare_pilot import prepare


def test_prepare_keeps_groups_in_one_deterministic_split(tmp_path: Path) -> None:
    samples = [
        {
            "task_id": f"task-{index}",
            "group_id": f"group-{index}",
            "domain": "test",
            "split": "train",
            "messages": [{"role": "user", "content": f"prompt {index}"}],
            "gold": "ok",
        }
        for index in range(100)
    ]
    source = tmp_path / "source.json"
    output = tmp_path / "pilot.json"
    source.write_text(json.dumps({"samples": samples}), encoding="utf-8")

    counts = prepare(source, output, 32)
    prepared = json.loads(output.read_text(encoding="utf-8"))["samples"]

    assert len(prepared) == 32
    assert all(counts[split] >= 4 for split in counts)
    assert {row["group_id"] for row in prepared} == {
        row["task_id"].replace("task", "group") for row in prepared
    }
