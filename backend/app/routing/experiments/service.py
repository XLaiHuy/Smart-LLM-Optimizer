import asyncio
import contextlib
import json
import subprocess
from decimal import Decimal
from statistics import median
from time import perf_counter
from typing import Literal, cast

from sqlalchemy import func, select

from app.analytics.service import administrator
from app.config import ROOT
from app.contracts.dtos import (
    CallRecord,
    CandidateExclusion,
    ContextResult,
    FeatureFlags,
    MeteringContext,
    OptimizationState,
    PolicySnapshot,
    Principal,
    ProviderOptions,
    RemainingBudget,
    RouteEstimate,
)
from app.contracts.errors import AppError
from app.contracts.research import (
    ExperimentSnapshot,
    PolicySummary,
    PredictorImportance,
    ResearchConfigs,
    ResearchPreflight,
    ResearchRequest,
    ResearchRunInfo,
    ResearchSummary,
    RunAccounting,
    SimulationMetrics,
    Strategy,
    TrialResult,
    UncommittedCall,
)
from app.core.metering import input_bound
from app.routing.experiments.fixtures import (
    FixtureProvider,
    digest,
    fixture_setup,
    grade_fixture,
    manifest,
)
from app.routing.experiments.live import LiveResearchWiring
from app.routing.features import extract_context_features
from app.routing.ml.service import MLRouterService
from app.routing.policies import PolicyRouter, RoutingRejected
from app.storage.database import Database
from app.storage.models import Attempt, ResearchRun, ResearchTrial, UsageRecord, User
from app.storage.repositories import now, uid

STRATEGIES: tuple[Strategy, ...] = (
    "fixed_reference",
    "fixed_candidate",
    "cheapest_feasible",
    "random_feasible",
    "rule_guarded",
    "ml_router",
    "ml_multi_model",
)


