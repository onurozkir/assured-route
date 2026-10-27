import asyncio
from dataclasses import dataclass
from decimal import Decimal

from assured_route.core.models import ExtractRequest, Invoice, VerificationResult
from assured_route.providers._mock import parse_labeled_invoice
from assured_route.validators.grounding_validator import normalize_text


@dataclass(frozen=True)
class MockVerifierProvider:
    estimated_cost_usd: Decimal = Decimal("0.0003")
    delay_ms: int = 5
    model_version: str = "mock-label-verifier-v1"
    prompt_version: str = "label-role-check-v1"

    async def verify(
        self, request: ExtractRequest, invoice: Invoice, *, timeout_ms: float | None = None
    ) -> VerificationResult:
        await asyncio.sleep(self.delay_ms / 1000)
        reference = parse_labeled_invoice(request.raw_ocr_text, extended=True)
        disputed = []
        for field, value in invoice.model_dump(mode="json").items():
            candidate = reference.get(field)
            if field in {"invoice_total", "vat_total"} and candidate is not None:
                matches = Decimal(str(value)) == Decimal(str(candidate))
            else:
                matches = candidate is not None and normalize_text(str(value)) == normalize_text(
                    str(candidate)
                )
            if not matches:
                disputed.append(field)
        return VerificationResult(
            agrees=not disputed, disputed_fields=disputed, model_version=self.model_version
        )


# TODO: Replace with an independently evaluated verifier; model agreement is not ground truth.
