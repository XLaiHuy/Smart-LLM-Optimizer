import asyncio
import hashlib
from decimal import Decimal
from time import perf_counter
from typing import Literal

import numpy as np
from sqlalchemy import select

from app.config import Settings
from app.contracts.dtos import (
    CallRecord,
    CostEstimate,
    ExecutionRequest,
    Message,
    MeteringContext,
    ProviderItem,
    ProviderOptions,
    ProviderResult,
    ToolDefinition,
    Usage,
)
from app.contracts.errors import AppError
from app.contracts.protocols import LLMProvider
from app.providers.catalog import Catalog, price, upper_cost
from app.providers.live import OpenAIProvider
from app.storage.database import Database
from app.storage.ledger import SqlBudgetLedger
from app.storage.models import PriceSnapshot, UsageRecord
from app.storage.repositories import now, uid

Stage = Literal["provider", "query_embedding", "indexing", "document_map", "document_reduce"]


def input_bound(
    messages: tuple[Message, ...],
    tools: tuple[ToolDefinition, ...] = (),
    items: tuple[ProviderItem, ...] = (),
) -> int:
    # Conservative UTF-8 byte bound plus role overhead, not provider usage.
    return (
        sum(len(m.content.encode("utf-8")) + 64 for m in messages)
        + 128
        + sum(len(t.model_dump_json().encode("utf-8")) + 64 for t in tools)
        + sum(len(i.payload_json.encode("utf-8")) + 64 for i in items)
    )


def aggregate(calls: tuple[CallRecord, ...]) -> tuple[Usage, CostEstimate]:
    fields = ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens")
    counts = {
        f: sum(getattr(c.usage, f) for c in calls)
        if all(getattr(c.usage, f) is not None for c in calls)
        else None
        for f in fields
    }
    mock = all(c.cost.status == "not_billable" for c in calls)
    complete = all(c.cost.serving_usd is not None for c in calls)
    subtotal = sum((c.cost.serving_usd or Decimal(0) for c in calls), Decimal(0))
    versions = {c.cost.price_catalog_version for c in calls if c.cost.price_catalog_version}
    return Usage(
        input_tokens=counts["input_tokens"],
        output_tokens=counts["output_tokens"],
        cached_input_tokens=counts["cached_input_tokens"],
        reasoning_tokens=counts["reasoning_tokens"],
        usage_source="mock" if mock else "provider",
    ), CostEstimate(
        status="not_billable" if mock else "estimated" if complete else "unknown",
        serving_usd=subtotal if complete else None,
        known_subtotal_usd=subtotal if not mock and not complete else None,
        price_catalog_version=next(iter(versions)) if len(versions) == 1 else None,
    )


