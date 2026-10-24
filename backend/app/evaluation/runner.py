import asyncio
import hashlib
from pathlib import Path

from app.composition import Container
from app.config import Settings
from app.contracts.dtos import ChatRequest, EvalManifest
from app.contracts.errors import AppError


def validate_manifest(path: Path, purpose: str) -> EvalManifest:
    manifest = EvalManifest.model_validate_json(path.read_text(encoding="utf-8"))
    if purpose != "smoke" or manifest.run_purpose != "smoke" or manifest.execution_source != "mock":
        raise AppError(
            "VALIDATION_ERROR",
            422,
            "G0 accepts synthetic mock smoke only; live research requires G1/G2 qualification",
        )
    return manifest


async def run_smoke(manifest_path: Path, settings: Settings, output: Path) -> int:
    manifest = await asyncio.to_thread(validate_manifest, manifest_path, "smoke")
    data_hash = hashlib.sha256(await asyncio.to_thread(manifest_path.read_bytes)).hexdigest()
    if manifest.execution_source == "mock" and settings.provider_mode != "mock":
        settings = settings.model_copy(update={"provider_mode": "mock"})
    container = Container(settings)
    rows: list[str] = []
    try:
        user = await container.auth.create_user("smoke-operator", "temporary-smoke-only")
        for case in manifest.cases:
            session = await container.sessions.create(user, case.case_id)
            result = await container.orchestrator.execute(
                user,
                ChatRequest(
                    session_id=session.id,
                    client_request_id=case.case_id,
                    message=case.message,
                    mode="baseline",
                ),
                namespace="eval",
            )
            if case.message not in result.response.content:
                raise AssertionError(f"Smoke echo mismatch: {case.case_id}")
            import json

            rows.append(
                json.dumps(
                    {
                        "case_id": case.case_id,
                        "run_purpose": "smoke",
                        "namespace": "eval",
                        "execution_source": "mock",
                        "suite_version": manifest.suite_version,
                        "data_sha256": data_hash,
                        "functional_pass": True,
                        "quality_score": None,
                        "cost_saving_ratio": None,
                        "prediction": result.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                )
            )
        await asyncio.to_thread(output.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(output.write_text, "\n".join(rows) + "\n", encoding="utf-8")
        return len(rows)
    finally:
        await container.db.close()