class ResearchService:
    def __init__(
        self,
        db: Database,
        live: LiveResearchWiring | None = None,
        *,
        ml: MLRouterService | None = None,
    ):
        self.db = db
        self.provider = FixtureProvider()
        self.ml = ml or MLRouterService()
        # Server approval is stable for frozen runs when a new Lab candidate is imported.
        self.ml_live_approved = self.ml.live_approved
        self.router = PolicyRouter(self.ml)
        self.task: asyncio.Task[None] | None = None
        self.wake = asyncio.Event()
        self.live = live

    def configs(
        self, principal: Principal, suite_id: str = "huy-router-fixtures-v1"
    ) -> ResearchConfigs:
        administrator(principal)
        registry, _, _ = fixture_setup(suite_id)
        return ResearchConfigs(
            suite_id=suite_id,
            cases=len(manifest(suite_id).cases),
            models=registry.configurations,
            policies=STRATEGIES,
            live_enabled=bool(self.live and self.live.enabled),
            live_models=self.live.registry.configurations if self.live else (),
            live_reference_id=self.live.registry.mock_config_id if self.live else None,
            ml_status=self.ml.status,
            ml_artifact_hash=self.ml.hash,
        )

    def freeze(self, request: ResearchRequest) -> ExperimentSnapshot:
        source_registry, costs, evidence = fixture_setup(request.suite_id)
        catalog_json = None
        if request.execution_source == "live":
            if request.suite_id == "huy-router-fixtures-v2":
                raise AppError(
                    "LIVE_RESEARCH_DISABLED",
                    422,
                    "V2 fixture tools are routing metadata, not a qualified live agent dataset",
                )
            if not self.live or not self.live.enabled:
                raise AppError(
                    "LIVE_RESEARCH_DISABLED",
                    422,
                    "Live research requires an explicit operator gate",
                )
            assert self.live.metering.catalog
            source_registry, costs, evidence = self.live.registry, self.live.costs(), ()
            catalog_json = self.live.metering.catalog.model_dump_json()
        if request.execution_source not in ("simulation", "live"):
            raise AppError(
                "LIVE_RESEARCH_DISABLED",
                422,
                "Live research requires a separate qualified-data/catalog gate",
            )
        ids = set(request.config_ids)
        if (
            not ids.issubset({m.config_id for m in source_registry.configurations})
            or source_registry.mock_config_id not in ids
        ):
            raise AppError(
                "NO_COMPATIBLE_MODEL",
                422,
                "Select configured candidates including the fixture reference",
            )
        suite = manifest(request.suite_id)
        registry = source_registry.model_copy(
            update={
                "configurations": tuple(
                    m for m in source_registry.configurations if m.config_id in ids
                )
            }
        )
        try:
            code = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
            dirty = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            code += "-dirty" if dirty else ""
        except (OSError, subprocess.SubprocessError):
            code = "unavailable"
        return ExperimentSnapshot(
            request=request,
            manifest=suite,
            registry=registry,
            costs=costs,
            evidence=evidence,
            manifest_hash=digest(suite.model_dump_json()),
            catalog_hash=digest(
                registry.model_dump_json() + costs.model_dump_json() + (catalog_json or "")
            ),
            code_sha=code,
            price_catalog_json=catalog_json,
            ml_artifact_json=self.ml.artifact_json
            if set(request.policies) & {"ml_router", "ml_multi_model"}
            else None,
            ml_artifact_hash=self.ml.hash
            if set(request.policies) & {"ml_router", "ml_multi_model"}
            else None,
        )

    def preflight(self, principal: Principal, request: ResearchRequest) -> ResearchPreflight:
        administrator(principal)
        snapshot = self.freeze(request)
        return self._preflight(snapshot)

    def _preflight(self, snapshot: ExperimentSnapshot) -> ResearchPreflight:
        request = snapshot.request
        policies = sum(
            len(request.config_ids) if p == "fixed_candidate" else 1 for p in request.policies
        )
        trials = len(snapshot.manifest.cases) * policies * request.repeats
        if trials > 1000:
            raise AppError("VALIDATION_ERROR", 422, "At most 1000 trials per run")
        rates = {r.config_id: r for r in snapshot.costs.rates}
        upper = (
            sum(
                (
                    max(
                        (
                            Decimal(input_bound(case.messages, case.tools))
                            * rates[m.config_id].input_per_million
                            + Decimal(m.max_output_tokens) * rates[m.config_id].output_per_million
                        )
                        / Decimal(1000000)
                        for m in snapshot.registry.configurations
                    )
                    for case in snapshot.manifest.cases
                ),
                Decimal(0),
            )
            * policies
            * request.repeats
        )
        if upper > request.budget_usd:
            raise AppError("BUDGET_EXCEEDED", 422, "Simulation preflight exceeds run budget")
        return ResearchPreflight(
            trials=trials,
            max_calls=trials,
            simulation_upper_usd=upper if request.execution_source == "simulation" else None,
            live_upper_usd=upper if request.execution_source == "live" else None,
            manifest_hash=snapshot.manifest_hash,
            live_enabled=bool(self.live and self.live.enabled),
        )

    async def create(self, principal: Principal, request: ResearchRequest) -> ResearchRunInfo:
        administrator(principal)
        payload_hash = digest(request.model_dump_json())
        async with self.db.sessions() as db:
            existing = await db.scalar(
                select(ResearchRun).where(
                    ResearchRun.owner_user_id == principal.id,
                    ResearchRun.client_request_id == request.client_request_id,
                )
            )
            if existing:
                if existing.payload_hash != payload_hash:
                    raise AppError(
                        "IDEMPOTENCY_CONFLICT",
                        409,
                        "Request ID already used with different payload",
                    )
                return await self.get(principal, existing.id)
        snapshot = await asyncio.to_thread(self.freeze, request)
        self._preflight(snapshot)
        async with self.db.write() as db:
            # Recheck dedupe under the same write lock as the global active-run claim.
            existing = await db.scalar(
                select(ResearchRun).where(
                    ResearchRun.owner_user_id == principal.id,
                    ResearchRun.client_request_id == request.client_request_id,
                )
            )
            if existing:
                if existing.payload_hash != payload_hash:
                    raise AppError("IDEMPOTENCY_CONFLICT", 409, "Conflicting request")
                run_id = existing.id
            else:
                if await db.scalar(
                    select(ResearchRun.id).where(ResearchRun.status.in_(("pending", "running")))
                ):
                    raise AppError("RESEARCH_BUSY", 409, "Another research run is active")
                run_id = uid()
                db.add(
                    ResearchRun(
                        id=run_id,
                        owner_user_id=principal.id,
                        client_request_id=request.client_request_id,
                        payload_hash=payload_hash,
                        snapshot_json=snapshot.model_dump_json(),
                        status="pending",
                        cancel_requested=False,
                        budget_usd=str(request.budget_usd),
                        created_at=now(),
                    )
                )
        self.wake.set()
        return await self.get(principal, run_id)

    async def get(self, principal: Principal, run_id: str) -> ResearchRunInfo:
        administrator(principal)
        async with self.db.sessions() as db:
            run = await db.get(ResearchRun, run_id)
            if not run or run.owner_user_id != principal.id:
                raise AppError("RESEARCH_NOT_FOUND", 404, "Research run not found")
            snapshot = ExperimentSnapshot.model_validate_json(run.snapshot_json)
            accounting = None
            if snapshot.request.execution_source == "live":
                records = list(
                    await db.scalars(
                        select(UsageRecord)
                        .join(Attempt, UsageRecord.operation_id == Attempt.id)
                        .where(Attempt.research_run_id == run_id)
                        .order_by(UsageRecord.created_at, UsageRecord.id)
                    )
                )
                trial_rows = await db.scalars(
                    select(ResearchTrial).where(ResearchTrial.run_id == run_id)
                )
                committed_ids = {
                    call.call_id
                    for row in trial_rows
                    for call in TrialResult.model_validate_json(row.result_json).calls
                }
                calls = [CallRecord.model_validate_json(row.record_json) for row in records]
                values = [
                    c.reconciled_usd if c.reconciled_usd is not None else c.cost.serving_usd
                    for c in calls
                ]
                known = [value for value in values if value is not None]
                accounting = RunAccounting(
                    calls=len(calls),
                    calculated_usd=sum(known, Decimal(0))
                    if calls and len(known) == len(calls)
                    else None,
                    known_subtotal_usd=sum(known, Decimal(0)) if known else None,
                    unknown_calls=sum(value is None for value in values),
                    uncommitted_calls=tuple(
                        UncommittedCall(operation_id=row.operation_id, call=call)
                        for row, call in zip(records, calls, strict=True)
                        if call.call_id not in committed_ids
                    ),
                )
            completed = await db.scalar(
                select(func.count())
                .select_from(ResearchTrial)
                .where(ResearchTrial.run_id == run_id)
            )
            count = sum(
                len(snapshot.request.config_ids) if p == "fixed_candidate" else 1
                for p in snapshot.request.policies
            )
            return ResearchRunInfo(
                id=run.id,
                status=cast("ResearchRunInfoStatus", run.status),
                created_at=run.created_at,
                completed=completed or 0,
                total=len(snapshot.manifest.cases) * snapshot.request.repeats * count,
                cancel_requested=run.cancel_requested,
                request=snapshot.request,
                manifest_hash=snapshot.manifest_hash,
                catalog_hash=snapshot.catalog_hash,
                ml_artifact_hash=snapshot.ml_artifact_hash,
                code_sha=snapshot.code_sha,
                checker_version=snapshot.checker_version,
                error_code=run.error_code,
                accounting=accounting,
                execution_source=snapshot.request.execution_source,
                run_purpose="live_pilot"
                if snapshot.request.execution_source == "live"
                else "functional_fixture",
            )

    async def list_runs(
        self, principal: Principal, offset: int, limit: int
    ) -> tuple[ResearchRunInfo, ...]:
        administrator(principal)
        async with self.db.sessions() as db:
            ids = list(
                await db.scalars(
                    select(ResearchRun.id)
                    .where(ResearchRun.owner_user_id == principal.id)
                    .order_by(ResearchRun.created_at.desc(), ResearchRun.id)
                    .offset(offset)
                    .limit(limit)
                )
            )
        return tuple([await self.get(principal, key) for key in ids])

    async def trials(
        self, principal: Principal, run_id: str, offset: int, limit: int
    ) -> tuple[TrialResult, ...]:
        await self.get(principal, run_id)
        async with self.db.sessions() as db:
            rows = await db.scalars(
                select(ResearchTrial)
                .where(ResearchTrial.run_id == run_id)
                .order_by(ResearchTrial.position)
                .offset(offset)
                .limit(limit)
            )
            return tuple(TrialResult.model_validate_json(r.result_json) for r in rows)

    async def cancel(self, principal: Principal, run_id: str) -> ResearchRunInfo:
        await self.get(principal, run_id)
        async with self.db.write() as db:
            row = await db.get(ResearchRun, run_id)
            assert row
            if row.status in ("pending", "running"):
                row.cancel_requested = True
                if row.status == "pending":
                    row.status = "cancelled"
        return await self.get(principal, run_id)

    async def summary(self, principal: Principal, run_id: str) -> ResearchSummary:
        rows = await self.trials(principal, run_id, 0, 1000)
        routes: dict[str, int] = {}
        for row in rows:
            if row.route:
                key = row.route.config_id
                routes[key] = routes.get(key, 0) + 1
        summaries = []
        for policy in sorted({row.policy for row in rows}):
            group = [r for r in rows if r.policy == policy]
            timings = sorted(r.duration_ms for r in group)
            summaries.append(
                PolicySummary(
                    policy=policy,
                    trials=len(group),
                    calls=sum(len(r.calls) for r in group),
                    functional_passes=sum(r.functional_pass for r in group),
                    errors=sum(r.error_code is not None for r in group),
                    fallbacks=sum(bool(r.route and r.route.fallback_used) for r in group),
                    fallback_rate=sum(bool(r.route and r.route.fallback_used) for r in group)
                    / len(group)
                    if group
                    else None,
                    p50_ms=median(timings) if timings else None,
                    p95_ms=timings[min(len(timings) - 1, int((len(timings) - 1) * 0.95 + 0.5))]
                    if timings
                    else None,
                    simulation_upper_usd=sum(
                        (
                            r.simulation.estimated_upper_usd or Decimal(0)
                            for r in group
                            if r.simulation
                        ),
                        Decimal(0),
                    )
                    if all(r.simulation for r in group)
                    else None,
                    calculated_usd=sum(
                        (
                            c.cost.serving_usd
                            for r in group
                            for c in r.calls
                            if c.cost.serving_usd is not None
                        ),
                        Decimal(0),
                    )
                    if any(r.calls for r in group)
                    and all(c.cost.serving_usd is not None for r in group for c in r.calls)
                    else None,
                )
            )
        # Historical runs must retain their own artifact even after an operator replaces it.
        async with self.db.sessions() as db:
            stored = await db.get(ResearchRun, run_id)
            assert stored
            snapshot = ExperimentSnapshot.model_validate_json(stored.snapshot_json)
        frozen = MLRouterService(snapshot.ml_artifact_json)
        artifact = frozen.multi.artifact
        importances = (
            tuple(
                PredictorImportance(config_id=p.config_id, importances=dict(p.feature_importances))
                for p in artifact.predictors
                if p.is_hybrid
            )
            if artifact and "ml_multi_model" in snapshot.request.policies
            else ()
        )
        return ResearchSummary(
            routes=routes,
            policies=tuple(summaries),
            predictor_importances=importances,
            feature_importance_artifact_hash=snapshot.ml_artifact_hash if importances else None,
        )

    async def start(self) -> None:
        async with self.db.write() as db:
            for run in await db.scalars(select(ResearchRun).where(ResearchRun.status == "running")):
                run.status, run.error_code = "interrupted", "PROCESS_INTERRUPTED"
        self.task = asyncio.create_task(self._worker())

    async def close(self) -> None:
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task

    async def _worker(self) -> None:
        while True:
            self.wake.clear()
            async with self.db.write() as db:
                run = await db.scalar(
                    select(ResearchRun)
                    .where(ResearchRun.status == "pending")
                    .order_by(ResearchRun.created_at)
                    .limit(1)
                )
                if run:
                    run.status = "running"
                    run_id, snapshot = (
                        run.id,
                        ExperimentSnapshot.model_validate_json(run.snapshot_json),
                    )
            if not run:
                try:
                    await asyncio.wait_for(self.wake.wait(), timeout=1)
                except TimeoutError:
                    pass
                continue
            try:
                await self._execute(run_id, snapshot)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                async with self.db.write() as db:
                    failed = await db.get(ResearchRun, run_id)
                    if failed:
                        failed.status, failed.error_code = (
                            "failed",
                            exc.code if isinstance(exc, AppError) else "RESEARCH_EXECUTION_FAILED",
                        )

    async def _execute(self, run_id: str, snapshot: ExperimentSnapshot) -> None:
        # Pending runs use their frozen data-only artifact, never a newly trained file.
        router = PolicyRouter(
            MLRouterService(snapshot.ml_artifact_json, live_approved=self.ml_live_approved)
        )
        position, simulated_spend = 0, Decimal(0)
        request = snapshot.request
        is_live = request.execution_source == "live"
        if is_live:
            if not self.live or not self.live.enabled:
                raise AppError("LIVE_RESEARCH_DISABLED", 422, "Live research is disabled")
            if (
                not self.live.metering.catalog
                or self.live.metering.catalog.model_dump_json() != snapshot.price_catalog_json
            ):
                raise AppError(
                    "CATALOG_CHANGED", 409, "Pending run catalog changed; create a reviewed run"
                )
        for repeat in range(request.repeats):
            for case in snapshot.manifest.cases:
                for strategy in request.policies:
                    for candidate in (
                        request.config_ids if strategy == "fixed_candidate" else (None,)
                    ):
                        async with self.db.write() as db:
                            row = await db.get(ResearchRun, run_id)
                            assert row
                            if row.cancel_requested:
                                row.status = "cancelled"
                                return
                            owner_id = row.owner_user_id
                        started = perf_counter()
                        profile = extract_context_features(case.messages).model_copy(
                            update={"tool_count": len(case.tools)}
                        )
                        prepared = ContextResult(
                            messages=case.messages,
                            tools=case.tools,
                            provenance=(),
                            state=OptimizationState(
                                module="context", status="disabled", reason="router_isolation"
                            ),
                        )
                        policy = PolicySnapshot(
                            policy_id=strategy,
                            policy_version="router-p0-v1",
                            flags=FeatureFlags(router=True),
                            strategy=strategy,
                            sandbox=not is_live
                            if strategy in ("ml_router", "ml_multi_model")
                            else True,
                            seed=int(digest(f"{request.seed}:{case.case_id}:{repeat}")[:8], 16),
                            candidate_id=candidate,
                            evidence=snapshot.evidence,
                            evidence_version=None if is_live else "fixture-only-v1",
                            ml_artifact_hash=snapshot.ml_artifact_hash,
                        )
                        calls: tuple[CallRecord, ...] = ()
                        route, error, prediction, projected = None, None, None, None
                        rejections: tuple[CandidateExclusion, ...] = ()
                        estimates: tuple[RouteEstimate, ...] = ()
                        operation: MeteringContext | None = None
                        if is_live:
                            assert self.live
                            async with self.db.write() as db:
                                user = await db.get(User, owner_id)
                                if not user or user.role != "admin":
                                    raise AppError(
                                        "FORBIDDEN_ACTION",
                                        403,
                                        "Research operator is no longer administrator",
                                    )
                                principal = Principal(
                                    id=user.id,
                                    username=user.username,
                                    role="admin",
                                    quota_usd=Decimal(user.quota_usd),
                                )
                                operation = MeteringContext(
                                    operation_id=uid(),
                                    principal=principal,
                                    category="evaluation",
                                    max_total_usd=min(case.max_usd, request.budget_usd),
                                )
                                db.add(
                                    Attempt(
                                        id=operation.operation_id,
                                        owner_user_id=owner_id,
                                        session_id=None,
                                        research_run_id=run_id,
                                        client_request_id=f"research:{run_id}:{position}",
                                        payload_hash=digest(case.model_dump_json()),
                                        status="running",
                                        dispatched=False,
                                        execution_source="live",
                                        created_at=now(),
                                    )
                                )
                        remaining = RemainingBudget(
                            usd=min(case.max_usd, request.budget_usd - simulated_spend),
                            deadline_ms=case.deadline_ms,
                        )
                        if operation and self.live:
                            remaining = (
                                await self.live.metering.ledger.remaining(
                                    operation.principal,
                                    operation.operation_id,
                                    operation.max_total_usd,
                                )
                            ).model_copy(update={"deadline_ms": case.deadline_ms})
                        try:
                            route = router.select(
                                profile,
                                prepared,
                                snapshot.registry,
                                snapshot.costs,
                                policy,
                                remaining,
                            )
                            projected = next(
                                e.upper_usd
                                for e in route.estimates
                                if e.config_id == route.config_id
                            )
                            options = ProviderOptions(
                                request_id=operation.operation_id if operation else run_id,
                                call_id=uid(),
                                config_id=route.config_id,
                                model_id=route.model_id,
                            )
                            if operation and self.live:
                                if not self.live.enabled:
                                    raise AppError(
                                        "LIVE_RESEARCH_DISABLED",
                                        422,
                                        "Live research disabled during run",
                                    )
                                async with asyncio.timeout(max(0, case.deadline_ms) / 1000):
                                    result = await self.live.metering.generate(
                                        operation, case.messages, options, self.live.provider
                                    )
                                calls = await self.live.metering.records(operation.operation_id)
                                if not result.text:
                                    raise AppError(
                                        "OUTPUT_INVALID",
                                        502,
                                        "Provider returned no complete output",
                                    )
                            else:
                                simulated_spend += projected or Decimal(0)
                                result = await self.provider.generate(case.messages, options)
                                calls = (
                                    CallRecord(
                                        call_id=options.call_id,
                                        model_id=route.model_id,
                                        usage=result.usage,
                                        cost=result.cost,
                                        duration_ms=result.duration_ms,
                                    ),
                                )
                            prediction = result.text
                        except asyncio.CancelledError:
                            if operation and self.live:
                                await asyncio.shield(
                                    self.live.sessions.fail(
                                        operation.operation_id, "PROCESS_INTERRUPTED"
                                    )
                                )
                            raise
                        except TimeoutError:
                            error = "PROVIDER_TIMEOUT"
                        except AppError as exc:
                            error = exc.code
                            if isinstance(exc, RoutingRejected):
                                rejections, estimates = exc.exclusions, exc.estimates
                            if route and not operation:
                                calls = (
                                    CallRecord(
                                        call_id=uid(),
                                        model_id=route.model_id,
                                        duration_ms=(perf_counter() - started) * 1000,
                                    ),
                                )
                        if operation and self.live:
                            calls = await self.live.metering.records(operation.operation_id)
                            if error:
                                await self.live.sessions.fail(operation.operation_id, error)
                        functional = grade_fixture(prediction, case, error)
                        trial = TrialResult(
                            id=uid(),
                            case_id=case.case_id,
                            repeat=repeat,
                            policy=strategy + (f":{candidate}" if candidate else ""),
                            snapshot_hash=digest(
                                json.dumps(
                                    [m.model_dump(mode="json") for m in case.messages],
                                    sort_keys=True,
                                    ensure_ascii=False,
                                )
                            ),
                            profile=profile,
                            route=route,
                            error_code=error,
                            prediction=prediction,
                            calls=calls,
                            duration_ms=(perf_counter() - started) * 1000,
                            simulation=SimulationMetrics(
                                estimated_input_bound=input_bound(case.messages, case.tools),
                                estimated_upper_usd=projected,
                                functional_pass=functional,
                            )
                            if not is_live
                            else None,
                            functional_pass=functional,
                            operation_id=operation.operation_id if operation else None,
                            rejections=rejections,
                            estimates=estimates,
                        )
                        async with self.db.write() as db:
                            if operation:
                                attempt = await db.get(Attempt, operation.operation_id)
                                if attempt and not error:
                                    attempt.status = "succeeded"
                            db.add(
                                ResearchTrial(
                                    id=trial.id,
                                    run_id=run_id,
                                    position=position,
                                    result_json=trial.model_dump_json(),
                                )
                            )
                        position += 1
                        await asyncio.sleep(0)
        async with self.db.write() as db:
            row = await db.get(ResearchRun, run_id)
            assert row
            row.status = "cancelled" if row.cancel_requested else "succeeded"


ResearchRunInfoStatus = Literal[
    "pending", "running", "succeeded", "failed", "cancelled", "interrupted"
]