class MeteredCalls:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        ledger: SqlBudgetLedger,
        catalog: Catalog | None,
        live: OpenAIProvider | None,
    ):
        self.db, self.settings, self.ledger, self.catalog, self.live = (
            db,
            settings,
            ledger,
            catalog,
            live,
        )

    async def _start(
        self,
        execution: ExecutionRequest | MeteringContext,
        stage: Stage,
        model: str,
        upper: Decimal,
    ) -> tuple[str, str | None]:
        context = (
            execution
            if isinstance(execution, MeteringContext)
            else MeteringContext.from_execution(
                execution, self.settings.document_operation_budget_usd
            )
        )
        call_id = uid()
        reservation = None
        if self.catalog:
            reservation = await self.ledger.reserve(
                context.principal,
                context.operation_id,
                call_id,
                upper,
                context.max_total_usd,
            )
            async with self.db.write() as db:
                stored = await db.get(PriceSnapshot, self.catalog.version)
                content = self.catalog.model_dump_json()
                if stored is None:
                    db.add(PriceSnapshot(id=self.catalog.version, catalog_json=content))
                elif stored.catalog_json != content:
                    raise AppError(
                        "VALIDATION_ERROR", 422, "Catalog changed without version change"
                    )
        record = CallRecord(
            call_id=call_id,
            stage=stage,
            model_id=model,
            usage=Usage(scope="call", usage_source="unknown" if self.catalog else "mock"),
            cost=CostEstimate(scope="call", status="unknown" if self.catalog else "not_billable"),
            duration_ms=None,
        )
        async with self.db.write() as db:
            db.add(
                UsageRecord(
                    id=call_id,
                    owner_user_id=context.principal.id,
                    operation_id=context.operation_id,
                    session_id=context.session_id,
                    created_at=now(),
                    category="indexing" if stage == "indexing" else context.category,
                    execution_source=self.settings.provider_mode,
                    model_id=model,
                    record_json=record.model_dump_json(),
                )
            )
        if reservation:
            await self.ledger.mark_dispatched(reservation)
        return call_id, reservation

    async def _finish(self, call: CallRecord, reservation: str | None) -> None:
        await self.ledger.finish_call(call, reservation)

    async def generate(
        self,
        execution: ExecutionRequest | MeteringContext,
        messages: tuple[Message, ...],
        opts: ProviderOptions,
        provider: LLMProvider,
        stage: Stage = "provider",
    ) -> ProviderResult:
        bound = input_bound(messages, opts.tools, opts.continuation_items)
        upper = Decimal(0)
        if self.catalog:
            entry = self.catalog.entry(opts.config_id)
            if entry.kind != "generation" or opts.model_id != entry.model_id:
                raise AppError("NO_COMPATIBLE_MODEL", 422, "Model/configuration mismatch")
            if opts.tools and not entry.function_calling:
                raise AppError(
                    "NO_COMPATIBLE_MODEL", 422, "Model does not support configured tools"
                )
            if any(
                value is not None and name not in entry.supported_parameters
                for name, value in (("temperature", opts.temperature), ("top_p", opts.top_p))
            ):
                raise AppError("VALIDATION_ERROR", 422, "Unsupported generation parameter")
            if bound + entry.max_output_tokens > entry.context_window:
                raise AppError(
                    "CONTEXT_OVERFLOW",
                    413,
                    "Conservative input bound exceeds configured context window",
                )
            upper = upper_cost(entry, bound)
        call_id, reservation = await self._start(execution, stage, opts.model_id, upper)
        started = perf_counter()
        try:
            result = await provider.generate(messages, opts.model_copy(update={"call_id": call_id}))
        except BaseException:
            await asyncio.shield(
                self._finish(
                    CallRecord(
                        call_id=call_id,
                        stage=stage,
                        model_id=opts.model_id,
                        usage=Usage(scope="call", usage_source="unknown"),
                        cost=CostEstimate(
                            scope="call", status="unknown" if self.catalog else "not_billable"
                        ),
                        duration_ms=(perf_counter() - started) * 1000,
                    ),
                    reservation,
                )
            )
            raise
        await self._finish(
            CallRecord(
                call_id=call_id,
                stage=stage,
                model_id=opts.model_id,
                usage=result.usage,
                provider_response_id=result.provider_response_id,
                native_usage_json=result.native_usage_json,
                cost=result.cost,
                duration_ms=result.duration_ms,
            ),
            reservation,
        )
        return result

    async def embed(
        self,
        execution: ExecutionRequest,
        texts: list[str],
        stage: Literal["query_embedding", "indexing"],
    ) -> list[list[float]]:
        entry = self.catalog.entry(self.catalog.embedding_config) if self.catalog else None
        model = entry.model_id if entry else "mock-hash-embedding-v1"
        bound = sum(len(t.encode("utf-8")) for t in texts)
        if entry and any(len(t.encode("utf-8")) > entry.context_window for t in texts):
            raise AppError("CONTEXT_OVERFLOW", 413, "Embedding input too large")
        upper = Decimal(bound) * entry.input_per_million / Decimal(1000000) if entry else Decimal(0)
        call_id, reservation = await self._start(execution, stage, model, upper)
        started = perf_counter()
        try:
            if self.live and entry and self.catalog:
                result = await self.live.client.embeddings.create(model=model, input=texts)
                vectors = [item.embedding for item in result.data]
                usage = Usage(
                    scope="call",
                    usage_source="provider",
                    input_tokens=result.usage.prompt_tokens,
                    output_tokens=0,
                    cached_input_tokens=0,
                    reasoning_tokens=0,
                )
                cost = price(entry, usage, self.catalog.version)
            else:
                # Functional fixture only: explicitly mock, never semantic quality evidence.
                vectors = []
                for value in texts:
                    vector = np.zeros(64)
                    for word in value.casefold().split():
                        vector[int(hashlib.sha256(word.encode()).hexdigest()[:8], 16) % 64] += 1
                    vectors.append((vector / (np.linalg.norm(vector) or 1)).tolist())
                usage, cost = Usage(scope="call"), CostEstimate(scope="call")
            if len(vectors) != len(texts):
                raise AppError("OUTPUT_INVALID", 502, "Embedding count mismatch")
        except BaseException:
            await asyncio.shield(
                self._finish(
                    CallRecord(
                        call_id=call_id,
                        stage=stage,
                        model_id=model,
                        usage=Usage(scope="call", usage_source="unknown"),
                        cost=CostEstimate(
                            scope="call", status="unknown" if entry else "not_billable"
                        ),
                        duration_ms=(perf_counter() - started) * 1000,
                    ),
                    reservation,
                )
            )
            raise
        await self._finish(
            CallRecord(
                call_id=call_id,
                stage=stage,
                model_id=model,
                usage=usage,
                cost=cost,
                duration_ms=(perf_counter() - started) * 1000,
            ),
            reservation,
        )
        return vectors

    async def records(self, operation_id: str) -> tuple[CallRecord, ...]:
        async with self.db.sessions() as db:
            rows = await db.scalars(
                select(UsageRecord)
                .where(UsageRecord.operation_id == operation_id)
                .order_by(UsageRecord.created_at)
            )
            return tuple(CallRecord.model_validate_json(r.record_json) for r in rows)
