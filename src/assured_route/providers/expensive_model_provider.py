import asyncio
from dataclasses import dataclass
from decimal import Decimal

from assured_route.core.models import ExtractRequest, ProviderResult
from assured_route.providers._mock import parse_labeled_invoice


@dataclass(frozen=True)
class ExpensiveModelProvider:
    estimated_cost_usd: Decimal = Decimal("0.015")
    delay_ms: int = 30
    model_version: str = "mock-expensive-v1"
    prompt_version: str = "labeled-invoice-extended-v1"

    async def extract(
        self, request: ExtractRequest, *, timeout_ms: float | None = None
    ) -> ProviderResult:
        await asyncio.sleep(self.delay_ms / 1000)
        return ProviderResult(
            payload=parse_labeled_invoice(request.raw_ocr_text, extended=True),
            model_version=self.model_version,
            prompt_version=self.prompt_version,
        )
