import csv
import io
import json
from decimal import Decimal
from typing import Literal

from app.contracts.research import ResearchRunInfo, TrialResult


def encode_export(
    run: ResearchRunInfo, rows: tuple[TrialResult, ...], format: Literal["csv", "jsonl"]
) -> str:
    if format == "jsonl":
        records = [
            {
                "record_type": "run",
                "export_version": "router-lab-v1",
                "run": run.model_dump(mode="json"),
            }
        ]
        records.extend(
            {"record_type": "trial", "run_id": run.id, "trial": row.model_dump(mode="json")}
            for row in rows
        )
        return "\n".join(json.dumps(row, ensure_ascii=False) for row in records) + "\n"
    fields = [
        "row_kind",
        "run_id",
        "source",
        "manifest_hash",
        "catalog_hash",
        "code_sha",
        "status",
        "trial_id",
        "case_id",
        "repeat",
        "policy",
        "model",
        "error",
        "functional_pass",
        "duration_ms",
        "simulation_upper_usd",
        "calls",
        "snapshot_hash",
        "policy_hash",
        "reason_code",
        "ml_score",
        "calibrated_threshold",
        "ml_artifact_hash",
        "ml_model_version",
        "routing_stages",
        "calculated_usd",
        "known_subtotal_usd",
        "input_tokens",
        "output_tokens",
        "operation_id",
        "call_id",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()

    def write(values: dict[str, object]) -> None:
        writer.writerow(
            {
                key: "'" + value
                if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r"))
                else value
                for key, value in values.items()
            }
        )

    write(
        {
            "row_kind": "run",
            "run_id": run.id,
            "source": run.execution_source,
            "manifest_hash": run.manifest_hash,
            "catalog_hash": run.catalog_hash,
            "code_sha": run.code_sha,
            "status": run.status,
            "calls": run.accounting.calls
            if run.accounting
            else sum(len(row.calls) for row in rows),
            "calculated_usd": run.accounting.calculated_usd if run.accounting else None,
            "known_subtotal_usd": run.accounting.known_subtotal_usd if run.accounting else None,
        }
    )
    for row in rows:
        write(
            {
                "row_kind": "trial",
                "run_id": run.id,
                "source": run.execution_source,
                "trial_id": row.id,
                "case_id": row.case_id,
                "repeat": row.repeat,
                "policy": row.policy,
                "model": row.route.config_id if row.route else None,
                "error": row.error_code,
                "functional_pass": row.functional_pass,
                "duration_ms": row.duration_ms,
                "simulation_upper_usd": row.simulation.estimated_upper_usd
                if row.simulation
                else None,
                "calls": len(row.calls),
                "snapshot_hash": row.snapshot_hash,
                "policy_hash": row.route.policy_hash if row.route else None,
                "reason_code": row.route.reason_code if row.route else None,
                "ml_score": row.route.ml_score if row.route else None,
                "calibrated_threshold": row.route.calibrated_threshold if row.route else None,
                "ml_artifact_hash": row.route.ml_artifact_hash if row.route else None,
                "ml_model_version": row.route.ml_model_version if row.route else None,
                "routing_stages": json.dumps([s.model_dump() for s in row.route.stages])
                if row.route
                else None,
                "calculated_usd": sum(
                    (c.cost.serving_usd for c in row.calls if c.cost.serving_usd is not None),
                    Decimal(0),
                )
                if row.calls and all(c.cost.serving_usd is not None for c in row.calls)
                else None,
                "input_tokens": sum(
                    c.usage.input_tokens for c in row.calls if c.usage.input_tokens is not None
                )
                if row.calls and all(c.usage.input_tokens is not None for c in row.calls)
                else None,
                "output_tokens": sum(
                    c.usage.output_tokens for c in row.calls if c.usage.output_tokens is not None
                )
                if row.calls and all(c.usage.output_tokens is not None for c in row.calls)
                else None,
                "operation_id": row.operation_id,
            }
        )
    if run.accounting:
        for item in run.accounting.uncommitted_calls:
            call = item.call
            write(
                {
                    "row_kind": "uncommitted_call",
                    "run_id": run.id,
                    "source": run.execution_source,
                    "status": run.status,
                    "error": "TRIAL_NOT_COMMITTED",
                    "operation_id": item.operation_id,
                    "call_id": call.call_id,
                    "model": call.model_id,
                    "duration_ms": call.duration_ms,
                    "calls": 1,
                    "calculated_usd": call.reconciled_usd
                    if call.reconciled_usd is not None
                    else call.cost.serving_usd,
                    "input_tokens": call.usage.input_tokens,
                    "output_tokens": call.usage.output_tokens,
                }
            )
    return "\ufeff" + output.getvalue()
