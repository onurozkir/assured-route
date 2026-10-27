import asyncio
import json
import logging
from decimal import Decimal

from assured_route.core.decisions import Decision, SelectedPath
from assured_route.core.models import DocumentMetadata, ExtractRequest
from assured_route.core.policy import Policy
from assured_route.providers.interfaces import ProviderError
from assured_route.routing.deadline_manager import DeadlineManager
from assured_route.routing.router import Router
from tests.helpers import Extractor, Verifier


def build(invoice, *, policy=None, cheap=None, expensive=None, verifier=None):
    return Router(
        cheap=cheap or Extractor(invoice),
        expensive=expensive or Extractor(invoice, estimated_cost_usd=Decimal("0.015")),
        verifier=verifier or Verifier(),
        policy=policy or Policy(),
    )


def run(router, source, **kwargs):
    return asyncio.run(router.extract(ExtractRequest(raw_ocr_text=source, **kwargs)))


def test_cheap_accepts_and_costs_one_call(invoice, source):
    result = run(build(invoice), source)
    assert result.decision == Decision.ACCEPT
    assert result.selected_path == SelectedPath.CHEAP
    assert result.estimated_cost == Decimal("0.0015")
    assert result.extracted_data.invoice_number == "INV-2026-001"


def test_high_risk_skips_cheap(invoice, source):
    cheap = Extractor(invoice)
    result = run(build(invoice, cheap=cheap), source, metadata=DocumentMetadata(high_risk=True))
    assert result.selected_path == SelectedPath.EXPENSIVE
    assert cheap.calls == 0
    assert result.estimated_cost == Decimal("0.015")
    assert any(e.reason == "metadata_high_risk" for e in result.audit.events)


def test_schema_failure_escalates_and_preserves_validation_history(invoice, source):
    broken = {k: v for k, v in invoice.items() if k != "currency"}
    result = run(build(invoice, cheap=Extractor(broken)), source)
    assert result.decision == Decision.ACCEPT
    assert result.selected_path == SelectedPath.EXPENSIVE
    assert result.estimated_cost == Decimal("0.0165")
    assert result.audit.validation_attempts[0].decision == Decision.ESCALATE_TO_EXPENSIVE
    assert result.audit.validation_attempts[-1].report.passed


def test_bad_expensive_output_is_review_without_data(invoice, source):
    broken = {**invoice, "invoice_total": "999.00"}
    result = run(
        build(invoice, expensive=Extractor(broken)),
        source,
        metadata=DocumentMetadata(high_risk=True),
    )
    assert result.decision == Decision.REVIEW
    assert result.extracted_data is None
    assert len(result.audit.calls) == 1
    assert not result.validation_report.passed


def test_fatal_business_contradiction_does_not_loop(invoice, source):
    broken = {**invoice, "invoice_total": "100.00"}
    expensive = Extractor(invoice)
    result = run(build(invoice, cheap=Extractor(broken), expensive=expensive), source)
    assert result.decision == Decision.REVIEW
    assert expensive.calls == 0
    assert result.extracted_data is None


def test_semantic_ambiguity_uses_verifier(invoice, source):
    result = run(build(invoice), source, metadata=DocumentMetadata(semantic_ambiguity=True))
    assert result.decision == Decision.ACCEPT
    assert result.selected_path == SelectedPath.CHEAP_VERIFIER
    assert result.estimated_cost == Decimal("0.0018")


def test_verifier_disagreement_survives_expensive_escalation(invoice, source):
    result = run(
        build(invoice, verifier=Verifier(agrees=False, disputed_fields=["seller_name"])),
        source,
        metadata=DocumentMetadata(semantic_ambiguity=True),
    )
    assert result.decision == Decision.REVIEW
    assert result.extracted_data is None
    assert [c.role for c in result.audit.calls] == ["cheap", "verifier", "expensive", "verifier"]
    assert result.estimated_cost == Decimal("0.0171")


def test_required_verifier_not_affordable_never_accepts(invoice, source):
    result = run(
        build(invoice, policy=Policy(verifier_expected_ms=120)),
        source,
        metadata=DocumentMetadata(semantic_ambiguity=True),
        latency_budget_ms=110,
    )
    assert result.decision == Decision.REVIEW
    assert result.extracted_data is None
    assert any(e.reason == "insufficient_verifier_budget" for e in result.audit.events)


def test_no_budget_returns_review_without_model_spend(invoice, source):
    result = run(build(invoice), source, latency_budget_ms=1)
    assert result.decision == Decision.REVIEW
    assert result.estimated_cost == Decimal(0)
    assert result.audit.calls == []


def test_timeout_is_cancelled_counted_and_can_escalate(invoice, source):
    cheap = Extractor(invoice, delay=1)
    result = run(build(invoice, cheap=cheap, policy=Policy(provider_timeout_ms=30)), source)
    assert result.decision == Decision.ACCEPT
    assert result.selected_path == SelectedPath.EXPENSIVE
    assert cheap.cancelled
    assert result.audit.calls[0].status == "timeout"
    assert result.estimated_cost == Decimal("0.0165")


def test_provider_failure_is_sanitized_and_can_escalate(invoice, source, caplog):
    caplog.set_level(logging.INFO, logger="assured_route.audit")
    cheap = Extractor(invoice, error=ProviderError("secret OCR and API key"))
    result = run(build(invoice, cheap=cheap), source)
    assert result.decision == Decision.ACCEPT
    assert result.audit.calls[0].status == "error"
    assert "secret OCR" not in caplog.text
    assert "Acme Ltd" not in caplog.text
    assert "1234567890" not in caplog.text
    assert result.audit.request_id in caplog.text


def test_simultaneous_requests_keep_independent_audit(invoice, source):
    router = build(invoice)

    async def batch():
        return await asyncio.gather(
            router.extract(ExtractRequest(raw_ocr_text=source)),
            router.extract(ExtractRequest(raw_ocr_text=source)),
        )

    a, b = asyncio.run(batch())
    assert a.audit.request_id != b.audit.request_id
    assert len(a.audit.calls) == len(b.audit.calls) == 1
    assert a.estimated_cost == b.estimated_cost == Decimal("0.0015")


def test_deadline_uses_monotonic_remaining_budget():
    now = [10.0]
    deadline = DeadlineManager(100, reserve_ms=20, clock=lambda: now[0])
    assert deadline.can_start(80)
    now[0] += 0.05
    assert not deadline.can_start(80)
    assert 29 <= deadline.call_timeout_ms(1000) <= 31


def test_cancelled_request_propagates_cancellation(invoice, source):
    cheap = Extractor(invoice, delay=1)
    router = build(invoice, cheap=cheap)

    async def cancel():
        task = asyncio.create_task(router.extract(ExtractRequest(raw_ocr_text=source)))
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return True
        return False

    assert asyncio.run(cancel())
    assert cheap.cancelled


def test_cancelled_request_emits_terminal_cost_audit(invoice, source, caplog):
    caplog.set_level(logging.INFO, logger="assured_route.audit")
    router = build(invoice, cheap=Extractor(invoice, delay=1))

    async def cancel():
        task = asyncio.create_task(router.extract(ExtractRequest(raw_ocr_text=source)))
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(cancel())
    records = [
        json.loads(r.getMessage()) for r in caplog.records if r.name == "assured_route.audit"
    ]
    assert len(records) == 1
    assert records[0]["decision"] == "REVIEW"
    assert records[0]["estimated_cost_usd"] == "0.0015"
    assert records[0]["calls"][0]["status"] == "cancelled"
    assert "Acme Ltd" not in json.dumps(records)
