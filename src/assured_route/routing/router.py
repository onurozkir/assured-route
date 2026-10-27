import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Literal
from uuid import uuid4

from assured_route import __version__
from assured_route.audit import log_result
from assured_route.core.decisions import Decision, SelectedPath
from assured_route.core.models import (
    AuditEvent,
    AuditInfo,
    CallRecord,
    ExtractRequest,
    ExtractResponse,
    GateResult,
    LatencyBreakdown,
    ProviderResult,
    ValidationAttempt,
    ValidationCheck,
    ValidationReport,
    VerificationResult,
)
from assured_route.core.policy import Policy
from assured_route.core.risk import score_risk
from assured_route.providers.interfaces import (
    ExtractionProvider,
    ProviderError,
    ProviderMetadata,
    VerifierProvider,
)
from assured_route.routing.deadline_manager import DeadlineManager
from assured_route.routing.escalation import can_escalate
from assured_route.routing.pre_router import PreRouter
from assured_route.validators.quality_gate import QualityGate

type Role = Literal["cheap", "expensive", "verifier"]


@dataclass
class _Run:
    deadline: DeadlineManager
    policy: Policy
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    request_id: str = field(default_factory=lambda: str(uuid4()))
    events: list[AuditEvent] = field(default_factory=list)
    calls: list[CallRecord] = field(default_factory=list)
    attempts: list[ValidationAttempt] = field(default_factory=list)
    stages: dict[str, float] = field(default_factory=dict)
    latest: GateResult | None = None

    def event(self, stage: str, reason: str, decision: Decision | None = None) -> None:
        self.events.append(
            AuditEvent(
                stage=stage,
                reason=reason,
                decision=decision,
                elapsed_ms=round(self.deadline.elapsed_ms, 3),
            )
        )


