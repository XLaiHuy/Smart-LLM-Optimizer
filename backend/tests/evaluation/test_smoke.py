import asyncio
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.cli import cli, migrate
from app.config import ROOT, Settings
from app.contracts.errors import AppError
from app.evaluation.runner import run_smoke, validate_manifest


async def test_smoke_predictions_reproducible_and_labeled(tmp_path: Path) -> None:
    outputs = []
    for i in range(2):
        path = tmp_path / f"{i}.db"
        await asyncio.to_thread(migrate, path)
        report = tmp_path / f"{i}.jsonl"
        assert (
            await run_smoke(
                ROOT / "benchmark/manifests/smoke.json",
                Settings(database_path=path, app_env="test", provider_mode="mock"),
                report,
            )
            == 3
        )
        rows = [json.loads(line) for line in report.read_text(encoding="utf-8").splitlines()]
        assert all(
            r["run_purpose"] == "smoke"
            and r["execution_source"] == "mock"
            and r["quality_score"] is None
            for r in rows
        )
        outputs.append([r["prediction"]["response"]["content"] for r in rows])
    assert outputs[0] == outputs[1]


def test_reject_live_research_and_incomplete_manifest(tmp_path: Path) -> None:
    with pytest.raises(AppError):
        validate_manifest(ROOT / "benchmark/manifests/smoke.json", "live_research")
    path = tmp_path / "bad.json"
    path.write_text('{"cases": []}', encoding="utf-8")
    with pytest.raises(ValueError):
        validate_manifest(path, "smoke")


def test_clean_migration_and_account_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "cli.db"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    migrate(path)
    result = CliRunner().invoke(
        cli, ["create-user", "--username", "operator"], input="a-test-password\na-test-password\n"
    )
    assert result.exit_code == 0, result.output
    assert "Created operator" in result.output and "a-test-password" not in result.output