class Router:
    def __init__(
        self,
        cheap: ExtractionProvider,
        expensive: ExtractionProvider,
        verifier: VerifierProvider,
        policy: Policy,
        gate: QualityGate | None = None,
        pre_router: PreRouter | None = None,
        close: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.cheap = cheap
        self.expensive = expensive
        self.verifier = verifier
        self.policy = policy
        self.gate = gate or QualityGate()
        self.pre_router = pre_router or PreRouter()
        self._close = close

    async def aclose(self) -> None:
        if self._close is not None:
            await self._close()

    async def _call[T](
        self,
        state: _Run,
        role: Role,
        provider: ProviderMetadata,
        operation: Callable[[float], Awaitable[T]],
    ) -> T | None:
        started = perf_counter()
        status: Literal["ok", "timeout", "error", "cancelled"] = "ok"
        result: T | None = None
        error_code: str | None = None
        http_status: int | None = None
        try:
            cap_ms = state.policy.provider_timeout_ms
            if role == "cheap" and state.policy.cheap_timeout_ms is not None:
                cap_ms = min(cap_ms, state.policy.cheap_timeout_ms)
            timeout_ms = state.deadline.call_timeout_ms(cap_ms)
            async with asyncio.timeout(timeout_ms / 1000):
                result = await operation(timeout_ms)
        except TimeoutError:
            status = "timeout"
            error_code = "provider_timeout"
            state.event(role, "provider_timeout")
        except ProviderError as exc:
            # Exception messages may contain OCR or credentials; log a stable reason only.
            error_code, http_status = exc.code, exc.http_status
            status = "timeout" if exc.code == "provider_timeout" else "error"
            state.event(role, exc.code)
        except asyncio.CancelledError:
            status = "cancelled"
            state.event(role, "provider_cancelled")
            raise
        finally:
            elapsed = (perf_counter() - started) * 1000
            state.stages[role] = state.stages.get(role, 0) + elapsed
            state.calls.append(
                CallRecord(
                    role=role,
                    model_version=result.model_version
                    if isinstance(result, ProviderResult | VerificationResult)
                    else provider.model_version,
                    prompt_version=provider.prompt_version,
                    status=status,
                    latency_ms=round(elapsed, 3),
                    estimated_cost_usd=provider.estimated_cost_usd,
                    error_code=error_code,
                    http_status=http_status,
                )
            )
        return result

    def _evaluate(
        self,
        state: _Run,
        request: ExtractRequest,
        output: ProviderResult,
        role: Literal["cheap", "expensive"],
        verifier: VerificationResult | None = None,
    ) -> GateResult:
        started = perf_counter()
        result = self.gate.evaluate(
            output.payload,
            request.raw_ocr_text,
            state.policy,
            verifier,
            request.metadata.semantic_ambiguity,
        )
        state.stages["validation"] = (
            state.stages.get("validation", 0) + (perf_counter() - started) * 1000
        )
        state.latest = result
        state.attempts.append(
            ValidationAttempt(
                role=role,
                report=result.report,
                decision=result.decision,
                risk_score=result.risk.score,
            )
        )
        state.event("quality_gate", "validators_evaluated", result.decision)
        return result

    async def _extract_and_validate(
        self, state: _Run, request: ExtractRequest, role: Literal["cheap", "expensive"]
    ) -> GateResult | None:
        provider = self.cheap if role == "cheap" else self.expensive
        output = await self._call(
            state,
            role,
            provider,
            lambda timeout_ms: provider.extract(request, timeout_ms=timeout_ms),
        )
        if output is None:
            return None
        result = self._evaluate(state, request, output, role)
        if result.needs_verifier and result.invoice is not None:
            if not state.policy.enable_verifier:
                state.event("verifier", "required_verifier_disabled")
            elif not state.deadline.can_start(state.policy.verifier_expected_ms):
                state.event("verifier", "insufficient_verifier_budget")
            else:
                invoice = result.invoice
                verification = await self._call(
                    state,
                    "verifier",
                    self.verifier,
                    lambda timeout_ms: self.verifier.verify(
                        request, invoice, timeout_ms=timeout_ms
                    ),
                )
                if verification is not None:
                    result = self._evaluate(state, request, output, role, verification)
        return result

    async def extract(self, request: ExtractRequest) -> ExtractResponse:
        # All mutable state is request-scoped; the shared Router is safe for concurrent requests.
        policy = self.policy.with_overrides(request.policy)
        state = _Run(DeadlineManager(request.latency_budget_ms, policy.response_reserve_ms), policy)
        try:
            return await self._execute(state, request)
        except asyncio.CancelledError:
            # Preserve spent-call accounting while still honoring the caller's cancellation.
            state.event("runtime", "request_cancelled", Decision.REVIEW)
            self._finish(state, request, SelectedPath.REVIEW, "request_cancelled")
            raise

    async def _execute(self, state: _Run, request: ExtractRequest) -> ExtractResponse:
        policy = state.policy
        started = perf_counter()
        route = self.pre_router.route(request, policy)
        state.stages["pre_router"] = (perf_counter() - started) * 1000
        for reason in route.reasons:
            state.event("pre_router", reason)
        role: Literal["cheap", "expensive"] = "expensive" if route.use_expensive else "cheap"
        expected = policy.expensive_expected_ms if route.use_expensive else policy.cheap_expected_ms
        if not state.deadline.can_start(expected):
            return self._finish(state, request, SelectedPath.REVIEW, "insufficient_initial_budget")
        result = await self._extract_and_validate(state, request, role)
        if result is not None and result.decision == Decision.ACCEPT:
            path = (
                SelectedPath.EXPENSIVE
                if role == "expensive"
                else (
                    SelectedPath.CHEAP_VERIFIER
                    if any(c.role == "verifier" for c in state.calls)
                    else SelectedPath.CHEAP
                )
            )
            return self._finish(state, request, path, "quality_gate_accept")
        if role == "cheap" and can_escalate(result, state.deadline, policy.expensive_expected_ms):
            state.event("escalation", "recoverable_failure", Decision.ESCALATE_TO_EXPENSIVE)
            # Never reuse a cheap result when the expensive attempt fails.
            state.latest = None
            result = await self._extract_and_validate(state, request, "expensive")
            if result is not None and result.decision == Decision.ACCEPT:
                return self._finish(state, request, SelectedPath.EXPENSIVE, "expensive_gate_accept")
        return self._finish(
            state, request, SelectedPath.REVIEW, "unresolved_or_insufficient_budget"
        )

    def _finish(
        self, state: _Run, request: ExtractRequest, path: SelectedPath, reason: str
    ) -> ExtractResponse:
        accepted = path != SelectedPath.REVIEW and state.latest is not None
        if state.deadline.remaining_ms <= 0:
            accepted, path, reason = False, SelectedPath.REVIEW, "deadline_exceeded"
        report = state.latest.report if state.latest else ValidationReport()
        if not accepted:
            report = ValidationReport(
                checks=[
                    *report.checks,
                    ValidationCheck(
                        validator="runtime",
                        code=reason,
                        passed=False,
                        severity="fatal",
                        recoverable=False,
                    ),
                ]
            )
        risk = score_risk(report)
        decision = Decision.ACCEPT if accepted else Decision.REVIEW
        state.event("final", reason, decision)
        result = ExtractResponse(
            extracted_data=state.latest.invoice if accepted and state.latest else None,
            decision=decision,
            selected_path=path,
            validation_report=report,
            estimated_risk_score=risk.score,
            field_risk_scores=risk.fields,
            estimated_cost=sum((call.estimated_cost_usd for call in state.calls), Decimal(0)),
            latency_breakdown=LatencyBreakdown(
                total_ms=round(state.deadline.elapsed_ms, 3),
                budget_ms=request.latency_budget_ms,
                stages_ms={key: round(value, 3) for key, value in state.stages.items()},
                deadline_exceeded=state.deadline.remaining_ms <= 0,
            ),
            audit=AuditInfo(
                request_id=state.request_id,
                document_sha256=hashlib.sha256(request.raw_ocr_text.encode()).hexdigest(),
                policy_sha256=hashlib.sha256(state.policy.model_dump_json().encode()).hexdigest(),
                policy=state.policy,
                started_at=state.started_at,
                versions={
                    "service": __version__,
                    "router": "heuristic-pre-v1",
                    "validators": "invoice-rules-v1",
                    "risk": "heuristic-max-v1",
                },
                events=state.events,
                calls=state.calls,
                validation_attempts=state.attempts,
            ),
        )
        log_result(result)
        return result
